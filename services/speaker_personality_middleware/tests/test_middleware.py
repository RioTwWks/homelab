from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.main import app
from app.personality import resolve_personality


@pytest.fixture
def settings() -> Settings:
    return Settings(
        speaker_service_url="http://speaker.test:8099",
        hermes_url="",
        confidence_threshold=0.7,
        default_personality="adult",
        personality_map={"Alice": "child", "Bob": "student"},
        audio_sample_rate=16000,
    )


def test_resolve_mapped_child(settings: Settings) -> None:
    decision = resolve_personality(
        settings,
        {"speaker": "Alice", "confidence": 0.91},
    )
    assert decision.personality == "child"
    assert decision.used_default is False
    assert decision.reason == "mapped"


def test_resolve_low_confidence_defaults_adult(settings: Settings) -> None:
    decision = resolve_personality(
        settings,
        {"speaker": "Alice", "confidence": 0.55},
    )
    assert decision.personality == "adult"
    assert decision.used_default is True
    assert decision.reason == "confidence_below_threshold"


def test_resolve_unknown_speaker_high_confidence(settings: Settings) -> None:
    decision = resolve_personality(
        settings,
        {"speaker": "Stranger", "confidence": 0.88},
    )
    assert decision.personality == "adult"
    assert decision.reason == "speaker_not_mapped"


@pytest.mark.asyncio
async def test_process_voice_mock_speaker_api(settings: Settings) -> None:
    recognition = {"speaker": "Bob", "confidence": 0.82}

    with (
        patch("app.main.get_settings", return_value=settings),
        patch(
            "app.main.recognize_speaker",
            new=AsyncMock(return_value=recognition),
        ),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/process_voice",
                files={"audio": ("sample.wav", b"\x00\x01\x02", "audio/wav")},
                data={"text": "Привет"},
            )

    assert response.status_code == 200
    body = response.json()
    assert body["personality"] == "student"
    assert body["speaker"] == "Bob"
    assert body["text"] == "Привет"
    assert body["hermes_personality_hint"] == "/personality student"


@pytest.mark.asyncio
async def test_healthz(settings: Settings) -> None:
    with (
        patch("app.main.get_settings", return_value=settings),
        patch("app.main.check_speaker_service_health", new=AsyncMock(return_value=True)),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/healthz")

    assert response.status_code == 200
    assert response.json()["speaker_recognition_reachable"] is True


def test_personality_map_env_merge(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PERSONALITY_MAP", json.dumps({"Eve": "child"}))
    monkeypatch.setenv("SPEAKER_SERVICE_URL", "http://localhost:8099")
    from app.config import load_settings

    loaded = load_settings()
    assert loaded.personality_map.get("Eve") == "child"
