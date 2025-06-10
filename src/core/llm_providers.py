"""
LLM Provider abstraction and implementations
"""
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
import re
import httpx
import json

from src.config import (
    API_ENDPOINT, DEFAULT_MODEL, REQUEST_TIMEOUT, OLLAMA_NUM_CTX,
    MAX_TRANSLATION_ATTEMPTS, RETRY_DELAY_SECONDS,
    TRANSLATE_TAG_IN, TRANSLATE_TAG_OUT
)


class LLMProvider(ABC):
    """Abstract base class for LLM providers"""
    
    def __init__(self, model: str):
        self.model = model
        self._compiled_regex = re.compile(
            rf"{re.escape(TRANSLATE_TAG_IN)}(.*?){re.escape(TRANSLATE_TAG_OUT)}", 
            re.DOTALL
        )
    
    @abstractmethod
    async def generate(self, prompt: str, timeout: int = REQUEST_TIMEOUT) -> Optional[str]:
        """Generate text from prompt"""
        pass
    
    def extract_translation(self, response: str) -> Optional[str]:
        """Extract translation from response using configured tags"""
        if not response:
            return None
            
        match = self._compiled_regex.search(response)
        if match:
            return match.group(1).strip()
        return None
    
    async def translate_text(self, prompt: str) -> Optional[str]:
        """Complete translation workflow: request + extraction"""
        response = await self.generate(prompt)
        if response:
            return self.extract_translation(response)
        return None


class OllamaProvider(LLMProvider):
    """Ollama API provider"""
    
    def __init__(self, api_endpoint: str = API_ENDPOINT, model: str = DEFAULT_MODEL):
        super().__init__(model)
        self.api_endpoint = api_endpoint
    
    async def generate(self, prompt: str, timeout: int = REQUEST_TIMEOUT) -> Optional[str]:
        """Generate text using Ollama API"""
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "think": False,
            "options": {"num_ctx": OLLAMA_NUM_CTX}
        }
        
        async with httpx.AsyncClient() as client:
            for attempt in range(MAX_TRANSLATION_ATTEMPTS):
                try:
                    print(f"Ollama API Request to {self.api_endpoint} with model {self.model}")
                    response = await client.post(
                        self.api_endpoint, 
                        json=payload, 
                        timeout=timeout
                    )
                    response.raise_for_status()
                    
                    response_json = response.json()
                    response_text = response_json.get("response", "")
                    print(f"Ollama API Response received: {len(response_text)} characters")
                    return response_text
                    
                except httpx.TimeoutException as e:
                    print(f"Ollama API Timeout (attempt {attempt + 1}/{MAX_TRANSLATION_ATTEMPTS}): {e}")
                    if attempt < MAX_TRANSLATION_ATTEMPTS - 1:
                        continue
                    return None
                except httpx.HTTPStatusError as e:
                    print(f"Ollama API HTTP Error (attempt {attempt + 1}/{MAX_TRANSLATION_ATTEMPTS}): {e}")
                    if attempt < MAX_TRANSLATION_ATTEMPTS - 1:
                        continue
                    return None
                except json.JSONDecodeError as e:
                    print(f"Ollama API JSON Decode Error (attempt {attempt + 1}/{MAX_TRANSLATION_ATTEMPTS}): {e}")
                    if attempt < MAX_TRANSLATION_ATTEMPTS - 1:
                        continue
                    return None
                except Exception as e:
                    print(f"Ollama API Unknown Error (attempt {attempt + 1}/{MAX_TRANSLATION_ATTEMPTS}): {e}")
                    if attempt < MAX_TRANSLATION_ATTEMPTS - 1:
                        continue
                    return None
                    
        return None


class GeminiProvider(LLMProvider):
    """Google Gemini API provider"""
    
    def __init__(self, api_key: str, model: str = "gemini-2.0-flash"):
        super().__init__(model)
        self.api_key = api_key
        self.api_endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    
    async def generate(self, prompt: str, timeout: int = REQUEST_TIMEOUT) -> Optional[str]:
        """Generate text using Gemini API"""
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self.api_key
        }
        
        payload = {
            "contents": [{
                "parts": [{
                    "text": prompt
                }]
            }],
            "generationConfig": {
                "temperature": 0.7,
                "maxOutputTokens": 2048
            }
        }
        
        print(f"[DEBUG] Gemini API URL: {self.api_endpoint}")
        print(f"[DEBUG] Using API key: {self.api_key[:10]}...{self.api_key[-4:]}")
        print(f"[DEBUG] Headers: {headers}")
        print(f"[DEBUG] Payload length: {len(str(payload))} characters")
        
        async with httpx.AsyncClient() as client:
            for attempt in range(MAX_TRANSLATION_ATTEMPTS):
                try:
                    print(f"Gemini API Request to {self.api_endpoint}")
                    response = await client.post(
                        self.api_endpoint,
                        headers=headers,
                        json=payload,
                        timeout=timeout
                    )
                    response.raise_for_status()
                    
                    response_json = response.json()
                    # Extract text from Gemini response structure
                    response_text = ""
                    if "candidates" in response_json and response_json["candidates"]:
                        content = response_json["candidates"][0].get("content", {})
                        parts = content.get("parts", [])
                        if parts:
                            response_text = parts[0].get("text", "")
                    
                    print(f"Gemini API Response received: {len(response_text)} characters")
                    return response_text
                    
                except httpx.TimeoutException as e:
                    print(f"Gemini API Timeout (attempt {attempt + 1}/{MAX_TRANSLATION_ATTEMPTS}): {e}")
                    if attempt < MAX_TRANSLATION_ATTEMPTS - 1:
                        continue
                    return None
                except httpx.HTTPStatusError as e:
                    print(f"Gemini API HTTP Error (attempt {attempt + 1}/{MAX_TRANSLATION_ATTEMPTS}): {e}")
                    if hasattr(e, 'response'):
                        print(f"Status Code: {e.response.status_code}")
                        print(f"Response Headers: {e.response.headers}")
                        print(f"Response Body: {e.response.text}")
                    else:
                        print("No response object available")
                    if attempt < MAX_TRANSLATION_ATTEMPTS - 1:
                        continue
                    return None
                except json.JSONDecodeError as e:
                    print(f"Gemini API JSON Decode Error (attempt {attempt + 1}/{MAX_TRANSLATION_ATTEMPTS}): {e}")
                    if attempt < MAX_TRANSLATION_ATTEMPTS - 1:
                        continue
                    return None
                except Exception as e:
                    print(f"Gemini API Unknown Error (attempt {attempt + 1}/{MAX_TRANSLATION_ATTEMPTS}): {e}")
                    if attempt < MAX_TRANSLATION_ATTEMPTS - 1:
                        continue
                    return None
                    
        return None


def create_llm_provider(provider_type: str = "ollama", **kwargs) -> LLMProvider:
    """Factory function to create LLM providers"""
    # Auto-detect provider from model name if not explicitly set
    model = kwargs.get("model", DEFAULT_MODEL)
    if provider_type == "ollama" and model and model.startswith("gemini"):
        print(f"[WARNING] Detected Gemini model '{model}' but provider is set to 'ollama'. Switching to 'gemini' provider.")
        provider_type = "gemini"
    
    if provider_type.lower() == "ollama":
        return OllamaProvider(
            api_endpoint=kwargs.get("api_endpoint", API_ENDPOINT),
            model=kwargs.get("model", DEFAULT_MODEL)
        )
    elif provider_type.lower() == "gemini":
        api_key = kwargs.get("api_key")
        if not api_key:
            # Try to get from environment
            import os
            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key:
                raise ValueError("Gemini provider requires an API key. Set GEMINI_API_KEY environment variable or pass api_key parameter.")
        return GeminiProvider(
            api_key=api_key,
            model=kwargs.get("model", "gemini-2.0-flash")
        )
    else:
        raise ValueError(f"Unknown provider type: {provider_type}")