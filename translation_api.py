"""
API Flask pour l'interface de traduction
Fonctionne avec translate.py
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

# Import du script de traduction original
try:
    from translate import (
        split_text_into_chunks_with_context,
        generate_translation_request,
        API_ENDPOINT as DEFAULT_OLLAMA_API_ENDPOINT, 
        DEFAULT_MODEL,
        MAIN_LINES_PER_CHUNK,
        REQUEST_TIMEOUT, 
        OLLAMA_NUM_CTX 
    )
    print("✅ Module 'translate' importé avec succès")
except ImportError as e:
    print("❌ Erreur lors de l'import du module 'translate':")
    print(f"   {e}")
    print("   Assurez-vous que 'translate.py' est dans le même dossier")
    exit(1)

app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

active_translations = {}
OUTPUT_DIR = "translated_files"

try:
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
    print(f"✅ Dossier de sortie '{OUTPUT_DIR}' est prêt.")
except OSError as e:
    print(f"❌ Erreur critique: Impossible de créer le dossier de sortie '{OUTPUT_DIR}': {e}")

@app.route('/')
def serve_interface():
    if os.path.exists('translation_interface.html'):
        return send_from_directory('.', 'translation_interface.html')
    return "<h1>Erreur: Interface non trouvée</h1>", 404

@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({
        "status": "ok",
        "message": "Translation API is running",
        "translate_module": "loaded",
        "ollama_default_endpoint": DEFAULT_OLLAMA_API_ENDPOINT
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
    except requests.exceptions.RequestException as e: # More specific exception for connection errors
        print(f"❌ Impossible de se connecter à Ollama à {ollama_base_from_ui}: {e}")
    except Exception as e:
        print(f"❌ Erreur lors de la récupération des modèles depuis {ollama_base_from_ui}: {e}")
    
    return jsonify({
        "models": [],
        "default": DEFAULT_MODEL,
        "status": "ollama_offline_or_error",
        "count": 0,
        "error": f"Ollama n'est pas accessible à {ollama_base_from_ui} ou une erreur est survenue. Vérifiez que Ollama est lancé ('ollama serve') et que l'endpoint est correct."
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
        "retry_delay": 2 
    })

@app.route('/api/translate', methods=['POST'])
def start_translation_request():
    data = request.json
    
    required_fields = ['text', 'source_language', 'target_language', 'model', 'api_endpoint', 'output_filename']
    for field in required_fields:
        if field not in data or not data[field]:
            return jsonify({"error": f"Champ manquant ou vide: {field}"}), 400
    
    translation_id = f"trans_{int(time.time() * 1000)}"
    
    config = {
        'text': data['text'],
        'source_language': data['source_language'],
        'target_language': data['target_language'],
        'model': data['model'],
        'chunk_size': int(data.get('chunk_size', MAIN_LINES_PER_CHUNK)),
        'llm_api_endpoint': data['api_endpoint'],
        'request_timeout': int(data.get('timeout', REQUEST_TIMEOUT)),
        'context_window': int(data.get('context_window', OLLAMA_NUM_CTX)),
        'max_attempts': int(data.get('max_attempts', 2)),
        'retry_delay': int(data.get('retry_delay', 2)),
        'output_filename': data['output_filename'] # Now required
    }
    
    active_translations[translation_id] = {
        'status': 'queued', # Initial status before thread picks it up
        'progress': 0,
        'stats': { 'start_time': time.time(), 'total_chunks': 0, 'completed_chunks': 0, 'failed_chunks': 0 },
        'logs': [f"[{datetime.now().strftime('%H:%M:%S')}] Traduction {translation_id} mise en file d'attente."],
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
        "message": "Traduction mise en file d'attente.",
        "config_received": config 
    })

def run_translation_async_wrapper(translation_id, config):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(perform_actual_translation(translation_id, config))
    except Exception as e:
        error_msg = f"Erreur majeure non interceptée dans le wrapper de traduction {translation_id}: {str(e)}"
        print(error_msg) # Server log
        if translation_id in active_translations:
            active_translations[translation_id]['status'] = 'error'
            active_translations[translation_id]['error'] = error_msg
            # Ensure logs list exists before appending
            if 'logs' not in active_translations[translation_id]:
                active_translations[translation_id]['logs'] = []
            active_translations[translation_id]['logs'].append(f"[{datetime.now().strftime('%H:%M:%S')}] CRITICAL WRAPPER ERROR: {error_msg}")
            emit_update(translation_id, {'error': error_msg, 'status': 'error', 'log': f"CRITICAL WRAPPER ERROR: {error_msg}"})
    finally:
        loop.close()

async def perform_actual_translation(translation_id, config):
    # Ensure the job entry exists; it should have been created in start_translation_request
    if translation_id not in active_translations:
        print(f"Erreur critique: {translation_id} non trouvé dans active_translations au début de perform_actual_translation.")
        return

    active_translations[translation_id]['status'] = 'running'
    emit_update(translation_id, {'status': 'running', 'log': 'Tâche de traduction démarrée par le worker.'})

    def log_message(message_key, message_content=""): # message_key can be specific like 'chunk_progress'
        timestamp = datetime.now().strftime('%H:%M:%S')
        full_log_entry = f"[{timestamp}] {message_content}"
        
        # Ensure logs list exists
        if 'logs' not in active_translations[translation_id]:
            active_translations[translation_id]['logs'] = []
        active_translations[translation_id]['logs'].append(full_log_entry)
        
        # Emit only the content for cleaner UI logs
        emit_update(translation_id, {'log': message_content})


    def update_translation_progress(progress_percent):
        if translation_id in active_translations:
            active_translations[translation_id]['progress'] = progress_percent
            emit_update(translation_id, {'progress': progress_percent})

    def update_translation_stats(new_stats):
        if translation_id in active_translations:
            if 'stats' not in active_translations[translation_id]: # Should not happen if initialized correctly
                 active_translations[translation_id]['stats'] = {}
            active_translations[translation_id]['stats'].update(new_stats)
            emit_update(translation_id, {'stats': active_translations[translation_id]['stats']})

    full_translation_parts = []
    
    try:
        log_message("config_info", f"🚀 Début de la traduction ({translation_id}). Configuration: {config['source_language']} vers {config['target_language']}, Modèle: {config['model']}")
        log_message("llm_endpoint_info", f"🔗 Endpoint LLM: {config['llm_api_endpoint']}")
        log_message("output_file_info", f"💾 Fichier de sortie prévu: {config['output_filename']}")

        structured_chunks = split_text_into_chunks_with_context(config['text'], config['chunk_size'])
        total_chunks = len(structured_chunks)
        # Initialize stats properly
        current_stats = active_translations[translation_id].get('stats', {})
        current_stats.update({'total_chunks': total_chunks, 'completed_chunks': 0, 'failed_chunks': 0})
        update_translation_stats(current_stats)


        if total_chunks == 0 and config['text'].strip():
            log_message("chunking_warn", "⚠️ Texte non vide mais aucun chunk généré. Tentative de traduction globale.")
            structured_chunks.append({ "context_before": "", "main_content": config['text'], "context_after": "" })
            total_chunks = 1
            update_translation_stats({'total_chunks': total_chunks})
        elif total_chunks == 0:
            log_message("empty_text", "Texte d'entrée vide. Aucune traduction nécessaire.")
            active_translations[translation_id]['status'] = 'completed'
            active_translations[translation_id]['result'] = ""
            update_translation_progress(100)
            emit_update(translation_id, {'status': 'completed', 'result': "", 'output_filename': config['output_filename']})
            # Attempt to create an empty output file
            try:
                empty_filepath = os.path.join(OUTPUT_DIR, config['output_filename'])
                with open(empty_filepath, 'w', encoding='utf-8') as f:
                    f.write("")
                active_translations[translation_id]['output_filepath'] = empty_filepath
                log_message("empty_file_saved", f"Fichier de sortie vide sauvegardé: {empty_filepath}")
            except Exception as e:
                log_message("empty_file_save_error", f"Erreur sauvegarde fichier vide: {str(e)}")
            return

        log_message("chunk_count", f"📊 Texte divisé en {total_chunks} chunks.")
        last_successful_translation_context = ""

        for i, chunk_data in enumerate(structured_chunks):
            if active_translations[translation_id].get('interrupted', False):
                log_message("interruption_detected_loop", "🛑 Interruption détectée. Arrêt avant le prochain chunk.")
                break 
            
            chunk_num = i + 1
            update_translation_progress( (i / total_chunks) * 100 )
            main_content = chunk_data["main_content"]

            if not main_content.strip():
                log_message("chunk_skip", f"⏭️ Chunk {chunk_num}/{total_chunks}: Vide, ignoré.")
                full_translation_parts.append("")
                current_stats = active_translations[translation_id]['stats'] # Get latest stats
                current_stats['completed_chunks'] = current_stats.get('completed_chunks', 0) + 1 # Count skipped as completed for progress
                update_translation_stats(current_stats)
                continue

            log_message("chunk_process_start", f"🔄 Traduction chunk {chunk_num}/{total_chunks}...")
            translated_chunk_text = None
            current_attempts = 0
            
            while current_attempts < config['max_attempts'] and translated_chunk_text is None:
                current_attempts += 1
                if current_attempts > 1:
                    log_message("chunk_retry", f"🔁 Nouvelle tentative pour chunk {chunk_num} ({current_attempts}/{config['max_attempts']})...")
                    await asyncio.sleep(config['retry_delay'])
                
                translated_chunk_text = await generate_translation_request(
                    main_content, chunk_data["context_before"], chunk_data["context_after"],
                    last_successful_translation_context, config['source_language'], config['target_language'],
                    config['model'], api_endpoint_param=config['llm_api_endpoint']
                )

            current_stats = active_translations[translation_id]['stats'] # Get latest stats again
            if translated_chunk_text is not None:
                full_translation_parts.append(translated_chunk_text)
                last_successful_translation_context = translated_chunk_text
                current_stats['completed_chunks'] = current_stats.get('completed_chunks', 0) + 1
                update_translation_stats(current_stats)
                log_message("chunk_success", f"✅ Chunk {chunk_num} traduit.")
            else:
                error_placeholder = f"[ERREUR TRADUCTION CHUNK {chunk_num} APRES {config['max_attempts']} TENTATIVES]\n{main_content}\n[FIN ERREUR CHUNK {chunk_num}]"
                full_translation_parts.append(error_placeholder)
                last_successful_translation_context = "" 
                current_stats['failed_chunks'] = current_stats.get('failed_chunks', 0) + 1
                update_translation_stats(current_stats)
                log_message("chunk_fail", f"❌ Échec traduction chunk {chunk_num} après {config['max_attempts']} tentatives.")
        
        # --- Assemblage et Sauvegarde ---
        final_translation_result = "\n".join(full_translation_parts)
        active_translations[translation_id]['result'] = final_translation_result
        output_filepath_on_server = os.path.join(OUTPUT_DIR, config['output_filename'])
        
        try:
            with open(output_filepath_on_server, 'w', encoding='utf-8') as f:
                f.write(final_translation_result)
            log_message("save_success", f"💾 Résultat sauvegardé: {output_filepath_on_server}")
            active_translations[translation_id]['output_filepath'] = output_filepath_on_server
        except Exception as e:
            save_error_msg = f"❌ Erreur sauvegarde fichier '{output_filepath_on_server}': {str(e)}"
            log_message("save_fail", save_error_msg)
            active_translations[translation_id]['output_filepath'] = None
            active_translations[translation_id]['status'] = 'error' # Mark as error if saving failed
            active_translations[translation_id]['error'] = active_translations[translation_id].get('error', '') + f"; Échec sauvegarde: {str(e)}"

        # --- Finalisation du statut ---
        elapsed_time = time.time() - active_translations[translation_id]['stats'].get('start_time', time.time()) # Robust access
        update_translation_stats({'elapsed_time': elapsed_time})

        final_status_payload = {'result': final_translation_result, 'output_filename': config['output_filename']}
        current_job_status = active_translations[translation_id].get('status', 'unknown') # Get current status

        if active_translations[translation_id].get('interrupted', False):
            active_translations[translation_id]['status'] = 'interrupted'
            log_message("summary_interrupted", f"🛑 Traduction interrompue. Résultat partiel sauvegardé. Temps: {elapsed_time:.2f}s.")
            final_status_payload['status'] = 'interrupted'
        elif current_job_status != 'error': # If not already an error (e.g. from saving)
             active_translations[translation_id]['status'] = 'completed'
             log_message("summary_completed", f"✅ Traduction terminée. Temps: {elapsed_time:.2f}s.")
             final_status_payload['status'] = 'completed'
        else: # Was already an error
            log_message("summary_error", f"❌ Traduction terminée avec erreurs. Temps: {elapsed_time:.2f}s.")
            final_status_payload['status'] = 'error'
            final_status_payload['error'] = active_translations[translation_id].get('error', 'Erreur inconnue durant la finalisation.')

        update_translation_progress(100)
        completed_chunks_final = active_translations[translation_id]['stats'].get('completed_chunks', 0)
        failed_chunks_final = active_translations[translation_id]['stats'].get('failed_chunks', 0)
        log_message("summary_stats", f"📊 Chunks: {completed_chunks_final} traités (réussis/ignorés), {failed_chunks_final} échoués sur {total_chunks} totaux.")
        emit_update(translation_id, final_status_payload)

    except Exception as e:
        critical_error_msg = f"Erreur critique durant la traduction ({translation_id}): {str(e)}"
        log_message("critical_error_perform", critical_error_msg) # Use log_message
        if translation_id in active_translations: # Check again, belt and braces
            active_translations[translation_id]['status'] = 'error'
            active_translations[translation_id]['error'] = critical_error_msg
            if full_translation_parts: # Try to save partial on critical failure
                partial_result_on_crit_error = "\n".join(full_translation_parts)
                active_translations[translation_id]['result'] = partial_result_on_crit_error
                crit_err_filename = f"CRITICAL_ERROR_{config.get('output_filename', translation_id + '.txt')}"
                crit_err_filepath = os.path.join(OUTPUT_DIR, crit_err_filename)
                try:
                    with open(crit_err_filepath, 'w', encoding='utf-8') as f_err: f_err.write(partial_result_on_crit_error)
                    log_message("save_partial_on_crit_error", f"💾 Sauvegarde partielle sur erreur critique: {crit_err_filepath}")
                    active_translations[translation_id]['output_filepath'] = crit_err_filepath
                except Exception as save_e:
                    log_message("save_partial_on_crit_error_fail", f"❌ Échec sauvegarde partielle sur erreur critique: {str(save_e)}")
            
            emit_update(translation_id, {
                'error': critical_error_msg, 
                'status': 'error',
                'result': active_translations[translation_id].get('result')
            })
        else:
            print(f"CRITICAL ERROR FOR UNTRACKED ID {translation_id}: {critical_error_msg}")


def emit_update(translation_id, data_to_emit):
    if translation_id in active_translations:
        data_to_emit['translation_id'] = translation_id
        try:
            socketio.emit('translation_update', data_to_emit, namespace='/')
        except Exception as e:
            print(f"Erreur émission WebSocket pour {translation_id}: {e}")

@app.route('/api/translation/<translation_id>', methods=['GET'])
def get_translation_job_status(translation_id):
    if translation_id not in active_translations:
        return jsonify({"error": "Traduction non trouvée"}), 404
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
        "logs": job_data.get('logs', [])[-100:], # Last 100 logs
        "result_preview": (job_data.get('result')[:1000] + '...' if len(job_data.get('result', '')) > 1000 else job_data.get('result')) if job_data.get('result') else None,
        "error": job_data.get('error'),
        "config": job_data.get('config'),
        "output_filepath": job_data.get('output_filepath')
    })

@app.route('/api/translation/<translation_id>/interrupt', methods=['POST'])
def interrupt_translation_job(translation_id):
    if translation_id not in active_translations:
        return jsonify({"error": "Traduction non trouvée"}), 404
    job = active_translations[translation_id]
    if job.get('status') == 'running' or job.get('status') == 'queued': # Can interrupt if queued too
        job['interrupted'] = True
        emit_update(translation_id, {'log': '🛑 Signal d\'interruption reçu par le serveur.'})
        return jsonify({"message": "Signal d'interruption envoyé et en cours de traitement."}), 200
    return jsonify({"message": "La traduction n'est pas dans un état interruptible (déjà terminée, échouée ou interrompue)."}), 400

@app.route('/api/download/<translation_id>', methods=['GET'])
def download_translated_output_file(translation_id):
    if translation_id not in active_translations:
        return jsonify({"error": "ID de traduction non trouvé."}), 404
    job_data = active_translations[translation_id]
    server_filepath = job_data.get('output_filepath')

    if not server_filepath or not os.path.exists(server_filepath):
        config_output_filename = job_data.get('config', {}).get('output_filename')
        if config_output_filename:
            potential_path = os.path.join(OUTPUT_DIR, config_output_filename)
            if os.path.exists(potential_path): server_filepath = potential_path
            else: return jsonify({"error": f"Fichier '{config_output_filename}' non trouvé sur le serveur."}), 404
        else: return jsonify({"error": "Chemin du fichier de traduction non disponible ou fichier inexistant."}), 404
    
    try:
        directory = os.path.abspath(os.path.dirname(server_filepath))
        filename = os.path.basename(server_filepath)
        return send_from_directory(directory, filename, as_attachment=True)
    except Exception as e:
        print(f"Erreur lors de l'envoi du fichier '{server_filepath}' pour {translation_id}: {e}")
        return jsonify({"error": f"Erreur serveur lors de la préparation du téléchargement: {str(e)}"}), 500

@app.route('/api/translations', methods=['GET'])
def list_all_translations():
    summary_list = []
    for tid, data in active_translations.items():
        summary_list.append({
            "translation_id": tid, "status": data.get('status'), "progress": data.get('progress'),
            "start_time": data.get('stats', {}).get('start_time'),
            "output_filename": data.get('config', {}).get('output_filename')})
    return jsonify({"translations": sorted(summary_list, key=lambda x: x.get('start_time', 0), reverse=True)}) # Sort by most recent

@socketio.on('connect')
def handle_websocket_connect():
    print(f'🔌 Client WebSocket connecté: {request.sid}')
    emit('connected', {'message': 'Connecté au serveur de traduction via WebSocket'})

@socketio.on('disconnect')
def handle_websocket_disconnect():
    print(f'🔌 Client WebSocket déconnecté: {request.sid}')

@app.errorhandler(404)
def route_not_found(error): return jsonify({"error": "Endpoint API non trouvé"}), 404
@app.errorhandler(500)
def internal_server_error(error): return jsonify({"error": "Erreur interne du serveur", "details": str(error)}), 500

if __name__ == '__main__':
    print("\n" + "="*60 + f"\n🚀 SERVEUR DE TRADUCTION LLM (Version {datetime.now().strftime('%Y%m%d-%H%M')})\n" + "="*60)
    print(f"   - Endpoint Ollama par défaut (translate.py): {DEFAULT_OLLAMA_API_ENDPOINT}")
    print(f"   - Interface: http://localhost:5000 (ou http://<votre_ip>:5000)")
    print(f"   - API: http://localhost:5000/api/")
    print("\n💡 Appuyez sur Ctrl+C pour arrêter le serveur\n")
    socketio.run(app, debug=False, host='0.0.0.0', port=5000)