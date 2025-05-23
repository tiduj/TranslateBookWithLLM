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
    print("✅ Module 'translate' importé avec succès")
except ImportError as e:
    print("❌ Erreur lors de l'import du module 'translate':")
    print(f"   {e}")
    print("   Assurez-vous que 'translate.py' est dans le même dossier")
    exit(1)

app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# État global pour suivre les traductions
active_translations = {}

@app.route('/')
def serve_interface():
    """Sert l'interface HTML"""
    if os.path.exists('translation_interface.html'):
        return send_from_directory('.', 'translation_interface.html')
    else:
        return """
        <h1>Erreur: Interface non trouvée</h1>
        <p>Le fichier 'translation_interface.html' n'a pas été trouvé dans le répertoire.</p>
        <p>Assurez-vous que tous les fichiers sont dans le même dossier.</p>
        """, 404

@app.route('/api/health', methods=['GET'])
def health_check():
    """Vérifie que l'API est en ligne"""
    return jsonify({
        "status": "ok",
        "message": "Translation API is running",
        "translate_module": "loaded",
        "ollama_endpoint": API_ENDPOINT
    })

@app.route('/api/models', methods=['GET'])
def get_available_models():
    """Retourne la liste des modèles disponibles sur Ollama"""
    try:
        # Extraire l'URL de base depuis API_ENDPOINT
        base_url = API_ENDPOINT.split('/api/')[0]
        tags_url = f"{base_url}/api/tags"
        
        print(f"Récupération des modèles depuis: {tags_url}")
        response = requests.get(tags_url, timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            models = data.get('models', [])
            
            # Extraire les noms des modèles et leurs informations
            model_list = []
            for model in models:
                model_info = {
                    "name": model.get('name', ''),
                    "size": model.get('size', 0),
                    "modified": model.get('modified_at', ''),
                    "digest": model.get('digest', '')[:12] + '...' if model.get('digest') else ''
                }
                model_list.append(model_info)
            
            # Trier par date de modification (plus récent en premier)
            model_list.sort(key=lambda x: x['modified'], reverse=True)
            
            # Extraire juste les noms pour la compatibilité
            model_names = [m['name'] for m in model_list]
            
            print(f"✅ {len(model_names)} modèles trouvés: {', '.join(model_names)}")
            
            return jsonify({
                "models": model_names,
                "models_detailed": model_list,
                "default": DEFAULT_MODEL if DEFAULT_MODEL in model_names else (model_names[0] if model_names else DEFAULT_MODEL),
                "status": "ollama_connected",
                "count": len(model_names)
            })
    except requests.exceptions.ConnectionError:
        print("❌ Impossible de se connecter à Ollama")
    except Exception as e:
        print(f"❌ Erreur lors de la récupération des modèles: {e}")
    
    # Retourne une liste vide si Ollama n'est pas accessible
    return jsonify({
        "models": [],
        "models_detailed": [],
        "default": DEFAULT_MODEL,
        "status": "ollama_offline",
        "count": 0,
        "error": "Ollama n'est pas accessible. Assurez-vous qu'il est lancé avec 'ollama serve'"
    })

@app.route('/api/config', methods=['GET'])
def get_default_config():
    """Retourne la configuration par défaut"""
    return jsonify({
        "api_endpoint": API_ENDPOINT,
        "default_model": DEFAULT_MODEL,
        "chunk_size": MAIN_LINES_PER_CHUNK,
        "timeout": REQUEST_TIMEOUT,
        "context_window": OLLAMA_NUM_CTX,
        "max_attempts": MAX_TRANSLATION_ATTEMPTS,
        "retry_delay": RETRY_DELAY_SECONDS
    })

@app.route('/api/translate', methods=['POST'])
def start_translation():
    """Lance une nouvelle traduction"""
    data = request.json
    
    # Validation des données
    required_fields = ['text', 'source_language', 'target_language']
    for field in required_fields:
        if field not in data:
            return jsonify({"error": f"Champ manquant: {field}"}), 400
    
    # Génération d'un ID unique
    translation_id = f"trans_{int(time.time() * 1000)}"
    
    # Configuration avec valeurs par défaut du script original
    config = {
        'text': data['text'],
        'source_language': data['source_language'],
        'target_language': data['target_language'],
        'model': data.get('model', DEFAULT_MODEL),
        'chunk_size': data.get('chunk_size', MAIN_LINES_PER_CHUNK),
        'api_endpoint': data.get('api_endpoint', API_ENDPOINT),
        'timeout': data.get('timeout', REQUEST_TIMEOUT),
        'context_window': data.get('context_window', OLLAMA_NUM_CTX),
        'max_attempts': data.get('max_attempts', MAX_TRANSLATION_ATTEMPTS),
        'retry_delay': data.get('retry_delay', RETRY_DELAY_SECONDS)
    }
    
    # Lancer la traduction dans un thread séparé
    thread = threading.Thread(
        target=run_translation,
        args=(translation_id, config)
    )
    thread.daemon = True
    thread.start()
    
    return jsonify({
        "translation_id": translation_id,
        "message": "Traduction démarrée",
        "config": config
    })

def run_translation(translation_id, config):
    """Exécute la traduction de manière asynchrone"""
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
        'result': None,
        'config': config
    }
    
    try:
        # Créer une nouvelle boucle d'événements pour ce thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(perform_translation(translation_id, config))
        loop.close()
    except Exception as e:
        active_translations[translation_id]['status'] = 'error'
        active_translations[translation_id]['error'] = str(e)
        emit_update(translation_id, {'error': str(e), 'status': 'error'})

async def perform_translation(translation_id, config):
    """Effectue la traduction réelle en utilisant les fonctions de translate.py"""
    
    def log(message):
        """Ajoute un log et l'envoie via WebSocket"""
        timestamp = datetime.now().strftime('%H:%M:%S')
        log_entry = f"[{timestamp}] {message}"
        active_translations[translation_id]['logs'].append(log_entry)
        emit_update(translation_id, {'log': log_entry})
    
    def update_progress(progress):
        """Met à jour la progression"""
        active_translations[translation_id]['progress'] = progress
        emit_update(translation_id, {'progress': progress})
    
    def update_stats(stats):
        """Met à jour les statistiques"""
        active_translations[translation_id]['stats'].update(stats)
        emit_update(translation_id, {'stats': active_translations[translation_id]['stats']})
    
    try:
        log("🚀 Début de la traduction...")
        log(f"📋 Configuration: {config['source_language']} → {config['target_language']}")
        log(f"🤖 Modèle: {config['model']}")
        log(f"🔗 API Endpoint: {config['api_endpoint']}")
        
        # Découpage du texte en utilisant la fonction du script original
        log("✂️ Découpage du texte en chunks...")
        structured_chunks = split_text_into_chunks_with_context(
            config['text'], 
            config['chunk_size']
        )
        
        total_chunks = len(structured_chunks)
        update_stats({'total_chunks': total_chunks})
        log(f"📊 Texte divisé en {total_chunks} chunks de ~{config['chunk_size']} lignes")
        
        if total_chunks == 0:
            raise Exception("Aucun chunk généré. Le texte est peut-être vide.")
        
        # Traduction des chunks
        full_translation_parts = []
        last_successful_translation = ""
        
        for i, chunk_data in enumerate(structured_chunks):
            chunk_num = i + 1
            progress = (i / total_chunks) * 100
            update_progress(progress)
            
            main_content = chunk_data["main_content"]
            context_before = chunk_data["context_before"]
            context_after = chunk_data["context_after"]
            
            if not main_content.strip():
                log(f"⏭️ Chunk {chunk_num}/{total_chunks}: Contenu vide, ignoré")
                full_translation_parts.append("")
                continue
            
            log(f"🔄 Traduction du chunk {chunk_num}/{total_chunks}...")
            
            translated_chunk = None
            attempts = 0
            
            while attempts < config['max_attempts'] and translated_chunk is None:
                attempts += 1
                
                if attempts > 1:
                    log(f"🔁 Nouvelle tentative pour le chunk {chunk_num} (tentative {attempts}/{config['max_attempts']})...")
                    await asyncio.sleep(config['retry_delay'])
                
                try:
                    # Utilisation de la fonction de traduction du script original
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
                        update_stats({
                            'completed_chunks': active_translations[translation_id]['stats']['completed_chunks'] + 1
                        })
                        log(f"✅ Chunk {chunk_num} traduit avec succès")
                    else:
                        raise Exception("Traduction vide ou tags non trouvés dans la réponse")
                        
                except Exception as e:
                    error_detail = str(e)
                    if attempts >= config['max_attempts']:
                        error_msg = f"[ERREUR TRADUCTION CHUNK {chunk_num} APRÈS {config['max_attempts']} TENTATIVES]\n{main_content}\n[FIN ERREUR]"
                        full_translation_parts.append(error_msg)
                        update_stats({
                            'failed_chunks': active_translations[translation_id]['stats']['failed_chunks'] + 1
                        })
                        log(f"❌ Échec définitif du chunk {chunk_num}: {error_detail}")
                        last_successful_translation = ""
                    else:
                        log(f"⚠️ Erreur chunk {chunk_num} (tentative {attempts}): {error_detail}")
        
        # Assemblage final
        update_progress(95)
        log("🔧 Assemblage de la traduction finale...")
        final_translation = "\n".join(full_translation_parts)
        
        # Calcul du temps écoulé
        elapsed_time = time.time() - active_translations[translation_id]['stats']['start_time']
        update_stats({'elapsed_time': elapsed_time})
        
        # Finalisation
        active_translations[translation_id]['status'] = 'completed'
        active_translations[translation_id]['result'] = final_translation
        update_progress(100)
        
        log(f"✅ Traduction terminée en {elapsed_time:.2f} secondes")
        log(f"📊 Résumé: {active_translations[translation_id]['stats']['completed_chunks']} chunks réussis, {active_translations[translation_id]['stats']['failed_chunks']} échoués")
        
        emit_update(translation_id, {
            'status': 'completed',
            'result': final_translation
        })
        
    except Exception as e:
        error_msg = f"Erreur critique: {str(e)}"
        log(f"❌ {error_msg}")
        active_translations[translation_id]['status'] = 'error'
        active_translations[translation_id]['error'] = error_msg
        emit_update(translation_id, {
            'error': error_msg,
            'status': 'error'
        })

def emit_update(translation_id, data):
    """Émet une mise à jour via WebSocket"""
    data['translation_id'] = translation_id
    try:
        socketio.emit('translation_update', data, namespace='/')
    except Exception as e:
        print(f"Erreur lors de l'émission WebSocket: {e}")

@app.route('/api/translation/<translation_id>', methods=['GET'])
def get_translation_status(translation_id):
    """Récupère le statut d'une traduction"""
    if translation_id not in active_translations:
        return jsonify({"error": "Traduction non trouvée"}), 404
    
    translation = active_translations[translation_id]
    elapsed = time.time() - translation['stats']['start_time']
    
    return jsonify({
        "translation_id": translation_id,
        "status": translation['status'],
        "progress": translation['progress'],
        "stats": {
            **translation['stats'],
            'elapsed_time': elapsed
        },
        "logs": translation['logs'][-50:],  # Derniers 50 logs
        "result": translation.get('result') if translation['status'] == 'completed' else None,
        "error": translation.get('error'),
        "config": translation.get('config')
    })

@app.route('/api/translations', methods=['GET'])
def list_translations():
    """Liste toutes les traductions"""
    translations = []
    for tid, data in active_translations.items():
        translations.append({
            "translation_id": tid,
            "status": data['status'],
            "progress": data['progress'],
            "start_time": data['stats']['start_time']
        })
    return jsonify({"translations": translations})

@socketio.on('connect')
def handle_connect():
    """Gère la connexion WebSocket"""
    print('🔌 Client connecté via WebSocket')
    emit('connected', {'message': 'Connecté au serveur de traduction'})

@socketio.on('disconnect')
def handle_disconnect():
    """Gère la déconnexion WebSocket"""
    print('🔌 Client déconnecté')

@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Endpoint non trouvé"}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({"error": "Erreur interne du serveur"}), 500

if __name__ == '__main__':
    print("\n" + "="*60)
    print("🚀 SERVEUR DE TRADUCTION LLM")
    print("="*60)
    
    # Vérifications au démarrage
    print("\n📋 Vérifications:")
    
    # Vérifier translate.py
    print("✅ Module 'translate.py' chargé")
    print(f"   - Modèle par défaut: {DEFAULT_MODEL}")
    print(f"   - Taille des chunks: {MAIN_LINES_PER_CHUNK} lignes")
    print(f"   - Endpoint Ollama: {API_ENDPOINT}")
    
    # Vérifier l'interface HTML
    if os.path.exists('translation_interface.html'):
        print("✅ Interface HTML trouvée")
    else:
        print("❌ Interface HTML non trouvée!")
        print("   Assurez-vous que 'translation_interface.html' est dans le même dossier")
    
    # Vérifier Ollama
    print("\n🔍 Test de connexion à Ollama...")
    try:
        response = requests.get(f'{API_ENDPOINT.replace("/api/generate", "/api/tags")}', timeout=2)
        if response.status_code == 200:
            print("✅ Ollama est accessible")
            models = response.json().get('models', [])
            if models:
                print(f"   - {len(models)} modèle(s) disponible(s)")
            else:
                print("   ⚠️  Aucun modèle installé")
        else:
            print("❌ Ollama répond mais avec une erreur")
    except:
        print("❌ Ollama n'est pas accessible")
        print("   Lancez 'ollama serve' dans un autre terminal")
    
    print("\n" + "="*60)
    print("📍 Interface disponible sur: http://localhost:5000")
    print("📡 API disponible sur: http://localhost:5000/api/")
    print("🔌 WebSocket actif pour les mises à jour en temps réel")
    print("="*60)
    print("\n💡 Appuyez sur Ctrl+C pour arrêter le serveur\n")
    
    # Lancer le serveur
    socketio.run(app, debug=False, host='0.0.0.0', port=5000)