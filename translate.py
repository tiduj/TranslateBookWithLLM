"""
Command-line interface for text translation
"""
import os
import argparse
import asyncio

from src.config import DEFAULT_MODEL, MAIN_LINES_PER_CHUNK, API_ENDPOINT
from src.utils.file_utils import translate_file
from src.utils.unified_logger import setup_cli_logger, LogType


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Translate a text, EPUB or SRT file using an LLM.")
    parser.add_argument("-i", "--input", required=True, help="Path to the input file (text, EPUB, or SRT).")
    parser.add_argument("-o", "--output", default=None, help="Path to the output file. If not specified, uses input filename with suffix.")
    parser.add_argument("-sl", "--source_lang", default="English", help="Source language (default: English).")
    parser.add_argument("-tl", "--target_lang", default="French", help="Target language (default: French).")
    parser.add_argument("-m", "--model", default=DEFAULT_MODEL, help=f"LLM model (default: {DEFAULT_MODEL}).")
    parser.add_argument("-cs", "--chunksize", type=int, default=MAIN_LINES_PER_CHUNK, help=f"Target lines per chunk (default: {MAIN_LINES_PER_CHUNK}).")
    parser.add_argument("--api_endpoint", default=API_ENDPOINT, help=f"Ollama API endpoint (default: {API_ENDPOINT}).")
    parser.add_argument("--custom_instructions", default="", help="Additional custom instructions for translation.")
    parser.add_argument("--no-color", action="store_true", help="Disable colored output.")

    args = parser.parse_args()

    if args.output is None:
        base, ext = os.path.splitext(args.input)
        output_ext = ext
        if args.input.lower().endswith('.epub'):
            output_ext = '.epub'
        elif args.input.lower().endswith('.srt'):
            output_ext = '.srt'
        args.output = f"{base}_translated_{args.target_lang.lower()}{output_ext}"

    # Determine file type
    if args.input.lower().endswith('.epub'):
        file_type = "EPUB"
    elif args.input.lower().endswith('.srt'):
        file_type = "SRT"
    else:
        file_type = "TEXT"
    
    # Setup unified logger
    logger = setup_cli_logger(enable_colors=not args.no_color)
    
    # Log translation start
    logger.info("Translation Started", LogType.TRANSLATION_START, {
        'source_lang': args.source_lang,
        'target_lang': args.target_lang,
        'file_type': file_type,
        'model': args.model,
        'input_file': args.input,
        'output_file': args.output,
        'chunk_size': args.chunksize,
        'api_endpoint': args.api_endpoint,
        'custom_instructions': args.custom_instructions
    })
    
    # Create legacy callback for backward compatibility
    log_callback = logger.create_legacy_callback()

    try:
        asyncio.run(translate_file(
            args.input,
            args.output,
            args.source_lang,
            args.target_lang,
            args.model,
            chunk_target_size_cli=args.chunksize,
            cli_api_endpoint=args.api_endpoint,
            progress_callback=None,
            log_callback=log_callback,
            stats_callback=None,
            check_interruption_callback=None,
            custom_instructions=args.custom_instructions
        ))
        
        # Log successful completion
        logger.info("Translation Completed Successfully", LogType.TRANSLATION_END, {
            'output_file': args.output
        })
        
    except Exception as e:
        logger.error(f"Translation failed: {str(e)}", LogType.ERROR_DETAIL, {
            'details': str(e),
            'input_file': args.input
        })