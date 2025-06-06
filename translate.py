"""
Command-line interface for text translation
"""
import os
import argparse
import asyncio

from config import DEFAULT_MODEL, MAIN_LINES_PER_CHUNK, API_ENDPOINT
from src.utils.file_utils import translate_file


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Translate a text, EPUB or SRT file using an LLM.")
    parser.add_argument("-i", "--input", required=True, help="Path to the input file (text, EPUB, or SRT).")
    parser.add_argument("-o", "--output", default=None, help="Path to the output file. If not specified, uses input filename with suffix.")
    parser.add_argument("-sl", "--source_lang", default="English", help="Source language (default: English).")
    parser.add_argument("-tl", "--target_lang", default="French", help="Target language (default: French).")
    parser.add_argument("-m", "--model", default=DEFAULT_MODEL, help=f"LLM model (default: {DEFAULT_MODEL}).")
    parser.add_argument("-cs", "--chunksize", type=int, default=MAIN_LINES_PER_CHUNK, help=f"Target lines per chunk (default: {MAIN_LINES_PER_CHUNK}).")
    parser.add_argument("--api_endpoint", default=API_ENDPOINT, help=f"Ollama API endpoint (default: {API_ENDPOINT}).")

    args = parser.parse_args()

    if args.output is None:
        base, ext = os.path.splitext(args.input)
        output_ext = ext
        if args.input.lower().endswith('.epub'):
            output_ext = '.epub'
        elif args.input.lower().endswith('.srt'):
            output_ext = '.srt'
        args.output = f"{base}_translated_{args.target_lang.lower()}{output_ext}"

    if args.input.lower().endswith('.epub'):
        file_type_msg = "EPUB"
    elif args.input.lower().endswith('.srt'):
        file_type_msg = "SRT subtitle"
    else:
        file_type_msg = "text"
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
        stats_callback=None,
        check_interruption_callback=None
    ))