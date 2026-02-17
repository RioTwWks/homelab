"""
Маппинг голосовых фраз в команды Media Control API.

Используется при intent=command: по тексту пользователя выбирается action/url/target,
команда отправляется в media-api, ответ ассистента — короткое подтверждение.
"""
from __future__ import annotations

import os
import re
from typing import Any, Literal

# Специальные значения URL: подставляются из env в parse_media_command
QBITTORRENT_URL_PLACEHOLDER = "__qbittorrent_web__"
STREMIO_URL_PLACEHOLDER = "__stremio_web__"

# Фразы (нижний регистр) → (action, url или None, target, label для ответа)
# Kodi — перед общими «пауза»/«играй», чтобы «коди пауза» давало target=kodi
MEDIA_PHRASES: list[tuple[list[str], str, str | None, str, str]] = [
    # Kodi
    (["коди пауза", "пауза в коди", "коди стоп"], "pause", None, "kodi", "Kodi: пауза"),
    (["коди играй", "коди продолжи", "играй в коди"], "play", None, "kodi", "Kodi: воспроизведение"),
    (["коди следующий", "следующий в коди"], "next", None, "kodi", "Kodi: следующий"),
    (["коди предыдущий", "предыдущий в коди"], "prev", None, "kodi", "Kodi: предыдущий"),
    (["включи коди", "открой коди", "запусти коди"], "open_url", "kodi://", "kodi", "Kodi"),
    # open_url — видео/стримы
    (["ютуб", "youtube", "ютьюб"], "open_url", "https://www.youtube.com", "browser", "YouTube"),
    (["вк видео", "вконтакте видео", "видео вк", "vk video"], "open_url", "https://vk.com/video", "browser", "VK Видео"),
    (["твитч", "twitch"], "open_url", "https://www.twitch.tv", "browser", "Twitch"),
    (["телеграм", "telegram"], "open_url", "https://web.telegram.org", "browser", "Telegram"),
    (["вк музыка", "vk музыка", "музыка вк"], "open_url", "https://vk.com/audio", "browser", "VK Музыка"),
    (["спотифай", "spotify"], "open_url", "https://open.spotify.com", "browser", "Spotify"),
    # Торренты — веб-интерфейс qBittorrent (URL из QBITTORRENT_WEB_URL или localhost:18084)
    (["торренты", "qbittorrent", "торрент", "открой торренты"], "open_url", QBITTORRENT_URL_PLACEHOLDER, "browser", "Торренты"),
    # Stremio — стриминг торрентов (URL из STREMIO_WEB_URL, target=stremio для десктоп-приложения)
    (["стремио", "stremio", "открой стремио", "запусти стремио"], "open_url", STREMIO_URL_PLACEHOLDER, "stremio", "Stremio"),
    # Управление воспроизведением
    (["пауза", "стоп", "останови"], "pause", None, "browser", "Пауза"),
    (["играй", "продолжи", "продолжить", "включи воспроизведение"], "play", None, "browser", "Воспроизведение"),
    (["следующий", "следующий трек", "след трек", "некст"], "next", None, "browser", "Следующий трек"),
    (["предыдущий", "предыдущий трек", "пред трек"], "prev", None, "browser", "Предыдущий трек"),
    (["громче", "увеличь громкость"], "volume_up", None, "browser", "Громче"),
    (["тише", "уменьши громкость"], "volume_down", None, "browser", "Тише"),
    (["полный экран", "полноэкранный", "на весь экран", "fullscreen"], "fullscreen", None, "browser", "Полный экран"),
]


def parse_media_command(text: str) -> dict[str, Any] | None:
    """
    По тексту пользователя вернуть команду для Media Control API или None.
    Возвращает dict: action, url?, value?, target, label (для ответа ассистента).
    """
    t = re.sub(r"\s+", " ", text.lower().strip())
    if not t:
        return None
    for phrases, action, url, target, label in MEDIA_PHRASES:
        if any(p in t for p in phrases):
            cmd: dict[str, Any] = {
                "action": action,
                "target": target,
                "label": label,
            }
            if url:
                if url == QBITTORRENT_URL_PLACEHOLDER:
                    url = os.getenv("QBITTORRENT_WEB_URL", "http://localhost:18084")
                elif url == STREMIO_URL_PLACEHOLDER:
                    url = os.getenv("STREMIO_WEB_URL", "stremio://")
                cmd["url"] = url
            if action == "volume_set":
                cmd["value"] = 80  # по умолчанию не используем, есть volume_up/down
            return cmd
    return None


def media_reply_text(cmd: dict[str, Any]) -> str:
    """Короткий ответ ассистента после выполнения медиа-команды."""
    label = cmd.get("label") or cmd.get("action", "")
    action = cmd.get("action", "")
    if action in ("play", "pause", "next", "prev", "volume_up", "volume_down", "fullscreen"):
        return f"{label}."
    if action == "open_url" and (cmd.get("url") or "").strip() == "kodi://":
        return "Запускаю Kodi."
    return f"Открываю {label}."
