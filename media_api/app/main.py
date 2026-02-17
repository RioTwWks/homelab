"""
Media Control API — единая точка для команд медиа от голосового ассистента.

Принимает команды (открыть URL, пауза, громкость, Kodi и т.д.) и при настроенном
MEDIA_EXECUTOR_URL пересылает их на хост (браузер kiosk, Kodi JSON-RPC, MPRIS и т.д.).
Без MEDIA_EXECUTOR_URL возвращает успех и сохраняет команду (для отладки).
"""
import os
import time
from typing import Any, Literal, Optional

import httpx
from fastapi import FastAPI
from pydantic import BaseModel, Field

app = FastAPI(title="media-api", version="0.2.0")

# Последняя команда (для отладки и GET /v1/command/last)
_last_command: Optional[dict[str, Any]] = None

# Допустимые action и target для контракта
ACTION_OPEN_URL = "open_url"
ACTION_PLAY = "play"
ACTION_PAUSE = "pause"
ACTION_NEXT = "next"
ACTION_PREV = "prev"
ACTION_VOLUME_SET = "volume_set"
ACTION_VOLUME_UP = "volume_up"
ACTION_VOLUME_DOWN = "volume_down"
ACTION_FULLSCREEN = "fullscreen"
ACTION_KODI = "kodi"  # произвольный метод Kodi JSON-RPC

TARGET_BROWSER = "browser"
TARGET_KODI = "kodi"
TARGET_MPRIS = "mpris"
TARGET_UI = "ui"


class MediaCommand(BaseModel):
    """Команда медиа. Передаётся в API и при наличии — в executor на хосте."""
    action: Literal[
        "open_url", "play", "pause", "next", "prev",
        "volume_set", "volume_up", "volume_down", "fullscreen", "kodi"
    ] = "open_url"
    url: Optional[str] = Field(default=None, description="URL для open_url или параметр для kodi")
    value: Optional[int] = Field(default=None, description="Значение (например громкость 0–100)")
    target: str = Field(
        default="browser",
        description="Куда отправить: browser | kodi | mpris | ui"
    )
    label: Optional[str] = Field(default=None, description="Человекочитаемая подпись для UI/логов")


@app.get("/")
def root() -> dict[str, Any]:
    return {
        "name": "media-api",
        "version": "0.2.0",
        "ok": True,
        "paths": {
            "health": "/healthz",
            "docs": "/docs",
            "command": "/v1/command",
            "last_command": "/v1/command/last",
        },
        "executor_configured": bool(os.getenv("MEDIA_EXECUTOR_URL", "").strip()),
    }


@app.get("/healthz")
def healthz() -> dict[str, Any]:
    return {"ok": True, "ts": int(time.time())}


def _forward_to_executor(cmd: MediaCommand) -> dict[str, Any]:
    """Отправить команду на хост (executor)."""
    url = os.getenv("MEDIA_EXECUTOR_URL", "").strip()
    if not url:
        return {"ok": True, "executor": None, "message": "No MEDIA_EXECUTOR_URL, command stored only"}
    payload = cmd.model_dump(mode="json")
    try:
        with httpx.Client(timeout=5.0) as client:
            r = client.post(url, json=payload)
            r.raise_for_status()
            return {"ok": True, "executor": url, "response": r.json() if r.content else None}
    except httpx.HTTPError as e:
        return {"ok": False, "executor": url, "error": str(e)}


@app.post("/v1/command")
def command(cmd: MediaCommand) -> dict[str, Any]:
    global _last_command
    _last_command = cmd.model_dump(mode="json")
    result = _forward_to_executor(cmd)
    return {
        "ok": result.get("ok", True),
        "received": _last_command,
        "executor": result.get("executor"),
        "executor_response": result.get("response"),
        "executor_error": result.get("error"),
    }


@app.get("/v1/command/last")
def last_command() -> dict[str, Any]:
    """Последняя принятая команда (для отладки и тестов)."""
    if _last_command is None:
        return {"ok": True, "last": None}
    return {"ok": True, "last": _last_command}
