#!/usr/bin/env python3
import asyncio, os, httpx
from _cli import run_main
from _runtime import init_runtime

def main(args):
    init_runtime()
    from app.tools.media_control import media_reply_text, parse_media_command
    cmd = parse_media_command(args.text)
    if not cmd:
        return {"answer": "Медиа-команда не распознана."}
    base = os.getenv("MEDIA_API_BASE_URL", "")
    async def run():
        try:
            async with httpx.AsyncClient(timeout=8.0) as c:
                await c.post(f"{base.rstrip('/')}/v1/command", json=cmd)
        except Exception as e:
            return {"answer": f"media-api: {e}"}
        return {"answer": media_reply_text(cmd)}
    return asyncio.run(run())

if __name__ == "__main__":
    run_main("media", main)
