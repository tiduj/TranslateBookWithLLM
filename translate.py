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
API_ENDPOINT = "http://ai_server.mds.com:11434/api/generate"
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
    except Exception as e:
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
                                       api_endpoint_param=API_ENDPOINT):
    full_raw_response = ""
    source_lang = source_language.upper()

    role_and_instructions_block = f"""## ROLE
# You are a {target_language} professional writer.

## TRANSLATION
+ Translate in the author's style
+ Precisely preserve the deeper meaning of the text, without necessarily adhering strictly to the original wording, to enhance style and fluidity
+ Adapt expressions and culture to the {target_language} language
+ Vary your vocabulary with synonyms, avoid words repetition
+ Maintain the original layout of the text

## FORMATING
+ Translate ONLY the text enclosed within the tags "[START TO TRANSLATE]" and "[END TO TRANSLATE]" from {source_lang} into {target_language}.
+ Refer to the "[START PREVIOUS TRANSLATION ({target_language})]" section (if provided) to ensure consistency with the previous paragraph.
+ Surround your translation with {TRANSLATE_TAG_IN} and {TRANSLATE_TAG_OUT} tags. For example: {TRANSLATE_TAG_IN}Your text translated here.{TRANSLATE_TAG_OUT}
+ Return only the translation, formatted as requested.

DO NOT WRITE ANYTHING BEFORE AND AFTER."""

    previous_translation_block_text = ""
    if previous_translation_context and previous_translation_context.strip():
        previous_translation_block_text = f"""
[START PREVIOUS TRANSLATION ({target_language})]
{previous_translation_context}
[END PREVIOUS TRANSLATION ({target_language})]"""
    
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

    payload = {
        "model": model,
        "prompt": structured_prompt, 
        "stream": False,
        "options": {
            "num_ctx": OLLAMA_NUM_CTX
        }
    }

    print("\n--- START LLM Request ---")
    print(structured_prompt)
    print("\n--- END LLM Request ---")
    
    try:
        response = requests.post(api_endpoint_param, json=payload, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        json_response = response.json()
        full_raw_response = json_response.get("response", "")
        
        if not full_raw_response and "error" in json_response:
            tqdm.write(f"\nError received from LLM API: {json_response['error']}")
            return None
            
    except requests.exceptions.Timeout as e:
        tqdm.write(f"\nLLM API request timed out after {REQUEST_TIMEOUT}s: {e}")
        return None
    except requests.exceptions.HTTPError as e:
        tqdm.write(f"\nLLM API HTTP error: {e.response.status_code} - {e.response.reason}. Response: {e.response.text[:500]}...")
        return None
    except requests.exceptions.RequestException as e:
        tqdm.write(f"\nLLM API request error: {e}")
        return None
    except json.JSONDecodeError as e:
        raw_response_text = response.text if 'response' in locals() and hasattr(response, 'text') else "N/A"
        tqdm.write(f"\nJSON decoding error: {e}. Raw response: {raw_response_text[:500]}...")
        return None
    
    escaped_tag_in = re.escape(TRANSLATE_TAG_IN)
    escaped_tag_out = re.escape(TRANSLATE_TAG_OUT)
    regex_pattern = rf"{escaped_tag_in}(.*?){escaped_tag_out}"
    match = re.search(regex_pattern, full_raw_response, re.DOTALL)
    
    if match:
        extracted_translation = match.group(1).strip()
        return extracted_translation
    else:
        tqdm.write(f"\nWARNING: Tags {TRANSLATE_TAG_IN}...{TRANSLATE_TAG_OUT} not found in LLM response.")
        tqdm.write(f"Full raw response was: {full_raw_response[:500]}...")
        return None

async def translate_text_file(input_filepath, output_filepath,
                               source_language="English", target_language="French",
                               model_name=DEFAULT_MODEL, chunk_target_lines_cli=MAIN_LINES_PER_CHUNK,
                               cli_api_endpoint=API_ENDPOINT):
    if not os.path.exists(input_filepath):
        print(f"Error: Input file '{input_filepath}' not found.")
        return

    try:
        with open(input_filepath, 'r', encoding='utf-8') as f:
            original_text = f.read()
    except Exception as e:
        print(f"Error reading input file: {e}")
        return

    print(f"Splitting text from '{source_language}' into chunks with sentence alignment...")
    structured_chunks = split_text_into_chunks_with_context(original_text, chunk_target_lines_cli)
    total_chunks = len(structured_chunks)

    if total_chunks == 0 and original_text.strip():
        print("Warning: Non-empty text but no chunks generated. Processing as a single chunk.")
        structured_chunks.append({ "context_before": "", "main_content": original_text, "context_after": "" })
        total_chunks = 1
    elif total_chunks == 0:
        print("Input file empty. No translation needed.")
        try:
            with open(output_filepath, 'w', encoding='utf-8') as f: f.write("")
            print(f"Empty output file '{output_filepath}' created.")
        except Exception as e: print(f"Error saving empty output file: {e}")
        return

    print(f"The text will be translated from {source_language} to {target_language}.")
    print(f"The text has been divided into {total_chunks} main chunks.")
    print(f"Target size for each main chunk: ~{chunk_target_lines_cli} lines.")

    full_translation_parts = []
    last_successful_llm_context = "" 

    for i, chunk_data in enumerate(tqdm(structured_chunks, desc=f"Translating {source_language} to {target_language}", unit="chunk")):
        main_content_to_translate = chunk_data["main_content"]
        context_before_text = chunk_data["context_before"]
        context_after_text = chunk_data["context_after"]

        if not main_content_to_translate.strip():
            full_translation_parts.append(main_content_to_translate) 
            continue

        translated_chunk_text = None
        current_attempts = 0
        while current_attempts < MAX_TRANSLATION_ATTEMPTS and translated_chunk_text is None:
            current_attempts += 1
            if current_attempts > 1:
                tqdm.write(f"\nRetrying chunk {i+1}/{total_chunks} (attempt {current_attempts}/{MAX_TRANSLATION_ATTEMPTS})...")
                await asyncio.sleep(RETRY_DELAY_SECONDS)

            translated_chunk_text = await generate_translation_request(
                main_content_to_translate,
                context_before_text,
                context_after_text,
                last_successful_llm_context,
                source_language,
                target_language,
                model_name,
                api_endpoint_param=cli_api_endpoint
            )

        if translated_chunk_text is not None:
            full_translation_parts.append(translated_chunk_text)
            words = translated_chunk_text.split()
            if len(words) > 150: 
                last_successful_llm_context = " ".join(words[-150:])
            else:
                last_successful_llm_context = translated_chunk_text
        else:
            tqdm.write(f"\nError translating/extracting chunk {i+1} after {MAX_TRANSLATION_ATTEMPTS} attempts. Original content preserved with error tags.")
            error_placeholder = f"[TRANSLATION_ERROR CHUNK {i+1}]\n{main_content_to_translate}\n[/TRANSLATION_ERROR CHUNK {i+1}]"
            full_translation_parts.append(error_placeholder)
            last_successful_llm_context = ""

    final_translated_text = "\n".join(full_translation_parts)
    try:
        with open(output_filepath, 'w', encoding='utf-8') as f:
            f.write(final_translated_text)
        print(f"Full translation saved to '{output_filepath}'")
    except Exception as e:
        print(f"Error saving output file: {e}")

async def translate_text_with_chunking(text_to_translate, source_language, target_language, model_name, cli_api_endpoint, chunk_target_lines, previous_llm_context=""):
    if not text_to_translate.strip():
        return text_to_translate 

    structured_chunks = split_text_into_chunks_with_context(text_to_translate, chunk_target_lines)

    if not structured_chunks:
        translated_text_segment = await generate_translation_request(
            text_to_translate, "", "", previous_llm_context,
            source_language, target_language, model_name, api_endpoint_param=cli_api_endpoint
        )
        return translated_text_segment if translated_text_segment is not None else text_to_translate

    translated_parts = []
    current_sub_chunk_llm_context = previous_llm_context 

    for chunk_data in structured_chunks:
        main_content = chunk_data["main_content"]
        context_before_for_llm = chunk_data["context_before"]
        context_after_for_llm = chunk_data["context_after"]
        
        if not main_content.strip():
            if main_content: 
                translated_parts.append(main_content)
            continue

        translated_segment = await generate_translation_request(
            main_content, context_before_for_llm, context_after_for_llm, current_sub_chunk_llm_context, 
            source_language, target_language, model_name, api_endpoint_param=cli_api_endpoint
        )

        if translated_segment is not None:
            translated_parts.append(translated_segment)
            words = translated_segment.split()
            if len(words) > 150: 
                current_sub_chunk_llm_context = " ".join(words[-150:])
            else:
                current_sub_chunk_llm_context = translated_segment
        else:
            error_placeholder = f"[EPUB_SUB_CHUNK_ERROR]\n{main_content}\n[/EPUB_SUB_CHUNK_ERROR]"
            translated_parts.append(error_placeholder)
            current_sub_chunk_llm_context = "" 

    final_translation = "\n".join(translated_parts)
    return final_translation if final_translation.strip() or text_to_translate.strip() == "" else text_to_translate

async def translate_element_preserve_structure(element, source_language, target_language, model_name, cli_api_endpoint, chunk_target_lines=MAIN_LINES_PER_CHUNK, previous_llm_context=""):
    if element.tag in ['{http://www.w3.org/1999/xhtml}script', 
                        '{http://www.w3.org/1999/xhtml}style',
                        '{http://www.w3.org/1999/xhtml}meta',
                        '{http://www.w3.org/1999/xhtml}link']:
        return previous_llm_context 
    
    content_block_tags = [
        '{http://www.w3.org/1999/xhtml}p', '{http://www.w3.org/1999/xhtml}div', 
        '{http://www.w3.org/1999/xhtml}li', '{http://www.w3.org/1999/xhtml}h1', 
        '{http://www.w3.org/1999/xhtml}h2', '{http://www.w3.org/1999/xhtml}h3', 
        '{http://www.w3.org/1999/xhtml}h4', '{http://www.w3.org/1999/xhtml}h5', 
        '{http://www.w3.org/1999/xhtml}h6', '{http://www.w3.org/1999/xhtml}blockquote',
        '{http://www.w3.org/1999/xhtml}td', '{http://www.w3.org/1999/xhtml}th',
        '{http://www.w3.org/1999/xhtml}caption',
        '{http://www.w3.org/1999/xhtml}dt', '{http://www.w3.org/1999/xhtml}dd'
    ]
    
    current_element_overall_context = previous_llm_context

    if element.tag in content_block_tags:
        block_text_content = "".join(element.itertext())

        if block_text_content.strip():
            translated_block = await translate_text_with_chunking(
                block_text_content.strip(),
                source_language, target_language, model_name,
                cli_api_endpoint, chunk_target_lines,
                current_element_overall_context
            )
            if translated_block is not None and translated_block.strip() != block_text_content.strip() : 
                element.text = translated_block
                for child_node in list(element): 
                    element.remove(child_node)
                
                words = translated_block.split() 
                if len(words) > 150: current_element_overall_context = " ".join(words[-150:])
                elif translated_block.strip(): current_element_overall_context = translated_block
            elif translated_block is None: 
                element.text = f"[BLOCK_TRANSLATION_ERROR]{block_text_content.strip()}[/BLOCK_TRANSLATION_ERROR]"
                for child_node in list(element): element.remove(child_node)
                current_element_overall_context = ""
        return current_element_overall_context

    if element.text:
        original_text_content = element.text
        text_to_translate = original_text_content.strip()
        if text_to_translate:
            leading_space = original_text_content[:len(original_text_content) - len(original_text_content.lstrip())]
            trailing_space = original_text_content[len(original_text_content.rstrip()):]
            
            translated = await translate_text_with_chunking(
                text_to_translate, source_language, target_language, model_name,
                cli_api_endpoint, chunk_target_lines, current_element_overall_context
            )
            if translated is not None and translated != text_to_translate:
                element.text = leading_space + translated + trailing_space
                words = translated.split()
                if len(words) > 150: current_element_overall_context = " ".join(words[-150:])
                elif translated.strip(): current_element_overall_context = translated
            elif translated is None:
                element.text = leading_space + f"[TEXT_TRANSLATION_ERROR]{text_to_translate}[/TEXT_TRANSLATION_ERROR]" + trailing_space
                current_element_overall_context = ""

    for child in element:
        current_element_overall_context = await translate_element_preserve_structure(
            child, source_language, target_language, model_name, 
            cli_api_endpoint, chunk_target_lines, current_element_overall_context
        )
    
    if element.tail:
        original_tail_content = element.tail
        tail_to_translate = original_tail_content.strip()
        if tail_to_translate:
            leading_space_tail = original_tail_content[:len(original_tail_content) - len(original_tail_content.lstrip())]
            trailing_space_tail = original_tail_content[len(original_tail_content.rstrip()):]

            translated_tail = await translate_text_with_chunking(
                tail_to_translate, source_language, target_language, model_name,
                cli_api_endpoint, chunk_target_lines, current_element_overall_context
            )
            if translated_tail is not None and translated_tail != tail_to_translate:
                element.tail = leading_space_tail + translated_tail + trailing_space_tail
                words = translated_tail.split()
                if len(words) > 150: current_element_overall_context = " ".join(words[-150:])
                elif translated_tail.strip(): current_element_overall_context = translated_tail
            elif translated_tail is None:
                element.tail = leading_space_tail + f"[TAIL_TRANSLATION_ERROR]{tail_to_translate}[/TAIL_TRANSLATION_ERROR]" + trailing_space_tail
                current_element_overall_context = ""
            
    return current_element_overall_context

async def translate_epub_file(input_filepath, output_filepath,
                               source_language="English", target_language="French",
                               model_name=DEFAULT_MODEL, chunk_target_lines_arg=MAIN_LINES_PER_CHUNK,
                               cli_api_endpoint=API_ENDPOINT):
    if not os.path.exists(input_filepath):
        print(f"Error: Input file '{input_filepath}' not found.")
        return
    
    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            with zipfile.ZipFile(input_filepath, 'r') as zip_ref:
                zip_ref.extractall(temp_dir)
            
            opf_path = None
            for root_dir, dirs, files in os.walk(temp_dir):
                for file in files:
                    if file.endswith('.opf'):
                        opf_path = os.path.join(root_dir, file)
                        break
                if opf_path:
                    break
            if not opf_path: raise FileNotFoundError("content.opf not found in EPUB.")
            
            tree = etree.parse(opf_path)
            xml_root = tree.getroot()
            metadata = xml_root.find('.//opf:metadata', namespaces=NAMESPACES)
            if metadata is not None:
                lang_el = metadata.find('.//dc:language', namespaces=NAMESPACES)
                if lang_el is not None: lang_el.text = target_language.lower()[:2]
                title_el = metadata.find('.//dc:title', namespaces=NAMESPACES)
                if title_el is not None and title_el.text: title_el.text = f"{title_el.text} ({target_language} Translation)"

            manifest = xml_root.find('.//opf:manifest', namespaces=NAMESPACES)
            spine = xml_root.find('.//opf:spine', namespaces=NAMESPACES)
            if manifest is None or spine is None: raise ValueError("Invalid EPUB: missing manifest or spine.")

            content_files_hrefs = []
            for itemref in spine.findall('.//opf:itemref', namespaces=NAMESPACES):
                idref = itemref.get('idref')
                item = manifest.find(f'.//opf:item[@id="{idref}"]', namespaces=NAMESPACES)
                if item is not None and item.get('media-type') in ['application/xhtml+xml', 'text/html'] and item.get('href'):
                    content_files_hrefs.append(item.get('href'))
            
            opf_dir = os.path.dirname(opf_path)
            last_processed_llm_chapter_context = "" 

            for idx, content_href in enumerate(tqdm(content_files_hrefs, desc="Translating EPUB chapters", unit="chapter")):
                file_path_abs = os.path.join(opf_dir, content_href)
                if not os.path.exists(file_path_abs):
                    tqdm.write(f"Warning: File {content_href} not found at {file_path_abs}, skipping.")
                    continue
                try:
                    with open(file_path_abs, 'r', encoding='utf-8') as f_chap:
                        chap_str_content = f_chap.read()
                    
                    parser = etree.XMLParser(encoding='utf-8', recover=True, remove_blank_text=False)
                    doc_chap_root = etree.fromstring(chap_str_content.encode('utf-8'), parser)
                    body_el = doc_chap_root.find('.//{http://www.w3.org/1999/xhtml}body')

                    if body_el is not None:
                        tqdm.write(f"\nTranslating chapter {idx+1}/{len(content_files_hrefs)}: {content_href}")
                        last_processed_llm_chapter_context = await translate_element_preserve_structure(
                            body_el, source_language, target_language, model_name, 
                            cli_api_endpoint, chunk_target_lines_arg, 
                            last_processed_llm_chapter_context
                        )
                    
                    with open(file_path_abs, 'wb') as f_chap_out:
                        f_chap_out.write(etree.tostring(doc_chap_root, encoding='utf-8', xml_declaration=True, pretty_print=True))
                
                except etree.XMLSyntaxError as e_xml:
                    tqdm.write(f"XML Syntax Error in {content_href}: {e_xml}. Chapter skipped.")
                except Exception as e_chap:
                    tqdm.write(f"Error processing chapter {content_href}: {e_chap}") 

            tree.write(opf_path, encoding='utf-8', xml_declaration=True, pretty_print=True)

            print("\nCreating translated EPUB file...")
            with zipfile.ZipFile(output_filepath, 'w', zipfile.ZIP_DEFLATED) as epub_zip:
                mimetype_path_abs = os.path.join(temp_dir, 'mimetype')
                if os.path.exists(mimetype_path_abs):
                    epub_zip.write(mimetype_path_abs, 'mimetype', compress_type=zipfile.ZIP_STORED)
                
                for root_path, _, files_in_root in os.walk(temp_dir):
                    for file_item in files_in_root:
                        if file_item != 'mimetype':
                            file_path_abs = os.path.join(root_path, file_item)
                            arcname = os.path.relpath(file_path_abs, temp_dir)
                            epub_zip.write(file_path_abs, arcname)
            print(f"Translated EPUB saved to '{output_filepath}'")

        except Exception as e_epub:
            print(f"Major error processing EPUB file '{input_filepath}': {e_epub}")
            import traceback
            traceback.print_exc()

async def translate_file(input_filepath, output_filepath,
                         source_language="English", target_language="French",
                         model_name=DEFAULT_MODEL, chunk_target_size_cli=MAIN_LINES_PER_CHUNK,
                         cli_api_endpoint=API_ENDPOINT):
    _, ext = os.path.splitext(input_filepath.lower())
    
    if ext == '.epub':
        await translate_epub_file(input_filepath, output_filepath,
                                  source_language, target_language,
                                  model_name, chunk_target_size_cli, 
                                  cli_api_endpoint)
    else:
        await translate_text_file(input_filepath, output_filepath,
                                  source_language, target_language,
                                  model_name, chunk_target_size_cli, 
                                  cli_api_endpoint)

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
        args.output = f"{base}_translated_{args.target_lang.lower()}{ext}"

    file_type_msg = "EPUB" if args.input.lower().endswith('.epub') else "text"
    print(f"Starting {file_type_msg} translation from '{args.input}' ({args.source_lang}) to '{args.output}' ({args.target_lang}) using model {args.model}.")
    print(f"Main content target per chunk: {args.chunksize} lines.")
    print(f"Using API Endpoint: {args.api_endpoint}")

    asyncio.run(translate_file(
        args.input,
        args.output,
        args.source_lang,
        args.target_lang,
        args.model,
        chunk_target_size_cli=args.chunksize,
        cli_api_endpoint=args.api_endpoint
    ))