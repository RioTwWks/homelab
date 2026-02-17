"""
Управление умным домом через Home Assistant API.

Используется при intent=command: по тексту пользователя определяется действие (свет вкл/выкл,
температура), подбирается entity_id по списку состояний HA, выполняется вызов сервиса.
Требуются HOME_ASSISTANT_URL и HOME_ASSISTANT_TOKEN (long-lived token в профиле HA).
"""
from __future__ import annotations

import os
import re
from typing import Any

import httpx

# Домены и сервисы HA
DOMAIN_LIGHT = "light"
DOMAIN_SWITCH = "switch"
DOMAIN_CLIMATE = "climate"

# Фразы (нижний регистр) → действие и домен
# Порядок: сначала явные "включи/выключи свет", потом общие "свет", потом климат
TURN_ON_PHRASES = [
    "включи свет", "свет включи", "включи свет в", "включи лампу", "включи освещение",
    "включи", "включи в",  # общее "включи" для света/выключателей
]
TURN_OFF_PHRASES = [
    "выключи свет", "свет выключи", "выключи свет в", "выключи лампу", "выключи освещение",
    "выключи", "выключи в",
]
# Ключевые слова комнат для сопоставления с friendly_name / entity_id
ROOM_KEYWORDS = [
    "гостиная", "кухня", "комната", "спальня", "ванная", "ванная комната",
    "кабинет", "коридор", "прихожая", "балкон", "детская", "туалет",
    "living", "kitchen", "bedroom", "bathroom", "office", "hall",
]


def _get_ha_config() -> tuple[str, str]:
    url = (os.getenv("HOME_ASSISTANT_URL") or "").strip().rstrip("/")
    token = (os.getenv("HOME_ASSISTANT_TOKEN") or "").strip()
    return url, token


def is_ha_configured() -> bool:
    url, token = _get_ha_config()
    return bool(url and token)


def parse_ha_command(text: str) -> dict[str, Any] | None:
    """
    По тексту пользователя вернуть команду для HA или None.
    Возвращает dict: action (turn_on | turn_off | set_temperature), domain, area_keywords?, temperature?
    """
    t = re.sub(r"\s+", " ", text.lower().strip())
    if not t:
        return None

    # Климат: "температура 22", "22 градуса", "поставь 22", "установи температуру 21"
    temp_match = re.search(r"(?:температур[ау]?\s*)?(\d{1,2}(?:[.,]\d)?)\s*(?:градус|°|и)?|(?:поставь|установи)\s*(?:температуру\s*)?(\d{1,2}(?:[.,]\d)?)", t)
    if temp_match and "погода" not in t and "на улице" not in t:
        g = temp_match.groups()
        value = float((g[0] or g[1] or "20").replace(",", "."))
        if 5 <= value <= 35:
            return {
                "action": "set_temperature",
                "domain": DOMAIN_CLIMATE,
                "temperature": value,
                "area_keywords": _extract_room_keywords(t),
            }

    # Свет вкл/выкл
    area_keywords = _extract_room_keywords(t)
    if any(p in t for p in TURN_OFF_PHRASES):
        if "свет" in t or "ламп" in t or "освещен" in t or area_keywords or "выключи" in t:
            return {
                "action": "turn_off",
                "domain": DOMAIN_LIGHT,
                "area_keywords": area_keywords,
            }
        return {
            "action": "turn_off",
            "domain": DOMAIN_SWITCH,
            "area_keywords": area_keywords,
        }
    if any(p in t for p in TURN_ON_PHRASES):
        if "свет" in t or "ламп" in t or "освещен" in t or area_keywords or "включи" in t:
            return {
                "action": "turn_on",
                "domain": DOMAIN_LIGHT,
                "area_keywords": area_keywords,
            }
        return {
            "action": "turn_on",
            "domain": DOMAIN_SWITCH,
            "area_keywords": area_keywords,
        }
    return None


def _extract_room_keywords(text: str) -> list[str]:
    found = []
    for kw in ROOM_KEYWORDS:
        if kw in text:
            found.append(kw)
    return found


async def _fetch_states(url: str, token: str) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=8.0) as client:
        r = await client.get(
            f"{url}/api/states",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
        r.raise_for_status()
        return r.json()


def _match_entities(
    states: list[dict[str, Any]],
    domain: str,
    area_keywords: list[str],
) -> list[str]:
    """Вернуть список entity_id подходящих под домен и (опционально) комнату."""
    candidates = []
    for s in states:
        eid = s.get("entity_id") or ""
        if not eid.startswith(domain + "."):
            continue
        friendly = (s.get("attributes") or {}).get("friendly_name") or ""
        combined = (eid + " " + friendly).lower()
        if not area_keywords:
            candidates.append(eid)
            continue
        if any(kw in combined for kw in area_keywords):
            candidates.append(eid)
    return candidates


async def call_ha_service(
    url: str,
    token: str,
    domain: str,
    service: str,
    data: dict[str, Any],
) -> bool:
    async with httpx.AsyncClient(timeout=8.0) as client:
        r = await client.post(
            f"{url}/api/services/{domain}/{service}",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=data,
        )
        return 200 <= r.status_code < 300


async def execute_ha_command(cmd: dict[str, Any]) -> tuple[bool, str]:
    """
    Выполнить команду HA. Возвращает (успех, текст ответа для пользователя).
    """
    url, token = _get_ha_config()
    if not url or not token:
        return False, "Home Assistant не настроен (HOME_ASSISTANT_URL, HOME_ASSISTANT_TOKEN)."

    try:
        states = await _fetch_states(url, token)
    except Exception as e:
        return False, f"Не удалось подключиться к Home Assistant: {e!s}."

    domain = cmd.get("domain", DOMAIN_LIGHT)
    action = cmd.get("action", "turn_on")
    area_keywords = cmd.get("area_keywords") or []

    entity_ids = _match_entities(states, domain, area_keywords)
    if not entity_ids:
        room = " ".join(area_keywords) if area_keywords else ""
        return False, f"Устройство не найдено{(' в ' + room) if room else ''}. Проверьте названия в HA."

    if action == "set_temperature":
        temp = cmd.get("temperature", 21)
        service = "set_temperature"
        data = {"entity_id": entity_ids, "temperature": temp}
    elif action == "turn_on":
        service = "turn_on"
        data = {"entity_id": entity_ids}
    elif action == "turn_off":
        service = "turn_off"
        data = {"entity_id": entity_ids}
    else:
        return False, "Неизвестная команда."

    try:
        ok = await call_ha_service(url, token, domain, service, data)
    except Exception as e:
        return False, f"Ошибка Home Assistant: {e!s}."

    if not ok:
        return False, "Команда не выполнена."

    # Короткий ответ для голоса
    if action == "set_temperature":
        return True, f"Температура {cmd.get('temperature', 21)} градусов."
    if action == "turn_on":
        return True, "Включила."
    return True, "Выключила."


def ha_reply_text(success: bool, message: str) -> str:
    return message.strip()
