import json
import requests
import os
import asyncio
import re
from tqdm.auto import tqdm
import argparse
import zipfile
import tempfile
import shutil
from lxml import etree
import html

# --- Configuration ---
DEFAULT_MODEL = "mistral-small:24b"
MAIN_LINES_PER_CHUNK = 25
REQUEST_TIMEOUT = 60
OLLAMA_NUM_CTX = 2048
SENTENCE_TERMINATORS = tuple(list(".!?") + ['."', '?"', '!"', '.”', ".'", "?'", "!'", ":", ".)"])
MAX_TRANSLATION_ATTEMPTS = 2
RETRY_DELAY_SECONDS = 2
TRANSLATE_TAG_IN = "[START]"
TRANSLATE_TAG_OUT = "[END]"

NAMESPACES = {
    'opf': 'http://www.idpf.org/2007/opf',
    'dc': 'http://purl.org/dc/elements/1.1/',
    'xhtml': 'http://www.w3.org/1999/xhtml',
    'epub': 'http://www.idpf.org/2007/ops'
}

# EPUB specific tags
IGNORED_TAGS_EPUB = [
    '{http://www.w3.org/1999/xhtml}script',
    '{http://www.w3.org/1999/xhtml}style',
    '{http://www.w3.org/1999/xhtml}meta',
    '{http://www.w3.org/1999/xhtml}link'
]

CONTENT_BLOCK_TAGS_EPUB = [
    '{http://www.w3.org/1999/xhtml}p', '{http://www.w3.org/1999/xhtml}div',
    '{http://www.w3.org/1999/xhtml}li', '{http://www.w3.org/1999/xhtml}h1',
    '{http://www.w3.org/1999/xhtml}h2', '{http://www.w3.org/1999/xhtml}h3',
    '{http://www.w3.org/1999/xhtml}h4', '{http://www.w3.org/1999/xhtml}h5',
    '{http://www.w3.org/1999/xhtml}h6', '{http://www.w3.org/1999/xhtml}blockquote',
    '{http://www.w3.org/1999/xhtml}td', '{http://www.w3.org/1999/xhtml}th',
    '{http://www.w3.org/1999/xhtml}caption',
    '{http://www.w3.org/1999/xhtml}dt', '{http://www.w3.org/1999/xhtml}dd'
]


def get_adjusted_start_index(all_lines, intended_start_idx, max_look_back_lines=20):
    if intended_start_idx == 0:
        return 0
    for i in range(intended_start_idx - 1, max(-1, intended_start_idx - 1 - max_look_back_lines), -1):
        if i < 0:
            break
        line_content_stripped = all_lines[i].strip()
        if line_content_stripped and line_content_stripped.endswith(SENTENCE_TERMINATORS):
            return i + 1
    if intended_start_idx <= max_look_back_lines:
        return 0
    return intended_start_idx

def get_adjusted_end_index(all_lines, intended_end_idx, max_look_forward_lines=20):
    if intended_end_idx >= len(all_lines):
        return len(all_lines)
    
    start_search_fwd = intended_end_idx - 1
    if start_search_fwd < 0: start_search_fwd = 0

    for i in range(start_search_fwd, min(len(all_lines), start_search_fwd + max_look_forward_lines)):
        line_content_stripped = all_lines[i].strip()
        if line_content_stripped and line_content_stripped.endswith(SENTENCE_TERMINATORS):
            return i + 1
            
    if intended_end_idx + max_look_forward_lines >= len(all_lines):
        return len(all_lines)
    return intended_end_idx

def split_text_into_chunks_with_context(text, main_lines_per_chunk_target):
    try:
        processed_text = re.sub(r'([a-zA-ZÀ-ÿ0-9])-(\n|\r\n|\r)\s*([a-zA-ZÀ-ÿ0-9])', r'\1\3', text)
    except Exception: # Minimal error handling here as it falls back
        processed_text = text

    all_lines = processed_text.splitlines()
    structured_chunks = []
    if not all_lines:
        return []

    look_back_main_limit = max(1, main_lines_per_chunk_target // 4)
    look_forward_main_limit = max(1, main_lines_per_chunk_target // 4)
    look_back_context_limit = max(1, main_lines_per_chunk_target // 8)
    look_forward_context_limit = max(1, main_lines_per_chunk_target // 8)

    current_position = 0
    while current_position < len(all_lines):
        initial_main_start_index = current_position
        initial_main_end_index = min(current_position + main_lines_per_chunk_target, len(all_lines))

        final_main_start_index = get_adjusted_start_index(all_lines, initial_main_start_index, look_back_main_limit)
        final_main_end_index = get_adjusted_end_index(all_lines, initial_main_end_index, look_forward_main_limit)
        
        if final_main_start_index > final_main_end_index:
            final_main_start_index = initial_main_start_index
            final_main_end_index = initial_main_end_index

        if final_main_end_index <= final_main_start_index:
            if initial_main_start_index < len(all_lines): 
                if initial_main_end_index > initial_main_start_index : 
                    final_main_start_index = initial_main_start_index
                    final_main_end_index = initial_main_end_index
                else: 
                    final_main_start_index = initial_main_start_index
                    final_main_end_index = len(all_lines) 
            else: 
                break 

        main_part_lines = all_lines[final_main_start_index:final_main_end_index]

        if not main_part_lines and final_main_start_index < len(all_lines):
            current_position = final_main_start_index + 1
            continue
        
        if not main_part_lines:
            break
        
        context_target_line_count_before = main_lines_per_chunk_target // 4
        intended_context_before_end_idx = final_main_start_index
        intended_context_before_start_idx = max(0, intended_context_before_end_idx - context_target_line_count_before)
        final_context_before_start_idx = get_adjusted_start_index(all_lines, intended_context_before_start_idx, look_back_context_limit)
        final_context_before_end_idx = min(intended_context_before_end_idx, final_main_start_index)
        if final_context_before_start_idx < final_context_before_end_idx:
            preceding_context_lines = all_lines[final_context_before_start_idx:final_context_before_end_idx]
        else:
            preceding_context_lines = []

        context_target_line_count_after = main_lines_per_chunk_target // 4
        intended_context_after_start_idx = final_main_end_index
        intended_context_after_end_idx = min(len(all_lines), intended_context_after_start_idx + context_target_line_count_after)
        final_context_after_start_idx = intended_context_after_start_idx
        final_context_after_end_idx = get_adjusted_end_index(all_lines, intended_context_after_end_idx, look_forward_context_limit)

        if final_context_after_start_idx < final_context_after_end_idx:
            succeeding_context_lines = all_lines[final_context_after_start_idx:final_context_after_end_idx]
        else:
            succeeding_context_lines = []
        
        if not "".join(main_part_lines).strip():
            current_position = final_main_end_index
            if current_position <= initial_main_start_index :
                current_position = initial_main_start_index + 1 
            continue

        structured_chunks.append({
            "context_before": "\n".join(preceding_context_lines),
            "main_content": "\n".join(main_part_lines),
            "context_after": "\n".join(succeeding_context_lines)
        })

        current_position = final_main_end_index
        if current_position <= initial_main_start_index :
            current_position = initial_main_start_index + 1 
    return structured_chunks

async def generate_translation_request(main_content, context_before, context_after, previous_translation_context,
                                       source_language="English", target_language="French", model=DEFAULT_MODEL,
                                       api_endpoint_param=API_ENDPOINT, log_callback=None):
    full_raw_response = ""
    source_lang = source_language.upper()

    role_and_instructions_block = f"""## ROLE
# You are a {target_language} professional writer.

## TRANSLATION
+ Translate in the author's style
+ Preserve meaning and enhance fluidity
+ Adapt expressions and culture to the {target_language} language
+ Maintain the original layout of the text

## FORMATING
+ Translate ONLY the text enclosed within the tags "[START TO TRANSLATE]" and "[END TO TRANSLATE]" from {source_lang} into {target_language}
+ Surround your translation with {TRANSLATE_TAG_IN} and {TRANSLATE_TAG_OUT} tags. For example: {TRANSLATE_TAG_IN}Your text translated here.{TRANSLATE_TAG_OUT}
+ Return ONLY the translation, formatted as requested
"""

    previous_translation_block_text = ""
    if previous_translation_context and previous_translation_context.strip():
        previous_translation_block_text = f"""

## Previous paragraph :
(...) {previous_translation_context}

"""
    
    text_to_translate_block = f"""
[START TO TRANSLATE]
{main_content}
[END TO TRANSLATE]"""

    structured_prompt_parts = [
        role_and_instructions_block,
        previous_translation_block_text,
        text_to_translate_block
    ]
    structured_prompt = "\n\n".join(part.strip() for part in structured_prompt_parts if part and part.strip()).strip()
    
    print("\n----SEND TO LLM----")
    print(structured_prompt)
    print("-------------------\n")
    
    payload = {
        "model": model, "prompt": structured_prompt, "stream": False,
        "options": { "num_ctx": OLLAMA_NUM_CTX }
    }

    try:
        response = requests.post(api_endpoint_param, json=payload, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        json_response = response.json()
        full_raw_response = json_response.get("response", "")

        print("\n----LLM RAW RESPONSE----")
        print(full_raw_response)
        print("------------------------\n")
        
        if not full_raw_response and "error" in json_response:
            err_msg = f"LLM API ERROR: {json_response['error']}"
            if log_callback: log_callback("llm_api_error", err_msg)
            else: tqdm.write(f"\n{err_msg}")
            return None
            
    except requests.exceptions.Timeout:
        err_msg = f"ERROR: LLM API Timeout ({REQUEST_TIMEOUT}s)"
        if log_callback: log_callback("llm_timeout_error", err_msg)
        else: tqdm.write(f"\n{err_msg}")
        return None
    except requests.exceptions.HTTPError as e:
        err_msg = f"LLM API HTTP ERROR: {e.response.status_code} {e.response.reason}. Response: {e.response.text[:200]}..."
        if log_callback: log_callback("llm_http_error", err_msg)
        else: tqdm.write(f"\n{err_msg}")
        return None
    except requests.exceptions.RequestException as e:
        err_msg = f"LLM API Request ERROR: {e}"
        if log_callback: log_callback("llm_request_error", err_msg)
        else: tqdm.write(f"\n{err_msg}")
        return None
    except json.JSONDecodeError as e:
        raw_response_text = response.text if 'response' in locals() and hasattr(response, 'text') else "N/A"
        err_msg = f"LLM API JSON Decoding ERROR. Raw response: {raw_response_text[:200]}..."
        if log_callback: log_callback("llm_json_decode_error", err_msg)
        else: tqdm.write(f"\n{err_msg}")
        return None
    
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
        
        if main_content in full_raw_response: # Heuristic: if input is in output, it's probably a failed generation
            discard_msg = "WARNING: LLM response seems to contain input. Discarded."
            if log_callback: log_callback("llm_prompt_in_response_warning", discard_msg)
            else: tqdm.write(discard_msg)
            return None
        return full_raw_response.strip() # Return raw if tags are missing but input is not obviously in output

async def translate_text_file_with_callbacks(input_filepath, output_filepath,
                                       source_language="English", target_language="French",
                                       model_name=DEFAULT_MODEL, chunk_target_lines_cli=MAIN_LINES_PER_CHUNK,
                                       cli_api_endpoint=API_ENDPOINT,
                                       progress_callback=None, log_callback=None, stats_callback=None):
    if not os.path.exists(input_filepath):
        err_msg = f"ERROR: Input file '{input_filepath}' not found."
        if log_callback: log_callback("file_not_found_error", err_msg)
        else: print(err_msg) # Critical, print directly
        return

    try:
        with open(input_filepath, 'r', encoding='utf-8') as f:
            original_text = f.read()
    except Exception as e:
        err_msg = f"ERROR: Reading input file '{input_filepath}': {e}"
        if log_callback: log_callback("file_read_error", err_msg)
        else: print(err_msg) # Critical
        return

    if log_callback: log_callback("txt_split_start", f"Splitting text from '{source_language}'...")
    # else: tqdm.write("Splitting text...") # Less critical for CLI

    structured_chunks = split_text_into_chunks_with_context(original_text, chunk_target_lines_cli)
    total_chunks = len(structured_chunks)

    if stats_callback and total_chunks > 0:
        stats_callback({'total_chunks': total_chunks, 'completed_chunks': 0, 'failed_chunks': 0})

    if total_chunks == 0 and original_text.strip():
        warn_msg = "WARNING: No segments generated for non-empty text. Processing as a single block."
        if log_callback: log_callback("txt_no_chunks_warning", warn_msg)
        else: tqdm.write(warn_msg)
        structured_chunks.append({ "context_before": "", "main_content": original_text, "context_after": "" })
        total_chunks = 1
        if stats_callback: stats_callback({'total_chunks': 1, 'completed_chunks': 0, 'failed_chunks': 0})
    elif total_chunks == 0:
        info_msg = "Empty input file. No translation needed."
        if log_callback: log_callback("txt_empty_input", info_msg)
        else: tqdm.write(info_msg)
        try:
            with open(output_filepath, 'w', encoding='utf-8') as f: f.write("")
            if log_callback: log_callback("txt_empty_output_created", f"Empty output file '{output_filepath}' created.")
            # else: tqdm.write(f"Empty output file '{output_filepath}' created.")
        except Exception as e:
            err_msg = f"ERROR: Saving empty file '{output_filepath}': {e}"
            if log_callback: log_callback("txt_empty_save_error", err_msg)
            else: tqdm.write(err_msg) # Important if it fails
        if progress_callback: progress_callback(100)
        return

    if log_callback:
        log_callback("txt_translation_info_lang", f"Translating from {source_language} to {target_language}.")
        log_callback("txt_translation_info_chunks1", f"{total_chunks} main segments in memory.")
        log_callback("txt_translation_info_chunks2", f"Target size per segment: ~{chunk_target_lines_cli} lines.")
    # else: # These are less critical for CLI, tqdm shows progress
    # print(f"Translating from {source_language} to {target_language} in {total_chunks} segments.")

    full_translation_parts = []
    last_successful_llm_context = "" 
    completed_chunks_count = 0
    failed_chunks_count = 0

    if log_callback: log_callback("txt_translation_loop_start", "Starting segment translation...")
    # else: print("Starting translation...")

    iterator = tqdm(structured_chunks, desc=f"Translating {source_language} to {target_language}", unit="seg") if not log_callback else structured_chunks

    for i, chunk_data in enumerate(iterator):
        if progress_callback and total_chunks > 0:
            progress_callback((i / total_chunks) * 100)

        main_content_to_translate = chunk_data["main_content"]
        context_before_text = chunk_data["context_before"]
        context_after_text = chunk_data["context_after"]

        if not main_content_to_translate.strip():
            full_translation_parts.append(main_content_to_translate) 
            completed_chunks_count +=1 
            if stats_callback and total_chunks > 0:
                stats_callback({'completed_chunks': completed_chunks_count, 'failed_chunks': failed_chunks_count})
            continue

        translated_chunk_text = None
        current_attempts = 0
        while current_attempts < MAX_TRANSLATION_ATTEMPTS and translated_chunk_text is None:
            current_attempts += 1
            if current_attempts > 1:
                retry_msg = f"Retrying segment {i+1}/{total_chunks} (attempt {current_attempts}/{MAX_TRANSLATION_ATTEMPTS})..."
                if log_callback: log_callback("txt_chunk_retry", retry_msg)
                else: tqdm.write(f"\n{retry_msg}")
                await asyncio.sleep(RETRY_DELAY_SECONDS)

            translated_chunk_text = await generate_translation_request(
                main_content_to_translate, context_before_text, context_after_text,
                last_successful_llm_context, source_language, target_language,
                model_name, api_endpoint_param=cli_api_endpoint, log_callback=log_callback
            )

        if translated_chunk_text is not None:
            full_translation_parts.append(translated_chunk_text)
            completed_chunks_count+=1
            words = translated_chunk_text.split()
            if len(words) > 150: 
                last_successful_llm_context = " ".join(words[-150:])
            else:
                last_successful_llm_context = translated_chunk_text
        else:
            err_msg_chunk = f"ERROR translating segment {i+1} after {MAX_TRANSLATION_ATTEMPTS} attempts. Original content preserved."
            if log_callback: log_callback("txt_chunk_translation_error", err_msg_chunk)
            else: tqdm.write(f"\n{err_msg_chunk}")
            error_placeholder = f"[TRANSLATION_ERROR SEGMENT {i+1}]\n{main_content_to_translate}\n[/TRANSLATION_ERROR SEGMENT {i+1}]"
            full_translation_parts.append(error_placeholder)
            failed_chunks_count+=1
            last_successful_llm_context = ""
        
        if stats_callback and total_chunks > 0:
            stats_callback({'completed_chunks': completed_chunks_count, 'failed_chunks': failed_chunks_count})
    
    if progress_callback: progress_callback(100)

    final_translated_text = "\n".join(full_translation_parts)
    try:
        with open(output_filepath, 'w', encoding='utf-8') as f:
            f.write(final_translated_text)
        success_msg = f"Full translation saved: '{output_filepath}'"
        if log_callback: log_callback("txt_save_success", success_msg)
        else: tqdm.write(success_msg) # Important feedback
    except Exception as e:
        err_msg = f"ERROR: Saving output file '{output_filepath}': {e}"
        if log_callback: log_callback("txt_save_error", err_msg)
        else: print(err_msg) # Critical

def _collect_epub_translation_jobs_recursive(element, file_path_abs, jobs_list, chunk_size, log_callback=None):
    if element.tag in IGNORED_TAGS_EPUB:
        return

    if element.tag in CONTENT_BLOCK_TAGS_EPUB:
        text_content_for_chunking = "".join(element.itertext()).strip()
        if text_content_for_chunking:
            sub_chunks = split_text_into_chunks_with_context(text_content_for_chunking, chunk_size)
            if not sub_chunks: 
                sub_chunks = [{"context_before": "", "main_content": text_content_for_chunking, "context_after": ""}]
            
            jobs_list.append({
                'element_ref': element, 'type': 'block_content',
                'original_text_stripped': text_content_for_chunking,
                'sub_chunks': sub_chunks, 'file_path': file_path_abs, 'translated_text': None
            })
        for child in element: # Recursive call for nested block tags
            if child.tag in CONTENT_BLOCK_TAGS_EPUB:
                    _collect_epub_translation_jobs_recursive(child, file_path_abs, jobs_list, chunk_size, log_callback)
        return # Stop further processing for this element's direct children text/tail

    if element.text:
        original_text_content = element.text
        text_to_translate = original_text_content.strip()
        if text_to_translate:
            leading_space = original_text_content[:len(original_text_content) - len(original_text_content.lstrip())]
            trailing_space = original_text_content[len(original_text_content.rstrip()):]
            sub_chunks = split_text_into_chunks_with_context(text_to_translate, chunk_size)
            if not sub_chunks:
                sub_chunks = [{"context_before": "", "main_content": text_to_translate, "context_after": ""}]
            jobs_list.append({
                'element_ref': element, 'type': 'text',
                'original_text_stripped': text_to_translate, 'sub_chunks': sub_chunks,
                'leading_space': leading_space, 'trailing_space': trailing_space,
                'file_path': file_path_abs, 'translated_text': None
            })

    for child in element:
        _collect_epub_translation_jobs_recursive(child, file_path_abs, jobs_list, chunk_size, log_callback)

    if element.tail:
        original_tail_content = element.tail
        tail_to_translate = original_tail_content.strip()
        if tail_to_translate:
            leading_space_tail = original_tail_content[:len(original_tail_content) - len(original_tail_content.lstrip())]
            trailing_space_tail = original_tail_content[len(original_tail_content.rstrip()):]
            sub_chunks = split_text_into_chunks_with_context(tail_to_translate, chunk_size)
            if not sub_chunks:
                sub_chunks = [{"context_before": "", "main_content": tail_to_translate, "context_after": ""}]
            jobs_list.append({
                'element_ref': element, 'type': 'tail',
                'original_text_stripped': tail_to_translate, 'sub_chunks': sub_chunks,
                'leading_space': leading_space_tail, 'trailing_space': trailing_space_tail,
                'file_path': file_path_abs, 'translated_text': None
            })

async def translate_epub_file(input_filepath, output_filepath,
                               source_language="English", target_language="French",
                               model_name=DEFAULT_MODEL, chunk_target_lines_arg=MAIN_LINES_PER_CHUNK,
                               cli_api_endpoint=API_ENDPOINT,
                               progress_callback=None, log_callback=None, stats_callback=None):
    if not os.path.exists(input_filepath):
        err_msg = f"ERROR: Input EPUB file '{input_filepath}' not found."
        if log_callback: log_callback("epub_input_file_not_found", err_msg)
        else: print(err_msg) # Critical
        return

    all_translation_jobs = [] 
    parsed_xhtml_docs = {}    

    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            with zipfile.ZipFile(input_filepath, 'r') as zip_ref:
                zip_ref.extractall(temp_dir)
            
            opf_path = None
            for root_dir, _, files in os.walk(temp_dir):
                for file in files:
                    if file.endswith('.opf'):
                        opf_path = os.path.join(root_dir, file)
                        break
                if opf_path: break
            if not opf_path: raise FileNotFoundError("CRITICAL ERROR: content.opf not found in EPUB.")
            
            opf_tree = etree.parse(opf_path)
            opf_root = opf_tree.getroot()
            
            manifest = opf_root.find('.//opf:manifest', namespaces=NAMESPACES)
            spine = opf_root.find('.//opf:spine', namespaces=NAMESPACES)
            if manifest is None or spine is None: raise ValueError("CRITICAL ERROR: manifest or spine missing in EPUB.")

            content_files_hrefs = []
            for itemref in spine.findall('.//opf:itemref', namespaces=NAMESPACES):
                idref = itemref.get('idref')
                item = manifest.find(f'.//opf:item[@id="{idref}"]', namespaces=NAMESPACES)
                if item is not None and item.get('media-type') in ['application/xhtml+xml', 'text/html'] and item.get('href'):
                    content_files_hrefs.append(item.get('href'))
            
            opf_dir = os.path.dirname(opf_path)

            if log_callback: log_callback("epub_phase1_start", "Phase 1: Collecting and splitting text from EPUB...")
            # else: print("Phase 1: Analyzing EPUB...") # Less critical for CLI

            iterator_phase1 = tqdm(content_files_hrefs, desc="Analyzing EPUB files", unit="file") if not log_callback else content_files_hrefs
            for file_idx, content_href in enumerate(iterator_phase1):
                if progress_callback and len(content_files_hrefs) > 0:
                    progress_callback( (file_idx / len(content_files_hrefs)) * 10 )


                file_path_abs = os.path.normpath(os.path.join(opf_dir, content_href))
                if not os.path.exists(file_path_abs):
                    warn_msg = f"WARNING: EPUB file '{content_href}' not found at '{file_path_abs}', ignored."
                    if log_callback: log_callback("epub_content_file_not_found", warn_msg)
                    else: tqdm.write(warn_msg)
                    continue
                try:
                    with open(file_path_abs, 'r', encoding='utf-8') as f_chap:
                        chap_str_content = f_chap.read()
                    
                    parser = etree.XMLParser(encoding='utf-8', recover=True, remove_blank_text=False)
                    doc_chap_root = etree.fromstring(chap_str_content.encode('utf-8'), parser)
                    parsed_xhtml_docs[file_path_abs] = doc_chap_root 
                    
                    body_el = doc_chap_root.find('.//{http://www.w3.org/1999/xhtml}body')
                    if body_el is not None:
                        _collect_epub_translation_jobs_recursive(body_el, file_path_abs, all_translation_jobs, chunk_target_lines_arg, log_callback)
                
                except etree.XMLSyntaxError as e_xml:
                    err_msg_xml = f"XML Syntax ERROR in '{content_href}': {e_xml}. Ignored."
                    if log_callback: log_callback("epub_xml_syntax_error", err_msg_xml)
                    else: tqdm.write(err_msg_xml) # Important warning
                except Exception as e_chap:
                    err_msg_chap = f"ERROR Collecting chapter jobs '{content_href}': {e_chap}. Ignored."
                    if log_callback: log_callback("epub_collect_job_error", err_msg_chap)
                    else: tqdm.write(err_msg_chap) # Important warning
            
            if not all_translation_jobs:
                info_msg_no_jobs = "No translatable text segments found in the EPUB."
                if log_callback: log_callback("epub_no_translatable_segments", info_msg_no_jobs)
                else: tqdm.write(info_msg_no_jobs)
                if progress_callback: progress_callback(100)
            else:
                if log_callback: log_callback("epub_jobs_collected", f"{len(all_translation_jobs)} translatable segments collected.")
                # else: tqdm.write(f"{len(all_translation_jobs)} segments to translate.")
            
            if stats_callback and all_translation_jobs:
                stats_callback({'total_chunks': len(all_translation_jobs), 'completed_chunks': 0, 'failed_chunks': 0})

            if log_callback: log_callback("epub_phase2_start", "\nPhase 2: Translating EPUB text segments...")
            # else: print("\nPhase 2: Translating EPUB...") # Less critical for CLI
            
            last_successful_llm_context = ""
            completed_jobs_count = 0
            failed_jobs_count = 0

            iterator_phase2 = tqdm(all_translation_jobs, desc="Translating EPUB segments", unit="seg") if not log_callback else all_translation_jobs
            for job_idx, job in enumerate(iterator_phase2):
                if progress_callback and len(all_translation_jobs) > 0:
                    base_progress_phase2 = ((job_idx +1) / len(all_translation_jobs)) * 90
                    progress_callback(10 + base_progress_phase2)

                translated_sub_parts_for_job = []
                current_segment_overall_context = last_successful_llm_context 
                sub_chunk_errors = 0
                # total_sub_chunks_in_job = len(job['sub_chunks']) # Not used currently

                for sub_chunk_idx, sub_chunk_data in enumerate(job['sub_chunks']):
                    main_content = sub_chunk_data["main_content"]
                    context_before = sub_chunk_data["context_before"]
                    context_after = sub_chunk_data["context_after"]

                    if not main_content.strip():
                        translated_sub_parts_for_job.append(main_content)
                        continue

                    translated_sub_chunk_text = None
                    current_attempts = 0
                    while current_attempts < MAX_TRANSLATION_ATTEMPTS and translated_sub_chunk_text is None:
                        current_attempts += 1
                        if current_attempts > 1:
                            retry_msg_sub = f"Retrying seg {job_idx+1}, sub-seg {sub_chunk_idx+1} (attempt {current_attempts}/{MAX_TRANSLATION_ATTEMPTS})..."
                            if log_callback: log_callback("epub_sub_chunk_retry", retry_msg_sub)
                            else: tqdm.write(f"\n{retry_msg_sub}")
                            await asyncio.sleep(RETRY_DELAY_SECONDS)
                        
                        translated_sub_chunk_text = await generate_translation_request(
                            main_content, context_before, context_after,
                            current_segment_overall_context, 
                            source_language, target_language, model_name,
                            api_endpoint_param=cli_api_endpoint, log_callback=log_callback
                        )
                    
                    if translated_sub_chunk_text is not None:
                        translated_sub_parts_for_job.append(translated_sub_chunk_text)
                        words = translated_sub_chunk_text.split()
                        if len(words) > 150: current_segment_overall_context = " ".join(words[-150:])
                        elif translated_sub_chunk_text.strip(): current_segment_overall_context = translated_sub_chunk_text
                    else: # Error occurred for this sub-chunk
                        sub_chunk_errors += 1
                        # Error message already printed by generate_translation_request if it was an API/extraction issue
                        tqdm.write(f"ERROR EPUB sub-segment {job_idx+1}.{sub_chunk_idx+1} (file: {os.path.basename(job['file_path'])}). Original preserved.")
                        error_placeholder = f"[SUB_SEGMENT_ERROR Seg {job_idx+1} Sub {sub_chunk_idx+1}]\n{main_content}\n[/SUB_SEGMENT_ERROR]"
                        translated_sub_parts_for_job.append(error_placeholder)
                        current_segment_overall_context = "" 

                job['translated_text'] = "\n".join(translated_sub_parts_for_job)
                last_successful_llm_context = current_segment_overall_context 

                if sub_chunk_errors > 0 : 
                    failed_jobs_count += 1
                else:
                    completed_jobs_count += 1
                
                if stats_callback and all_translation_jobs:
                    stats_callback({'completed_chunks': completed_jobs_count, 'failed_chunks': failed_jobs_count})

            if progress_callback: progress_callback(100)

            if log_callback: log_callback("epub_phase3_start", "\nPhase 3: Applying translations to EPUB files...")
            # else: print("\nPhase 3: Updating EPUB...") # Less critical for CLI
            
            iterator_phase3 = tqdm(all_translation_jobs, desc="Updating EPUB content", unit="seg") if not log_callback else all_translation_jobs
            for job in iterator_phase3:
                if job['translated_text'] is None: continue 

                element = job['element_ref']
                translated_content = job['translated_text']

                if job['type'] == 'block_content':
                    element.text = translated_content # Set the new translated content
                    for child_node in list(element): # Remove all children as their text is now part of translated_content
                        element.remove(child_node)
                elif job['type'] == 'text':
                    element.text = job['leading_space'] + translated_content + job['trailing_space']
                elif job['type'] == 'tail':
                    element.tail = job['leading_space'] + translated_content + job['trailing_space']
            
            # Update language in OPF metadata
            metadata = opf_root.find('.//opf:metadata', namespaces=NAMESPACES)
            if metadata is not None:
                lang_el = metadata.find('.//dc:language', namespaces=NAMESPACES)
                if lang_el is not None: lang_el.text = target_language.lower()[:2] # Use 2-letter code

            opf_tree.write(opf_path, encoding='utf-8', xml_declaration=True, pretty_print=True)

            for file_path_abs, doc_root in parsed_xhtml_docs.items():
                try:
                    with open(file_path_abs, 'wb') as f_out: # Write as bytes
                        f_out.write(etree.tostring(doc_root, encoding='utf-8', xml_declaration=True, pretty_print=True))
                except Exception as e_write:
                    err_msg_write = f"ERROR writing modified EPUB file '{file_path_abs}': {e_write}"
                    if log_callback: log_callback("epub_write_error", err_msg_write)
                    else: tqdm.write(err_msg_write) # Important


            if log_callback: log_callback("epub_zip_start", "\nCreating translated EPUB file...")
            # else: print("\nCreating final EPUB...") # Less critical for CLI

            with zipfile.ZipFile(output_filepath, 'w', zipfile.ZIP_DEFLATED) as epub_zip:
                mimetype_path_abs = os.path.join(temp_dir, 'mimetype')
                if os.path.exists(mimetype_path_abs): # mimetype must be first and uncompressed
                    epub_zip.write(mimetype_path_abs, 'mimetype', compress_type=zipfile.ZIP_STORED)
                
                for root_path, _, files_in_root in os.walk(temp_dir):
                    for file_item in files_in_root:
                        if file_item != 'mimetype': # Already added or doesn't exist
                            file_path_abs_for_zip = os.path.join(root_path, file_item)
                            arcname = os.path.relpath(file_path_abs_for_zip, temp_dir)
                            epub_zip.write(file_path_abs_for_zip, arcname)
            
            success_save_msg = f"Translated EPUB saved: '{output_filepath}'"
            if log_callback: log_callback("epub_save_success", success_save_msg)
            else: tqdm.write(success_save_msg) # Important feedback

        except Exception as e_epub:
            major_err_msg = f"MAJOR ERROR processing EPUB '{input_filepath}': {e_epub}"
            if log_callback:
                log_callback("epub_major_error", major_err_msg)
                import traceback
                log_callback("epub_major_error_traceback", traceback.format_exc())
            else:
                print(major_err_msg) # Critical
                import traceback
                traceback.print_exc() # Show full traceback for critical CLI errors


async def translate_file(input_filepath, output_filepath,
                         source_language="English", target_language="French",
                         model_name=DEFAULT_MODEL, chunk_target_size_cli=MAIN_LINES_PER_CHUNK,
                         cli_api_endpoint=API_ENDPOINT,
                         progress_callback=None, log_callback=None, stats_callback=None):
    _, ext = os.path.splitext(input_filepath.lower())
    
    if ext == '.epub':
        await translate_epub_file(input_filepath, output_filepath,
                                  source_language, target_language,
                                  model_name, chunk_target_size_cli, 
                                  cli_api_endpoint,
                                  progress_callback, log_callback, stats_callback) 
    else: 
        await translate_text_file_with_callbacks(
            input_filepath, output_filepath,
            source_language, target_language,
            model_name, chunk_target_size_cli,
            cli_api_endpoint,
            progress_callback, log_callback, stats_callback
        )

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Translate a text or EPUB file using an LLM.")
    parser.add_argument("-i", "--input", required=True, help="Path to the input file (text or EPUB).")
    parser.add_argument("-o", "--output", default=None, help="Path to the output file. If not specified, uses input filename with suffix.")
    parser.add_argument("-sl", "--source_lang", default="English", help="Source language (default: English).")
    parser.add_argument("-tl", "--target_lang", default="French", help="Target language (default: French).")
    parser.add_argument("-m", "--model", default=DEFAULT_MODEL, help=f"LLM model (default: {DEFAULT_MODEL}).")
    parser.add_argument("-cs", "--chunksize", type=int, default=MAIN_LINES_PER_CHUNK, help=f"Target lines per chunk (default: {MAIN_LINES_PER_CHUNK}).")
    parser.add_argument("--api_endpoint", default=API_ENDPOINT, help=f"Ollama API endpoint (default: {API_ENDPOINT}).")

    args = parser.parse_args()

    if args.output is None:
        base, ext = os.path.splitext(args.input)
        output_ext = ext # Default to same extension
        # Ensure .epub output for .epub input, even if original ext had varied casing
        if args.input.lower().endswith('.epub'):
            output_ext = '.epub' 
        args.output = f"{base}_translated_{args.target_lang.lower()}{output_ext}"


    file_type_msg = "EPUB" if args.input.lower().endswith('.epub') else "text"
    print(f"Translating {file_type_msg} from '{args.input}' ({args.source_lang}) to '{args.output}' ({args.target_lang}) with model {args.model}.")
    print(f"Target size per main segment: {args.chunksize} lines.")
    print(f"API endpoint: {args.api_endpoint}")

    asyncio.run(translate_file(
        args.input,
        args.output,
        args.source_lang,
        args.target_lang,
        args.model,
        chunk_target_size_cli=args.chunksize,
        cli_api_endpoint=args.api_endpoint,
        progress_callback=None, 
        log_callback=None, 
        stats_callback=None 
    ))