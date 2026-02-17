import json
import os
from dataclasses import dataclass
from typing import Any, AsyncIterator, Optional

import httpx


@dataclass(frozen=True)
class OllamaClient:
    base_url: str
    model_fast: str
    model_chat: str
    timeout_seconds: float
    temperature: float
    num_predict_fast: int
    num_predict_chat: int
    think: bool

    @staticmethod
    def from_env() -> "OllamaClient":
        return OllamaClient(
            base_url=os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434").rstrip("/"),
            model_fast=os.getenv("OLLAMA_MODEL_FAST", "qwen3:4b"),
            model_chat=os.getenv("OLLAMA_MODEL_CHAT", "qwen3:8b"),
            timeout_seconds=float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "240")),
            temperature=float(os.getenv("OLLAMA_TEMPERATURE", "0.2")),
            num_predict_fast=int(os.getenv("OLLAMA_NUM_PREDICT_FAST", "160")),
            num_predict_chat=int(os.getenv("OLLAMA_NUM_PREDICT_CHAT", "320")),
            # Qwen3 is a "thinking" model in Ollama. Disable by default so we get final answers
            # in message.content (faster and avoids empty content when token-limited).
            think=os.getenv("OLLAMA_THINK", "false").lower() in ("1", "true", "yes", "y"),
        )

    async def chat(
        self,
        *,
        model: str,
        system: str,
        user: str,
        session_id: str,
        mode: str,
        response_format: Optional[dict[str, Any]] = None,
        num_predict_override: Optional[int] = None,
    ) -> str:
        # Using /api/chat provides better multi-turn support if we later store history.
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "think": self.think,
            "stream": False,
            "options": {
                # Keep it deterministic for home automation use-cases
                "temperature": self.temperature,
                # Hard cap output length to reduce latency.
                "num_predict": (
                    int(num_predict_override)
                    if num_predict_override is not None
                    else (self.num_predict_fast if mode == "fast" else self.num_predict_chat)
                ),
            },
        }
        if response_format is not None:
            payload["format"] = response_format

        # Local models (especially on first run) can be slow to respond.
        # Use a generous read timeout to avoid 500s on long generations.
        timeout = httpx.Timeout(self.timeout_seconds, connect=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(f"{self.base_url}/api/chat", json=payload)
            r.raise_for_status()
            data = r.json()
            # Ollama returns: { message: { role, content }, ... }
            msg = data.get("message", {})
            content = msg.get("content")
            if not isinstance(content, str) or not content.strip():
                return "Не удалось получить ответ от модели."
            return content.strip()

    async def chat_stream(
        self,
        *,
        model: str,
        system: str,
        user: str,
        session_id: str,
        mode: str,
        num_predict_override: Optional[int] = None,
    ) -> AsyncIterator[str]:
        """Stream Ollama /api/chat response; yields content deltas. No response_format (plain text)."""
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "think": self.think,
            "stream": True,
            "options": {
                "temperature": self.temperature,
                "num_predict": (
                    int(num_predict_override)
                    if num_predict_override is not None
                    else (self.num_predict_fast if mode == "fast" else self.num_predict_chat)
                ),
            },
        }
        timeout = httpx.Timeout(self.timeout_seconds, connect=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/api/chat",
                json=payload,
            ) as r:
                r.raise_for_status()
                async for line in r.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    msg = data.get("message") or {}
                    content = msg.get("content")
                    if isinstance(content, str) and content:
                        yield content

