"""
DSSA AI Provider — Unified interface for Gemini and Local LM Studio models.

Provides a single abstraction that agents.py and pipeline.py use,
with the backend selected by the AI_PROVIDER env variable.

Local mode uses LM Studio's OpenAI-compatible endpoint — no extra
dependencies needed beyond `requests` (or httpx).
"""
import os
import json
import base64
import requests
import threading
from abc import ABC, abstractmethod

from config import (
    AI_PROVIDER, GEMINI_API_KEY, GENERATION_MODEL, EMBEDDING_MODEL,
    LOCAL_ENDPOINT_URL, LOCAL_MODEL_ID, LOCAL_MAX_FRAMES,
)


# ════════════════════════════════════════════════════════════
#  ABSTRACT BASE
# ════════════════════════════════════════════════════════════

class AIProvider(ABC):
    """Common interface for all AI backends."""

    @property
    def supports_function_calling(self) -> bool:
        return False

    @property
    def supports_video_upload(self) -> bool:
        return False

    @abstractmethod
    def generate(self, system_prompt: str, user_text: str,
                 images: list[bytes] | None = None,
                 temperature: float = 0.3,
                 max_tokens: int = 1024) -> str:
        ...

    @abstractmethod
    def generate_embedding(self, text: str) -> list[float]:
        ...


# ════════════════════════════════════════════════════════════
#  GEMINI PROVIDER
# ════════════════════════════════════════════════════════════

class GeminiProvider(AIProvider):

    def __init__(self):
        from google import genai
        from google.genai import types
        self._genai = genai
        self._types = types
        self.client = genai.Client(api_key=GEMINI_API_KEY)
        self.model = GENERATION_MODEL
        self.embedding_model = EMBEDDING_MODEL
        print(f"[AIProvider] Gemini provider initialised — model={self.model}")

    @property
    def supports_function_calling(self) -> bool:
        return True

    @property
    def supports_video_upload(self) -> bool:
        return True

    def generate(self, system_prompt: str, user_text: str,
                 images: list[bytes] | None = None,
                 temperature: float = 0.3,
                 max_tokens: int = 1024) -> str:
        types = self._types
        parts = []
        if images:
            for img in images:
                parts.append(types.Part(inline_data=types.Blob(data=img, mime_type="image/jpeg")))
        parts.append(types.Part(text=user_text))

        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=temperature,
            max_output_tokens=max_tokens,
        )
        response = self.client.models.generate_content(
            model=self.model,
            contents=[types.Content(role="user", parts=parts)],
            config=config,
        )
        return response.text.strip() if response.text else ""

    def generate_embedding(self, text: str) -> list[float]:
        try:
            result = self.client.models.embed_content(
                model=self.embedding_model,
                contents=text,
            )
            if result.embeddings and len(result.embeddings) > 0:
                return list(result.embeddings[0].values)
        except Exception as e:
            print(f"[Gemini Embedding Error] {e}")
        return []


# ════════════════════════════════════════════════════════════
#  LM STUDIO PROVIDER  (OpenAI-compatible endpoint)
# ════════════════════════════════════════════════════════════

class LMStudioProvider(AIProvider):
    """Talks to LM Studio's local OpenAI-compatible API.
    Sends base64 images via the standard chat completions format.
    GPU acceleration is handled by LM Studio itself.
    """

    def __init__(self):
        self.base_url = LOCAL_ENDPOINT_URL.rstrip("/")
        self.model_id = LOCAL_MODEL_ID
        self.max_frames = LOCAL_MAX_FRAMES
        self._lock = threading.Lock()
        
        print(f"[AIProvider] LM Studio provider initialised")
        print(f"   Endpoint : {self.base_url}")
        print(f"   Model    : {self.model_id}")
        print(f"   MaxFrames: {self.max_frames}")

        # Quick health check
        try:
            r = requests.get(f"{self.base_url}/v1/models", timeout=5)
            if r.ok:
                models = r.json().get("data", [])
                model_ids = [m.get("id", "") for m in models]
                print(f"   Available models: {model_ids}")
            else:
                print(f"   ⚠ Models endpoint returned {r.status_code}")
        except requests.ConnectionError:
            print(f"   ⚠ Cannot reach LM Studio at {self.base_url} — make sure it's running")
        except Exception as e:
            print(f"   ⚠ Health check error: {e}")

    @property
    def supports_function_calling(self) -> bool:
        return False

    @property
    def supports_video_upload(self) -> bool:
        return False

    def generate(self, system_prompt: str, user_text: str,
                 images: list[bytes] | None = None,
                 temperature: float = 0.3,
                 max_tokens: int = 1024) -> str:
        """Send a chat completion request to LM Studio with optional images."""

        # Build content array (OpenAI vision format)
        content_parts = []

        if images:
            for img_bytes in images[:self.max_frames]:
                b64 = base64.b64encode(img_bytes).decode("utf-8")
                content_parts.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                })

        content_parts.append({"type": "text", "text": user_text})

        payload = {
            "model": self.model_id,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content_parts},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        try:
            # Prevent parallel vision requests which cause LM Studio OOM/Channel Errors
            print("[LM Studio] Waiting for inference lock...")
            with self._lock:
                print("[LM Studio] Lock acquired. Sending generation request.")
                r = requests.post(
                    f"{self.base_url}/v1/chat/completions",
                    json=payload,
                    timeout=300,  # vision can be slow
                )
                r.raise_for_status()
                data = r.json()
                return data["choices"][0]["message"]["content"].strip()
        except requests.ConnectionError:
            print(f"[LM Studio Error] Cannot reach {self.base_url} — is LM Studio running?")
            return ""
        except Exception as e:
            print(f"[LM Studio Error] {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"[LM Studio Error] Response: {e.response.text[:500]}")
            return ""

    def generate_embedding(self, text: str) -> list[float]:
        """Try LM Studio's embedding endpoint if available."""
        try:
            r = requests.post(
                f"{self.base_url}/v1/embeddings",
                json={"model": self.model_id, "input": text},
                timeout=30,
            )
            if r.ok:
                data = r.json()
                return data["data"][0]["embedding"]
        except Exception as e:
            print(f"[LM Studio Embedding] Not available: {e}")
        return []


# ════════════════════════════════════════════════════════════
#  SINGLETON FACTORY
# ════════════════════════════════════════════════════════════

_provider_instance: AIProvider | None = None


def get_provider() -> AIProvider:
    global _provider_instance
    if _provider_instance is not None:
        return _provider_instance

    if AI_PROVIDER == "local":
        _provider_instance = LMStudioProvider()
    else:
        _provider_instance = GeminiProvider()

    return _provider_instance
