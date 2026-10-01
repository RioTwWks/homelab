#!/usr/bin/env python3
import asyncio
from _cli import run_main
from _runtime import init_runtime

def main(args):
    init_runtime()
    from app.redis_cache import RedisCache
    from app.tools.news import fetch_russian_news
    return asyncio.run(fetch_russian_news(cache=RedisCache.from_env()))

if __name__ == "__main__":
    run_main("news", main)
