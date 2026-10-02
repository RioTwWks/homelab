"""Load middleware settings from YAML file and environment variables."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "speaker_personality.yaml"


class Settings(BaseModel):
    speaker_service_url: str = Field(
        default="http://speaker-recognition:8099",
        description="Base URL of speaker-recognition REST API",
    )
    hermes_url: str = Field(
        default="",
        description="Optional Hermes HTTP gateway (forward recognized text)",
    )
    confidence_threshold: float = Field(default=0.7, ge=0.0, le=1.0)
    default_personality: str = Field(default="adult")
    personality_map: dict[str, str] = Field(default_factory=dict)
    audio_sample_rate: int = Field(default=16000, ge=8000, le=48000)
    config_path: str = ""


def _merge_personality_map(raw: dict[str, Any], env_map: str) -> dict[str, str]:
    merged: dict[str, str] = {}
    if isinstance(raw.get("personality_map"), dict):
        merged.update({str(k): str(v) for k, v in raw["personality_map"].items()})
    if env_map.strip():
        try:
            parsed = json.loads(env_map)
            if isinstance(parsed, dict):
                merged.update({str(k): str(v) for k, v in parsed.items()})
        except json.JSONDecodeError as exc:
            logger.warning("Invalid PERSONALITY_MAP JSON: %s", exc)
    return merged


def load_settings() -> Settings:
    config_path = Path(os.getenv("SPEAKER_PERSONALITY_CONFIG", DEFAULT_CONFIG_PATH))
    raw: dict[str, Any] = {}
    if config_path.is_file():
        with config_path.open(encoding="utf-8") as fh:
            loaded = yaml.safe_load(fh) or {}
            if isinstance(loaded, dict):
                raw = loaded
    else:
        logger.info("Config file not found at %s, using env defaults", config_path)

    personality_map = _merge_personality_map(raw, os.getenv("PERSONALITY_MAP", ""))

    return Settings(
        speaker_service_url=os.getenv(
            "SPEAKER_SERVICE_URL",
            str(raw.get("speaker_service_url", "http://speaker-recognition:8099")),
        ).rstrip("/"),
        hermes_url=os.getenv("HERMES_URL", str(raw.get("hermes_url", ""))).rstrip("/"),
        confidence_threshold=float(
            os.getenv(
                "CONFIDENCE_THRESHOLD",
                raw.get("confidence_threshold", 0.7),
            )
        ),
        default_personality=os.getenv(
            "DEFAULT_PERSONALITY",
            str(raw.get("default_personality", "adult")),
        ),
        personality_map=personality_map,
        audio_sample_rate=int(
            os.getenv("AUDIO_SAMPLE_RATE", raw.get("audio_sample_rate", 16000))
        ),
        config_path=str(config_path),
    )
