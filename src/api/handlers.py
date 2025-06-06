"""
Translation job handlers and processing logic
"""
import os
import time
import asyncio
import tempfile
import threading
from datetime import datetime

from src.core.text_processor import split_text_into_chunks_with_context
from src.core.translator import translate_chunks
from src.core.epub_processor import translate_epub_file
from .websocket import emit_update


def run_translation_async_wrapper(translation_id, config, active_translations, output_dir, socketio):
    """
    Wrapper for running translation in async context
    
    Args:
        translation_id (str): Translation job ID
        config (dict): Translation configuration
        active_translations (dict): Active translations dictionary
        output_dir (str): Output directory path
        socketio: SocketIO instance
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(perform_actual_translation(translation_id, config, active_translations, output_dir, socketio))
    except Exception as e:
        error_msg = f"Uncaught major error in translation wrapper {translation_id}: {str(e)}"
        print(error_msg)
        if translation_id in active_translations:
            active_translations[translation_id]['status'] = 'error'
            active_translations[translation_id]['error'] = error_msg
            if 'logs' not in active_translations[translation_id]: 
                active_translations[translation_id]['logs'] = []
            active_translations[translation_id]['logs'].append(f"[{datetime.now().strftime('%H:%M:%S')}] CRITICAL WRAPPER ERROR: {error_msg}")
            emit_update(socketio, translation_id, {'error': error_msg, 'status': 'error', 'log': f"CRITICAL WRAPPER ERROR: {error_msg}"}, active_translations)
    finally:
        loop.close()


async def perform_actual_translation(translation_id, config, active_translations, output_dir, socketio):
    """
    Perform the actual translation job
    
    Args:
        translation_id (str): Translation job ID
        config (dict): Translation configuration
        active_translations (dict): Active translations dictionary
        output_dir (str): Output directory path
        socketio: SocketIO instance
    """
    if translation_id not in active_translations:
        print(f"Critical error: {translation_id} not found in active_translations.")
        return

    active_translations[translation_id]['status'] = 'running'
    emit_update(socketio, translation_id, {'status': 'running', 'log': 'Translation task started by worker.'}, active_translations)

    def should_interrupt_current_task():
        if translation_id in active_translations and active_translations[translation_id].get('interrupted', False):
            _log_message_callback("interruption_check", f"Interruption signal detected for job {translation_id}. Halting processing.")
            return True
        return False

    def _log_message_callback(message_key_from_translate_module, message_content=""):
        timestamp = datetime.now().strftime('%H:%M:%S')
        full_log_entry = f"[{timestamp}] {message_content}"

        print(full_log_entry)

        if message_key_from_translate_module in ["llm_prompt_debug", "llm_raw_response_preview"]:
            pass
        else:
            if 'logs' not in active_translations[translation_id]: 
                active_translations[translation_id]['logs'] = []
            active_translations[translation_id]['logs'].append(full_log_entry)
            emit_update(socketio, translation_id, {'log': message_content}, active_translations)

    def _update_translation_progress_callback(progress_percent):
        if translation_id in active_translations:
            if not active_translations[translation_id].get('interrupted', False):
                active_translations[translation_id]['progress'] = progress_percent
            emit_update(socketio, translation_id, {'progress': active_translations[translation_id]['progress']}, active_translations)

    def _update_translation_stats_callback(new_stats_dict):
        if translation_id in active_translations:
            if 'stats' not in active_translations[translation_id]: 
                active_translations[translation_id]['stats'] = {}
            current_stats = active_translations[translation_id]['stats']
            current_stats.update(new_stats_dict)
            
            current_stats['elapsed_time'] = time.time() - current_stats.get('start_time', time.time())
            emit_update(socketio, translation_id, {'stats': current_stats}, active_translations)

    try:
        _log_message_callback("config_info", f"🚀 Starting translation ({translation_id}). Config: {config['source_language']} to {config['target_language']}, Model: {config['model']}")
        _log_message_callback("llm_endpoint_info", f"🔗 LLM Endpoint: {config['llm_api_endpoint']}")
        _log_message_callback("output_file_info", f"💾 Expected output file: {config['output_filename']}")
        _log_message_callback("file_type_info", f"📄 File type: {config['file_type']}")

        output_filepath_on_server = os.path.join(output_dir, config['output_filename'])
        
        input_path_for_translate_module = config.get('file_path')
        
        if config['file_type'] == 'epub':
            if not input_path_for_translate_module:
                _log_message_callback("epub_error_no_path", "❌ EPUB translation requires a file path from upload.")
                raise Exception("EPUB translation requires a file_path.")
            
            await translate_epub_file(
                input_path_for_translate_module,
                output_filepath_on_server,
                config['source_language'],
                config['target_language'],
                config['model'],
                config['chunk_size'],
                config['llm_api_endpoint'],
                progress_callback=_update_translation_progress_callback,
                log_callback=_log_message_callback,
                stats_callback=_update_translation_stats_callback,
                check_interruption_callback=should_interrupt_current_task
            )
            active_translations[translation_id]['result'] = "[EPUB file translated - download to view]"
            
        elif config['file_type'] == 'txt':
            temp_txt_file_path = None
            if 'text' in config and input_path_for_translate_module is None:
                with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False, suffix=".txt", dir=output_dir) as tmp_f:
                    tmp_f.write(config['text'])
                    temp_txt_file_path = tmp_f.name
                input_path_for_translate_module = temp_txt_file_path

            if not input_path_for_translate_module:
                _log_message_callback("txt_error_no_input", "❌ TXT translation requires text content or a file path.")
                raise Exception("TXT translation input missing.")

            # Read and process text file
            try:
                with open(input_path_for_translate_module, 'r', encoding='utf-8') as f:
                    original_text = f.read()
            except Exception as e:
                err_msg = f"ERROR: Reading input file '{input_path_for_translate_module}': {e}"
                _log_message_callback("file_read_error", err_msg)
                raise Exception(err_msg)

            if _log_message_callback: 
                _log_message_callback("txt_split_start", f"Splitting text from '{config['source_language']}'...")

            structured_chunks = split_text_into_chunks_with_context(original_text, config['chunk_size'])
            total_chunks = len(structured_chunks)

            if _update_translation_stats_callback and total_chunks > 0:
                _update_translation_stats_callback({'total_chunks': total_chunks, 'completed_chunks': 0, 'failed_chunks': 0})

            if total_chunks == 0 and original_text.strip():
                warn_msg = "WARNING: No segments generated for non-empty text. Processing as a single block."
                _log_message_callback("txt_no_chunks_warning", warn_msg)
                structured_chunks = [{"context_before": "", "main_content": original_text, "context_after": ""}]
                total_chunks = 1
                if _update_translation_stats_callback: 
                    _update_translation_stats_callback({'total_chunks': 1, 'completed_chunks': 0, 'failed_chunks': 0})
            elif total_chunks == 0:
                info_msg = "Empty input file. No translation needed."
                _log_message_callback("txt_empty_input", info_msg)
                try:
                    with open(output_filepath_on_server, 'w', encoding='utf-8') as f: 
                        f.write("")
                    _log_message_callback("txt_empty_output_created", f"Empty output file '{output_filepath_on_server}' created.")
                except Exception as e:
                    err_msg = f"ERROR: Saving empty file '{output_filepath_on_server}': {e}"
                    _log_message_callback("txt_empty_save_error", err_msg)
                if _update_translation_progress_callback: 
                    _update_translation_progress_callback(100)
                return

            # Translate chunks
            translated_parts = await translate_chunks(
                structured_chunks,
                config['source_language'],
                config['target_language'],
                config['model'],
                config['llm_api_endpoint'],
                progress_callback=_update_translation_progress_callback,
                log_callback=_log_message_callback,
                stats_callback=_update_translation_stats_callback,
                check_interruption_callback=should_interrupt_current_task
            )

            # Save result
            final_translated_text = "\n".join(translated_parts)
            try:
                with open(output_filepath_on_server, 'w', encoding='utf-8') as f:
                    f.write(final_translated_text)
                success_msg = f"Full/Partial translation saved: '{output_filepath_on_server}'"
                _log_message_callback("txt_save_success", success_msg)
            except Exception as e:
                err_msg = f"ERROR: Saving output file '{output_filepath_on_server}': {e}"
                _log_message_callback("txt_save_error", err_msg)
                raise Exception(err_msg)

            if os.path.exists(output_filepath_on_server) and active_translations[translation_id].get('status') not in ['error', 'interrupted_before_save']:
                active_translations[translation_id]['result'] = "[TXT file translated - content available for download]"
            elif not os.path.exists(output_filepath_on_server):
                active_translations[translation_id]['result'] = "[TXT file (partially) translated - content not loaded for preview or write failed]"

            if temp_txt_file_path and os.path.exists(temp_txt_file_path):
                os.remove(temp_txt_file_path)
        else:
            _log_message_callback("unknown_file_type", f"❌ Unknown file type: {config['file_type']}")
            raise Exception(f"Unsupported file type: {config['file_type']}")

        _log_message_callback("save_process_info", f"💾 Translation process ended. File saved (or partially saved) at: {output_filepath_on_server}")
        active_translations[translation_id]['output_filepath'] = output_filepath_on_server

        elapsed_time = time.time() - active_translations[translation_id]['stats'].get('start_time', time.time())
        _update_translation_stats_callback({'elapsed_time': elapsed_time})

        final_status_payload = {
            'result': active_translations[translation_id]['result'],
            'output_filename': config['output_filename'],
            'file_type': config['file_type']
        }
        
        if active_translations[translation_id].get('interrupted', False):
            active_translations[translation_id]['status'] = 'interrupted'
            _log_message_callback("summary_interrupted", f"🛑 Translation interrupted by user. Partial result saved. Time: {elapsed_time:.2f}s.")
            final_status_payload['status'] = 'interrupted'
            final_status_payload['progress'] = active_translations[translation_id].get('progress', 0)

        elif active_translations[translation_id].get('status') != 'error':
            active_translations[translation_id]['status'] = 'completed'
            _log_message_callback("summary_completed", f"✅ Translation completed. Time: {elapsed_time:.2f}s.")
            final_status_payload['status'] = 'completed'
            _update_translation_progress_callback(100)
            final_status_payload['progress'] = 100
        else:
            _log_message_callback("summary_error_final", f"❌ Translation finished with errors. Time: {elapsed_time:.2f}s.")
            final_status_payload['status'] = 'error'
            final_status_payload['error'] = active_translations[translation_id].get('error', 'Unknown error during finalization.')
            final_status_payload['progress'] = active_translations[translation_id].get('progress', 0)
        
        if config['file_type'] == 'txt' or (config['file_type'] == 'epub' and active_translations[translation_id]['stats'].get('total_chunks', 0) > 0):
            final_stats = active_translations[translation_id]['stats']
            _log_message_callback("summary_stats_final", f"📊 Stats: {final_stats.get('completed_chunks', 0)} processed, {final_stats.get('failed_chunks', 0)} failed out of {final_stats.get('total_chunks', 0)} total segments/chunks.")
        
        emit_update(socketio, translation_id, final_status_payload, active_translations)

    except Exception as e:
        critical_error_msg = f"Critical error during translation task ({translation_id}): {str(e)}"
        _log_message_callback("critical_error_perform_task", critical_error_msg)
        print(f"!!! {critical_error_msg}")
        import traceback
        tb_str = traceback.format_exc()
        _log_message_callback("critical_error_perform_task_traceback", tb_str)
        print(tb_str)

        if translation_id in active_translations:
            active_translations[translation_id]['status'] = 'error'
            active_translations[translation_id]['error'] = critical_error_msg
            
            emit_update(socketio, translation_id, {
                'error': critical_error_msg, 
                'status': 'error',
                'result': active_translations[translation_id].get('result', f"Translation failed: {critical_error_msg}"),
                'progress': active_translations[translation_id].get('progress', 0)
            }, active_translations)


def start_translation_job(translation_id, config, active_translations, output_dir, socketio):
    """
    Start a translation job in a separate thread
    
    Args:
        translation_id (str): Translation job ID
        config (dict): Translation configuration
        active_translations (dict): Active translations dictionary
        output_dir (str): Output directory path
        socketio: SocketIO instance
    """
    thread = threading.Thread(
        target=run_translation_async_wrapper,
        args=(translation_id, config, active_translations, output_dir, socketio)
    )
    thread.daemon = True
    thread.start()