import os
import time
from typing import Any, Literal, TypedDict

import httpx

from app.redis_cache import RedisCache


class WebSearchResult(TypedDict, total=False):
    title: str
    url: str
    snippet: str
    engine: str
    score: float


class WebSearchPayload(TypedDict):
    provider: Literal["searxng", "ddg", "both"]
    query: str
    results: list[WebSearchResult]
    instant_answer: str | None
    fact_context: str
    sources: list[dict[str, Any]]
    fetched_at_unix: int


def _normalize_query_for_cache(query: str) -> str:
    """Normalize query so small variations (punctuation, city case) hit the same cache."""
    q = " ".join((query or "").strip().split()).lower()
    # Strip trailing sentence punctuation so "зоопарке Новосибирска?" and "зоопарке Новосибирска" match
    q = q.rstrip("?!.;,")
    # Common Russian place-name variants (genitive → nominative) so "Новосибирска" ≈ "Новосибирск"
    for genitive, nominative in (("новосибирска", "новосибирск"), ("москвы", "москва"), ("петербурга", "петербург")):
        q = q.replace(genitive, nominative)
    return q


def _cache_key(provider: str, query: str, lang: str, max_results: int, time_range: str | None = None) -> str:
    q = _normalize_query_for_cache(query)
    tr = (time_range or "").strip().lower() or ""
    return f"websearch:v2:{provider}:{lang}:{max_results}:{tr}:{q}"


def _env_bool(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).lower() in ("1", "true", "yes", "y", "on")


async def _searxng_search(
    *,
    query: str,
    lang: str,
    max_results: int,
    base_url: str,
    safesearch: int = 0,
    time_range: str | None = None,
) -> list[WebSearchResult]:
    """
    SearxNG JSON API:
      GET {base_url}/search?q=...&format=json&language=ru&safesearch=0
    Docs: https://docs.searxng.org/dev/search_api.html
    """
    base = base_url.rstrip("/")
    url = f"{base}/search"
    params: dict[str, Any] = {
        "q": query,
        "format": "json",
        "language": lang,
        "safesearch": str(int(safesearch)),
    }
    if time_range:
        params["time_range"] = time_range
    timeout = httpx.Timeout(12.0, connect=6.0)
    # Some SearxNG deployments require these headers (botdetection).
    headers = {
        "User-Agent": "moltbot-api/0.1",
        "X-Forwarded-For": os.getenv("SEARXNG_X_FORWARDED_FOR", "127.0.0.1"),
        "X-Real-IP": os.getenv("SEARXNG_X_REAL_IP", "127.0.0.1"),
    }
    async with httpx.AsyncClient(timeout=timeout, headers=headers) as client:
        r = await client.get(url, params=params)
        r.raise_for_status()
        data = r.json()

    items = data.get("results") if isinstance(data, dict) else None
    out: list[WebSearchResult] = []
    if isinstance(items, list):
        for it in items[: max(1, max_results)]:
            if not isinstance(it, dict):
                continue
            title = str(it.get("title") or "").strip()
            urlv = str(it.get("url") or "").strip()
            snippet = str(it.get("content") or it.get("snippet") or "").strip()
            engine = str(it.get("engine") or "").strip()
            score = it.get("score")
            if not title or not urlv:
                continue
            res: WebSearchResult = {"title": title, "url": urlv}
            if snippet:
                res["snippet"] = snippet
            if engine:
                res["engine"] = engine
            try:
                if score is not None:
                    res["score"] = float(score)
            except Exception:
                pass
            out.append(res)
    return out


async def _ddg_instant_answer(*, query: str, lang: str) -> tuple[str | None, list[WebSearchResult]]:
    """
    DuckDuckGo Instant Answer API (free, no key):
      https://api.duckduckgo.com/?q=...&format=json&no_html=1&skip_disambig=1
    NOTE: This is not full web search; it's "instant answers" / knowledge.
    """
    params: dict[str, Any] = {
        "q": query,
        "format": "json",
        "no_html": "1",
        "skip_disambig": "1",
        "t": "moltbot",
    }
    # DDG language param is not strongly documented; keep optional.
    if lang:
        params["kl"] = lang
    timeout = httpx.Timeout(10.0, connect=5.0)
    async with httpx.AsyncClient(timeout=timeout, headers={"User-Agent": "moltbot-api/0.1"}) as client:
        r = await client.get("https://api.duckduckgo.com/", params=params)
        r.raise_for_status()
        data = r.json()

    if not isinstance(data, dict):
        return None, []

    # Prefer Answer/Abstract/Definition.
    instant = (data.get("Answer") or "").strip()
    if not instant:
        instant = (data.get("AbstractText") or "").strip()
    if not instant:
        instant = (data.get("Definition") or "").strip()
    if instant:
        heading = (data.get("Heading") or "").strip()
        if heading and heading.lower() not in instant.lower():
            instant = f"{heading}: {instant}"

    # Convert Results / RelatedTopics into a pseudo result list (best effort).
    out: list[WebSearchResult] = []
    for it in (data.get("Results") or [])[:5]:
        if isinstance(it, dict):
            title = str(it.get("Text") or "").strip()
            urlv = str(it.get("FirstURL") or "").strip()
            if title and urlv:
                out.append({"title": title, "url": urlv})

    # RelatedTopics can be nested (Topics groups).
    related = data.get("RelatedTopics") or []
    if isinstance(related, list):
        for it in related:
            if len(out) >= 8:
                break
            if isinstance(it, dict) and "Topics" in it and isinstance(it.get("Topics"), list):
                for sub in it["Topics"]:
                    if len(out) >= 8:
                        break
                    if isinstance(sub, dict):
                        title = str(sub.get("Text") or "").strip()
                        urlv = str(sub.get("FirstURL") or "").strip()
                        if title and urlv:
                            out.append({"title": title, "url": urlv})
            elif isinstance(it, dict):
                title = str(it.get("Text") or "").strip()
                urlv = str(it.get("FirstURL") or "").strip()
                if title and urlv:
                    out.append({"title": title, "url": urlv})

    return (instant or None), out


def _format_fact_context(
    *,
    provider: str,
    query: str,
    instant_answer: str | None,
    results: list[WebSearchResult],
    max_results: int,
) -> str:
    lines: list[str] = [f"WEB_SEARCH provider={provider}", f"Query: {query}"]
    if instant_answer:
        lines.append(f"InstantAnswer: {instant_answer}")
    for i, r in enumerate(results[: max(1, max_results)], start=1):
        title = r.get("title") or ""
        url = r.get("url") or ""
        snip = (r.get("snippet") or "").strip()
        engine = (r.get("engine") or "").strip()
        tail = []
        if engine:
            tail.append(engine)
        if snip:
            tail.append(snip)
        tail_s = " | ".join(tail)
        lines.append(f"[{i}] {title} — {url}{(' | ' + tail_s) if tail_s else ''}")
    return "\n".join(lines).strip()


async def fetch_web_search(
    *,
    cache: RedisCache,
    query: str,
    provider: Literal["searxng", "ddg", "both"],
    lang: str = "ru",
    max_results: int = 6,
) -> WebSearchPayload:
    ttl = int(os.getenv("WEB_SEARCH_CACHE_TTL_SECONDS", "21600"))  # 6h
    q = " ".join((query or "").strip().split())
    lang = (lang or "ru").strip().lower()
    max_results = int(max_results or 6)
    # Prefer recent results: day | week | month | year (SearxNG time_range; empty = no filter)
    time_range_raw = os.getenv("WEB_SEARCH_TIME_RANGE", "").strip().lower()
    time_range: str | None = time_range_raw if time_range_raw in ("day", "week", "month", "year") else None

    key = _cache_key(provider, q, lang, max_results, time_range)
    cached = cache.get_json(key)
    if isinstance(cached, dict) and cached.get("query") == q and cached.get("provider") == provider:
        return cached  # type: ignore[return-value]

    results: list[WebSearchResult] = []
    instant: str | None = None
    sources: list[dict[str, Any]] = []

    if provider in ("searxng", "both"):
        searx_url = os.getenv("SEARXNG_BASE_URL", "").strip()
        if searx_url:
            try:
                se = await _searxng_search(
                    query=q,
                    lang=lang,
                    max_results=max_results,
                    base_url=searx_url,
                    time_range=time_range,
                )
                results.extend(se)
                sources.append({"type": "websearch", "provider": "searxng", "base_url": searx_url})
            except Exception as e:
                sources.append({"type": "websearch", "provider": "searxng", "error": str(e), "base_url": searx_url})

    if provider in ("ddg", "both"):
        try:
            inst, ddg_res = await _ddg_instant_answer(query=q, lang=lang)
            if inst:
                instant = inst
            # Append DDG links if we don't have enough results.
            if len(results) < max_results:
                for r in ddg_res:
                    if len(results) >= max_results:
                        break
                    results.append(r)
            sources.append({"type": "websearch", "provider": "ddg", "base_url": "https://api.duckduckgo.com/"})
        except Exception as e:
            sources.append({"type": "websearch", "provider": "ddg", "error": str(e), "base_url": "https://api.duckduckgo.com/"})

    fact_context = _format_fact_context(
        provider=provider,
        query=q,
        instant_answer=instant,
        results=results,
        max_results=max_results,
    )

    payload: WebSearchPayload = {
        "provider": provider,
        "query": q,
        "results": results[: max_results],
        "instant_answer": instant,
        "fact_context": fact_context,
        "sources": sources,
        "fetched_at_unix": int(time.time()),
    }
    cache.set_json(key, payload, ttl_seconds=ttl)
    return payload

