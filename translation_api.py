"""
Flask API for the Translation Interface
Works with translate.py - Now supports EPUB files
"""

import json
import requests
import os
import asyncio
import re
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from flask_socketio import SocketIO, emit
import threading
import time
from datetime import datetime
import tempfile
import zipfile

# Import the original translation script
try:
    from translate import (
        split_text_into_chunks_with_context,
        generate_translation_request,
        translate_epub_file,
        translate_text_file,
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
    print("   Ensure 'translate.py' is in the same folder")
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
                "default": DEFAULT_MODEL if DEFAULT_MODEL in model_names else (model_names[0] if model_names else DEFAULT_MODEL),
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

    # For file uploads, handle differently
    if 'file_path' in data:
        # This is a file-based translation request
        required_fields = ['file_path', 'source_language', 'target_language', 'model', 'api_endpoint', 'output_filename', 'file_type']
    else:
        # This is a text-based translation request
        required_fields = ['text', 'source_language', 'target_language', 'model', 'api_endpoint', 'output_filename']
    
    for field in required_fields:
        if field not in data or not data[field]:
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

    # Handle file type
    if 'file_path' in data:
        config['file_path'] = data['file_path']
        config['file_type'] = data['file_type']
    else:
        config['text'] = data['text']
        config['file_type'] = 'txt'

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
    """Handle file uploads and store them temporarily"""
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    
    # Check file extension
    filename = file.filename.lower()
    if not (filename.endswith('.txt') or filename.endswith('.epub')):
        return jsonify({"error": "Only .txt and .epub files are supported"}), 400
    
    # Create a temporary directory for uploads if it doesn't exist
    upload_dir = os.path.join(OUTPUT_DIR, 'uploads')
    if not os.path.exists(upload_dir):
        os.makedirs(upload_dir)
    
    # Save the file with a unique name
    timestamp = int(time.time() * 1000)
    safe_filename = f"{timestamp}_{file.filename}"
    file_path = os.path.join(upload_dir, safe_filename)
    
    try:
        file.save(file_path)
        
        # For text files, read content
        if filename.endswith('.txt'):
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            return jsonify({
                "success": True,
                "file_path": file_path,
                "filename": file.filename,
                "file_type": "txt",
                "content": content,
                "size": os.path.getsize(file_path)
            })
        else:
            # For EPUB files, just return the path
            return jsonify({
                "success": True,
                "file_path": file_path,
                "filename": file.filename,
                "file_type": "epub",
                "size": os.path.getsize(file_path)
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
            if 'logs' not in active_translations[translation_id]:
                active_translations[translation_id]['logs'] = []
            active_translations[translation_id]['logs'].append(f"[{datetime.now().strftime('%H:%M:%S')}] CRITICAL WRAPPER ERROR: {error_msg}")
            emit_update(translation_id, {'error': error_msg, 'status': 'error', 'log': f"CRITICAL WRAPPER ERROR: {error_msg}"})
    finally:
        loop.close()

async def perform_actual_translation(translation_id, config):
    if translation_id not in active_translations:
        print(f"Critical error: {translation_id} not found in active_translations at the start of perform_actual_translation.")
        return

    active_translations[translation_id]['status'] = 'running'
    emit_update(translation_id, {'status': 'running', 'log': 'Translation task started by worker.'})

    def log_message(message_key, message_content=""):
        timestamp = datetime.now().strftime('%H:%M:%S')
        full_log_entry = f"[{timestamp}] {message_content}"

        if 'logs' not in active_translations[translation_id]:
            active_translations[translation_id]['logs'] = []
        active_translations[translation_id]['logs'].append(full_log_entry)

        emit_update(translation_id, {'log': message_content})

    def update_translation_progress(progress_percent):
        if translation_id in active_translations:
            active_translations[translation_id]['progress'] = progress_percent
            emit_update(translation_id, {'progress': progress_percent})

    def update_translation_stats(new_stats):
        if translation_id in active_translations:
            if 'stats' not in active_translations[translation_id]:
                 active_translations[translation_id]['stats'] = {}
            active_translations[translation_id]['stats'].update(new_stats)
            emit_update(translation_id, {'stats': active_translations[translation_id]['stats']})

    try:
        log_message("config_info", f"🚀 Starting translation ({translation_id}). Configuration: {config['source_language']} to {config['target_language']}, Model: {config['model']}")
        log_message("llm_endpoint_info", f"🔗 LLM Endpoint: {config['llm_api_endpoint']}")
        log_message("output_file_info", f"💾 Expected output file: {config['output_filename']}")
        log_message("file_type_info", f"📄 File type: {config['file_type']}")

        output_filepath_on_server = os.path.join(OUTPUT_DIR, config['output_filename'])

        # Handle different file types
        if config['file_type'] == 'epub':
            # For EPUB files, use the translate_epub_file function
            log_message("epub_processing", "📚 Processing EPUB file...")
            
            # Create a temporary file for the input if text content is provided
            if 'file_path' in config:
                input_path = config['file_path']
            else:
                # This shouldn't happen for EPUB, but handle it gracefully
                log_message("epub_error", "❌ EPUB translation requires a file path")
                raise Exception("EPUB translation requires a file path")
            
            # Use the translate_epub_file function
            await translate_epub_file(
                input_path,
                output_filepath_on_server,
                config['source_language'],
                config['target_language'],
                config['model'],
                config['chunk_size'],
                config['llm_api_endpoint']
            )
            
            # For EPUB, we can't easily extract the result text
            active_translations[translation_id]['result'] = "[EPUB file translated - download to view]"
            
        else:
            # For text files, use the existing logic
            if 'text' in config:
                text_to_translate = config['text']
            elif 'file_path' in config:
                with open(config['file_path'], 'r', encoding='utf-8') as f:
                    text_to_translate = f.read()
            else:
                raise Exception("No text or file path provided")
            
            # Use the existing text translation logic
            structured_chunks = split_text_into_chunks_with_context(text_to_translate, config['chunk_size'])
            total_chunks = len(structured_chunks)

            current_stats = active_translations[translation_id].get('stats', {})
            current_stats.update({'total_chunks': total_chunks, 'completed_chunks': 0, 'failed_chunks': 0})
            update_translation_stats(current_stats)

            if total_chunks == 0 and text_to_translate.strip():
                log_message("chunking_warn", "⚠️ Non-empty text but no chunks generated. Attempting global translation.")
                structured_chunks.append({ "context_before": "", "main_content": text_to_translate, "context_after": "" })
                total_chunks = 1
                update_translation_stats({'total_chunks': total_chunks})
            elif total_chunks == 0:
                log_message("empty_text", "Empty input text. No translation needed.")
                active_translations[translation_id]['status'] = 'completed'
                active_translations[translation_id]['result'] = ""
                update_translation_progress(100)
                emit_update(translation_id, {'status': 'completed', 'result': "", 'output_filename': config['output_filename']})
                
                with open(output_filepath_on_server, 'w', encoding='utf-8') as f:
                    f.write("")
                active_translations[translation_id]['output_filepath'] = output_filepath_on_server
                return

            log_message("chunk_count", f"📊 Text divided into {total_chunks} chunks.")
            
            full_translation_parts = []
            last_successful_translation_context = ""

            for i, chunk_data in enumerate(structured_chunks):
                if active_translations[translation_id].get('interrupted', False):
                    log_message("interruption_detected_loop", "🛑 Interruption detected. Stopping before the next chunk.")
                    break
                
                chunk_num = i + 1
                update_translation_progress((i / total_chunks) * 100)
                main_content = chunk_data["main_content"]

                if not main_content.strip():
                    log_message("chunk_skip", f"⏭️ Chunk {chunk_num}/{total_chunks}: Empty, skipped.")
                    full_translation_parts.append("")
                    current_stats = active_translations[translation_id]['stats'] 
                    current_stats['completed_chunks'] = current_stats.get('completed_chunks', 0) + 1
                    update_translation_stats(current_stats)
                    continue

                log_message("chunk_process_start", f"🔄 Translating chunk {chunk_num}/{total_chunks}...")
                translated_chunk_text = None
                current_attempts = 0
                
                while current_attempts < config['max_attempts'] and translated_chunk_text is None:
                    current_attempts += 1
                    if current_attempts > 1:
                        log_message("chunk_retry", f"🔁 Retrying chunk {chunk_num} ({current_attempts}/{config['max_attempts']})...")
                        await asyncio.sleep(config['retry_delay'])
                    
                    translated_chunk_text = await generate_translation_request(
                        main_content, chunk_data["context_before"], chunk_data["context_after"],
                        last_successful_translation_context, config['source_language'], config['target_language'],
                        config['model'], api_endpoint_param=config['llm_api_endpoint']
                    )

                current_stats = active_translations[translation_id]['stats']
                if translated_chunk_text is not None:
                    full_translation_parts.append(translated_chunk_text)
                    last_successful_translation_context = translated_chunk_text
                    current_stats['completed_chunks'] = current_stats.get('completed_chunks', 0) + 1
                    update_translation_stats(current_stats)
                    log_message("chunk_success", f"✅ Chunk {chunk_num} translated.")
                else:
                    error_placeholder = f"[TRANSLATION ERROR CHUNK {chunk_num} AFTER {config['max_attempts']} ATTEMPTS]\n{main_content}\n[END CHUNK ERROR {chunk_num}]"
                    full_translation_parts.append(error_placeholder)
                    last_successful_translation_context = ""
                    current_stats['failed_chunks'] = current_stats.get('failed_chunks', 0) + 1
                    update_translation_stats(current_stats)
                    log_message("chunk_fail", f"❌ Failed to translate chunk {chunk_num} after {config['max_attempts']} attempts.")
            
            # Assembly and Saving for text files
            final_translation_result = "\n".join(full_translation_parts)
            active_translations[translation_id]['result'] = final_translation_result
            
            with open(output_filepath_on_server, 'w', encoding='utf-8') as f:
                f.write(final_translation_result)

        # Common finalization for both file types
        log_message("save_success", f"💾 Result saved: {output_filepath_on_server}")
        active_translations[translation_id]['output_filepath'] = output_filepath_on_server

        # Finalizing status
        elapsed_time = time.time() - active_translations[translation_id]['stats'].get('start_time', time.time())
        update_translation_stats({'elapsed_time': elapsed_time})

        final_status_payload = {
            'result': active_translations[translation_id]['result'],
            'output_filename': config['output_filename'],
            'file_type': config['file_type']
        }
        
        current_job_status = active_translations[translation_id].get('status', 'unknown')

        if active_translations[translation_id].get('interrupted', False):
            active_translations[translation_id]['status'] = 'interrupted'
            log_message("summary_interrupted", f"🛑 Translation interrupted. Partial result saved. Time: {elapsed_time:.2f}s.")
            final_status_payload['status'] = 'interrupted'
        elif current_job_status != 'error':
             active_translations[translation_id]['status'] = 'completed'
             log_message("summary_completed", f"✅ Translation completed. Time: {elapsed_time:.2f}s.")
             final_status_payload['status'] = 'completed'
        else:
            log_message("summary_error", f"❌ Translation completed with errors. Time: {elapsed_time:.2f}s.")
            final_status_payload['status'] = 'error'
            final_status_payload['error'] = active_translations[translation_id].get('error', 'Unknown error during finalization.')

        update_translation_progress(100)
        
        if config['file_type'] == 'txt':
            completed_chunks_final = active_translations[translation_id]['stats'].get('completed_chunks', 0)
            failed_chunks_final = active_translations[translation_id]['stats'].get('failed_chunks', 0)
            total_chunks = active_translations[translation_id]['stats'].get('total_chunks', 0)
            log_message("summary_stats", f"📊 Chunks: {completed_chunks_final} processed (successful/skipped), {failed_chunks_final} failed out of {total_chunks} total.")
        
        emit_update(translation_id, final_status_payload)

    except Exception as e:
        critical_error_msg = f"Critical error during translation ({translation_id}): {str(e)}"
        log_message("critical_error_perform", critical_error_msg)
        if translation_id in active_translations:
            active_translations[translation_id]['status'] = 'error'
            active_translations[translation_id]['error'] = critical_error_msg
            
            emit_update(translation_id, {
                'error': critical_error_msg,
                'status': 'error',
                'result': active_translations[translation_id].get('result')
            })

def emit_update(translation_id, data_to_emit):
    if translation_id in active_translations:
        data_to_emit['translation_id'] = translation_id
        try:
            socketio.emit('translation_update', data_to_emit, namespace='/')
        except Exception as e:
            print(f"WebSocket emission error for {translation_id}: {e}")

@app.route('/api/translation/<translation_id>', methods=['GET'])
def get_translation_job_status(translation_id):
    if translation_id not in active_translations:
        return jsonify({"error": "Translation not found"}), 404
    job_data = active_translations[translation_id]
    stats = job_data.get('stats', {})
    elapsed = time.time() - stats.get('start_time', time.time()) if 'start_time' in stats else 0
    
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
        "result_preview": (job_data.get('result')[:1000] + '...' if len(job_data.get('result', '')) > 1000 else job_data.get('result')) if job_data.get('result') else None,
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
        emit_update(translation_id, {'log': '🛑 Interruption signal received by the server.'})
        return jsonify({"message": "Interruption signal sent and being processed."}), 200
    return jsonify({"message": "The translation is not in an interruptible state (already completed, failed, or interrupted)."}), 400

@app.route('/api/download/<translation_id>', methods=['GET'])
def download_translated_output_file(translation_id):
    if translation_id not in active_translations:
        return jsonify({"error": "Translation ID not found."}), 404
    job_data = active_translations[translation_id]
    server_filepath = job_data.get('output_filepath')

    if not server_filepath or not os.path.exists(server_filepath):
        config_output_filename = job_data.get('config', {}).get('output_filename')
        if config_output_filename:
            potential_path = os.path.join(OUTPUT_DIR, config_output_filename)
            if os.path.exists(potential_path): server_filepath = potential_path
            else: return jsonify({"error": f"File '{config_output_filename}' not found on the server."}), 404
        else: return jsonify({"error": "Translation file path not available or file does not exist."}), 404
    
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
def internal_server_error(error): return jsonify({"error": "Internal server error", "details": str(error)}), 500

if __name__ == '__main__':
    print("\n" + "="*60 + f"\n🚀 LLM TRANSLATION SERVER (Version {datetime.now().strftime('%Y%m%d-%H%M')})\n" + "="*60)
    print(f"   - Default Ollama Endpoint (translate.py): {DEFAULT_OLLAMA_API_ENDPOINT}")
    print(f"   - Interface: http://localhost:5000 (or http://<your_ip>:5000)")
    print(f"   - API: http://localhost:5000/api/")
    print(f"   - Supported formats: .txt and .epub")
    print("\n💡 Press Ctrl+C to stop the server\n")
    socketio.run(app, debug=False, host='0.0.0.0', port=5000)