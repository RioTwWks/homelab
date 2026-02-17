import os
import re
import time
from typing import Any

import feedparser
import httpx

from app.redis_cache import RedisCache


DEFAULT_RSS_SOURCES = [
    "https://tass.ru/rss/v2.xml",
    "https://www.interfax.ru/rss.asp",
    "https://lenta.ru/rss",
    "https://www.kommersant.ru/rss/news.xml",
]

_TAG_RE = re.compile(r"<[^>]+>")


def _rss_sources() -> list[str]:
    env = os.getenv("NEWS_RSS_SOURCES", "").strip()
    if not env:
        return DEFAULT_RSS_SOURCES
    return [s.strip() for s in env.split(",") if s.strip()]

def _clean_summary(raw: Any) -> str:
    if not raw:
        return ""
    s = str(raw)
    s = _TAG_RE.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip()
    max_len = int(os.getenv("NEWS_ITEM_SUMMARY_CHARS", "180"))
    if len(s) > max_len:
        s = s[: max_len - 1].rstrip() + "…"
    return s


async def fetch_russian_news(*, cache: RedisCache) -> dict[str, Any]:
    ttl = int(os.getenv("NEWS_CACHE_TTL_SECONDS", "900"))
    cache_key = "news:rss:v4"
    cached = cache.get_json(cache_key)
    if cached:
        return cached

    sources = _rss_sources()
    items: list[dict[str, Any]] = []

    timeout = httpx.Timeout(20.0, connect=10.0)
    async with httpx.AsyncClient(timeout=timeout, headers={"User-Agent": "moltbot-api/0.1"}) as client:
        for url in sources:
            try:
                r = await client.get(url)
                r.raise_for_status()
                feed = feedparser.parse(r.text)
                for e in feed.entries[:8]:
                    title = getattr(e, "title", None)
                    link = getattr(e, "link", None)
                    published = getattr(e, "published", None) or getattr(e, "updated", None)
                    summary = _clean_summary(getattr(e, "summary", None) or getattr(e, "description", None))
                    if not title or not link:
                        continue
                    items.append(
                        {
                            "title": str(title).strip(),
                            "link": str(link).strip(),
                            "published": str(published).strip() if published else None,
                            "summary": summary or None,
                            "source": url,
                        }
                    )
            except Exception:
                continue

    # Deduplicate by link/title
    seen = set()
    deduped: list[dict[str, Any]] = []
    for it in items:
        key = (it.get("link"), it.get("title"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(it)

    max_items = int(os.getenv("NEWS_MAX_ITEMS_FACTS", "15"))
    deduped = deduped[:max_items]

    fact_lines = []
    for it in deduped:
        when = f" ({it['published']})" if it.get("published") else ""
        if it.get("summary"):
            fact_lines.append(f"- {it['title']}{when}. {it['summary']} — {it['link']}")
        else:
            fact_lines.append(f"- {it['title']}{when} — {it['link']}")

    # Smaller context for LLM: top N items only, each line ends with URL.
    llm_lines = []
    for it in deduped[:10]:
        if it.get("summary"):
            llm_lines.append(f"- {it['title']}. {it['summary']} — {it['link']}")
        else:
            llm_lines.append(f"- {it['title']} — {it['link']}")

    # Short deterministic digest (no LLM): 5 bullets, no links (voice-friendly).
    digest_lines = []
    for it in deduped[:5]:
        if it.get("summary"):
            digest_lines.append(f"- {it['title']}. {it['summary']}")
        else:
            digest_lines.append(f"- {it['title']}")

    payload = {
        "answer": "\n".join(digest_lines) if digest_lines else "Не удалось получить новости.",
        "items": deduped,
        "llm_fact_context": "Заголовки новостей (Россия, RSS):\n" + ("\n".join(llm_lines) if llm_lines else "- (не удалось получить новости)"),
        "fact_context": "Заголовки новостей (Россия, RSS):\n" + ("\n".join(fact_lines) if fact_lines else "- (не удалось получить новости)"),
        "sources": [{"type": "rss", "url": u} for u in sources],
        "fetched_at_unix": int(time.time()),
    }
    cache.set_json(cache_key, payload, ttl_seconds=ttl)
    return payload

