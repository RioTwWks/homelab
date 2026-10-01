#!/usr/bin/env python3
from _cli import run_main
from _runtime import init_runtime

def main(args):
    init_runtime()
    from app.redis_cache import RedisCache
    from app.tools.timers import handle_timer_request
    return handle_timer_request(user_text=args.text, session_id=args.session_id, cache=RedisCache.from_env())

if __name__ == "__main__":
    run_main("timers", main)
