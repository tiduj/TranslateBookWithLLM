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

# Import des fonctions du script original
from translate import (
    get_adjusted_start_index,
    get_adjusted_end_index,
    split_text_into_chunks_with_context,
    generate_translation_request,
    SENTENCE_TERMINATORS,
    MAX_TRANSLATION_ATTEMPTS,
    RETRY_DELAY_SECONDS,
    API_ENDPOINT,
    DEFAULT_MODEL,
    MAIN_LINES_PER_CHUNK,
    REQUEST_TIMEOUT,
    OLLAMA_NUM_CTX
)

app = Flask(__name__)
CORS(app)  # Pour permettre les requêtes cross-origin
socketio = SocketIO(app, cors_allowed_origins="*")

# État global pour suivre les traductions en cours
active_translations = {}

@app.route('/')
def serve_interface():
    """Sert l'interface HTML"""
    return send_from_directory('.', 'translation_interface.html')

@app.route('/api/health', methods=['GET'])
def health_check():
    """Vérifie que l'API est en ligne"""
    return jsonify({"status": "ok", "message": "Translation API is running"})

@app.route('/api/models', methods=['GET'])
def get_available_models():
    """Retourne la liste des modèles disponibles sur Ollama"""
    try:
        response = requests.get('http://localhost:11434/api/tags')
        if response.status_code == 200:
            models = response.json().get('models', [])
            model_names = [model['name'] for model in models]
            return jsonify({"models": model_names})
        else:
            return jsonify({"models": ["mistral-small:24b", "mistral:7b", "llama3:8b", "mixtral:8x7b"]})
    except:
        # Retourne une liste par défaut si Ollama n'est pas accessible
        return jsonify({"models": ["mistral-small:24b", "mistral:7b", "llama3:8b", "mixtral:8x7b"]})

@app.route('/api/translate', methods=['POST'])
def start_translation():
    """Lance une nouvelle traduction"""
    data = request.json
    
    # Validation des données
    required_fields = ['text', 'source_language', 'target_language', 'model']
    for field in required_fields:
        if field not in data:
            return jsonify({"error": f"Missing field: {field}"}), 400
    
    # Génération d'un ID unique pour cette traduction
    translation_id = f"trans_{int(time.time() * 1000)}"
    
    # Configuration
    config = {
        'text': data['text'],
        'source_language': data['source_language'],
        'target_language': data['target_language'],
        'model': data.get('model', 'mistral-small:24b'),
        'chunk_size': data.get('chunk_size', 25),
        'api_endpoint': data.get('api_endpoint', 'http://localhost:11434/api/generate'),
        'timeout': data.get('timeout', 180),
        'context_window': data.get('context_window', 4096),
        'max_attempts': data.get('max_attempts', 2),
        'retry_delay': data.get('retry_delay', 2)
    }
    
    # Lancer la traduction dans un thread séparé
    thread = threading.Thread(
        target=run_translation,
        args=(translation_id, config)
    )
    thread.start()
    
    return jsonify({
        "translation_id": translation_id,
        "message": "Translation started"
    })

def run_translation(translation_id, config):
    """Exécute la traduction de manière asynchrone"""
    # Initialisation du statut
    active_translations[translation_id] = {
        'status': 'running',
        'progress': 0,
        'stats': {
            'total_chunks': 0,
            'completed_chunks': 0,
            'failed_chunks': 0,
            'start_time': time.time()
        },
        'logs': [],
        'result': None
    }
    
    try:
        # Utiliser asyncio pour exécuter la traduction
        asyncio.run(perform_translation(translation_id, config))
    except Exception as e:
        active_translations[translation_id]['status'] = 'error'
        active_translations[translation_id]['error'] = str(e)
        emit_update(translation_id, {'error': str(e)})

async def perform_translation(translation_id, config):
    """Effectue la traduction réelle"""
    def log(message):
        timestamp = datetime.now().strftime('%H:%M:%S')
        log_entry = f"[{timestamp}] {message}"
        active_translations[translation_id]['logs'].append(log_entry)
        emit_update(translation_id, {'log': log_entry})
    
    def update_progress(progress):
        active_translations[translation_id]['progress'] = progress
        emit_update(translation_id, {'progress': progress})
    
    def update_stats(stats):
        active_translations[translation_id]['stats'].update(stats)
        emit_update(translation_id, {'stats': active_translations[translation_id]['stats']})
    
    log("Début de la traduction...")
    log(f"Configuration: {config['source_language']} → {config['target_language']}")
    log(f"Modèle: {config['model']}")
    
    # Découpage du texte
    log("Découpage du texte en chunks...")
    structured_chunks = split_text_into_chunks_with_context(
        config['text'], 
        config['chunk_size']
    )
    
    total_chunks = len(structured_chunks)
    update_stats({'total_chunks': total_chunks})
    log(f"Texte divisé en {total_chunks} chunks de ~{config['chunk_size']} lignes")
    
    # Traduction des chunks
    full_translation_parts = []
    last_successful_translation = ""
    
    for i, chunk_data in enumerate(structured_chunks):
        chunk_num = i + 1
        progress = (chunk_num / total_chunks) * 100
        update_progress(progress)
        
        main_content = chunk_data["main_content"]
        context_before = chunk_data["context_before"]
        context_after = chunk_data["context_after"]
        
        if not main_content.strip():
            log(f"Chunk {chunk_num}/{total_chunks}: Contenu vide, ignoré")
            full_translation_parts.append("")
            continue
        
        log(f"Traduction du chunk {chunk_num}/{total_chunks}...")
        
        # Configuration pour generate_translation_request
        translated_chunk = None
        attempts = 0
        
        while attempts < config['max_attempts'] and translated_chunk is None:
            attempts += 1
            
            if attempts > 1:
                log(f"Nouvelle tentative pour le chunk {chunk_num} (tentative {attempts}/{config['max_attempts']})...")
                await asyncio.sleep(config['retry_delay'])
            
            try:
                # Appel de la fonction de traduction avec les bons paramètres
                translated_chunk = await generate_translation_request(
                    main_content,
                    context_before,
                    context_after,
                    last_successful_translation,
                    config['source_language'],
                    config['target_language'],
                    config['model']
                )
                
                if translated_chunk:
                    full_translation_parts.append(translated_chunk)
                    last_successful_translation = translated_chunk
                    update_stats({'completed_chunks': active_translations[translation_id]['stats']['completed_chunks'] + 1})
                    log(f"✓ Chunk {chunk_num} traduit avec succès")
                else:
                    raise Exception("Traduction vide retournée")
                    
            except Exception as e:
                if attempts >= config['max_attempts']:
                    error_msg = f"[ERREUR TRADUCTION CHUNK {chunk_num}]\n{main_content}\n[FIN ERREUR]"
                    full_translation_parts.append(error_msg)
                    update_stats({'failed_chunks': active_translations[translation_id]['stats']['failed_chunks'] + 1})
                    log(f"✗ Échec de la traduction du chunk {chunk_num}: {str(e)}")
                    last_successful_translation = ""
    
    # Assemblage final
    log("Assemblage de la traduction finale...")
    final_translation = "\n".join(full_translation_parts)
    
    # Calcul du temps écoulé
    elapsed_time = time.time() - active_translations[translation_id]['stats']['start_time']
    update_stats({'elapsed_time': elapsed_time})
    
    # Finalisation
    active_translations[translation_id]['status'] = 'completed'
    active_translations[translation_id]['result'] = final_translation
    update_progress(100)
    
    log(f"Traduction terminée en {elapsed_time:.2f}s")
    emit_update(translation_id, {
        'status': 'completed',
        'result': final_translation
    })

def emit_update(translation_id, data):
    """Émet une mise à jour via WebSocket"""
    data['translation_id'] = translation_id
    socketio.emit('translation_update', data, namespace='/')

@app.route('/api/translation/<translation_id>', methods=['GET'])
def get_translation_status(translation_id):
    """Récupère le statut d'une traduction"""
    if translation_id not in active_translations:
        return jsonify({"error": "Translation not found"}), 404
    
    translation = active_translations[translation_id]
    return jsonify({
        "translation_id": translation_id,
        "status": translation['status'],
        "progress": translation['progress'],
        "stats": translation['stats'],
        "logs": translation['logs'][-20:],  # Derniers 20 logs
        "result": translation.get('result') if translation['status'] == 'completed' else None,
        "error": translation.get('error')
    })

@socketio.on('connect')
def handle_connect():
    """Gère la connexion WebSocket"""
    print('Client connected')
    emit('connected', {'data': 'Connected to translation server'})

@socketio.on('disconnect')
def handle_disconnect():
    """Gère la déconnexion WebSocket"""
    print('Client disconnected')

if __name__ == '__main__':
    # Créer le fichier HTML de l'interface s'il n'existe pas
    if not os.path.exists('translation_interface.html'):
        print("⚠️  Fichier 'translation_interface.html' non trouvé!")
        print("Assurez-vous d'avoir l'interface HTML dans le même répertoire.")
    
    print("🚀 Serveur de traduction démarré!")
    print("📍 Interface disponible sur: http://localhost:5000")
    print("📡 API disponible sur: http://localhost:5000/api/")
    print("🔌 WebSocket actif pour les mises à jour en temps réel")
    
    # Lancer le serveur avec WebSocket
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)