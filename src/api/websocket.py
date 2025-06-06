"""
WebSocket handlers for real-time communication
"""
from flask import request
from flask_socketio import emit


def configure_websocket_handlers(socketio):
    """Configure WebSocket event handlers"""
    
    @socketio.on('connect')
    def handle_websocket_connect():
        print(f'🔌 WebSocket client connected: {request.sid}')
        emit('connected', {'message': 'Connected to translation server via WebSocket'})

    @socketio.on('disconnect')
    def handle_websocket_disconnect():
        print(f'🔌 WebSocket client disconnected: {request.sid}')


def emit_update(socketio, translation_id, data_to_emit, active_translations):
    """
    Emit WebSocket update for translation progress
    
    Args:
        socketio: SocketIO instance
        translation_id (str): Translation job ID
        data_to_emit (dict): Data to send
        active_translations (dict): Active translations dictionary
    """
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