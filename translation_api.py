import requests
import os
import asyncio
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from flask_socketio import SocketIO, emit
import threading
import time
from datetime import datetime
import tempfile

try:
    from translate import (
        translate_epub_file,
        translate_text_file_with_callbacks,
        API_ENDPOINT as DEFAULT_OLLAMA_API_ENDPOINT,
        DEFAULT_MODEL,
        MAIN_LINES_PER_CHUNK,
        REQUEST_TIMEOUT,
        OLLAMA_NUM_CTX
    )
    print("✅ 'translate' module imported successfully")
except ImportError as e:
    print("❌ Error importing 'translate' module:")
    print(f"   {e}")
    print("   Ensure 'translate.py' is in the same folder or 'translate_text_file' is named 'translate_text_file_with_callbacks'")
    exit(1)

app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

active_translations = {}
OUTPUT_DIR = "translated_files"

try:
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
    print(f"✅ Output folder '{OUTPUT_DIR}' is ready.")
except OSError as e:
    print(f"❌ Critical error: Unable to create output folder '{OUTPUT_DIR}': {e}")

@app.route('/')
def serve_interface():
    if os.path.exists('translation_interface.html'):
        return send_from_directory('.', 'translation_interface.html')
    return "<h1>Error: Interface not found</h1>", 404

@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({
        "status": "ok",
        "message": "Translation API is running",
        "translate_module": "loaded",
        "ollama_default_endpoint": DEFAULT_OLLAMA_API_ENDPOINT,
        "supported_formats": ["txt", "epub"]
    })

@app.route('/api/models', methods=['GET'])
def get_available_models():
    ollama_base_from_ui = request.args.get('api_endpoint', DEFAULT_OLLAMA_API_ENDPOINT)
    try:
        base_url = ollama_base_from_ui.split('/api/')[0]
        tags_url = f"{base_url}/api/tags"
        response = requests.get(tags_url, timeout=5)

        if response.status_code == 200:
            data = response.json()
            models_data = data.get('models', [])
            model_names = [m.get('name') for m in models_data if m.get('name')]

            return jsonify({
                "models": model_names,
                "default": DEFAULT_MODEL if DEFAULT_MODEL in model_names else (model_names[0] if model_names else DEFAULT_names[0]),
                "status": "ollama_connected",
                "count": len(model_names)
            })
    except requests.exceptions.RequestException as e:
        print(f"❌ Could not connect to Ollama at {ollama_base_from_ui}: {e}")
    except Exception as e:
        print(f"❌ Error retrieving models from {ollama_base_from_ui}: {e}")

    return jsonify({
        "models": [],
        "default": DEFAULT_MODEL,
        "status": "ollama_offline_or_error",
        "count": 0,
        "error": f"Ollama is not accessible at {ollama_base_from_ui} or an error occurred. Verify that Ollama is running ('ollama serve') and the endpoint is correct."
    })

@app.route('/api/config', methods=['GET'])
def get_default_config():
    return jsonify({
        "api_endpoint": DEFAULT_OLLAMA_API_ENDPOINT,
        "default_model": DEFAULT_MODEL,
        "chunk_size": MAIN_LINES_PER_CHUNK,
        "timeout": REQUEST_TIMEOUT,
        "context_window": OLLAMA_NUM_CTX,
        "max_attempts": 2,
        "retry_delay": 2,
        "supported_formats": ["txt", "epub"]
    })

@app.route('/api/translate', methods=['POST'])
def start_translation_request():
    data = request.json

    if 'file_path' in data:
        required_fields = ['file_path', 'source_language', 'target_language', 'model', 'api_endpoint', 'output_filename', 'file_type']
    else:
        required_fields = ['text', 'source_language', 'target_language', 'model', 'api_endpoint', 'output_filename']
    
    for field in required_fields:
        if field not in data or (isinstance(data[field], str) and not data[field].strip()) or (not isinstance(data[field], str) and data[field] is None):
             if field == 'text' and data.get('file_type') == 'txt' and data.get('text') == "":
                 pass
             else:
                 return jsonify({"error": f"Missing or empty field: {field}"}), 400


    translation_id = f"trans_{int(time.time() * 1000)}"

    config = {
        'source_language': data['source_language'],
        'target_language': data['target_language'],
        'model': data['model'],
        'chunk_size': int(data.get('chunk_size', MAIN_LINES_PER_CHUNK)),
        'llm_api_endpoint': data['api_endpoint'],
        'request_timeout': int(data.get('timeout', REQUEST_TIMEOUT)),
        'context_window': int(data.get('context_window', OLLAMA_NUM_CTX)),
        'max_attempts': int(data.get('max_attempts', 2)),
        'retry_delay': int(data.get('retry_delay', 2)),
        'output_filename': data['output_filename']
    }

    if 'file_path' in data:
        config['file_path'] = data['file_path']
        config['file_type'] = data['file_type']
    else:
        config['text'] = data['text']
        config['file_type'] = data.get('file_type', 'txt')

    active_translations[translation_id] = {
        'status': 'queued',
        'progress': 0,
        'stats': { 'start_time': time.time(), 'total_chunks': 0, 'completed_chunks': 0, 'failed_chunks': 0 },
        'logs': [f"[{datetime.now().strftime('%H:%M:%S')}] Translation {translation_id} queued."],
        'result': None,
        'config': config,
        'interrupted': False,
        'output_filepath': None
    }

    thread = threading.Thread(
        target=run_translation_async_wrapper,
        args=(translation_id, config)
    )
    thread.daemon = True
    thread.start()

    return jsonify({
        "translation_id": translation_id,
        "message": "Translation queued.",
        "config_received": config
    })

@app.route('/api/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    
    filename = file.filename.lower()
    if not (filename.endswith('.txt') or filename.endswith('.epub')):
        return jsonify({"error": "Only .txt and .epub files are supported"}), 400
    
    upload_dir = os.path.join(OUTPUT_DIR, 'uploads')
    if not os.path.exists(upload_dir):
        os.makedirs(upload_dir)
    
    timestamp = int(time.time() * 1000)
    safe_filename = f"{timestamp}_{os.path.basename(file.filename)}"
    file_path = os.path.join(upload_dir, safe_filename)
    
    try:
        file.save(file_path)
        file_size = os.path.getsize(file_path)

        if filename.endswith('.txt'):
            return jsonify({
                "success": True, "file_path": file_path, "filename": file.filename,
                "file_type": "txt", "size": file_size
            })
        else:
            return jsonify({
                "success": True, "file_path": file_path, "filename": file.filename,
                "file_type": "epub", "size": file_size
            })
    
    except Exception as e:
        return jsonify({"error": f"Failed to save file: {str(e)}"}), 500


def run_translation_async_wrapper(translation_id, config):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(perform_actual_translation(translation_id, config))
    except Exception as e:
        error_msg = f"Uncaught major error in translation wrapper {translation_id}: {str(e)}"
        print(error_msg)
        if translation_id in active_translations:
            active_translations[translation_id]['status'] = 'error'
            active_translations[translation_id]['error'] = error_msg
            if 'logs' not in active_translations[translation_id]: active_translations[translation_id]['logs'] = []
            active_translations[translation_id]['logs'].append(f"[{datetime.now().strftime('%H:%M:%S')}] CRITICAL WRAPPER ERROR: {error_msg}")
            emit_update(translation_id, {'error': error_msg, 'status': 'error', 'log': f"CRITICAL WRAPPER ERROR: {error_msg}"})
    finally:
        loop.close()

async def perform_actual_translation(translation_id, config):
    if translation_id not in active_translations:
        print(f"Critical error: {translation_id} not found in active_translations.")
        return

    active_translations[translation_id]['status'] = 'running'
    emit_update(translation_id, {'status': 'running', 'log': 'Translation task started by worker.'})

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
            if 'logs' not in active_translations[translation_id]: active_translations[translation_id]['logs'] = []
            active_translations[translation_id]['logs'].append(full_log_entry)
            emit_update(translation_id, {'log': message_content})

    def _update_translation_progress_callback(progress_percent):
        if translation_id in active_translations:
            if not active_translations[translation_id].get('interrupted', False):
                active_translations[translation_id]['progress'] = progress_percent
            emit_update(translation_id, {'progress': active_translations[translation_id]['progress']})


    def _update_translation_stats_callback(new_stats_dict):
        if translation_id in active_translations:
            if 'stats' not in active_translations[translation_id]: active_translations[translation_id]['stats'] = {}
            current_stats = active_translations[translation_id]['stats']
            current_stats.update(new_stats_dict)
            
            current_stats['elapsed_time'] = time.time() - current_stats.get('start_time', time.time())
            emit_update(translation_id, {'stats': current_stats})


    try:
        _log_message_callback("config_info", f"🚀 Starting translation ({translation_id}). Config: {config['source_language']} to {config['target_language']}, Model: {config['model']}")
        _log_message_callback("llm_endpoint_info", f"🔗 LLM Endpoint: {config['llm_api_endpoint']}")
        _log_message_callback("output_file_info", f"💾 Expected output file: {config['output_filename']}")
        _log_message_callback("file_type_info", f"📄 File type: {config['file_type']}")

        output_filepath_on_server = os.path.join(OUTPUT_DIR, config['output_filename'])
        
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
                with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False, suffix=".txt", dir=OUTPUT_DIR) as tmp_f:
                    tmp_f.write(config['text'])
                    temp_txt_file_path = tmp_f.name
                input_path_for_translate_module = temp_txt_file_path

            if not input_path_for_translate_module:
                _log_message_callback("txt_error_no_input", "❌ TXT translation requires text content or a file path.")
                raise Exception("TXT translation input missing.")

            await translate_text_file_with_callbacks(
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

            if os.path.exists(output_filepath_on_server) and active_translations[translation_id].get('status') not in ['error', 'interrupted_before_save']: # Assuming a status if save fails
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
        
        if config['file_type'] == 'txt' or (config['file_type'] == 'epub' and active_translations[translation_id]['stats'].get('total_chunks',0) > 0):
            final_stats = active_translations[translation_id]['stats']
            _log_message_callback("summary_stats_final", f"📊 Stats: {final_stats.get('completed_chunks',0)} processed, {final_stats.get('failed_chunks',0)} failed out of {final_stats.get('total_chunks',0)} total segments/chunks.")
        
        emit_update(translation_id, final_status_payload)

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
            
            emit_update(translation_id, {
                'error': critical_error_msg, 'status': 'error',
                'result': active_translations[translation_id].get('result', f"Translation failed: {critical_error_msg}"),
                'progress': active_translations[translation_id].get('progress', 0)
            })

def emit_update(translation_id, data_to_emit):
    if translation_id in active_translations:
        data_to_emit['translation_id'] = translation_id
        try:
            if 'stats' not in data_to_emit and 'stats' in active_translations[translation_id]:
                data_to_emit['stats'] = active_translations[translation_id]['stats']

            if 'progress' not in data_to_emit and 'progress' in active_translations[translation_id]:
                 data_to_emit['progress'] = active_translations[translation_id]['progress']

            socketio.emit('translation_update', data_to_emit, namespace='/')
        except Exception as e:
            print(f"WebSocket emission error for {translation_id}: {e}")


@app.route('/api/translation/<translation_id>', methods=['GET'])
def get_translation_job_status(translation_id):
    if translation_id not in active_translations:
        return jsonify({"error": "Translation not found"}), 404
    
    job_data = active_translations[translation_id]
    stats = job_data.get('stats', {'start_time': time.time(), 'total_chunks': 0, 'completed_chunks': 0, 'failed_chunks': 0})
    
    if job_data.get('status') == 'running' or job_data.get('status') == 'queued':
        elapsed = time.time() - stats.get('start_time', time.time())
    else:
        elapsed = stats.get('elapsed_time', time.time() - stats.get('start_time', time.time()))

    return jsonify({
        "translation_id": translation_id,
        "status": job_data.get('status'),
        "progress": job_data.get('progress'),
        "stats": {
            'total_chunks': stats.get('total_chunks', 0),
            'completed_chunks': stats.get('completed_chunks', 0),
            'failed_chunks': stats.get('failed_chunks', 0),
            'start_time': stats.get('start_time'),
            'elapsed_time': elapsed
        },
        "logs": job_data.get('logs', [])[-100:],
        "result_preview": "[Preview functionality removed. Download file to view content.]" if job_data.get('status') in ['completed', 'interrupted'] else None,
        "error": job_data.get('error'),
        "config": job_data.get('config'),
        "output_filepath": job_data.get('output_filepath')
    })

@app.route('/api/translation/<translation_id>/interrupt', methods=['POST'])
def interrupt_translation_job(translation_id):
    if translation_id not in active_translations:
        return jsonify({"error": "Translation not found"}), 404
    job = active_translations[translation_id]
    if job.get('status') == 'running' or job.get('status') == 'queued':
        job['interrupted'] = True

        emit_update(translation_id, {'log': '🛑 Interruption signal received by the server. Processing will halt after current segment.'})
        return jsonify({"message": "Interruption signal sent. Translation will stop after the current segment."}), 200
    return jsonify({"message": "The translation is not in an interruptible state (e.g., already completed or failed)."}), 400

@app.route('/api/download/<translation_id>', methods=['GET'])
def download_translated_output_file(translation_id):
    if translation_id not in active_translations:
        return jsonify({"error": "Translation ID not found."}), 404
    
    job_data = active_translations[translation_id]
    server_filepath = job_data.get('output_filepath')

    if not server_filepath:
        config_output_filename = job_data.get('config', {}).get('output_filename')
        if config_output_filename:
            server_filepath = os.path.join(OUTPUT_DIR, config_output_filename)
        else:
            return jsonify({"error": "Output filename configuration missing."}), 404
            
    if not os.path.exists(server_filepath):
        print(f"Download error: File '{server_filepath}' for TID {translation_id} not found on server.")
        return jsonify({"error": f"File '{os.path.basename(server_filepath)}' not found. It might have failed, been interrupted before saving, or been cleaned up."}), 404
    
    try:
        directory = os.path.abspath(os.path.dirname(server_filepath))
        filename = os.path.basename(server_filepath)
        return send_from_directory(directory, filename, as_attachment=True)
    except Exception as e:
        print(f"Error sending file '{server_filepath}' for {translation_id}: {e}")
        return jsonify({"error": f"Server error during download preparation: {str(e)}"}), 500

@app.route('/api/translations', methods=['GET'])
def list_all_translations():
    summary_list = []
    for tid, data in active_translations.items():
        summary_list.append({
            "translation_id": tid,
            "status": data.get('status'),
            "progress": data.get('progress'),
            "start_time": data.get('stats', {}).get('start_time'),
            "output_filename": data.get('config', {}).get('output_filename'),
            "file_type": data.get('config', {}).get('file_type', 'txt')
        })
    return jsonify({"translations": sorted(summary_list, key=lambda x: x.get('start_time', 0), reverse=True)})


@socketio.on('connect')
def handle_websocket_connect():
    print(f'🔌 WebSocket client connected: {request.sid}')
    emit('connected', {'message': 'Connected to translation server via WebSocket'})

@socketio.on('disconnect')
def handle_websocket_disconnect():
    print(f'🔌 WebSocket client disconnected: {request.sid}')


@app.errorhandler(404)
def route_not_found(error): return jsonify({"error": "API Endpoint not found"}), 404
@app.errorhandler(500)
def internal_server_error(error):
    import traceback
    tb_str = traceback.format_exc()
    print(f"INTERNAL SERVER ERROR: {error}\nTRACEBACK:\n{tb_str}")
    return jsonify({"error": "Internal server error", "details": str(error)}), 500


if __name__ == '__main__':
    print("\n" + "="*60 + f"\n🚀 LLM TRANSLATION SERVER (Version {datetime.now().strftime('%Y%m%d-%H%M')})\n" + "="*60)
    print(f"   - Default Ollama Endpoint (translate.py): {DEFAULT_OLLAMA_API_ENDPOINT}")
    print(f"   - Interface: http://localhost:5000 (or http://<your_ip>:5000)")
    print(f"   - API: http://localhost:5000/api/")
    print(f"   - Supported formats: .txt and .epub")
    print("\n💡 Press Ctrl+C to stop the server\n")
    socketio.run(app, debug=False, host='0.0.0.0', port=5000)