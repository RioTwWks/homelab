"""
Speaker personality middleware for Hermes voice.

Flow: audio (+ optional STT text) → speaker-recognition → personality map → optional Hermes forward.
"""

from __future__ import annotations

import logging
import time
from typing import Annotated, Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.config import Settings, load_settings
from app.hermes_client import forward_to_hermes
from app.personality import PersonalityDecision, resolve_personality
from app.speaker_client import SpeakerRecognitionError, check_speaker_service_health, recognize_speaker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="speaker-personality-middleware", version="0.1.0")

_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = load_settings()
    return _settings


class ProcessVoiceResponse(BaseModel):
    ok: bool = True
    personality: str
    speaker: str | None = None
    confidence: float = 0.0
    used_default_personality: bool = False
    personality_reason: str = ""
    text: str | None = None
    hermes: dict[str, Any] | None = None
    hermes_personality_hint: str = Field(
        description="CLI hint for manual session switch, e.g. /personality child",
    )


@app.on_event("startup")
async def on_startup() -> None:
    settings = get_settings()
    logger.info(
        "Middleware started: speaker=%s threshold=%.2f default=%s map_keys=%d",
        settings.speaker_service_url,
        settings.confidence_threshold,
        settings.default_personality,
        len(settings.personality_map),
    )


@app.get("/")
def root() -> dict[str, Any]:
    settings = get_settings()
    return {
        "name": "speaker-personality-middleware",
        "version": "0.1.0",
        "ok": True,
        "paths": {
            "health": "/healthz",
            "process_voice": "/process_voice",
        },
        "speaker_service_url": settings.speaker_service_url,
        "hermes_url_configured": bool(settings.hermes_url),
    }


@app.get("/healthz")
async def healthz() -> dict[str, Any]:
    settings = get_settings()
    speaker_ok = await check_speaker_service_health(settings.speaker_service_url)
    return {
        "ok": True,
        "ts": int(time.time()),
        "speaker_recognition_reachable": speaker_ok,
        "default_personality": settings.default_personality,
        "confidence_threshold": settings.confidence_threshold,
    }


async def _process_audio(
    audio_bytes: bytes,
    text: str | None,
    sample_rate: int | None = None,
) -> ProcessVoiceResponse:
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="audio file is empty")

    settings = get_settings()
    rate = sample_rate if sample_rate is not None else settings.audio_sample_rate
    try:
        recognition = await recognize_speaker(
            base_url=settings.speaker_service_url,
            audio_bytes=audio_bytes,
            sample_rate=rate,
        )
    except SpeakerRecognitionError as exc:
        logger.exception("Recognition error")
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    decision: PersonalityDecision = resolve_personality(settings, recognition)
    hermes_result = None
    if text and text.strip():
        hermes_result = await forward_to_hermes(
            base_url=settings.hermes_url,
            text=text.strip(),
            personality=decision.personality,
            speaker=decision.speaker,
            confidence=decision.confidence,
        )

    return ProcessVoiceResponse(
        ok=True,
        personality=decision.personality,
        speaker=decision.speaker,
        confidence=decision.confidence,
        used_default_personality=decision.used_default,
        personality_reason=decision.reason,
        text=text.strip() if text else None,
        hermes=hermes_result,
        hermes_personality_hint=f"/personality {decision.personality}",
    )


@app.post("/process_voice", response_model=ProcessVoiceResponse)
async def process_voice(
    audio: Annotated[UploadFile, File(description="Raw audio (WAV/PCM recommended, 16 kHz mono)")],
    text: Annotated[str | None, Form(description="Optional STT transcript from upstream")] = None,
) -> ProcessVoiceResponse:
    """
    Identify speaker from ``audio`` and map to Hermes personality.

    When ``text`` is supplied (post-STT), optionally forwards to ``HERMES_URL`` voice hook.
    """
    audio_bytes = await audio.read()
    return await _process_audio(audio_bytes, text)


class ProcessVoiceJsonBody(BaseModel):
    """Alternate JSON body when audio is already base64-encoded (integrations)."""

    audio_base64: str
    text: str | None = None
    sample_rate: int | None = None


@app.post("/process_voice/json", response_model=ProcessVoiceResponse)
async def process_voice_json(body: ProcessVoiceJsonBody) -> ProcessVoiceResponse:
    import base64

    try:
        audio_bytes = base64.b64decode(body.audio_base64, validate=True)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="invalid audio_base64") from exc
    return await _process_audio(audio_bytes, body.text, sample_rate=body.sample_rate)
