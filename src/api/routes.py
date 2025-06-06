"""
Flask routes for the translation API
"""
import os
import time
import requests
from flask import request, jsonify, send_from_directory
from datetime import datetime

from config import (
    API_ENDPOINT as DEFAULT_OLLAMA_API_ENDPOINT,
    DEFAULT_MODEL,
    MAIN_LINES_PER_CHUNK,
    REQUEST_TIMEOUT,
    OLLAMA_NUM_CTX
)


def configure_routes(app, active_translations, output_dir, start_translation_job):
    """Configure Flask routes"""
    
    @app.route('/')
    def serve_interface():
        interface_path = 'src/web/templates/translation_interface.html'
        if os.path.exists(interface_path):
            return send_from_directory('src/web/templates', 'translation_interface.html')
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
            'stats': {'start_time': time.time(), 'total_chunks': 0, 'completed_chunks': 0, 'failed_chunks': 0},
            'logs': [f"[{datetime.now().strftime('%H:%M:%S')}] Translation {translation_id} queued."],
            'result': None,
            'config': config,
            'interrupted': False,
            'output_filepath': None
        }

        start_translation_job(translation_id, config)

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
        file_type = "txt"
        if filename.endswith('.epub'):
            file_type = "epub"
        
        upload_dir = os.path.join(output_dir, 'uploads')
        if not os.path.exists(upload_dir):
            os.makedirs(upload_dir)
        
        timestamp = int(time.time() * 1000)
        safe_filename = f"{timestamp}_{os.path.basename(file.filename)}"
        file_path = os.path.join(upload_dir, safe_filename)
        
        try:
            file.save(file_path)
            file_size = os.path.getsize(file_path)

            return jsonify({
                "success": True, 
                "file_path": file_path, 
                "filename": file.filename,
                "file_type": file_type, 
                "size": file_size
            })
        
        except Exception as e:
            return jsonify({"error": f"Failed to save file: {str(e)}"}), 500

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
                server_filepath = os.path.join(output_dir, config_output_filename)
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

    @app.errorhandler(404)
    def route_not_found(error): 
        return jsonify({"error": "API Endpoint not found"}), 404
    
    @app.errorhandler(500)
    def internal_server_error(error):
        import traceback
        tb_str = traceback.format_exc()
        print(f"INTERNAL SERVER ERROR: {error}\nTRACEBACK:\n{tb_str}")
        return jsonify({"error": "Internal server error", "details": str(error)}), 500