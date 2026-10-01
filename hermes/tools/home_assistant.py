#!/usr/bin/env python3
import asyncio
from _cli import run_main
from _runtime import init_runtime

def main(args):
    init_runtime()
    from app.tools.home_assistant import execute_ha_command, ha_reply_text, is_ha_configured, parse_ha_command
    cmd = parse_ha_command(args.text)
    if not cmd:
        return {"answer": "Команда не распознана."}
    if not is_ha_configured():
        return {"answer": "HA не настроен."}
    async def run():
        ok, msg = await execute_ha_command(cmd)
        return {"answer": ha_reply_text(ok, msg)}
    return asyncio.run(run())

if __name__ == "__main__":
    run_main("home_assistant", main)
