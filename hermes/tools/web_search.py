#!/usr/bin/env python3
import asyncio, json, os
from _cli import build_parser
from _runtime import init_runtime

if __name__ == "__main__":
    init_runtime()
    from app.redis_cache import RedisCache
    from app.tools.web_search import fetch_web_search
    p = build_parser("web_search")
    p.add_argument("--provider", choices=("searxng", "ddg", "both"))
    args = p.parse_args()
    prov = args.provider or os.getenv("WEB_SEARCH_PROVIDER", "searxng")
    if prov in ("off", "none", ""):
        prov = "searxng"
    payload = asyncio.run(fetch_web_search(cache=RedisCache.from_env(), query=args.text, provider=prov,
        lang=os.getenv("WEB_SEARCH_LANGUAGE", "ru"), max_results=int(os.getenv("WEB_SEARCH_MAX_RESULTS", "6"))))
    print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else payload.get("fact_context", ""))
