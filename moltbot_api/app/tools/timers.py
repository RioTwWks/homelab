"""
Таймеры, будильники и напоминания.

Поддерживаемые форматы:
- "поставь таймер на 5 минут"
- "будильник на 8:00"
- "напомни через час купить молоко"
- "таймер на 10 минут для яиц"
- "отмени все таймеры"
- "какие таймеры установлены"
"""
import os
import re
import time
from datetime import datetime, timedelta
from typing import Any, Optional, Literal
from zoneinfo import ZoneInfo

from app.redis_cache import RedisCache


_MONTHS_RU = [
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]

_TZ = ZoneInfo("Europe/Moscow")


def _parse_time_delta(text: str) -> Optional[timedelta]:
    """Парсит относительное время: 'через 5 минут', 'на минуту', 'таймер на минуту', 'через час'."""
    t = text.lower()
    
    total_minutes = 0
    total_hours = 0

    # Ищем число + минут/час (однократно, берём первое совпадение)
    m_min = re.search(r"(\d+)\s*минут[уы]?", t)
    m_hr = re.search(r"(\d+)\s*час[аов]?", t)
    if m_min:
        total_minutes = int(m_min.group(1))
    if m_hr:
        total_hours = int(m_hr.group(1))

    # Без числа: "на минуту", "через минуту", "таймер на минуту", "на час", "через час"
    if total_minutes == 0 and re.search(r"(?:на|через)\s+минуту|таймер\s+на\s+минуту", t):
        total_minutes = 1
    if total_hours == 0 and re.search(r"(?:на|через)\s+час\b|таймер\s+на\s+час\b", t):
        total_hours = 1

    if total_minutes == 0 and total_hours == 0:
        return None

    return timedelta(hours=total_hours, minutes=total_minutes)


def _parse_absolute_time(text: str) -> Optional[datetime]:
    """Парсит абсолютное время: '8:00', '8:30', 'завтра в 8:00'."""
    t = text.lower()
    now = datetime.now(_TZ)
    
    # Паттерн: HH:MM или H:MM
    time_match = re.search(r"(\d{1,2}):(\d{2})", text)
    if not time_match:
        return None
    
    hour = int(time_match.group(1))
    minute = int(time_match.group(2))
    
    if not (0 <= hour < 24 and 0 <= minute < 60):
        return None
    
    # Определяем день
    target_date = now.date()
    if "завтра" in t:
        target_date = (now + timedelta(days=1)).date()
    elif "послезавтра" in t:
        target_date = (now + timedelta(days=2)).date()
    elif re.search(r"\d+\s+(январ|феврал|март|апрел|май|июн|июл|август|сентябр|октябр|ноябр|декабр)", t):
        # "15 января" или "15 января 2025"
        for i, month_name in enumerate(_MONTHS_RU, 1):
            if month_name in t:
                day_match = re.search(r"(\d{1,2})\s+" + month_name, t)
                if day_match:
                    day = int(day_match.group(1))
                    year_match = re.search(r"(\d{4})", t)
                    year = int(year_match.group(1)) if year_match else now.year
                    try:
                        target_date = datetime(year, i, day).date()
                    except ValueError:
                        pass
                    break
    
    target_dt = datetime.combine(target_date, datetime.min.time().replace(hour=hour, minute=minute))
    target_dt = _TZ.localize(target_dt) if target_dt.tzinfo is None else target_dt.replace(tzinfo=_TZ)
    
    # Если время уже прошло сегодня, значит завтра
    if target_dt <= now and target_date == now.date():
        target_dt += timedelta(days=1)
    
    return target_dt


def _extract_message(text: str) -> Optional[str]:
    """Извлекает текст напоминания: 'напомни через час купить молоко' -> 'купить молоко'."""
    t = text.lower()
    
    # Убираем команды (в т.ч. "ставь таймер" — разговорная форма)
    prefixes = [
        r"(?:ставь|поставь|установи)\s+таймер\s+",
        r"поставь\s+будильник\s+",
        r"установи\s+будильник\s+",
        r"напомни\s+",
        r"таймер\s+на\s+",
        r"будильник\s+на\s+",
    ]
    for prefix in prefixes:
        t = re.sub(prefix, "", t, flags=re.IGNORECASE)
    
    # Убираем указание времени (без числа и с числом)
    t = re.sub(r"на\s+минуту\.?", "", t)
    t = re.sub(r"на\s+час\b\.?", "", t)
    t = re.sub(r"через\s+минуту\.?", "", t)
    t = re.sub(r"через\s+час\b\.?", "", t)
    t = re.sub(r"через\s+\d+\s*минут[уы]?", "", t)
    t = re.sub(r"через\s+\d+\s*час[аов]?", "", t)
    t = re.sub(r"\d+\s*минут[уы]?", "", t)
    t = re.sub(r"\d+\s*час[аов]?", "", t)
    t = re.sub(r"\d{1,2}:\d{2}", "", t)
    t = re.sub(r"завтра\s+в", "", t)
    t = re.sub(r"для\s+", "", t)
    t = t.strip(" ,.!?")
    
    # Не считать напоминанием артефакты команды ("ставь минуту", "на минуту" и т.п.)
    if len(t) < 3:
        return None
    if re.match(r"^(ставь|поставь|установи|на|через)\s*\.?$", t):
        return None
    # Остаток вроде "ставь 1 минуту", "на 5 минут" — не напоминание
    if re.match(r"^(ставь|поставь|установи)\s+\d*\s*минут", t):
        return None
    if re.match(r"^\d+\s*минут", t) or re.match(r"^\d+\s*час", t):
        return None
    if t in ("минуту", "минуты", "час", "часа", "часов"):
        return None
    # Остаток только указание времени — не напоминание
    if re.match(r"^на\s+минуту\.?$", t) or re.match(r"^на\s+час\.?$", t):
        return None
    if t.strip() in ("на минуту", "на час", "на минуту.", "на час."):
        return None
    
    return t if t else None


def parse_timer_request(text: str) -> Optional[dict[str, Any]]:
    """
    Парсит запрос на таймер/будильник/напоминание.
    
    Возвращает:
    {
        "type": "timer" | "alarm" | "reminder",
        "trigger_at": datetime,
        "message": str | None,
        "duration_seconds": int,
    }
    или None если не распознан.
    """
    t = text.lower()
    
    # Определяем тип
    is_alarm = any(k in t for k in ["будильник", "разбуди"])
    is_reminder = any(k in t for k in ["напомни", "напоминание"])
    timer_type: Literal["timer", "alarm", "reminder"] = "alarm" if is_alarm else ("reminder" if is_reminder else "timer")
    
    # Парсим время
    trigger_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    
    # Сначала пробуем абсолютное время
    trigger_at = _parse_absolute_time(text)
    
    # Если не получилось, пробуем относительное
    if not trigger_at:
        delta = _parse_time_delta(text)
        if delta:
            trigger_at = datetime.now(_TZ) + delta
            duration_seconds = int(delta.total_seconds())
    
    if not trigger_at:
        return None
    
    # Извлекаем сообщение
    message = _extract_message(text)
    
    return {
        "type": timer_type,
        "trigger_at": trigger_at.isoformat(),
        "message": message,
        "duration_seconds": duration_seconds,
    }


def create_timer(
    *,
    session_id: str,
    timer_data: dict[str, Any],
    cache: RedisCache,
) -> dict[str, Any]:
    """Создаёт таймер/будильник/напоминание и сохраняет в Redis."""
    timer_id = f"timer:{session_id}:{int(time.time() * 1000)}"
    
    trigger_at = datetime.fromisoformat(timer_data["trigger_at"])
    now = datetime.now(_TZ)
    
    if trigger_at <= now:
        return {
            "ok": False,
            "error": "Время уже прошло",
        }
    
    # Сохраняем в Redis с TTL до времени срабатывания + 1 час (на случай задержек)
    ttl_seconds = int((trigger_at - now).total_seconds()) + 3600
    
    payload = {
        "id": timer_id,
        "session_id": session_id,
        "type": timer_data["type"],
        "trigger_at": timer_data["trigger_at"],
        "message": timer_data.get("message"),
        "created_at": now.isoformat(),
        "duration_seconds": timer_data.get("duration_seconds"),
    }
    
    cache.set_json(timer_id, payload, ttl_seconds=ttl_seconds)
    
    # Также сохраняем в список таймеров сессии
    list_key = f"timers:list:{session_id}"
    timers = cache.get_json(list_key) or []
    timers.append(timer_id)
    cache.set_json(list_key, timers, ttl_seconds=ttl_seconds)
    
    return {
        "ok": True,
        "timer_id": timer_id,
        "trigger_at": timer_data["trigger_at"],
        "message": timer_data.get("message"),
        "duration_seconds": timer_data.get("duration_seconds"),
        "type": timer_data.get("type", "timer"),
    }


def list_timers(*, session_id: str, cache: RedisCache) -> list[dict[str, Any]]:
    """Возвращает список активных таймеров для сессии."""
    list_key = f"timers:list:{session_id}"
    timer_ids = cache.get_json(list_key) or []
    
    active_timers = []
    now = datetime.now(_TZ)
    
    for timer_id in timer_ids:
        timer_data = cache.get_json(timer_id)
        if not timer_data:
            continue
        
        trigger_at = datetime.fromisoformat(timer_data["trigger_at"])
        if trigger_at > now:
            active_timers.append(timer_data)
    
    # Обновляем список (убираем истёкшие)
    active_ids = [t["id"] for t in active_timers]
    cache.set_json(list_key, active_ids, ttl_seconds=86400 * 7)  # 7 дней
    
    return sorted(active_timers, key=lambda x: x["trigger_at"])


def cancel_timer(*, session_id: str, timer_id: Optional[str], cache: RedisCache) -> dict[str, Any]:
    """Отменяет таймер(ы). Если timer_id=None, отменяет все."""
    if timer_id:
        cache.client.delete(timer_id)
        list_key = f"timers:list:{session_id}"
        timer_ids = cache.get_json(list_key) or []
        if timer_id in timer_ids:
            timer_ids.remove(timer_id)
            cache.set_json(list_key, timer_ids, ttl_seconds=86400 * 7)
        return {"ok": True, "cancelled": [timer_id]}
    else:
        # Отменяем все таймеры сессии
        list_key = f"timers:list:{session_id}"
        timer_ids = cache.get_json(list_key) or []
        for tid in timer_ids:
            cache.client.delete(tid)
        cache.client.delete(list_key)
        return {"ok": True, "cancelled": timer_ids}


def timer_reply_text(timer_data: dict[str, Any], action: str = "created") -> str:
    """Формирует текстовый ответ о таймере."""
    timer_type = timer_data.get("type", "timer")
    trigger_at = datetime.fromisoformat(timer_data["trigger_at"])
    message = timer_data.get("message")
    duration_seconds = timer_data.get("duration_seconds")
    
    def _minute_word(n: int) -> str:
        if n == 1:
            return "минуту"
        if 2 <= n <= 4:
            return "минуты"
        return "минут"

    def _hour_word(n: int) -> str:
        if n == 1:
            return "час"
        if 2 <= n <= 4:
            return "часа"
        return "часов"

    # Используем исходную длительность (а не пересчитываем delta, т.к. прошло время)
    if duration_seconds and duration_seconds > 0:
        total_min = round(duration_seconds / 60)
        if total_min < 60:
            when = f"через {total_min} {_minute_word(total_min)}"
        else:
            hours = total_min // 60
            minutes = total_min % 60
            if minutes > 0:
                when = f"через {hours} {_hour_word(hours)} {minutes} {_minute_word(minutes)}"
            else:
                when = f"через {hours} {_hour_word(hours)}"
    else:
        # Абсолютное время (будильник на HH:MM)
        when = trigger_at.strftime("%H:%M")
    
    type_names = {
        "timer": "Таймер",
        "alarm": "Будильник",
        "reminder": "Напоминание",
    }
    type_name = type_names.get(timer_type, "Таймер")
    
    if action == "created":
        if message:
            return f"{type_name} установлен на {when}. Напоминание: {message}."
        return f"{type_name} установлен на {when}."
    elif action == "cancelled":
        return f"{type_name} отменён."
    else:
        return f"{type_name} на {when}."


def handle_timer_request(
    *,
    user_text: str,
    session_id: str,
    cache: RedisCache,
) -> dict[str, Any]:
    """
    Обрабатывает запрос на таймер/будильник/напоминание.
    
    Возвращает:
    {
        "answer": str,
        "fact_context": str,
        "sources": [],
    }
    """
    t = user_text.lower()
    
    # Проверяем команды на отмену/список
    if any(k in t for k in ["отмени", "удали", "отмена", "сброс"]):
        if "все" in t or "всех" in t:
            result = cancel_timer(session_id=session_id, timer_id=None, cache=cache)
            if result["ok"]:
                count = len(result.get("cancelled", []))
                return {
                    "answer": f"Отменено таймеров: {count}." if count > 0 else "Нет активных таймеров.",
                    "fact_context": f"Отменено таймеров: {count}",
                    "sources": [],
                }
        else:
            # Пробуем найти ID таймера в тексте или отменяем последний
            timers = list_timers(session_id=session_id, cache=cache)
            if timers:
                last_timer = timers[-1]
                result = cancel_timer(session_id=session_id, timer_id=last_timer["id"], cache=cache)
                if result["ok"]:
                    return {
                        "answer": timer_reply_text(last_timer, action="cancelled"),
                        "fact_context": f"Отменён таймер {last_timer['id']}",
                        "sources": [],
                    }
            return {
                "answer": "Не найдено таймеров для отмены.",
                "fact_context": "Запрос на отмену таймера, но активных таймеров нет.",
                "sources": [],
            }
    
    if any(k in t for k in ["какие", "список", "покажи", "есть", "установлен"]):
        timers = list_timers(session_id=session_id, cache=cache)
        if not timers:
            return {
                "answer": "Нет активных таймеров.",
                "fact_context": "Список таймеров пуст.",
                "sources": [],
            }
        
        lines = []
        for i, timer in enumerate(timers, 1):
            trigger_at = datetime.fromisoformat(timer["trigger_at"])
            msg = timer.get("message")
            type_name = {"timer": "Таймер", "alarm": "Будильник", "reminder": "Напоминание"}.get(timer["type"], "Таймер")
            time_str = trigger_at.strftime("%H:%M")
            if msg:
                lines.append(f"{i}. {type_name} на {time_str}: {msg}")
            else:
                lines.append(f"{i}. {type_name} на {time_str}")
        
        return {
            "answer": "Активные таймеры:\n" + "\n".join(lines),
            "fact_context": f"Найдено таймеров: {len(timers)}",
            "sources": [],
        }
    
    # Создание нового таймера
    try:
        timer_data = parse_timer_request(user_text)
    except Exception:
        timer_data = None
    if not timer_data:
        return {
            "answer": "Не удалось распознать время для таймера. Попробуйте: «поставь таймер на 5 минут» или «будильник на 8:00».",
            "fact_context": "Не удалось распознать запрос на таймер.",
            "sources": [],
        }

    try:
        result = create_timer(session_id=session_id, timer_data=timer_data, cache=cache)
    except Exception as e:
        return {
            "answer": "Таймер не удалось сохранить. Проверьте подключение к Redis и попробуйте снова.",
            "fact_context": f"Ошибка Redis при создании таймера: {e}",
            "sources": [],
        }

    if not result.get("ok"):
        return {
            "answer": result.get("error", "Не удалось создать таймер."),
            "fact_context": f"Ошибка создания таймера: {result.get('error')}",
            "sources": [],
        }

    return {
        "answer": timer_reply_text(result, action="created"),
        "fact_context": f"Создан таймер {result['timer_id']}, срабатывание: {result['trigger_at']}",
        "sources": [],
    }
