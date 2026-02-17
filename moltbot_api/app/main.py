import os
import time
from typing import Any, Literal
import json
import re

import httpx
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.ollama_client import OllamaClient
from app.redis_cache import RedisCache
from app.tools.news import fetch_russian_news
from app.tools.weather import fetch_weather
from app.tools.versions import fetch_latest_version
from app.tools.web_search import fetch_web_search
from app.tools.media_control import parse_media_command, media_reply_text
from app.tools.home_assistant import (
    is_ha_configured,
    parse_ha_command,
    execute_ha_command,
    ha_reply_text,
)
from app.tools.timers import handle_timer_request


app = FastAPI(title="moltbot-api", version="0.1.0")


class ChatRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    session_id: str = Field(default="default", max_length=128)
    mode: Literal["auto", "fast", "chat"] = "auto"


class ChatResponse(BaseModel):
    reply_text: str
    intent: str
    used_model: str
    sources: list[dict[str, Any]] = []
    timings_ms: dict[str, int] = {}


def detect_intent_ru(text: str) -> str:
    t = text.lower()
    if any(k in t for k in ["погода", "ветер", "осадки", "прогноз", "на улице"]):
        return "weather"
    # Установка температуры в доме (климат), не погода
    if "температур" in t and (
        "поставь" in t or "установи" in t or re.search(r"\d+\s*градус|температур[ау]?\s*\d+", t)
    ):
        return "command"
    if "температур" in t:
        return "weather"
    if any(k in t for k in ["новост", "что нового", "сводка", "дай новости"]):
        return "news"
    if any(k in t for k in ["последняя версия", "latest version", "релиз", "release"]):
        return "version"
    if any(k in t for k in ["таймер", "будильник", "напомни", "напоминание", "разбуди"]):
        return "timer"
    if any(k in t for k in ["включи", "выключи", "сделай", "открой", "запусти", "свет"]):
        return "command"
    return "chat"

def should_use_chat_model(text: str, intent: str) -> bool:
    t = text.lower()
    if any(k in t for k in ["подробно", "объясни", "почему", "развернуто", "сравни", "плюсы и минусы"]):
        return True
    # For news/weather we keep default fast unless user explicitly asks for depth.
    if intent not in ("news", "weather") and len(text) > 220:
        return True
    # Most “tool” intents do not need the bigger model.
    if intent in ("news", "weather", "version", "command", "timer"):
        return False
    return False

def is_probably_math_question(text: str) -> bool:
    t = text.lower()
    if any(k in t for k in ["+", "-", "*", "/", "=", "×", "÷"]):
        return True
    if any(k in t for k in ["плюс", "минус", "умнож", "дел", "сколько будет"]):
        return True
    # Simple pattern: contains digits and arithmetic-ish words
    if any(ch.isdigit() for ch in t) and any(k in t for k in ["плюс", "минус", "умнож", "дел", "+", "-", "*", "/"]):
        return True
    return False

def needs_web_lookup_hint(text: str, intent: str) -> bool:
    # Heuristic: user asks for an exact count/number but we don't have a web tool for it.
    t = text.lower()
    if intent in ("weather", "news", "version", "timer"):
        return False
    if "сколько" in t and not is_probably_math_question(text):
        return True
    if "точное число" in t:
        return True
    return False

def _looks_factual_question(text: str) -> bool:
    """True if the question is likely asking for a fact (number, date, place) that needs web search."""
    t = text.lower()
    triggers = (
        "сколько", "какое количество", "какая числен", "когда основан", "когда открыт",
        "сколько лет", "сколько человек", "сколько животных", "где находится",
        "когда произошло", "кто такой", "что такое",
    )
    return any(trigger in t for trigger in triggers)

def _is_unknown_answer(answer: str) -> bool:
    """True if the model effectively said it doesn't know."""
    if not answer:
        return True
    t = answer.lower()
    unknown_phrases = ("не знаю", "не уверен", "нет информации", "не могу", "не имею", "не знаю.")
    return any(p in t for p in unknown_phrases)

def _parse_json_reply(raw: str) -> dict[str, Any] | None:
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except Exception:
        return None

def _format_schema_for_intent(intent: str) -> dict[str, Any] | None:
    if intent == "weather":
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": {"answer": {"type": "string", "maxLength": 140}},
            "required": ["answer"],
        }
    if intent == "version":
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": {"answer": {"type": "string", "maxLength": 500}},
            "required": ["answer"],
        }
    if intent == "news":
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "items": {
                    "type": "array",
                    "minItems": 3,
                    "maxItems": 5,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "summary": {"type": "string", "maxLength": 140},
                            "url": {"type": "string", "maxLength": 500},
                        },
                        "required": ["summary", "url"],
                    },
                }
            },
            "required": ["items"],
        }
    return None


def _web_decision_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "answer": {"type": "string", "maxLength": 700},
            "need_search": {"type": "boolean"},
            "search_query": {"type": "string", "maxLength": 180},
            "provider": {"type": "string", "maxLength": 16},
        },
        "required": ["answer", "need_search", "search_query", "provider"],
    }


def _env_web_provider() -> str:
    # off | searxng | ddg | both
    return os.getenv("WEB_SEARCH_PROVIDER", "off").strip().lower()


_URL_RE = re.compile(r"https?://\\S+")


def _strip_urls(text: str) -> str:
    if not text:
        return ""
    t = _URL_RE.sub("", text)
    # Collapse whitespace around removed URLs/dashes.
    t = re.sub(r"[ \\t]+", " ", t)
    t = re.sub(r"\\s+\\n", "\n", t)
    return t.strip()


@app.get("/healthz")
def healthz() -> dict[str, Any]:
    return {"ok": True, "ts": int(time.time())}

@app.get("/")
def root() -> dict[str, Any]:
    return {
        "name": "moltbot-api",
        "ok": True,
        "paths": {
            "health": "/healthz",
            "docs": "/docs",
            "chat": "/v1/chat",
            "chat_stream": "/v1/chat/stream",
            "system_status": "/v1/system/status",
            "system_services": "/v1/system/services",
        },
    }


@app.get("/v1/system/status")
async def system_status() -> dict[str, Any]:
    """Lightweight status: check reachability of known backend services."""
    import asyncio

    checks: dict[str, str] = {}

    async def _probe(name: str, url: str) -> None:
        try:
            async with httpx.AsyncClient(timeout=3.0) as c:
                r = await c.get(url)
                checks[name] = "ok" if r.status_code < 500 else f"http {r.status_code}"
        except Exception as exc:
            checks[name] = f"error: {type(exc).__name__}"

    media_api = os.getenv("MEDIA_API_BASE_URL", "").strip()
    ha_url = os.getenv("HOME_ASSISTANT_URL", "").strip()
    ha_token = os.getenv("HOME_ASSISTANT_TOKEN", "").strip()
    ollama_url = os.getenv("OLLAMA_BASE_URL", "").strip()

    tasks = []
    # Redis
    try:
        cache = RedisCache.from_env()
        cache.client.ping()
        checks["redis"] = "ok"
    except Exception as exc:
        checks["redis"] = f"error: {type(exc).__name__}"

    if media_api:
        tasks.append(_probe("media-api", f"{media_api.rstrip('/')}/healthz"))
    if ha_url and ha_token:
        tasks.append(_probe("home-assistant", f"{ha_url.rstrip('/')}/api/"))
    if ollama_url:
        tasks.append(_probe("ollama", f"{ollama_url.rstrip('/')}/api/tags"))

    if tasks:
        await asyncio.gather(*tasks)

    return {
        "ok": True,
        "ts": int(time.time()),
        "services": checks,
        "models": {
            "fast": os.getenv("OLLAMA_MODEL_FAST", ""),
            "chat": os.getenv("OLLAMA_MODEL_CHAT", ""),
        },
    }


class ServiceProbeItem(BaseModel):
    name: str = Field(..., max_length=64)
    url: str | None = Field(default=None, max_length=512)


@app.post("/v1/system/services")
async def probe_services(req: list[ServiceProbeItem]) -> dict[str, Any]:
    """Probe arbitrary service URLs; returns { name: "ok" | "error: ..." } for dashboard.
    Built-in names with empty url: redis (ping), ollama (OLLAMA_BASE_URL/api/tags)."""
    import asyncio

    results: dict[str, str] = {}

    async def _probe(item: ServiceProbeItem) -> None:
        url = (item.url or "").strip()
        name = (item.name or "").strip().lower()

        # Built-in: redis — ping via RedisCache
        if not url and name == "redis":
            try:
                cache = RedisCache.from_env()
                cache.client.ping()
                results[item.name] = "ok"
            except Exception as exc:
                results[item.name] = f"error: {type(exc).__name__}"
            return

        # Built-in: ollama — GET from OLLAMA_BASE_URL
        if not url and name == "ollama":
            ollama_url = os.getenv("OLLAMA_BASE_URL", "").strip()
            if not ollama_url:
                results[item.name] = "error: OLLAMA_BASE_URL not set"
                return
            url = f"{ollama_url.rstrip('/')}/api/tags"

        if not url:
            results[item.name] = "skip"
            return
        try:
            async with httpx.AsyncClient(timeout=3.0) as c:
                r = await c.get(url)
                results[item.name] = "ok" if r.status_code < 500 else f"http {r.status_code}"
        except Exception as exc:
            results[item.name] = f"error: {type(exc).__name__}"

    await asyncio.gather(*(_probe(item) for item in req[:64]))
    return {"ok": True, "ts": int(time.time()), "services": results}


class WeatherSettings(BaseModel):
    session_id: str = Field(default="default", max_length=128)
    city: str | None = Field(default=None, max_length=120)
    district: str | None = Field(default=None, max_length=120, description="Optional: район/округ внутри города")

def _settings_key_weather(session_id: str) -> str:
    return f"settings:weather:v1:{session_id}"

@app.get("/v1/settings/weather")
def get_weather_settings(session_id: str = "default") -> dict[str, Any]:
    cache = RedisCache.from_env()
    data = cache.get_json(_settings_key_weather(session_id)) or {}
    return {"session_id": session_id, "city": data.get("city"), "district": data.get("district")}

@app.post("/v1/settings/weather")
def set_weather_settings(req: WeatherSettings) -> dict[str, Any]:
    cache = RedisCache.from_env()
    payload = {"city": req.city, "district": req.district}
    # Persist “forever” (1 year). Can be changed later.
    cache.set_json(_settings_key_weather(req.session_id), payload, ttl_seconds=365 * 24 * 3600)
    return {"ok": True, "session_id": req.session_id, **payload}


@app.post("/v1/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    allow_internet = os.getenv("ALLOW_INTERNET_TOOLS", "true").lower() in ("1", "true", "yes", "y")

    t0 = time.perf_counter()
    cache = RedisCache.from_env()
    ollama = OllamaClient.from_env()

    intent = detect_intent_ru(req.text)
    sources: list[dict[str, Any]] = []
    fact_context = ""
    tool_ms = 0
    tool_answer: str | None = None
    web_ms = 0

    # Media: пробуем выполнить медиа-команду через media-api вне зависимости от intent
    media_cmd = parse_media_command(req.text)
    media_api_base = os.getenv("MEDIA_API_BASE_URL", "").strip()
    if media_cmd and media_api_base:
        t_media = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.post(
                    f"{media_api_base.rstrip('/')}/v1/command",
                    json=media_cmd,
                )
                r.raise_for_status()
        except Exception:
            # Даже если executor недоступен, лучше всё равно вернуть голосовой ответ
            pass
        media_ms = int((time.perf_counter() - t_media) * 1000)
        total_ms = int((time.perf_counter() - t0) * 1000)
        return ChatResponse(
            reply_text=media_reply_text(media_cmd),
            intent=intent if intent == "command" else "command",
            used_model="media",
            sources=[],
            timings_ms={"tools": media_ms, "llm": 0, "total": total_ms},
        )

    # Умный дом: команды свет/климат через Home Assistant API
    ha_cmd = parse_ha_command(req.text)
    if ha_cmd and is_ha_configured() and intent == "command":
        t_ha = time.perf_counter()
        ha_ok, ha_message = await execute_ha_command(ha_cmd)
        ha_ms = int((time.perf_counter() - t_ha) * 1000)
        total_ms = int((time.perf_counter() - t0) * 1000)
        return ChatResponse(
            reply_text=ha_reply_text(ha_ok, ha_message),
            intent="command",
            used_model="ha",
            sources=[],
            timings_ms={"tools": ha_ms, "llm": 0, "total": total_ms},
        )

    # Tools: fetch facts first, then generate a Russian answer using facts.
    if intent == "news":
        if not allow_internet:
            fact_context = "Интернет-доступ отключён (ALLOW_INTERNET_TOOLS=false)."
        else:
            t1 = time.perf_counter()
            news = await fetch_russian_news(cache=cache)
            tool_ms = int((time.perf_counter() - t1) * 1000)
            sources = news["sources"]
            fact_context = news.get("llm_fact_context") or news["fact_context"]
            tool_answer = news.get("answer")

    elif intent == "weather":
        if not allow_internet:
            fact_context = "Интернет-доступ отключён (ALLOW_INTERNET_TOOLS=false)."
        else:
            t1 = time.perf_counter()
            settings = cache.get_json(_settings_key_weather(req.session_id)) or {}
            w = await fetch_weather(
                user_text=req.text,
                session_id=req.session_id,
                cache=cache,
                default_city=(settings.get("city") or os.getenv("DEFAULT_WEATHER_CITY") or "Новосибирск"),
                default_district=(settings.get("district") or os.getenv("DEFAULT_WEATHER_DISTRICT") or None),
            )
            tool_ms = int((time.perf_counter() - t1) * 1000)
            sources = w["sources"]
            fact_context = w["fact_context"]
            tool_answer = w.get("answer")

    elif intent == "version":
        if not allow_internet:
            fact_context = "Интернет-доступ отключён (ALLOW_INTERNET_TOOLS=false)."
        else:
            t1 = time.perf_counter()
            v = await fetch_latest_version(user_text=req.text, cache=cache)
            tool_ms = int((time.perf_counter() - t1) * 1000)
            sources = v["sources"]
            fact_context = v["fact_context"]

    elif intent == "timer":
        t1 = time.perf_counter()
        try:
            timer_result = handle_timer_request(
                user_text=req.text,
                session_id=req.session_id,
                cache=cache,
            )
            sources = timer_result.get("sources", [])
            fact_context = timer_result.get("fact_context", "")
            tool_answer = timer_result.get("answer") or ""
        except Exception as e:
            tool_answer = "Не удалось установить таймер. Попробуйте ещё раз."
            fact_context = f"Ошибка таймера: {e}"
            sources = []
        tool_ms = int((time.perf_counter() - t1) * 1000)

    web_provider = _env_web_provider()

    system = (
        "Ты — домашний голосовой ассистент.\n"
        "Отвечай на русском.\n"
        "ПРАВИЛА:\n"
        "- Пиши только итоговый ответ. Не показывай рассуждения, план, самопроверку. Не начинай с \"Хорошо\".\n"
        "- Никогда не упоминай слова FACTS/контекст/промпт/инструкция в ответе.\n"
        "- Не выдумывай факты. Если не уверен — прямо скажи \"Не знаю\" и предложи, что можно сделать дальше.\n"
        "- Если нужно уточнение — задай один короткий вопрос."
    )

    user = req.text.strip()
    if fact_context:
        user = f"{user}\n\nFACTS:\n{fact_context}"

    model_choice = req.mode
    if model_choice == "auto":
        model_choice = "chat" if should_use_chat_model(req.text, intent) else "fast"

    # Fast path: for simple tool intents return deterministic tool answer (no LLM latency)
    if model_choice == "fast" and intent in ("weather", "timer") and tool_answer:
        total_ms = int((time.perf_counter() - t0) * 1000)
        return ChatResponse(
            reply_text=str(tool_answer).strip(),
            intent=intent,
            used_model="tool-only",
            sources=sources,
            timings_ms={"tools": tool_ms, "llm": 0, "total": total_ms},
        )

    model = ollama.model_fast if model_choice == "fast" else ollama.model_chat

    # Structured outputs help avoid verbose “reasoning” text in content.
    response_format = _format_schema_for_intent(intent)
    if intent in ("chat", "command"):
        response_format = {
            "type": "object",
            "additionalProperties": False,
            "properties": {"answer": {"type": "string", "maxLength": 700}},
            "required": ["answer"],
        }
        if needs_web_lookup_hint(req.text, intent):
            # Override: prefer honesty to hallucination.
            system = (
                "Верни ТОЛЬКО валидный JSON по схеме: {answer:string}.\n"
                "answer: если пользователь просит точное число/количество, а у тебя нет актуальных данных,\n"
                "скажи, что точное число требует веб-поиска/официального источника, и предложи найти в интернете.\n"
                "Никаких рассуждений. Не выдумывай.\n"
            )
        else:
            system = (
                "Верни ТОЛЬКО валидный JSON по схеме: {answer:string}.\n"
                "answer: короткий итоговый ответ на русском, без рассуждений.\n"
                "Если не уверен — скажи \"Не знаю\" и предложи уточнить/проверить источник.\n"
                "Никогда не упоминай FACTS/контекст/промпт.\n"
            )

    num_predict_override = 512 if intent == "news" else 256
    if intent == "news":
        system = (
            "Ты — локальный голосовой ассистент.\n"
            "Сформируй сводку новостей на русском.\n"
            "Верни ТОЛЬКО валидный JSON по схеме: {items:[{summary,url}]}.\n"
            "items: 5 пунктов (если фактов меньше — меньше).\n"
            "summary: 8–14 слов, без ссылок.\n"
            "url: ссылка строго из FACTS.\n"
            "Используй только FACTS, не выдумывай."
        )
    if intent == "weather":
        system = (
            "Ты — локальный голосовой ассистент.\n"
            "Верни ТОЛЬКО валидный JSON по схеме: {answer:string}.\n"
            "answer: одна строка на русском (температура, ощущается, ветер/осадки если есть).\n"
            "Используй только факты из FACTS, не выдумывай."
        )
    elif intent == "version":
        system = (
            "Ты — локальный голосовой ассистент.\n"
            "Верни ТОЛЬКО валидный JSON по схеме: {answer:string}.\n"
            "answer: 2–4 короткие строки на русском.\n"
            "Используй только факты из FACTS, не выдумывай."
        )

    # Optional: for open-ended chat, if model is unsure → do web lookup (SearxNG / DDG IA).
    # This is intentionally gated by WEB_SEARCH_PROVIDER to avoid surprise internet calls.
    if intent == "chat" and allow_internet and web_provider in ("searxng", "ddg", "both"):
        # Step 1: model decides whether to search.
        decide_system = (
            "Верни ТОЛЬКО валидный JSON по схеме:\n"
            "{answer:string, need_search:boolean, search_query:string, provider:string}.\n"
            "Правила:\n"
            "- Вопросы о числах, количествах, датах, фактах о местах/организациях/событиях (сколько, когда, где, какой) — если у тебя нет точных данных, обязательно need_search=true, answer=\"\", search_query=короткий запрос 3–12 слов.\n"
            "- Если уверен в ответе и он не требует актуальных данных — need_search=false, answer=короткий ответ.\n"
            "- Если не уверен или нужен свежий факт — need_search=true, answer=\"\", search_query=поисковый запрос.\n"
            "- Не отвечай «Не знаю» в answer, если ответ можно найти поиском — ставь need_search=true.\n"
            "- provider: один из searxng | ddg | both. Только JSON, без рассуждений."
        )
        decide_user = req.text.strip()
        t_decide = time.perf_counter()
        raw_decide = await ollama.chat(
            model=ollama.model_fast,
            system=decide_system,
            user=decide_user,
            session_id=req.session_id,
            mode="fast",
            response_format=_web_decision_schema(),
            num_predict_override=180,
        )
        decide_ms = int((time.perf_counter() - t_decide) * 1000)

        decide = _parse_json_reply(raw_decide) or {}
        need_search = bool(decide.get("need_search"))
        search_query = str(decide.get("search_query") or "").strip()
        provider_model = str(decide.get("provider") or "").strip().lower()
        # Provider is chosen by config, not by the model (predictable + easier to compare).
        provider = web_provider
        if provider == "both" and provider_model in ("searxng", "ddg", "both"):
            provider = provider_model

        # Fallback: factual question + model said "don't know" → always search (ignore model's need_search/search_query)
        answer_preview = (decide.get("answer") or "").strip().lower()
        if _looks_factual_question(decide_user) and _is_unknown_answer(answer_preview):
            need_search = True
            search_query = decide_user[:200].strip()
        # Fallback: model set need_search=true but left search_query empty — use question as query
        elif need_search and not search_query and _looks_factual_question(decide_user):
            search_query = decide_user[:200].strip()

        if need_search and search_query:
            t_ws = time.perf_counter()
            max_results = int(os.getenv("WEB_SEARCH_MAX_RESULTS", "6"))
            ws = await fetch_web_search(
                cache=cache,
                query=search_query,
                provider=provider,  # type: ignore[arg-type]
                lang=os.getenv("WEB_SEARCH_LANGUAGE", "ru"),
                max_results=max_results,
            )
            web_ms = int((time.perf_counter() - t_ws) * 1000)
            sources.extend(ws.get("sources") or [])
            fact_context = (ws.get("fact_context") or "").strip()
            # No real results (only "WEB_SEARCH... Query:..." lines, no [1] [2] entries) → don't ask LLM, return hint
            has_results = "[1]" in fact_context or "InstantAnswer:" in fact_context
            if not has_results or len(fact_context) < 80:
                total_ms = int((time.perf_counter() - t0) * 1000)
                return ChatResponse(
                    reply_text="Поиск не дал результатов. Запусти SearxNG: docker compose --profile search up -d",
                    intent=intent,
                    used_model=ollama.model_fast,
                    sources=sources,
                    timings_ms={"tools": tool_ms, "web": web_ms, "llm": decide_ms, "total": total_ms},
                )
            # Step 2: ask model to answer using only web facts.
            system = (
                "Верни ТОЛЬКО валидный JSON по схеме: {answer:string}.\n"
                "answer: краткий ответ на русском по материалам из FACTS. Не вставляй URL.\n"
                "Если в фактах есть подходящая информация — сформулируй ответ (можно приблизительно).\n"
                "Если в FACTS разные числа по одному вопросу — предпочитай данные из официального источника (официальный сайт, страница организации в соцсетях) или более свежие.\n"
                "Скажи \"Не знаю\" только если в FACTS вообще нет ничего по теме вопроса."
            )
            user = f"{req.text.strip()}\n\nFACTS:\n{fact_context}"
            response_format = {
                "type": "object",
                "additionalProperties": False,
                "properties": {"answer": {"type": "string", "maxLength": 700}},
                "required": ["answer"],
            }
            model = ollama.model_chat if model_choice == "chat" else ollama.model_fast
            t2 = time.perf_counter()
            raw_reply = await ollama.chat(
                model=model,
                system=system,
                user=user,
                session_id=req.session_id,
                mode=model_choice,
                response_format=response_format,
                num_predict_override=320,
            )
            llm_ms = int((time.perf_counter() - t2) * 1000) + decide_ms
            parsed = _parse_json_reply(raw_reply)
            reply = parsed.get("answer", "").strip() if isinstance(parsed, dict) else str(raw_reply).strip()
            total_ms = int((time.perf_counter() - t0) * 1000)
            return ChatResponse(
                reply_text=reply,
                intent=intent,
                used_model=model,
                sources=sources,
                timings_ms={"tools": tool_ms, "web": web_ms, "llm": llm_ms, "total": total_ms},
            )

    t2 = time.perf_counter()
    raw_reply = await ollama.chat(
        model=model,
        system=system,
        user=user,
        session_id=req.session_id,
        mode=model_choice,
        response_format=response_format,
        num_predict_override=num_predict_override,
    )
    llm_ms = int((time.perf_counter() - t2) * 1000)

    reply = raw_reply
    if response_format is not None:
        parsed = _parse_json_reply(raw_reply)
        if intent == "weather" and parsed and isinstance(parsed.get("answer"), str):
            reply = parsed["answer"].strip()
        elif intent == "version" and parsed and isinstance(parsed.get("answer"), str):
            reply = parsed["answer"].strip()
        elif intent == "news" and parsed and isinstance(parsed.get("items"), list):
            lines: list[str] = []
            for it in parsed["items"][:5]:
                if not isinstance(it, dict):
                    continue
                summary = it.get("summary")
                url = it.get("url")
                if isinstance(summary, str) and isinstance(url, str) and summary.strip() and url.strip():
                    # Voice-friendly: do not speak URLs.
                    lines.append(f"- {summary.strip()}")
            reply = "\n".join(lines) if lines else (tool_answer or "Не удалось сформировать сводку новостей.")
        elif intent == "news":
            # If model returned invalid JSON, fall back to tool digest instead of partial output.
            reply = tool_answer or "Не удалось сформировать сводку новостей."
        elif intent in ("chat", "command") and parsed and isinstance(parsed.get("answer"), str):
            reply = parsed["answer"].strip()

    total_ms = int((time.perf_counter() - t0) * 1000)

    # Safety: strip URLs from news replies (even if model leaked them).
    if intent == "news":
        reply = _strip_urls(reply)

    return ChatResponse(
        reply_text=reply,
        intent=intent,
        used_model=model,
        sources=sources,
        timings_ms={"tools": tool_ms, "llm": llm_ms, "total": total_ms},
    )


async def _chat_stream_events(req: ChatRequest):
    """Async generator yielding SSE event dicts: {chunk} or {done, reply_text, intent, used_model, sources, timings_ms}."""
    allow_internet = os.getenv("ALLOW_INTERNET_TOOLS", "true").lower() in ("1", "true", "yes", "y")
    t0 = time.perf_counter()
    cache = RedisCache.from_env()
    ollama = OllamaClient.from_env()
    intent = detect_intent_ru(req.text)
    sources: list[dict[str, Any]] = []
    fact_context = ""
    tool_ms = 0
    tool_answer: str | None = None
    web_ms = 0

    async def _emit_early(reply_text: str, used_model: str, timings_extra: dict[str, int] | None = None):
        t = {"tools": tool_ms, "llm": 0, "total": int((time.perf_counter() - t0) * 1000)}
        if timings_extra:
            t.update(timings_extra)
        yield {"chunk": reply_text}
        yield {"done": True, "reply_text": reply_text, "intent": intent, "used_model": used_model, "sources": sources, "timings_ms": t}

    # Media
    media_cmd = parse_media_command(req.text)
    media_api_base = os.getenv("MEDIA_API_BASE_URL", "").strip()
    if media_cmd and media_api_base:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.post(f"{media_api_base.rstrip('/')}/v1/command", json=media_cmd)
                r.raise_for_status()
        except Exception:
            pass
        reply = media_reply_text(media_cmd)
        async for ev in _emit_early(reply, "media"):
            yield ev
        return

    # HA
    ha_cmd = parse_ha_command(req.text)
    if ha_cmd and is_ha_configured() and intent == "command":
        t_ha = time.perf_counter()
        ha_ok, ha_message = await execute_ha_command(ha_cmd)
        ha_ms = int((time.perf_counter() - t_ha) * 1000)
        reply = ha_reply_text(ha_ok, ha_message)
        async for ev in _emit_early(reply, "ha", {"tools": ha_ms}):
            yield ev
        return

    # Tools: news, weather, version, timer (same as chat)
    if intent == "news":
        if not allow_internet:
            fact_context = "Интернет-доступ отключён (ALLOW_INTERNET_TOOLS=false)."
        else:
            t1 = time.perf_counter()
            news = await fetch_russian_news(cache=cache)
            tool_ms = int((time.perf_counter() - t1) * 1000)
            sources = news["sources"]
            fact_context = news.get("llm_fact_context") or news["fact_context"]
            tool_answer = news.get("answer")
    elif intent == "weather":
        if not allow_internet:
            fact_context = "Интернет-доступ отключён (ALLOW_INTERNET_TOOLS=false)."
        else:
            t1 = time.perf_counter()
            settings = cache.get_json(_settings_key_weather(req.session_id)) or {}
            w = await fetch_weather(
                user_text=req.text,
                session_id=req.session_id,
                cache=cache,
                default_city=(settings.get("city") or os.getenv("DEFAULT_WEATHER_CITY") or "Новосибирск"),
                default_district=(settings.get("district") or os.getenv("DEFAULT_WEATHER_DISTRICT") or None),
            )
            tool_ms = int((time.perf_counter() - t1) * 1000)
            sources = w["sources"]
            fact_context = w["fact_context"]
            tool_answer = w.get("answer")
    elif intent == "version":
        if not allow_internet:
            fact_context = "Интернет-доступ отключён (ALLOW_INTERNET_TOOLS=false)."
        else:
            t1 = time.perf_counter()
            v = await fetch_latest_version(user_text=req.text, cache=cache)
            tool_ms = int((time.perf_counter() - t1) * 1000)
            sources = v["sources"]
            fact_context = v["fact_context"]
    elif intent == "timer":
        t1 = time.perf_counter()
        try:
            timer_result = handle_timer_request(user_text=req.text, session_id=req.session_id, cache=cache)
            sources = timer_result.get("sources", [])
            fact_context = timer_result.get("fact_context", "")
            tool_answer = timer_result.get("answer") or ""
        except Exception as e:
            tool_answer = "Не удалось установить таймер. Попробуйте ещё раз."
            fact_context = f"Ошибка таймера: {e}"
        tool_ms = int((time.perf_counter() - t1) * 1000)

    system = (
        "Ты — домашний голосовой ассистент.\n"
        "Отвечай на русском.\n"
        "ПРАВИЛА:\n"
        "- Пиши только итоговый ответ. Не показывай рассуждения, план, самопроверку. Не начинай с \"Хорошо\".\n"
        "- Никогда не упоминай слова FACTS/контекст/промпт/инструкция в ответе.\n"
        "- Не выдумывай факты. Если не уверен — прямо скажи \"Не знаю\" и предложи, что можно сделать дальше.\n"
        "- Если нужно уточнение — задай один короткий вопрос."
    )
    user = req.text.strip()
    if fact_context:
        user = f"{user}\n\nFACTS:\n{fact_context}"

    model_choice = req.mode if req.mode != "auto" else ("chat" if should_use_chat_model(req.text, intent) else "fast")
    model = ollama.model_fast if model_choice == "fast" else ollama.model_chat

    # Fast path: tool-only return
    if model_choice == "fast" and intent in ("weather", "timer") and tool_answer:
        async for ev in _emit_early(str(tool_answer).strip(), "tool-only"):
            yield ev
        return

    # For all other paths we need LLM. Use streaming only for open chat; for structured intents send one chunk.
    num_predict_override = 512 if intent == "news" else 256
    if intent in ("chat", "command"):
        system = (
            "Верни ТОЛЬКО валидный JSON по схеме: {answer:string}.\n"
            "answer: короткий итоговый ответ на русском, без рассуждений.\n"
            "Если не уверен — скажи \"Не знаю\" и предложи уточнить/проверить источник.\n"
            "Никогда не упоминай FACTS/контекст/промпт.\n"
        )
    if intent == "news":
        system = (
            "Ты — локальный голосовой ассистент.\n"
            "Сформируй сводку новостей на русском.\n"
            "Верни ТОЛЬКО валидный JSON по схеме: {items:[{summary,url}]}.\n"
            "items: 5 пунктов (если фактов меньше — меньше).\n"
            "summary: 8–14 слов, без ссылок.\n"
            "url: ссылка строго из FACTS.\n"
            "Используй только FACTS, не выдумывай."
        )
    if intent == "weather":
        system = (
            "Ты — локальный голосовой ассистент.\n"
            "Верни ТОЛЬКО валидный JSON по схеме: {answer:string}.\n"
            "answer: одна строка на русском (температура, ощущается, ветер/осадки если есть).\n"
            "Используй только факты из FACTS, не выдумывай."
        )
    elif intent == "version":
        system = (
            "Ты — локальный голосовой ассистент.\n"
            "Верни ТОЛЬКО валидный JSON по схеме: {answer:string}.\n"
            "answer: 2–4 короткие строки на русском.\n"
            "Используй только факты из FACTS, не выдумывай."
        )

    web_provider = _env_web_provider()
    if intent == "chat" and allow_internet and web_provider in ("searxng", "ddg", "both"):
        decide_system = (
            "Верни ТОЛЬКО валидный JSON по схеме:\n"
            "{answer:string, need_search:boolean, search_query:string, provider:string}.\n"
            "Правила: вопросы о числах/датах/фактах — need_search=true и search_query; иначе need_search=false. Только JSON."
        )
        raw_decide = await ollama.chat(
            model=ollama.model_fast,
            system=decide_system,
            user=req.text.strip(),
            session_id=req.session_id,
            mode="fast",
            response_format=_web_decision_schema(),
            num_predict_override=180,
        )
        decide = _parse_json_reply(raw_decide) or {}
        need_search = bool(decide.get("need_search"))
        search_query = str(decide.get("search_query") or "").strip()
        if _looks_factual_question(req.text) and _is_unknown_answer(str(decide.get("answer") or "").strip().lower()):
            need_search = True
            search_query = req.text[:200].strip()
        elif need_search and not search_query and _looks_factual_question(req.text):
            search_query = req.text[:200].strip()

        if need_search and search_query:
            ws = await fetch_web_search(
                cache=cache,
                query=search_query,
                provider=web_provider,
                lang=os.getenv("WEB_SEARCH_LANGUAGE", "ru"),
                max_results=int(os.getenv("WEB_SEARCH_MAX_RESULTS", "6")),
            )
            web_ms = int((time.perf_counter() - t0) * 1000) - tool_ms
            sources.extend(ws.get("sources") or [])
            fact_context = (ws.get("fact_context") or "").strip()
            if not fact_context or len(fact_context) < 80 or ("[1]" not in fact_context and "InstantAnswer:" not in fact_context):
                async for ev in _emit_early(
                    "Поиск не дал результатов. Запусти SearxNG: docker compose --profile search up -d",
                    ollama.model_fast,
                ):
                    yield ev
                return
            system = (
                "Верни ТОЛЬКО валидный JSON по схеме: {answer:string}.\n"
                "answer: краткий ответ на русском по материалам из FACTS. Не вставляй URL. Скажи \"Не знаю\" только если в FACTS нет ничего по теме."
            )
            user = f"{req.text.strip()}\n\nFACTS:\n{fact_context}"
            raw_reply = await ollama.chat(
                model=model,
                system=system,
                user=user,
                session_id=req.session_id,
                mode=model_choice,
                response_format={"type": "object", "additionalProperties": False, "properties": {"answer": {"type": "string", "maxLength": 700}}, "required": ["answer"]},
                num_predict_override=320,
            )
            parsed = _parse_json_reply(raw_reply)
            reply = (parsed.get("answer") or "").strip() if isinstance(parsed, dict) else raw_reply.strip()
            total_ms = int((time.perf_counter() - t0) * 1000)
            async for ev in _emit_early(reply, model, {"web": web_ms, "llm": 0, "total": total_ms}):
                yield ev
            return

    # Structured intents: non-streaming with JSON so the model returns only the answer, no reasoning
    response_format = _format_schema_for_intent(intent)
    if intent in ("chat", "command"):
        response_format = {
            "type": "object",
            "additionalProperties": False,
            "properties": {"answer": {"type": "string", "maxLength": 700}},
            "required": ["answer"],
        }
    if intent in ("news", "weather", "version", "chat", "command"):
        t2 = time.perf_counter()
        raw_reply = await ollama.chat(
            model=model,
            system=system,
            user=user,
            session_id=req.session_id,
            mode=model_choice,
            response_format=response_format,
            num_predict_override=num_predict_override,
        )
        llm_ms = int((time.perf_counter() - t2) * 1000)
        parsed = _parse_json_reply(raw_reply)
        reply = raw_reply
        if parsed is not None:
            if intent == "weather" and isinstance(parsed.get("answer"), str):
                reply = parsed["answer"].strip()
            elif intent == "version" and isinstance(parsed.get("answer"), str):
                reply = parsed["answer"].strip()
            elif intent == "news" and isinstance(parsed.get("items"), list):
                lines = []
                for it in parsed["items"][:5]:
                    if isinstance(it, dict):
                        summary = it.get("summary")
                        url = it.get("url")
                        if isinstance(summary, str) and isinstance(url, str) and summary.strip() and url.strip():
                            lines.append(f"- {summary.strip()}")
                reply = "\n".join(lines) if lines else (tool_answer or "Не удалось сформировать сводку новостей.")
            elif intent == "news":
                reply = tool_answer or "Не удалось сформировать сводку новостей."
            elif intent in ("chat", "command") and isinstance(parsed.get("answer"), str):
                reply = parsed["answer"].strip()
        if intent == "news":
            reply = _strip_urls(reply)
        total_ms = int((time.perf_counter() - t0) * 1000)
        async for ev in _emit_early(reply, model, {"web": web_ms, "llm": llm_ms, "total": total_ms}):
            yield ev
        return

    # Main LLM path: stream plain text (no JSON) for best UX
    stream_system = (
        "Ты — домашний голосовой ассистент. Отвечай на русском кратко, без рассуждений и без упоминания FACTS/промпт."
    )
    if fact_context:
        stream_system += "\nИспользуй только факты из контекста пользователя (FACTS), не выдумывай."
    full_reply: list[str] = []
    t2 = time.perf_counter()
    async for chunk in ollama.chat_stream(
        model=model,
        system=stream_system,
        user=user,
        session_id=req.session_id,
        mode=model_choice,
        num_predict_override=num_predict_override,
    ):
        full_reply.append(chunk)
        yield {"chunk": chunk}
    llm_ms = int((time.perf_counter() - t2) * 1000)
    reply = "".join(full_reply).strip()
    if intent == "news":
        reply = _strip_urls(reply)
    total_ms = int((time.perf_counter() - t0) * 1000)
    yield {
        "done": True,
        "reply_text": reply or "Не удалось получить ответ.",
        "intent": intent,
        "used_model": model,
        "sources": sources,
        "timings_ms": {"tools": tool_ms, "web": web_ms, "llm": llm_ms, "total": total_ms},
    }


@app.post("/v1/chat/stream")
async def chat_stream(req: ChatRequest):
    """Stream chat response as Server-Sent Events. Each event: data: {chunk} or data: {done, reply_text, ...}."""
    async def event_stream():
        async for ev in _chat_stream_events(req):
            yield f"data: {json.dumps(ev)}\n\n"
    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

