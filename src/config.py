"""
Centralized configuration class
"""
from dataclasses import dataclass
from typing import Optional
from config import (
    API_ENDPOINT, DEFAULT_MODEL, MAIN_LINES_PER_CHUNK, REQUEST_TIMEOUT,
    OLLAMA_NUM_CTX, MAX_TRANSLATION_ATTEMPTS, RETRY_DELAY_SECONDS
)


@dataclass
class TranslationConfig:
    """Unified configuration for both CLI and web interfaces"""
    
    # Core settings
    source_language: str = "English"
    target_language: str = "French"
    model: str = DEFAULT_MODEL
    api_endpoint: str = API_ENDPOINT
    
    # Translation parameters
    chunk_size: int = MAIN_LINES_PER_CHUNK
    custom_instructions: str = ""
    
    # LLM parameters
    timeout: int = REQUEST_TIMEOUT
    max_attempts: int = MAX_TRANSLATION_ATTEMPTS
    retry_delay: int = RETRY_DELAY_SECONDS
    context_window: int = OLLAMA_NUM_CTX
    
    # Interface-specific
    interface_type: str = "cli"  # or "web"
    enable_colors: bool = True
    enable_interruption: bool = False
    
    @classmethod
    def from_cli_args(cls, args) -> 'TranslationConfig':
        """Create config from CLI arguments"""
        return cls(
            source_language=args.source_lang,
            target_language=args.target_lang,
            model=args.model,
            api_endpoint=args.api_endpoint,
            chunk_size=args.chunksize,
            custom_instructions=args.custom_instructions,
            interface_type="cli",
            enable_colors=not args.no_color
        )
    
    @classmethod
    def from_web_request(cls, request_data: dict) -> 'TranslationConfig':
        """Create config from web request data"""
        return cls(
            source_language=request_data.get('source_language', 'English'),
            target_language=request_data.get('target_language', 'French'),
            model=request_data.get('model', DEFAULT_MODEL),
            api_endpoint=request_data.get('llm_api_endpoint', API_ENDPOINT),
            chunk_size=request_data.get('chunk_size', MAIN_LINES_PER_CHUNK),
            custom_instructions=request_data.get('custom_instructions', ''),
            timeout=request_data.get('timeout', REQUEST_TIMEOUT),
            max_attempts=request_data.get('max_attempts', MAX_TRANSLATION_ATTEMPTS),
            retry_delay=request_data.get('retry_delay', RETRY_DELAY_SECONDS),
            context_window=request_data.get('context_window', OLLAMA_NUM_CTX),
            interface_type="web",
            enable_interruption=True
        )
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization"""
        return {
            'source_language': self.source_language,
            'target_language': self.target_language,
            'model': self.model,
            'api_endpoint': self.api_endpoint,
            'chunk_size': self.chunk_size,
            'custom_instructions': self.custom_instructions,
            'timeout': self.timeout,
            'max_attempts': self.max_attempts,
            'retry_delay': self.retry_delay,
            'context_window': self.context_window
        }