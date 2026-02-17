import re
import time
from typing import Any, Optional

import httpx

from app.redis_cache import RedisCache


_RE_REPO = re.compile(r"([A-Za-z0-9_.-]+)\/([A-Za-z0-9_.-]+)")


def _extract_repo(text: str) -> Optional[str]:
    # Accept "owner/repo" or github.com/owner/repo
    m = re.search(r"github\.com\/([A-Za-z0-9_.-]+)\/([A-Za-z0-9_.-]+)", text)
    if m:
        return f"{m.group(1)}/{m.group(2)}"
    m = _RE_REPO.search(text)
    if m and len(m.group(1)) >= 2 and len(m.group(2)) >= 2:
        return f"{m.group(1)}/{m.group(2)}"
    return None


async def _github_latest_release(repo: str) -> dict[str, Any]:
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    timeout = httpx.Timeout(20.0, connect=10.0)
    async with httpx.AsyncClient(timeout=timeout, headers={"User-Agent": "moltbot-api/0.1"}) as client:
        r = await client.get(url)
        r.raise_for_status()
        return r.json()


async def fetch_latest_version(*, user_text: str, cache: RedisCache) -> dict[str, Any]:
    repo = _extract_repo(user_text)
    if not repo:
        return {
            "fact_context": "Чтобы проверить «последнюю версию», укажи GitHub репозиторий в формате owner/repo (например: kubernetes/kubernetes).",
            "sources": [],
            "fetched_at_unix": int(time.time()),
        }

    cache_key = f"version:github:v1:{repo.lower()}"
    cached = cache.get_json(cache_key)
    if cached:
        return cached

    try:
        data = await _github_latest_release(repo)
        tag = data.get("tag_name")
        name = data.get("name")
        html = data.get("html_url")
        published = data.get("published_at")
        fact_context = (
            f"GitHub repo: {repo}\n"
            f"Latest release tag: {tag}\n"
            f"Release name: {name}\n"
            f"Published at: {published}\n"
            f"URL: {html}\n"
        ).strip()
        payload = {
            "fact_context": fact_context,
            "sources": [{"type": "github", "url": html or f"https://github.com/{repo}/releases/latest"}],
            "fetched_at_unix": int(time.time()),
        }
    except Exception:
        payload = {
            "fact_context": f"Не удалось получить последнюю версию для {repo} через GitHub Releases.",
            "sources": [{"type": "github", "url": f"https://github.com/{repo}/releases"}],
            "fetched_at_unix": int(time.time()),
        }

    cache.set_json(cache_key, payload, ttl_seconds=3600)
    return payload

