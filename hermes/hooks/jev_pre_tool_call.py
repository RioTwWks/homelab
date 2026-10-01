#!/usr/bin/env python3
"""Hermes shell hook: map pre_tool_call JSON to jev-style guard and back."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_GUARD_CONFIG = _REPO_ROOT / "hermes" / "hooks" / "guard_config.homelab.json"

_TOOL_MAP = {
    "terminal": "Bash",
    "bash": "Bash",
    "run_terminal_cmd": "Bash",
}


def _hermes_to_guard_payload(raw: dict[str, Any]) -> dict[str, Any]:
    tool = str(raw.get("tool_name") or "")
    tool_input = raw.get("tool_input")
    if tool_input is None:
        tool_input = raw.get("args") or {}
    if not isinstance(tool_input, dict):
        tool_input = {"value": tool_input}
    mapped = _TOOL_MAP.get(tool.lower(), tool)
    extra = raw.get("extra") if isinstance(raw.get("extra"), dict) else {}
    return {
        "tool_name": mapped,
        "tool_input": tool_input,
        "cwd": raw.get("cwd") or extra.get("cwd") or os.getcwd(),
        "session_id": raw.get("session_id") or extra.get("session_id"),
        "project_dir": raw.get("project_dir") or extra.get("project_dir"),
        "home": raw.get("home") or extra.get("home"),
    }


def _guard_to_hermes(emitted: dict[str, Any] | None, reason: str) -> dict[str, Any]:
    if not emitted:
        return {}
    hso = emitted.get("hookSpecificOutput") or {}
    decision = str(hso.get("permissionDecision") or "").lower()
    msg = str(hso.get("permissionDecisionReason") or reason or "Jev-Style guard")
    if decision == "deny":
        return {"action": "block", "message": msg}
    if decision == "ask":
        return {"action": "approve", "message": msg, "rule_key": "jev-style-guard"}
    return {}


def main() -> int:
    try:
        raw = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        print(json.dumps({"action": "block", "message": "Invalid hook JSON on stdin"}))
        return 0

    if not os.environ.get("JEV_STYLE_GUARD_CONFIG") and DEFAULT_GUARD_CONFIG.is_file():
        os.environ.setdefault("JEV_STYLE_GUARD_CONFIG", str(DEFAULT_GUARD_CONFIG))

    from jev_style import guard

    cfg = guard.load_config(os.environ.get("JEV_STYLE_GUARD_CONFIG"))
    hook_input = _hermes_to_guard_payload(raw if isinstance(raw, dict) else {})
    res = guard.evaluate(hook_input, cfg)
    emitted = guard.hook_output(res, cfg)
    guard.write_log(cfg, hook_input, res, emitted)
    out = _guard_to_hermes(emitted, guard.reason_text(res))
    if out:
        print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
