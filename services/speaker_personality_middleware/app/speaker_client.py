"""Async client for EuleMitKeule/speaker-recognition REST API."""

from __future__ import annotations

import base64
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class SpeakerRecognitionError(Exception):
    """Speaker service returned an error or invalid payload."""


async def recognize_speaker(
    *,
    base_url: str,
    audio_bytes: bytes,
    sample_rate: int,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """
    Call POST /recognize with base64-encoded audio.

    Returns dict with at least ``speaker`` and ``confidence`` keys when successful.
    """
    url = f"{base_url.rstrip('/')}/recognize"
    payload = {
        "audio_input": {
            "audio_data": base64.b64encode(audio_bytes).decode("ascii"),
            "sample_rate": sample_rate,
        }
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(url, json=payload)
        if response.status_code >= 400:
            logger.error(
                "Speaker recognition failed: status=%s body=%s",
                response.status_code,
                response.text[:500],
            )
            raise SpeakerRecognitionError(
                f"speaker-recognition HTTP {response.status_code}: {response.text[:200]}"
            )
        data = response.json()
        if not isinstance(data, dict):
            raise SpeakerRecognitionError("speaker-recognition returned non-object JSON")
        return data


async def check_speaker_service_health(base_url: str, timeout: float = 5.0) -> bool:
    """GET /health — returns True when status is healthy."""
    url = f"{base_url.rstrip('/')}/health"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url)
            if response.status_code != 200:
                return False
            body = response.json()
            return isinstance(body, dict) and body.get("status") == "healthy"
    except httpx.HTTPError:
        logger.debug("Speaker health check failed for %s", base_url, exc_info=True)
        return False
