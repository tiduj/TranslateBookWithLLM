import json
import requests
import os
import asyncio
import re
from tqdm.auto import tqdm
import argparse

# --- Configuration ---
# User settings: Modify these values to change the script's default behavior.
API_ENDPOINT = "http://localhost:11434/api/generate"  # Ollama API endpoint
DEFAULT_MODEL = "mistral-small:24b"  # Default LLM model to use for translation, best for french language
MAIN_LINES_PER_CHUNK = 25  # Target number of main lines per translation chunk
REQUEST_TIMEOUT = 180  # Timeout in seconds for API requests (adjust if your model is slow or text is very long)
OLLAMA_NUM_CTX = 4096  # Context window size for Ollama (model-dependent)
SENTENCE_TERMINATORS = tuple(list(".!?") + ['."', '?"', '!"', '.”', ".'", "?'", "!'", ":", ".)"]) # Characters indicating end of a sentence for chunking logic
MAX_TRANSLATION_ATTEMPTS = 2  # Max number of retries for a failing chunk
RETRY_DELAY_SECONDS = 2  # Seconds to wait before retrying a failed chunk


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
                                     source_language="English", target_language="French", model=DEFAULT_MODEL):
    full_raw_response = ""
    source_lang = source_language.upper() # For the tags

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

    ## [OUTPUT] 
    + Translate ONLY the text enclosed within the tags "[START OF MAIN PART TO TRANSLATE ({source_lang})]" and "[END OF MAIN PART TO TRANSLATE ({source_lang})]" from {source_lang} into {target_language}.
    + Refer to the "[START OF PREVIOUS TRANSLATION BLOCK ({target_language})]" section (if provided) to ensure consistency with the previous paragraph.
    + Surround your translation with <translate> and </translate> tags. For example: <translate>Your text translated here.</translate>
    + Return only the translation of the main part, formatted as requested.

    DO NOT WRITE ANYTHING BEFORE OR AFTER.
    """
    payload = {
        "model": model,
        "prompt": structured_prompt,
        "stream": False, # Set to True if you want to process streaming responses
        "options": {
            "num_ctx": OLLAMA_NUM_CTX # Ollama specific: context window size
        }
    }

    try:
        response = requests.post(API_ENDPOINT, json=payload, timeout=REQUEST_TIMEOUT)
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

    # Output parsing: If the LLM's output format changes, this regex will need to be updated.
    match = re.search(r"<translate>(.*?)</translate>", full_raw_response, re.DOTALL)
    if match:
        extracted_translation = match.group(1).strip()
        return extracted_translation
    else:
        print(f"\nWARNING: <translate>...</translate> tags not found in LLM response.")
        print(f"Raw response (partial): {full_raw_response[:500]}...")
        # If tags are not found, you might want to return the raw response or handle it differently.
        # For now, it returns None, leading to an error message for the chunk.
        return None


async def translate_text_file(input_filepath, output_filepath,
                              source_language="English", target_language="French",
                              model_name=DEFAULT_MODEL, chunk_target_size=MAIN_LINES_PER_CHUNK):
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
    print(f"Ollama num_ctx parameter set to: {OLLAMA_NUM_CTX} tokens.")

    full_translation_parts = []
    last_successful_translation = "" # Used to provide context from the previously translated chunk

    for i, chunk_data in enumerate(tqdm(structured_chunks, desc=f"Translating {source_language} to {target_language}", unit="chunk")):
        main_content_to_translate = chunk_data["main_content"]
        context_before_text = chunk_data["context_before"]
        context_after_text = chunk_data["context_after"]

        if not main_content_to_translate.strip():
            tqdm.write(f"Chunk {i+1}/{total_chunks}: Main content empty or whitespace, skipping.")
            full_translation_parts.append("") # Append empty string to maintain order if needed later
            continue

        translated_chunk_text = None
        current_attempts = 0

        while current_attempts < MAX_TRANSLATION_ATTEMPTS and translated_chunk_text is None:
            current_attempts += 1
            if current_attempts > 1:
                tqdm.write(f"\nRetrying chunk {i+1}/{total_chunks} (attempt {current_attempts}/{MAX_TRANSLATION_ATTEMPTS})...")
                await asyncio.sleep(RETRY_DELAY_SECONDS) # Wait before retrying

            translated_chunk_text = await generate_translation_request(
                main_content_to_translate,
                context_before_text,
                context_after_text,
                last_successful_translation,
                source_language,
                target_language,
                model_name
            )

        if translated_chunk_text is not None:
            full_translation_parts.append(translated_chunk_text)
            last_successful_translation = translated_chunk_text # Update context for the next chunk
        else:
            tqdm.write(f"\nError translating/extracting chunk {i+1} after {MAX_TRANSLATION_ATTEMPTS} attempts. Marking as ERROR in output.")
            # Placeholder for failed chunks. User might want to customize this.
            error_placeholder = f"[TRANSLATION/EXTRACTION ERROR CHUNK {i+1} AFTER {MAX_TRANSLATION_ATTEMPTS} ATTEMPTS - Original content ({source_language}):\n{main_content_to_translate}\nEND ERROR CHUNK {i+1}]"
            full_translation_parts.append(error_placeholder)
            last_successful_translation = "" # Reset context if a chunk fails

    print("\n--- Assembling final translation ---")
    final_translated_text = "\n".join(full_translation_parts)
    try:
        with open(output_filepath, 'w', encoding='utf-8') as f:
            f.write(final_translated_text)
        print(f"Full translation saved to '{output_filepath}'")
    except Exception as e:
        print(f"Error saving output file: {e}")

# --- Script Entry Point ---
if __name__ == "__main__":
    # Command-line arguments: These allow overriding default settings for a specific run.
    parser = argparse.ArgumentParser(description="Translate a text file using an LLM.")
    parser.add_argument("-i", "--input", required=True, help="Path to the input text file to translate.")
    parser.add_argument("-o", "--output", default="output.txt", help="Path to the output file for the translation (default: output.txt).")
    parser.add_argument("-sl", "--source_lang", default="English", help="Source language of the text (default: English).") # User setting: Source language
    parser.add_argument("-tl", "--target_lang", default="French", help="Target language for translation (default: French).") # User setting: Target language
    parser.add_argument("-m", "--model", default=DEFAULT_MODEL, help=f"LLM model to use (default: {DEFAULT_MODEL}).") # User setting: Model override
    parser.add_argument("-cs", "--chunksize", type=int, default=MAIN_LINES_PER_CHUNK, help=f"Target number of lines per chunk (default: {MAIN_LINES_PER_CHUNK}).") # User setting: Chunk size override

    args = parser.parse_args()

    input_file = args.input
    output_file = args.output
    source_language_setting = args.source_lang
    target_language_setting = args.target_lang
    model_to_use = args.model
    lines_per_chunk_for_this_run = args.chunksize

    print(f"Starting translation from '{input_file}' ({source_language_setting}) to '{output_file}' ({target_language_setting}) using model {model_to_use}.")
    print(f"Main content target per chunk: {lines_per_chunk_for_this_run} lines.")
    print(f"Ollama num_ctx will be set to: {OLLAMA_NUM_CTX} tokens for each API request.")
    print(f"Max translation attempts per chunk: {MAX_TRANSLATION_ATTEMPTS}.")

    asyncio.run(translate_text_file(
        input_file,
        output_file,
        source_language_setting,
        target_language_setting,
        model_to_use,
        chunk_target_size=lines_per_chunk_for_this_run
    ))
