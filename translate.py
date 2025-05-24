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
# User settings: Modify these values to change the script's default behavior.
API_ENDPOINT = "http://ai_server.mds.com:11434/api/generate"  # Ollama API endpoint (default if not overridden)
DEFAULT_MODEL = "mistral-small:24b"  # Default LLM model to use for translation, best for french language
MAIN_LINES_PER_CHUNK = 25  # Target number of main lines per translation chunk
REQUEST_TIMEOUT = 380  # Timeout in seconds for API requests (adjust if your model is slow or text is very long)
OLLAMA_NUM_CTX = 4096  # Context window size for Ollama (model-dependent)
SENTENCE_TERMINATORS = tuple(list(".!?") + ['."', '?"', '!"', '."', ".'", "?'", "!'", ":", ".)"]) # Characters indicating end of a sentence for chunking logic
MAX_TRANSLATION_ATTEMPTS = 2  # Max number of retries for a failing chunk
RETRY_DELAY_SECONDS = 2  # Seconds to wait before retrying a failed chunk
TRANSLATE_TAG_IN = "[START]"
TRANSLATE_TAG_OUT = "[END]"

# EPUB namespaces
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
        line_content = all_lines[i].strip()
        if not line_content or line_content.endswith(SENTENCE_TERMINATORS):
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
        line_content = all_lines[i].strip()
        if line_content.endswith(SENTENCE_TERMINATORS):
            return i + 1
    if intended_end_idx + max_look_forward_lines >= len(all_lines):
        return len(all_lines)
    return intended_end_idx

def split_text_into_chunks_with_context(text, main_lines_per_chunk_target):
    all_lines = text.splitlines()
    structured_chunks = []
    if not all_lines:
        return []

    look_back_main_limit = main_lines_per_chunk_target // 4
    look_forward_main_limit = main_lines_per_chunk_target // 4
    look_back_context_limit = main_lines_per_chunk_target // 8
    look_forward_context_limit = main_lines_per_chunk_target // 8

    current_position = 0
    while current_position < len(all_lines):
        initial_main_start_index = current_position
        initial_main_end_index = min(current_position + main_lines_per_chunk_target, len(all_lines))

        final_main_start_index = get_adjusted_start_index(all_lines, initial_main_start_index, look_back_main_limit)
        final_main_end_index = get_adjusted_end_index(all_lines, initial_main_end_index, look_forward_main_limit)

        if final_main_end_index <= final_main_start_index:
            final_main_start_index = initial_main_start_index
            final_main_end_index = initial_main_end_index
            if final_main_end_index <= final_main_start_index:
                if initial_main_start_index < len(all_lines):
                    final_main_end_index = len(all_lines)
                else:
                    break

        main_part_lines = all_lines[final_main_start_index:final_main_end_index]

        if not main_part_lines and final_main_start_index < len(all_lines):
            final_main_end_index = len(all_lines)
            main_part_lines = all_lines[final_main_start_index:final_main_end_index]

        if not main_part_lines:
            break

        context_target_line_count = main_lines_per_chunk_target // 4
        intended_context_before_end_idx = final_main_start_index
        intended_context_before_start_idx = max(0, intended_context_before_end_idx - context_target_line_count)
        final_context_before_start_idx = get_adjusted_start_index(all_lines, intended_context_before_start_idx, look_back_context_limit)
        final_context_before_end_idx = intended_context_before_end_idx
        if final_context_before_start_idx >= final_context_before_end_idx:
            final_context_before_start_idx = intended_context_before_start_idx
        preceding_context_lines = all_lines[final_context_before_start_idx:final_context_before_end_idx]

        intended_context_after_start_idx = final_main_end_index
        intended_context_after_end_idx = min(len(all_lines), intended_context_after_start_idx + context_target_line_count)
        final_context_after_start_idx = intended_context_after_start_idx
        final_context_after_end_idx = get_adjusted_end_index(all_lines, intended_context_after_end_idx, look_forward_context_limit)
        if final_context_after_start_idx >= final_context_after_end_idx:
            final_context_after_end_idx = intended_context_after_end_idx
        succeeding_context_lines = all_lines[final_context_after_start_idx:final_context_after_end_idx]

        if not "".join(main_part_lines).strip() and final_main_end_index < len(all_lines):
            current_position = final_main_end_index
            if current_position <= initial_main_start_index: current_position = initial_main_start_index + 1
            continue

        structured_chunks.append({
            "context_before": "\n".join(preceding_context_lines),
            "main_content": "\n".join(main_part_lines),
            "context_after": "\n".join(succeeding_context_lines)
        })

        current_position = final_main_end_index
        if current_position <= initial_main_start_index and current_position < len(all_lines):
            current_position = initial_main_start_index + main_lines_per_chunk_target
            if current_position <= initial_main_start_index: current_position += 1
    return structured_chunks

async def generate_translation_request(main_content, context_before, context_after, previous_translation_context,
                                     source_language="English", target_language="French", model=DEFAULT_MODEL,
                                     api_endpoint_param=API_ENDPOINT):
    full_raw_response = ""
    source_lang = source_language.upper()

    previous_translation_block_text = ""
    if previous_translation_context and previous_translation_context.strip():
        previous_translation_block_text = f"""

    [START OF PREVIOUS TRANSLATION BLOCK ({target_language})]
    {previous_translation_context}
    [END OF PREVIOUS TRANSLATION BLOCK ({target_language})]
    """
    structured_prompt = f"""{previous_translation_block_text}
    [START OF MAIN PART TO TRANSLATE ({source_lang})]
    {main_content}
    [END OF MAIN PART TO TRANSLATE ({source_lang})]

    ## [ROLE]
    # You are a {target_language} professional translator.

    ## [TRANSLATION INSTRUCTIONS]
    + Translate in the author's style.
    + Precisely preserve the deeper meaning of the text, without necessarily adhering strictly to the original wording, to enhance style and fluidity.
    + Adapt expressions and culture to the {target_language} language.
    + Vary your vocabulary with synonyms, avoid words repetition.
    + Maintain the original layout of the text, but remove typos, extraneous characters and line-break hyphens.

    ## [FORMATING INSTRUCTIONS]
    + Translate ONLY the text enclosed within the tags "[START OF MAIN PART TO TRANSLATE ({source_lang})]" and "[END OF MAIN PART TO TRANSLATE ({source_lang})]" from {source_lang} into {target_language}.
    + Refer to the "[START OF PREVIOUS TRANSLATION BLOCK ({target_language})]" section (if provided) to ensure consistency with the previous paragraph.
    + Surround your translation with {TRANSLATE_TAG_IN} and {TRANSLATE_TAG_OUT} tags. For example: {TRANSLATE_TAG_IN}Your text translated here.{TRANSLATE_TAG_OUT}
    + Return only the translation of the main part, formatted as requested.

    DO NOT WRITE ANYTHING BEFORE AND AFTER.
    """
    payload = {
        "model": model,
        "prompt": structured_prompt,
        "stream": False,
        "options": {
            "num_ctx": OLLAMA_NUM_CTX
        }
    }

    try:
        response = requests.post(api_endpoint_param, json=payload, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        json_response = response.json()
        full_raw_response = json_response.get("response", "")
        if not full_raw_response and "error" in json_response:
            print(f"\nError received from LLM API: {json_response['error']}")
            return None
    except requests.exceptions.RequestException as e:
        print(f"\nLLM API request error: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"\nJSON decoding error: {e}. Raw response: {response.text[:500]}...")
        return None
    
    escaped_tag_in = re.escape(TRANSLATE_TAG_IN)
    escaped_tag_out = re.escape(TRANSLATE_TAG_OUT)
    regex_pattern = rf"{escaped_tag_in}(.*?){escaped_tag_out}"
    match = re.search(regex_pattern, full_raw_response, re.DOTALL)
    if match:
        extracted_translation = match.group(1).strip()
        return extracted_translation
    else:
        print(f"\nWARNING: {TRANSLATE_TAG_IN}...{TRANSLATE_TAG_OUT} tags not found in LLM response.")
        print(f"Raw response (partial): {full_raw_response[:500]}...")
        return None


async def translate_text_file(input_filepath, output_filepath,
                              source_language="English", target_language="French",
                              model_name=DEFAULT_MODEL, chunk_target_size=MAIN_LINES_PER_CHUNK,
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
    structured_chunks = split_text_into_chunks_with_context(original_text, chunk_target_size)
    total_chunks = len(structured_chunks)

    if total_chunks == 0 and original_text.strip():
        print("Warning: Non-empty text but no chunks generated by splitting logic.")
        structured_chunks.append({ "context_before": "", "main_content": original_text, "context_after": "" })
        total_chunks = 1
        print(f"Processing the entire text as a single chunk (fallback).")
    elif total_chunks == 0:
        print("Input file empty. No translation needed.")
        try:
            with open(output_filepath, 'w', encoding='utf-8') as f: f.write("")
            print(f"Empty output file '{output_filepath}' created.")
        except Exception as e: print(f"Error saving empty output file: {e}")
        return

    print(f"The text will be translated from {source_language} to {target_language}.")
    print(f"The text has been divided into {total_chunks} main chunks.")
    print(f"Target size for each main chunk: ~{chunk_target_size} lines (may vary due to sentence alignment).")
    print(f"Ollama API endpoint set to: {cli_api_endpoint}")
    print(f"Ollama num_ctx parameter set to: {OLLAMA_NUM_CTX} tokens.")


    full_translation_parts = []
    last_successful_translation = ""

    for i, chunk_data in enumerate(tqdm(structured_chunks, desc=f"Translating {source_language} to {target_language}", unit="chunk")):
        main_content_to_translate = chunk_data["main_content"]
        context_before_text = chunk_data["context_before"]
        context_after_text = chunk_data["context_after"]

        if not main_content_to_translate.strip():
            tqdm.write(f"Chunk {i+1}/{total_chunks}: Main content empty or whitespace, skipping.")
            full_translation_parts.append("")
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
                last_successful_translation,
                source_language,
                target_language,
                model_name,
                api_endpoint_param=cli_api_endpoint
            )

        if translated_chunk_text is not None:
            full_translation_parts.append(translated_chunk_text)
            last_successful_translation = translated_chunk_text
        else:
            tqdm.write(f"\nError translating/extracting chunk {i+1} after {MAX_TRANSLATION_ATTEMPTS} attempts. Marking as ERROR in output.")
            error_placeholder = f"[TRANSLATION/EXTRACTION ERROR CHUNK {i+1} AFTER {MAX_TRANSLATION_ATTEMPTS} ATTEMPTS - Original content ({source_language}):\n{main_content_to_translate}\nEND ERROR CHUNK {i+1}]"
            full_translation_parts.append(error_placeholder)
            last_successful_translation = ""

    print("\n--- Assembling final translation ---")
    final_translated_text = "\n".join(full_translation_parts)
    try:
        with open(output_filepath, 'w', encoding='utf-8') as f:
            f.write(final_translated_text)
        print(f"Full translation saved to '{output_filepath}'")
    except Exception as e:
        print(f"Error saving output file: {e}")


async def translate_text_with_chunking(text, source_language, target_language, model_name, cli_api_endpoint, chunk_size, last_translation=""):
    """Translate text using chunking if needed."""
    
    # If text is short enough, translate directly
    if len(text.split('\n')) <= chunk_size:
        translated = await generate_translation_request(
            text,
            "",
            "",
            last_translation,
            source_language,
            target_language,
            model_name,
            api_endpoint_param=cli_api_endpoint
        )
        return translated if translated else text
    
    # Otherwise, use chunking
    structured_chunks = split_text_into_chunks_with_context(text, chunk_size)
    translated_parts = []
    
    for chunk_data in structured_chunks:
        if chunk_data["main_content"].strip():
            translated = await generate_translation_request(
                chunk_data["main_content"],
                chunk_data["context_before"],
                chunk_data["context_after"],
                last_translation,
                source_language,
                target_language,
                model_name,
                api_endpoint_param=cli_api_endpoint
            )
            if translated:
                translated_parts.append(translated)
                last_translation = translated
            else:
                translated_parts.append(chunk_data["main_content"])
    
    return ' '.join(translated_parts) if translated_parts else text


async def translate_element_preserve_structure(element, source_language, target_language, model_name, cli_api_endpoint, chunk_size=MAIN_LINES_PER_CHUNK, last_translation=""):
    """Translate an XML element recursively while preserving HTML structure."""
    
    # Skip script, style and other non-content elements
    if element.tag in ['{http://www.w3.org/1999/xhtml}script', 
                      '{http://www.w3.org/1999/xhtml}style',
                      '{http://www.w3.org/1999/xhtml}meta',
                      '{http://www.w3.org/1999/xhtml}link']:
        return last_translation
    
    # For block elements with lots of text, collect all text first
    block_tags = ['{http://www.w3.org/1999/xhtml}p', 
                  '{http://www.w3.org/1999/xhtml}div',
                  '{http://www.w3.org/1999/xhtml}li',
                  '{http://www.w3.org/1999/xhtml}blockquote']
    
    # Check if this is a block element with significant text
    if element.tag in block_tags:
        # Count text length in this element
        text_length = 0
        if element.text:
            text_length += len(element.text.split())
        for child in element:
            if child.tail:
                text_length += len(child.tail.split())
        
        # If it's a long block, use chunking approach
        if text_length > chunk_size * 3:  # If it's significantly long
            full_text = element.text or ""
            for child in element:
                if child.tag not in ['{http://www.w3.org/1999/xhtml}script', '{http://www.w3.org/1999/xhtml}style']:
                    if child.text:
                        full_text += child.text
                    if child.tail:
                        full_text += child.tail
            
            if full_text.strip():
                translated = await translate_text_with_chunking(
                    full_text.strip(),
                    source_language,
                    target_language,
                    model_name,
                    cli_api_endpoint,
                    chunk_size,
                    last_translation
                )
                
                # Clear existing text and add translated version
                element.text = translated
                for child in element:
                    child.tail = None
                element[:] = []  # Remove all children
                
                return translated
    
    # Otherwise, translate element by element
    # Translate element's text content if present
    if element.text and element.text.strip():
        translated = await translate_text_with_chunking(
            element.text.strip(),
            source_language,
            target_language,
            model_name,
            cli_api_endpoint,
            chunk_size,
            last_translation
        )
        if translated:
            # Preserve leading/trailing whitespace
            leading_space = len(element.text) - len(element.text.lstrip())
            trailing_space = len(element.text) - len(element.text.rstrip())
            element.text = ' ' * leading_space + translated + ' ' * trailing_space
            last_translation = translated
    
    # Process children recursively
    for child in element:
        last_translation = await translate_element_preserve_structure(
            child, source_language, target_language, model_name, cli_api_endpoint, chunk_size, last_translation
        )
    
# Translate tail text if present
    if element.tail and element.tail.strip():
        translated = await translate_text_with_chunking(
            element.tail.strip(),
            source_language,
            target_language,
            model_name,
            cli_api_endpoint,
            chunk_size,
            last_translation
        )
        if translated:
            # Preserve leading/trailing whitespace
            leading_space = len(element.tail) - len(element.tail.lstrip())
            trailing_space = len(element.tail) - len(element.tail.rstrip())
            element.tail = ' ' * leading_space + translated + ' ' * trailing_space
            last_translation = translated
    
    return last_translation
    
    # Process children recursively
    for child in element:
        last_translation = await translate_element_preserve_structure(
            child, source_language, target_language, model_name, cli_api_endpoint, last_translation
        )
    
    # Translate tail text if present
    if element.tail and element.tail.strip():
        translated = await generate_translation_request(
            element.tail.strip(),
            "",
            "",
            last_translation,
            source_language,
            target_language,
            model_name,
            api_endpoint_param=cli_api_endpoint
        )
        if translated:
            # Preserve leading/trailing whitespace
            leading_space = len(element.tail) - len(element.tail.lstrip())
            trailing_space = len(element.tail) - len(element.tail.rstrip())
            element.tail = ' ' * leading_space + translated + ' ' * trailing_space
            last_translation = translated
    
    return last_translation


async def translate_epub_file(input_filepath, output_filepath,
                            source_language="English", target_language="French",
                            model_name=DEFAULT_MODEL, chunk_target_size=MAIN_LINES_PER_CHUNK,
                            cli_api_endpoint=API_ENDPOINT):
    """Translate an EPUB file while preserving its structure."""
    
    if not os.path.exists(input_filepath):
        print(f"Error: Input file '{input_filepath}' not found.")
        return
    
    # Create temporary directory for extraction
    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            # Extract EPUB
            with zipfile.ZipFile(input_filepath, 'r') as zip_ref:
                zip_ref.extractall(temp_dir)
            
            print(f"EPUB extracted successfully. Starting translation from {source_language} to {target_language}...")
            
            # Find and parse content.opf
            opf_path = None
            for root, dirs, files in os.walk(temp_dir):
                for file in files:
                    if file.endswith('.opf'):
                        opf_path = os.path.join(root, file)
                        break
                if opf_path:
                    break
            
            if not opf_path:
                print("Error: Could not find content.opf file in EPUB")
                return
            
            # Parse OPF file
            tree = etree.parse(opf_path)
            root = tree.getroot()
            
            # Update metadata for translated version
            metadata = root.find('.//opf:metadata', namespaces=NAMESPACES)
            if metadata is not None:
                # Update language
                language_elem = metadata.find('.//dc:language', namespaces=NAMESPACES)
                if language_elem is not None:
                    language_elem.text = target_language.lower()[:2]  # Use ISO 639-1 code
                
                # Add note about translation
                title_elem = metadata.find('.//dc:title', namespaces=NAMESPACES)
                if title_elem is not None:
                    original_title = title_elem.text
                    title_elem.text = f"{original_title} ({target_language} Translation)"
            
            # Find all content files
            manifest = root.find('.//opf:manifest', namespaces=NAMESPACES)
            spine = root.find('.//opf:spine', namespaces=NAMESPACES)
            
            if manifest is None or spine is None:
                print("Error: Invalid EPUB structure")
                return
            
            # Get content files in reading order
            content_files = []
            for itemref in spine.findall('.//opf:itemref', namespaces=NAMESPACES):
                idref = itemref.get('idref')
                item = manifest.find(f'.//opf:item[@id="{idref}"]', namespaces=NAMESPACES)
                if item is not None:
                    href = item.get('href')
                    media_type = item.get('media-type')
                    if media_type in ['application/xhtml+xml', 'text/html']:
                        content_files.append(href)
            
            # Base directory for content files
            opf_dir = os.path.dirname(opf_path)
            
            # Translate each content file
            total_files = len(content_files)
            for idx, content_file in enumerate(tqdm(content_files, desc="Translating EPUB chapters", unit="chapter")):
                file_path = os.path.join(opf_dir, content_file)
                
                if os.path.exists(file_path):
                    try:
                        # Read content
                        with open(file_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                        
                        # Parse XHTML
                        parser = etree.XMLParser(encoding='utf-8', recover=True, remove_blank_text=True)
                        doc = etree.fromstring(content.encode('utf-8'), parser)
                        
                        # Find the body element
                        body = doc.find('.//{http://www.w3.org/1999/xhtml}body')
                        if body is not None:
                            print(f"\nTranslating chapter {idx+1}/{total_files}: {content_file}")
                            
                            # Translate the body content while preserving structure
                            await translate_element_preserve_structure(
                                body,
                                source_language,
                                target_language,
                                model_name,
                                cli_api_endpoint
                            )
                        
                        # Save translated content
                        with open(file_path, 'wb') as f:
                            f.write(etree.tostring(doc, encoding='utf-8', xml_declaration=True, pretty_print=True))
                        
                    except Exception as e:
                        print(f"Error processing {content_file}: {e}")
                        continue
            
            # Save updated OPF
            tree.write(opf_path, encoding='utf-8', xml_declaration=True)
            
            # Create new EPUB
            print("\nCreating translated EPUB file...")
            with zipfile.ZipFile(output_filepath, 'w', zipfile.ZIP_DEFLATED) as epub:
                # Add mimetype first (uncompressed)
                mimetype_path = os.path.join(temp_dir, 'mimetype')
                if os.path.exists(mimetype_path):
                    epub.write(mimetype_path, 'mimetype', compress_type=zipfile.ZIP_STORED)
                
                # Add all other files
                for root, dirs, files in os.walk(temp_dir):
                    for file in files:
                        if file != 'mimetype':  # Skip mimetype as it's already added
                            file_path = os.path.join(root, file)
                            arcname = os.path.relpath(file_path, temp_dir)
                            epub.write(file_path, arcname)
            
            print(f"Translated EPUB saved to '{output_filepath}'")
            
        except Exception as e:
            print(f"Error processing EPUB file: {e}")
            import traceback
            traceback.print_exc()


async def translate_file(input_filepath, output_filepath,
                        source_language="English", target_language="French",
                        model_name=DEFAULT_MODEL, chunk_target_size=MAIN_LINES_PER_CHUNK,
                        cli_api_endpoint=API_ENDPOINT):
    """Translate a file based on its extension."""
    
    # Determine file type
    _, ext = os.path.splitext(input_filepath.lower())
    
    if ext == '.epub':
        await translate_epub_file(input_filepath, output_filepath,
                                source_language, target_language,
                                model_name, chunk_target_size,
                                cli_api_endpoint)
    else:
        # Default to text file translation
        await translate_text_file(input_filepath, output_filepath,
                                source_language, target_language,
                                model_name, chunk_target_size,
                                cli_api_endpoint)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Translate a text or EPUB file using an LLM.")
    parser.add_argument("-i", "--input", required=True, help="Path to the input file to translate (text or EPUB).")
    parser.add_argument("-o", "--output", default=None, help="Path to the output file for the translation. If not specified, will use input filename with '_translated' suffix.")
    parser.add_argument("-sl", "--source_lang", default="English", help="Source language of the text (default: English).")
    parser.add_argument("-tl", "--target_lang", default="French", help="Target language for translation (default: French).")
    parser.add_argument("-m", "--model", default=DEFAULT_MODEL, help=f"LLM model to use (default: {DEFAULT_MODEL}).")
    parser.add_argument("-cs", "--chunksize", type=int, default=MAIN_LINES_PER_CHUNK, help=f"Target number of lines per chunk (default: {MAIN_LINES_PER_CHUNK}).")
    parser.add_argument("--api_endpoint", default=API_ENDPOINT, help=f"Ollama API endpoint (default: {API_ENDPOINT}).") # For CLI override

    args = parser.parse_args()

    # Auto-generate output filename if not specified
    if args.output is None:
        base, ext = os.path.splitext(args.input)
        args.output = f"{base}_translated_{args.target_lang.lower()}{ext}"

    cli_api_endpoint_to_use = args.api_endpoint

    # Determine file type
    _, ext = os.path.splitext(args.input.lower())
    file_type = "EPUB" if ext == '.epub' else "text"

    print(f"Starting {file_type} translation from '{args.input}' ({args.source_lang}) to '{args.output}' ({args.target_lang}) using model {args.model}.")
    print(f"Main content target per chunk: {args.chunksize} lines.")
    print(f"Using API Endpoint: {cli_api_endpoint_to_use}")

    asyncio.run(translate_file(
        args.input,
        args.output,
        args.source_lang,
        args.target_lang,
        args.model,
        chunk_target_size=args.chunksize,
        cli_api_endpoint=cli_api_endpoint_to_use
    ))