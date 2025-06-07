"""
Translation module for LLM communication
"""
import json
import requests
import re
import asyncio
import time
from tqdm.auto import tqdm

from config import (
    API_ENDPOINT, DEFAULT_MODEL, REQUEST_TIMEOUT, OLLAMA_NUM_CTX,
    MAX_TRANSLATION_ATTEMPTS, RETRY_DELAY_SECONDS, 
    TRANSLATE_TAG_IN, TRANSLATE_TAG_OUT
)
from prompts import generate_translation_prompt
from typing import List, Dict, Tuple


async def generate_translation_request(main_content, context_before, context_after, previous_translation_context,
                                       source_language="English", target_language="French", model=DEFAULT_MODEL,
                                       api_endpoint_param=API_ENDPOINT, log_callback=None, custom_instructions=""):
    """
    Generate translation request to LLM API
    
    Args:
        main_content (str): Text to translate
        context_before (str): Context before main content
        context_after (str): Context after main content
        previous_translation_context (str): Previous translation for consistency
        source_language (str): Source language
        target_language (str): Target language
        model (str): LLM model name
        api_endpoint_param (str): API endpoint
        log_callback (callable): Logging callback function
        
    Returns:
        str: Translated text or None if failed
    """
    full_raw_response = ""
    
    structured_prompt = generate_translation_prompt(
        main_content, 
        context_before, 
        context_after, 
        previous_translation_context,
        source_language, 
        target_language,
        TRANSLATE_TAG_IN, 
        TRANSLATE_TAG_OUT,
        custom_instructions
    )
    
    # Log LLM request
    if log_callback:
        log_callback("", "info", {
            'type': 'llm_request',
            'prompt': structured_prompt,
            'model': model,
            'endpoint': api_endpoint_param
        })

    payload = {
        "model": model, 
        "prompt": structured_prompt, 
        "stream": False,
        "options": {"num_ctx": OLLAMA_NUM_CTX}
    }

    start_time = time.time()
    try:
        response = requests.post(api_endpoint_param, json=payload, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        json_response = response.json()
        full_raw_response = json_response.get("response", "")
        execution_time = time.time() - start_time

        # Log LLM response
        if log_callback:
            log_callback("", "info", {
                'type': 'llm_response',
                'response': full_raw_response,
                'execution_time': execution_time
            })

        if not full_raw_response and "error" in json_response:
            err_msg = f"LLM API ERROR: {json_response['error']}"
            if log_callback: 
                log_callback("llm_api_error", err_msg)
            else: 
                tqdm.write(f"\n{err_msg}")
            return None

    except requests.exceptions.Timeout:
        err_msg = f"ERROR: LLM API Timeout ({REQUEST_TIMEOUT}s)"
        if log_callback: 
            log_callback("llm_timeout_error", err_msg)
        else: 
            tqdm.write(f"\n{err_msg}")
        return None
    except requests.exceptions.HTTPError as e:
        err_msg = f"LLM API HTTP ERROR: {e.response.status_code} {e.response.reason}. Response: {e.response.text[:200]}..."
        if log_callback: 
            log_callback("llm_http_error", err_msg)
        else: 
            tqdm.write(f"\n{err_msg}")
        return None
    except requests.exceptions.RequestException as e:
        err_msg = f"LLM API Request ERROR: {e}"
        if log_callback: 
            log_callback("llm_request_error", err_msg)
        else: 
            tqdm.write(f"\n{err_msg}")
        return None
    except json.JSONDecodeError as e:
        raw_response_text = response.text if 'response' in locals() and hasattr(response, 'text') else "N/A"
        err_msg = f"LLM API JSON Decoding ERROR. Raw response: {raw_response_text[:200]}..."
        if log_callback: 
            log_callback("llm_json_decode_error", err_msg)
        else: 
            tqdm.write(f"\n{err_msg}")
        return None

    # Extract translation from response
    escaped_tag_in = re.escape(TRANSLATE_TAG_IN)
    escaped_tag_out = re.escape(TRANSLATE_TAG_OUT)
    regex_pattern = rf"{escaped_tag_in}(.*?){escaped_tag_out}"
    match = re.search(regex_pattern, full_raw_response, re.DOTALL)

    if match:
        return match.group(1).strip()
    else:
        warn_msg = f"WARNING: Tags {TRANSLATE_TAG_IN}...{TRANSLATE_TAG_OUT} missing in LLM response."
        if log_callback:
            log_callback("llm_tag_warning", warn_msg)
            log_callback("llm_raw_response_preview", f"LLM raw response: {full_raw_response[:500]}...")
        else:
            tqdm.write(f"\n{warn_msg} Excerpt: {full_raw_response[:100]}...")

        if main_content in full_raw_response:
            discard_msg = "WARNING: LLM response seems to contain input. Discarded."
            if log_callback: 
                log_callback("llm_prompt_in_response_warning", discard_msg)
            else: 
                tqdm.write(discard_msg)
            return None
        return full_raw_response.strip()


async def translate_chunks(chunks, source_language, target_language, model_name, 
                          api_endpoint, progress_callback=None, log_callback=None, 
                          stats_callback=None, check_interruption_callback=None, custom_instructions=""):
    """
    Translate a list of text chunks
    
    Args:
        chunks (list): List of chunk dictionaries
        source_language (str): Source language
        target_language (str): Target language
        model_name (str): LLM model name
        api_endpoint (str): API endpoint
        progress_callback (callable): Progress update callback
        log_callback (callable): Logging callback
        stats_callback (callable): Statistics update callback
        check_interruption_callback (callable): Interruption check callback
        
    Returns:
        list: List of translated chunks
    """
    total_chunks = len(chunks)
    full_translation_parts = []
    last_successful_llm_context = ""
    completed_chunks_count = 0
    failed_chunks_count = 0

    if log_callback: 
        log_callback("txt_translation_loop_start", "Starting segment translation...")

    iterator = tqdm(chunks, desc=f"Translating {source_language} to {target_language}", unit="seg") if not log_callback else chunks

    for i, chunk_data in enumerate(iterator):
        if check_interruption_callback and check_interruption_callback():
            if log_callback: 
                log_callback("txt_translation_interrupted", f"Translation process for segment {i+1}/{total_chunks} interrupted by user signal.")
            else: 
                tqdm.write(f"\nTranslation interrupted by user at segment {i+1}/{total_chunks}.")
            break

        if progress_callback and total_chunks > 0:
            progress_callback((i / total_chunks) * 100)
        
        # Log progress summary periodically
        if log_callback and i > 0 and i % 5 == 0:
            log_callback("", "info", {
                'type': 'progress'
            })

        main_content_to_translate = chunk_data["main_content"]
        context_before_text = chunk_data["context_before"]
        context_after_text = chunk_data["context_after"]

        if not main_content_to_translate.strip():
            full_translation_parts.append(main_content_to_translate)
            completed_chunks_count += 1
            if stats_callback and total_chunks > 0:
                stats_callback({'completed_chunks': completed_chunks_count, 'failed_chunks': failed_chunks_count})
            continue

        translated_chunk_text = None
        current_attempts = 0
        
        while current_attempts < MAX_TRANSLATION_ATTEMPTS and translated_chunk_text is None:
            current_attempts += 1
            if current_attempts > 1:
                retry_msg = f"Retrying segment {i+1}/{total_chunks} (attempt {current_attempts}/{MAX_TRANSLATION_ATTEMPTS})..."
                if log_callback: 
                    log_callback("txt_chunk_retry", retry_msg)
                else: 
                    tqdm.write(f"\n{retry_msg}")
                await asyncio.sleep(RETRY_DELAY_SECONDS)

            translated_chunk_text = await generate_translation_request(
                main_content_to_translate, context_before_text, context_after_text,
                last_successful_llm_context, source_language, target_language,
                model_name, api_endpoint_param=api_endpoint, log_callback=log_callback,
                custom_instructions=custom_instructions
            )

        if translated_chunk_text is not None:
            full_translation_parts.append(translated_chunk_text)
            completed_chunks_count += 1
            words = translated_chunk_text.split()
            if len(words) > 150:
                last_successful_llm_context = " ".join(words[-150:])
            else:
                last_successful_llm_context = translated_chunk_text
        else:
            err_msg_chunk = f"ERROR translating segment {i+1} after {MAX_TRANSLATION_ATTEMPTS} attempts. Original content preserved."
            if log_callback: 
                log_callback("txt_chunk_translation_error", err_msg_chunk)
            else: 
                tqdm.write(f"\n{err_msg_chunk}")
            error_placeholder = f"[TRANSLATION_ERROR SEGMENT {i+1}]\n{main_content_to_translate}\n[/TRANSLATION_ERROR SEGMENT {i+1}]"
            full_translation_parts.append(error_placeholder)
            failed_chunks_count += 1
            last_successful_llm_context = ""

        if stats_callback and total_chunks > 0:
            stats_callback({'completed_chunks': completed_chunks_count, 'failed_chunks': failed_chunks_count})

    return full_translation_parts


async def translate_subtitles(subtitles: List[Dict[str, str]], source_language: str, 
                            target_language: str, model_name: str, api_endpoint: str,
                            progress_callback=None, log_callback=None, 
                            stats_callback=None, check_interruption_callback=None, custom_instructions="") -> Dict[int, str]:
    """
    Translate subtitle entries preserving structure
    
    Args:
        subtitles (list): List of subtitle dictionaries from SRT parser
        source_language (str): Source language
        target_language (str): Target language
        model_name (str): LLM model name
        api_endpoint (str): API endpoint
        progress_callback (callable): Progress update callback
        log_callback (callable): Logging callback
        stats_callback (callable): Statistics update callback
        check_interruption_callback (callable): Interruption check callback
        
    Returns:
        dict: Mapping of subtitle index to translated text
    """
    total_subtitles = len(subtitles)
    translations = {}
    completed_count = 0
    failed_count = 0
    
    if log_callback:
        log_callback("srt_translation_start", f"Starting translation of {total_subtitles} subtitles...")
    
    iterator = tqdm(enumerate(subtitles), total=total_subtitles, 
                   desc=f"Translating subtitles ({source_language} to {target_language})", 
                   unit="subtitle") if not log_callback else enumerate(subtitles)
    
    for idx, subtitle in iterator:
        if check_interruption_callback and check_interruption_callback():
            if log_callback:
                log_callback("srt_translation_interrupted", 
                           f"Translation interrupted at subtitle {idx+1}/{total_subtitles}")
            else:
                tqdm.write(f"\nTranslation interrupted at subtitle {idx+1}/{total_subtitles}")
            break
        
        if progress_callback and total_subtitles > 0:
            progress_callback((idx / total_subtitles) * 100)
        
        text_to_translate = subtitle['text'].strip()
        
        # Skip empty subtitles
        if not text_to_translate:
            translations[idx] = ""
            completed_count += 1
            continue
        
        # Get context from surrounding subtitles
        context_before = ""
        context_after = ""
        
        # Get previous subtitle text for context
        if idx > 0 and idx-1 in translations:
            context_before = translations[idx-1]
        elif idx > 0:
            context_before = subtitles[idx-1].get('text', '')
        
        # Get next subtitle text for context
        if idx < len(subtitles) - 1:
            context_after = subtitles[idx+1].get('text', '')
        
        # Translation attempts
        translated_text = None
        attempts = 0
        
        while attempts < MAX_TRANSLATION_ATTEMPTS and translated_text is None:
            attempts += 1
            if attempts > 1:
                retry_msg = f"Retrying subtitle {idx+1} (attempt {attempts}/{MAX_TRANSLATION_ATTEMPTS})..."
                if log_callback:
                    log_callback("srt_subtitle_retry", retry_msg)
                else:
                    tqdm.write(f"\n{retry_msg}")
                await asyncio.sleep(RETRY_DELAY_SECONDS)
            
            # Use existing translation function with subtitle-specific context
            translated_text = await generate_translation_request(
                text_to_translate,
                context_before,
                context_after,
                "", # No previous translation context for subtitles
                source_language,
                target_language,
                model_name,
                api_endpoint_param=api_endpoint,
                log_callback=log_callback,
                custom_instructions=custom_instructions
            )
        
        if translated_text is not None:
            translations[idx] = translated_text
            completed_count += 1
        else:
            # Keep original text if translation fails
            err_msg = f"Failed to translate subtitle {idx+1} after {MAX_TRANSLATION_ATTEMPTS} attempts"
            if log_callback:
                log_callback("srt_subtitle_error", err_msg)
            else:
                tqdm.write(f"\n{err_msg}")
            translations[idx] = text_to_translate  # Keep original
            failed_count += 1
        
        if stats_callback and total_subtitles > 0:
            stats_callback({
                'completed_subtitles': completed_count,
                'failed_subtitles': failed_count,
                'total_subtitles': total_subtitles
            })
    
    if log_callback:
        log_callback("srt_translation_complete", 
                    f"Completed translation: {completed_count} successful, {failed_count} failed")
    
    return translations