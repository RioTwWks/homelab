import os
import re
import time
from typing import Any, Optional, Literal

import httpx

from app.redis_cache import RedisCache
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

_MONTHS_RU_GEN = [
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
]


_CITY_RE = re.compile(r"(?:в|во)\s+([а-яА-ЯёЁ\\-\\s]+?)(?:\\?|\\.|!|$)")
_HOURS_RE = re.compile(r"через\\s+(\\d{1,2})\\s*час")
_CITY_STOPWORDS = {
    "сейчас",
    "сегодня",
    "завтра",
    "послезавтра",
    # Weather intent keywords often end up as last token in voice queries
    "погода",
    "погодка",
    "прогноз",
    "температура",
    "температуру",
    "осадки",
    "ветер",
    "неделю",
    "неделя",
    "час",
    "часа",
    "часов",
    "минут",
    "минуту",
    "дня",
    "день",
    "утром",
    "вечером",
    "ночью",
    "днём",
}


def _extract_city_ru(text: str) -> Optional[str]:
    m = _CITY_RE.search(text)
    if m:
        city = m.group(1).strip()
        if len(city) >= 2:
            return city
    # Fallback: last word-ish
    parts = [p.strip(" ,.!?") for p in text.split() if p.strip(" ,.!?")]
    if parts:
        last = parts[-1]
        last_l = last.lower()
        # Extra guard: sometimes voice queries end with generic words like "погода"
        if last_l.startswith("погод") or last_l.startswith("прогноз"):
            return None
        if last_l in _CITY_STOPWORDS:
            return None
        # Avoid treating time phrases as cities ("час", "завтра", etc.)
        if len(last) >= 2 and all(ch.isalpha() or ch in "-ёЁ" for ch in last):
            return last
    return None

def _parse_time_request(text: str) -> tuple[Literal["current", "hourly", "daily", "weekly"], int]:
    """
    Returns (kind, offset):
    - current: offset ignored
    - hourly: offset hours (>=1)
    - daily: offset days (>=1)
    - weekly: offset days (7)
    """
    t = text.lower()
    if "через час" in t:
        return "hourly", 1
    m = _HOURS_RE.search(t)
    if m:
        try:
            h = int(m.group(1))
            if 1 <= h <= 48:
                return "hourly", h
        except Exception:
            pass
    if "послезавтра" in t:
        return "daily", 2
    if "завтра" in t:
        return "daily", 1
    if "через неделю" in t or "на неделю" in t:
        return "weekly", 7
    return "current", 0


def _city_only(display: str, fallback_city: str) -> str:
    """
    Return only the city name for speech (no district/region/country/postcode).
    """
    d = (display or "").strip()
    if not d:
        return fallback_city
    # Display can start with district; best effort: take second token if it contains fallback city.
    parts = [p.strip() for p in d.split(",") if p.strip()]
    if not parts:
        return fallback_city
    # If the fallback city is present in any part, use that.
    fc = (fallback_city or "").strip()
    if fc:
        for p in parts:
            if p.lower() == fc.lower():
                return p
    # Otherwise use the first part (usually city for open-meteo geocode).
    return parts[0]


def _fmt_day_label_ru(now: datetime, *, offset_days: int, target_date_iso: str) -> str:
    if offset_days == 0:
        return "сегодня"
    if offset_days == 1:
        return "завтра"
    if offset_days == 2:
        return "послезавтра"
    try:
        d = datetime.fromisoformat(target_date_iso).date()
        return f"{d.day} {_MONTHS_RU_GEN[d.month - 1]}"
    except Exception:
        return target_date_iso


def _rint(x: Any) -> int | None:
    try:
        return int(round(float(x)))
    except Exception:
        return None


def _fmt_temp_ru(t: Any) -> str:
    v = _rint(t)
    if v is None:
        return "н/д"
    return f"{v}"


def _fmt_wind_ru(ms: Any) -> str:
    v = _rint(ms)
    if v is None:
        return "н/д"
    return f"{v} м/с"


def _deg_c_ru() -> str:
    return "градусов по Цельсию"

def _extract_district_ru(text: str) -> Optional[str]:
    # Very lightweight: "в районе <X>" / "район <X>"
    t = text.lower()
    m = re.search(r"(?:в\\s+районе|район)\\s+([а-яё\\-\\s]{3,60})", t, flags=re.IGNORECASE)
    if m:
        val = m.group(1).strip(" ,.!?")
        return val if val else None
    return None


async def _geocode_nominatim(city: str) -> Optional[tuple[float, float, str]]:
    # For personal use; Nominatim requires a User-Agent.
    url = "https://nominatim.openstreetmap.org/search"
    params = {"format": "json", "q": f"{city}, Россия", "limit": 1, "accept-language": "ru"}
    timeout = httpx.Timeout(15.0, connect=10.0)
    async with httpx.AsyncClient(timeout=timeout, headers={"User-Agent": "moltbot-api/0.1"}) as client:
        r = await client.get(url, params=params)
        r.raise_for_status()
        data = r.json()
        if not data:
            return None
        item = data[0]
        lat = float(item["lat"])
        lon = float(item["lon"])
        display = str(item.get("display_name") or city)
        return lat, lon, display

async def _geocode_nominatim_district(city: str, district: str) -> Optional[tuple[float, float, str]]:
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "format": "json",
        "q": f"{district}, {city}, Россия",
        "limit": 3,
        "accept-language": "ru",
        "addressdetails": 1,
    }
    timeout = httpx.Timeout(15.0, connect=10.0)
    async with httpx.AsyncClient(timeout=timeout, headers={"User-Agent": "moltbot-api/0.1"}) as client:
        r = await client.get(url, params=params)
        r.raise_for_status()
        data = r.json()
        if not data:
            return None
        item = data[0]
        lat = float(item["lat"])
        lon = float(item["lon"])
        display = str(item.get("display_name") or f"{district}, {city}")
        return lat, lon, display

async def _geocode_open_meteo(city: str) -> Optional[tuple[float, float, str]]:
    """
    Open-Meteo geocoding tends to return proper city/admin results (better than POIs),
    which matches our “use administrative center” goal.
    """
    url = "https://geocoding-api.open-meteo.com/v1/search"
    params = {
        "name": city,
        "count": 5,
        "language": "ru",
        "format": "json",
        "country_code": "RU",
    }
    timeout = httpx.Timeout(15.0, connect=10.0)
    async with httpx.AsyncClient(timeout=timeout, headers={"User-Agent": "moltbot-api/0.1"}) as client:
        r = await client.get(url, params=params)
        r.raise_for_status()
        data = r.json()
        results = data.get("results") if isinstance(data, dict) else None
        if not isinstance(results, list) or not results:
            return None

        def score(it: dict[str, Any]) -> tuple[int, float]:
            fc = str(it.get("feature_code") or "")
            importance = float(it.get("importance") or 0.0)
            # Prefer populated places / admin centers
            pref = 0
            if fc in ("PPLC", "PPLA"):
                pref = 3
            elif fc.startswith("PPL"):
                pref = 2
            elif fc.startswith("ADM"):
                pref = 1
            return (pref, importance)

        best = None
        for it in results:
            if not isinstance(it, dict):
                continue
            if best is None or score(it) > score(best):
                best = it
        if not best:
            return None

        lat = float(best["latitude"])
        lon = float(best["longitude"])
        name = str(best.get("name") or city)
        admin1 = best.get("admin1")
        country = best.get("country") or "Россия"
        display = name
        if admin1:
            display = f"{name}, {admin1}, {country}"
        else:
            display = f"{name}, {country}"
        return lat, lon, display


async def _weather_open_meteo(lat: float, lon: float) -> dict[str, Any]:
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,relative_humidity_2m,apparent_temperature,is_day,precipitation,weather_code,wind_speed_10m,wind_direction_10m",
        "hourly": "temperature_2m,apparent_temperature,precipitation,precipitation_probability,weather_code,wind_speed_10m",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max,weather_code,wind_speed_10m_max",
        "wind_speed_unit": "ms",
        "timezone": "Europe/Moscow",
        "forecast_days": 8,
    }
    timeout = httpx.Timeout(20.0, connect=10.0)
    async with httpx.AsyncClient(timeout=timeout, headers={"User-Agent": "moltbot-api/0.1"}) as client:
        r = await client.get(url, params=params)
        r.raise_for_status()
        return r.json()


async def _weather_openweather(city: str, api_key: str) -> dict[str, Any]:
    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {"q": f"{city},RU", "appid": api_key, "units": "metric", "lang": "ru"}
    timeout = httpx.Timeout(20.0, connect=10.0)
    async with httpx.AsyncClient(timeout=timeout, headers={"User-Agent": "moltbot-api/0.1"}) as client:
        r = await client.get(url, params=params)
        r.raise_for_status()
        return r.json()


async def _weather_yandex(lat: float, lon: float, api_key: str) -> dict[str, Any]:
    # Official docs may vary by plan; keep endpoint configurable.
    base = os.getenv("YANDEX_WEATHER_ENDPOINT", "https://api.weather.yandex.ru/v2/informers")
    params = {"lat": lat, "lon": lon, "lang": "ru_RU"}
    headers = {"X-Yandex-Weather-Key": api_key, "User-Agent": "moltbot-api/0.1"}
    timeout = httpx.Timeout(20.0, connect=10.0)
    async with httpx.AsyncClient(timeout=timeout, headers=headers) as client:
        r = await client.get(base, params=params)
        r.raise_for_status()
        return r.json()


async def fetch_weather(
    *,
    user_text: str,
    session_id: str,
    cache: RedisCache,
    default_city: str,
    default_district: str | None,
) -> dict[str, Any]:
    ttl = int(os.getenv("WEATHER_CACHE_TTL_SECONDS", "600"))
    requested_city = _extract_city_ru(user_text)
    city = requested_city or default_city
    district = _extract_district_ru(user_text) or default_district
    kind, offset = _parse_time_request(user_text)
    cache_key = f"weather:v7:{city.lower()}:{(district or '').lower()}:{kind}:{offset}"
    cached = cache.get_json(cache_key)
    if cached:
        return cached

    sources: list[dict[str, Any]] = []
    fact_context = ""
    answer = ""

    try:
        geo = None
        if district:
            geo = await _geocode_nominatim_district(city, district)
            if geo:
                sources.append({"type": "geocode", "provider": "nominatim", "query": f"{district}, {city}", "url": "https://nominatim.openstreetmap.org"})
        if not geo:
            geo = await _geocode_open_meteo(city)
        if not geo:
            # fallback
            geo = await _geocode_nominatim(city)
        if not geo:
            raise RuntimeError("geocode_failed")
        lat, lon, display = geo
        speak_city = _city_only(display, city)
        if not any(s.get("type") == "geocode" for s in sources):
            sources.append(
                {
                    "type": "geocode",
                    "provider": "open-meteo",
                    "query": city,
                    "url": "https://geocoding-api.open-meteo.com",
                }
            )

        ykey = os.getenv("YANDEX_WEATHER_API_KEY", "").strip()
        owm_key = os.getenv("OPENWEATHER_API_KEY", "").strip()

        # NOTE: time-based forecast is implemented for Open-Meteo (no key required).
        # For keyed providers we keep "current" behavior for now.
        if ykey and kind == "current":
            data = await _weather_yandex(lat, lon, ykey)
            sources.append({"type": "weather", "provider": "yandex", "endpoint": os.getenv("YANDEX_WEATHER_ENDPOINT", "https://api.weather.yandex.ru/v2/informers")})

            # Typical payload has "fact" section
            fact = data.get("fact", {}) if isinstance(data, dict) else {}
            temp = fact.get("temp")
            feels = fact.get("feels_like")
            wind = fact.get("wind_speed")
            cond = fact.get("condition")
            fact_context = (
                f"Локация: {display}\n"
                f"Температура: {temp}°C\n"
                f"Ощущается как: {feels}°C\n"
                f"Ветер: {wind} м/с\n"
                f"Состояние: {cond}\n"
            )
            answer = (
                f"{speak_city}, сейчас: {_fmt_temp_ru(temp)} {_deg_c_ru()} (ощущается {_fmt_temp_ru(feels)}), "
                f"ветер {_fmt_wind_ru(wind)}, {cond}"
            )
        elif owm_key and kind == "current":
            data = await _weather_openweather(city, owm_key)
            sources.append({"type": "weather", "provider": "openweathermap", "endpoint": "https://api.openweathermap.org/data/2.5/weather"})
            main = data.get("main", {})
            wind = data.get("wind", {})
            weather = (data.get("weather") or [{}])[0]
            desc = weather.get("description")
            fact_context = (
                f"Локация: {data.get('name') or display}\n"
                f"Температура: {main.get('temp')}°C\n"
                f"Ощущается как: {main.get('feels_like')}°C\n"
                f"Влажность: {main.get('humidity')}%\n"
                f"Ветер: {wind.get('speed')} м/с\n"
                f"Описание: {desc}\n"
            )
            answer = (
                f"{speak_city}, сейчас: {_fmt_temp_ru(main.get('temp'))} {_deg_c_ru()} (ощущается {_fmt_temp_ru(main.get('feels_like'))}), "
                f"ветер {_fmt_wind_ru(wind.get('speed'))}, {desc}"
            )
        else:
            data = await _weather_open_meteo(lat, lon)
            sources.append({"type": "weather", "provider": "open-meteo", "endpoint": "https://api.open-meteo.com/v1/forecast"})
            tz = ZoneInfo("Europe/Moscow")
            now = datetime.now(tz)
            cur = data.get("current", {}) if isinstance(data, dict) else {}

            def wmo_ru(code: Any) -> str:
                try:
                    c = int(code)
                except Exception:
                    return "н/д"
                # WMO weather interpretation codes (Open-Meteo).
                # See: https://open-meteo.com/en/docs (weather_code)
                return {
                    0: "ясно",
                    1: "в основном ясно",
                    2: "переменная облачность",
                    3: "пасмурно",
                    45: "туман",
                    48: "изморозь (туман)",
                    51: "морось",
                    53: "морось",
                    55: "сильная морось",
                    56: "переохлаждённая морось",
                    57: "сильная переохлаждённая морось",
                    61: "дождь",
                    63: "дождь",
                    65: "сильный дождь",
                    66: "переохлаждённый дождь",
                    67: "сильный переохлаждённый дождь",
                    71: "снег",
                    73: "снег",
                    75: "сильный снег",
                    77: "снежные зёрна",
                    80: "ливни",
                    81: "ливни",
                    82: "сильные ливни",
                    85: "снегопад",
                    86: "сильный снегопад",
                    95: "гроза",
                    96: "гроза с градом",
                    99: "сильная гроза с градом",
                }.get(c, f"код {c}")

            def fmt_conditions(precip_mm: Any, prob: Any | None, code: Any) -> str:
                cond = wmo_ru(code)
                # If it's a precipitation-type condition, show it; otherwise show cloudiness/clear.
                try:
                    p = float(precip_mm) if precip_mm is not None else 0.0
                except Exception:
                    p = 0.0
                is_precip = any(k in cond for k in ["дожд", "снег", "морос", "лив", "гроза", "град", "зёрна", "туман"])
                if is_precip:
                    if prob is not None:
                        return f"{cond}, вероятность {prob}%"
                    return cond
                # No precip type in code → show cloudiness/clear, plus note no precipitation if we know it.
                if p == 0.0:
                    return cond
                return cond

            if kind == "current":
                precip = cur.get("precipitation")
                code = cur.get("weather_code")
                fact_context = (
                    f"Локация: {display}\n"
                    f"Температура: {cur.get('temperature_2m')}°C\n"
                    f"Ощущается как: {cur.get('apparent_temperature')}°C\n"
                    f"Влажность: {cur.get('relative_humidity_2m')}%\n"
                    f"Осадки: {precip} мм\n"
                    f"Ветер: {cur.get('wind_speed_10m')} м/с\n"
                    f"Условия: {wmo_ru(code)}\n"
                )
                answer = (
                    f"{speak_city}, сейчас: {_fmt_temp_ru(cur.get('temperature_2m'))} {_deg_c_ru()} "
                    f"(ощущается {_fmt_temp_ru(cur.get('apparent_temperature'))}), "
                    f"ветер {_fmt_wind_ru(cur.get('wind_speed_10m'))}, {fmt_conditions(precip, None, code)}"
                )
            elif kind == "hourly":
                target = now + timedelta(hours=offset)
                hourly = data.get("hourly", {})
                times = (hourly.get("time") or [])
                temps = (hourly.get("temperature_2m") or [])
                feels = (hourly.get("apparent_temperature") or [])
                precip = (hourly.get("precipitation") or [])
                prob = (hourly.get("precipitation_probability") or [])
                codes = (hourly.get("weather_code") or [])
                wind = (hourly.get("wind_speed_10m") or [])

                def parse_local(ts: str) -> datetime:
                    # Open-Meteo returns local time without offset (timezone param applied)
                    return datetime.fromisoformat(ts).replace(tzinfo=tz)

                idx = None
                for i, ts in enumerate(times):
                    try:
                        if parse_local(ts) >= target:
                            idx = i
                            break
                    except Exception:
                        continue
                if idx is None:
                    idx = min(len(times) - 1, 0)
                ts = times[idx] if idx is not None and idx < len(times) else None
                code = codes[idx] if idx is not None and idx < len(codes) else None
                pprob = prob[idx] if idx is not None and idx < len(prob) else None
                # Speech-friendly: "через N часов"
                when = f"через {offset} ч."
                answer = (
                    f"{speak_city}, {when}: {_fmt_temp_ru(temps[idx])} {_deg_c_ru()} (ощущается {_fmt_temp_ru(feels[idx])}), "
                    f"ветер {_fmt_wind_ru(wind[idx])}, {fmt_conditions(precip[idx], pprob, code)}"
                )
                fact_context = f"Запрос: через {offset} ч. Локация: {display}. Время: {ts}."
            elif kind == "daily":
                target_date = (now.date() + timedelta(days=offset)).isoformat()
                daily = data.get("daily", {})
                days = (daily.get("time") or [])
                tmax = (daily.get("temperature_2m_max") or [])
                tmin = (daily.get("temperature_2m_min") or [])
                psum = (daily.get("precipitation_sum") or [])
                pprob = (daily.get("precipitation_probability_max") or [])
                codes = (daily.get("weather_code") or [])
                wmax = (daily.get("wind_speed_10m_max") or [])

                idx = None
                for i, d in enumerate(days):
                    if d == target_date:
                        idx = i
                        break
                if idx is None:
                    idx = 0

                code = codes[idx] if idx is not None and idx < len(codes) else None
                day_label = _fmt_day_label_ru(now, offset_days=offset, target_date_iso=target_date)
                answer = (
                    f"{speak_city}, {day_label}: днём {_fmt_temp_ru(tmax[idx])}, ночью {_fmt_temp_ru(tmin[idx])} {_deg_c_ru()}, "
                    f"ветер до {_fmt_wind_ru(wmax[idx])}, {fmt_conditions(psum[idx], pprob[idx] if idx < len(pprob) else None, code)}"
                )
                fact_context = f"Запрос: завтра/дата+{offset}. Локация: {display}. Дата: {target_date}."
            else:  # weekly
                daily = data.get("daily", {})
                days = (daily.get("time") or [])
                tmax = (daily.get("temperature_2m_max") or [])
                tmin = (daily.get("temperature_2m_min") or [])
                psum = (daily.get("precipitation_sum") or [])
                codes = (daily.get("weather_code") or [])
                # Keep it readable (7 lines)
                lines = []
                for i in range(min(7, len(days))):
                    # Date → "D месяц"
                    try:
                        d = datetime.fromisoformat(days[i]).date()
                        dlab = f"{d.day} {_MONTHS_RU_GEN[d.month - 1]}"
                    except Exception:
                        dlab = str(days[i])
                    lines.append(
                        f"{dlab}: днём {_fmt_temp_ru(tmax[i])}, ночью {_fmt_temp_ru(tmin[i])} {_deg_c_ru()}, {wmo_ru(codes[i] if i < len(codes) else None)}"
                    )
                answer = f"{speak_city} (на неделю):\n" + "\n".join(lines)
                fact_context = f"Запрос: на неделю. Локация: {display}."
    except Exception:
        fact_context = f"Не удалось получить погоду для запроса: {city}"
        answer = fact_context

    payload = {
        "answer": (answer or fact_context).strip(),
        "fact_context": fact_context.strip(),
        "sources": sources,
        "fetched_at_unix": int(time.time()),
    }
    cache.set_json(cache_key, payload, ttl_seconds=ttl)
    return payload

