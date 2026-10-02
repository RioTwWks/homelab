"""Optional forward of STT text to a Hermes HTTP gateway."""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


async def forward_to_hermes(
    *,
    base_url: str,
    text: str,
    personality: str,
    speaker: str | None,
    confidence: float,
    timeout: float = 120.0,
) -> dict[str, Any] | None:
    """
    POST recognized utterance to Hermes middleware hook.

    Contract (homelab): ``POST {HERMES_URL}/v1/voice/process`` with JSON body.
    When the endpoint is not configured or unreachable, returns None (caller uses local mapping only).
    """
    if not base_url.strip() or not text.strip():
        return None

    url = f"{base_url.rstrip('/')}/v1/voice/process"
    payload = {
        "text": text,
        "personality": personality,
        "speaker": speaker,
        "confidence": confidence,
    }
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, json=payload)
            if response.status_code == 404:
                logger.warning("Hermes voice hook not found at %s (404)", url)
                return None
            response.raise_for_status()
            if not response.content:
                return {"ok": True}
            data = response.json()
            return data if isinstance(data, dict) else {"ok": True, "raw": data}
    except httpx.HTTPError as exc:
        logger.warning("Hermes forward failed: %s", exc)
        return None
