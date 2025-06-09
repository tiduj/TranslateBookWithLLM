"""
Centralized LLM client for all API communication
"""
import json
import re
import httpx
from typing import Optional, Dict, Any

from src.config import (
    API_ENDPOINT, DEFAULT_MODEL, REQUEST_TIMEOUT, OLLAMA_NUM_CTX,
    MAX_TRANSLATION_ATTEMPTS, RETRY_DELAY_SECONDS, 
    TRANSLATE_TAG_IN, TRANSLATE_TAG_OUT
)


class LLMClient:
    """Centralized client for LLM API communication"""
    
    def __init__(self, api_endpoint: str = API_ENDPOINT, model: str = DEFAULT_MODEL):
        self.api_endpoint = api_endpoint
        self.model = model
        self._compiled_regex = re.compile(
            rf"{re.escape(TRANSLATE_TAG_IN)}(.*?){re.escape(TRANSLATE_TAG_OUT)}", 
            re.DOTALL
        )
    
    async def make_request(self, prompt: str, model: Optional[str] = None, 
                    timeout: int = REQUEST_TIMEOUT) -> Optional[str]:
        """
        Make a request to the LLM API with error handling and retries
        
        Args:
            prompt: The prompt to send
            model: Model to use (defaults to instance model)
            timeout: Request timeout in seconds
            
        Returns:
            Raw response text or None if failed
        """
        payload = {
            "model": model or self.model,
            "prompt": prompt,
            "stream": False,
            "think": False,
            "options": {"num_ctx": OLLAMA_NUM_CTX}
        }
        
        async with httpx.AsyncClient() as client:
            for attempt in range(MAX_TRANSLATION_ATTEMPTS):
                try:
                    print(f"LLM API Request to {self.api_endpoint} with model {payload['model']}")
                    response = await client.post(
                        self.api_endpoint, 
                        json=payload, 
                        timeout=timeout
                    )
                    response.raise_for_status()
                    
                    response_json = response.json()
                    response_text = response_json.get("response", "")
                    print(f"LLM API Response received: {len(response_text)} characters")
                    return response_text
                    
                except httpx.TimeoutException as e:
                    print(f"LLM API Timeout (attempt {attempt + 1}/{MAX_TRANSLATION_ATTEMPTS}): {e}")
                    if attempt < MAX_TRANSLATION_ATTEMPTS - 1:
                        continue
                    return None
                except httpx.HTTPStatusError as e:
                    print(f"LLM API HTTP Error (attempt {attempt + 1}/{MAX_TRANSLATION_ATTEMPTS}): {e}")
                    if attempt < MAX_TRANSLATION_ATTEMPTS - 1:
                        continue
                    return None
                except json.JSONDecodeError as e:
                    print(f"LLM API JSON Decode Error (attempt {attempt + 1}/{MAX_TRANSLATION_ATTEMPTS}): {e}")
                    if attempt < MAX_TRANSLATION_ATTEMPTS - 1:
                        continue
                    return None
                except Exception as e:
                    print(f"LLM API Unknown Error (attempt {attempt + 1}/{MAX_TRANSLATION_ATTEMPTS}): {e}")
                    if attempt < MAX_TRANSLATION_ATTEMPTS - 1:
                        continue
                    return None
                    
        return None
    
    def extract_translation(self, response: str) -> Optional[str]:
        """
        Extract translation from response using configured tags
        
        Args:
            response: Raw LLM response
            
        Returns:
            Extracted translation or None if not found
        """
        if not response:
            return None
            
        match = self._compiled_regex.search(response)
        if match:
            return match.group(1).strip()
        return None
    
    async def translate_text(self, prompt: str, model: Optional[str] = None) -> Optional[str]:
        """
        Complete translation workflow: request + extraction
        
        Args:
            prompt: Translation prompt
            model: Model to use
            
        Returns:
            Extracted translation or None if failed
        """
        response = await self.make_request(prompt, model)
        if response:
            return self.extract_translation(response)
        return None


# Global instance for backward compatibility
default_client = LLMClient()