#!/usr/bin/env python3
import asyncio, os
from _cli import run_main
from _runtime import init_runtime

def main(args):
    init_runtime()
    from app.redis_cache import RedisCache
    from app.tools.weather import fetch_weather
    return asyncio.run(fetch_weather(user_text=args.text, session_id=args.session_id, cache=RedisCache.from_env(),
        default_city=os.getenv("DEFAULT_WEATHER_CITY") or "Новосибирск", default_district=os.getenv("DEFAULT_WEATHER_DISTRICT")))

if __name__ == "__main__":
    run_main("weather", main)
