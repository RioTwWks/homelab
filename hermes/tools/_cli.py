from __future__ import annotations
import argparse, json
from typing import Any, Callable

def build_parser(desc: str) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=desc)
    p.add_argument("--text", "-t", required=True)
    p.add_argument("--session-id", "-s", default="hermes")
    p.add_argument("--json", action="store_true")
    return p

def run_main(desc: str, fn: Callable[[argparse.Namespace], dict[str, Any]]) -> None:
    args = build_parser(desc).parse_args()
    out = fn(args)
    print(json.dumps(out, ensure_ascii=False, indent=2) if args.json else out.get("answer", json.dumps(out, ensure_ascii=False)))
