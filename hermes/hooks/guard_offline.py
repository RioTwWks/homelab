"""Homelab guard: hard_rules from JSON without jev-style (CI / offline)."""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any

ORDER = {"allow": 0, "ask": 1, "deny": 2}

_DEFAULTS: dict[str, Any] = {
    "dry_run": False,
    "emit_allow": False,
    "on_error": "ask",
    "log_path": None,
    "skip_tools": [],
    "skip_tools_regex": [],
    "hard_rules": [],
}


def load_config(path: str | None = None) -> dict[str, Any]:
    cfg = json.loads(json.dumps(_DEFAULTS))
    p = Path(
        path or os.environ.get("JEV_STYLE_GUARD_CONFIG") or ""
    ).expanduser()
    if p.is_file():
        with p.open(encoding="utf-8") as fh:
            user = json.load(fh)
        for key, val in user.items():
            if str(key).startswith("_"):
                continue
            cfg[key] = val
    if os.environ.get("JEV_STYLE_GUARD_DRY_RUN", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    ):
        cfg["dry_run"] = True
    if os.environ.get("JEV_STYLE_GUARD_LOG"):
        cfg["log_path"] = os.environ["JEV_STYLE_GUARD_LOG"]
    if cfg.get("on_error") not in ("ask", "deny"):
        cfg["on_error"] = "ask"
    return cfg


def should_skip(tool: str, cfg: dict[str, Any]) -> bool:
    if tool in (cfg.get("skip_tools") or []):
        return True
    return any(re.search(rx, tool) for rx in (cfg.get("skip_tools_regex") or []))


def apply_hard_rules(
    hook_input: dict[str, Any], rules: list[dict[str, Any]]
) -> dict[str, Any] | None:
    tool = str(hook_input.get("tool_name") or "")
    ti = hook_input.get("tool_input") or {}
    if isinstance(ti, dict) and isinstance(ti.get("command"), str):
        text = ti.get("command")
    else:
        text = json.dumps(ti)
    best: dict[str, Any] | None = None
    for rule in rules or []:
        tools = rule.get("tools")
        if tools and tool not in tools:
            continue
        try:
            if not re.search(rule["pattern"], text or ""):
                continue
        except (re.error, KeyError):
            continue
        level = rule.get("decision", "deny")
        if level not in ORDER:
            continue
        if best is None or ORDER[level] > ORDER[best["decision"]]:
            best = {
                "decision": level,
                "rule": rule.get("name") or rule["pattern"],
                "reason": rule.get("reason", ""),
            }
    return best


def evaluate(hook_input: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
    t0 = time.perf_counter()
    tool = str(hook_input.get("tool_name") or "")
    out: dict[str, Any] = {
        "tool": tool,
        "decision": "allow",
        "source": "offline",
        "reasons": [],
        "values": {},
    }
    if should_skip(tool, cfg):
        out["source"] = "skip"
        out["latency_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        return out
    rule = apply_hard_rules(hook_input, cfg.get("hard_rules") or [])
    if rule:
        out["rule"] = rule
        out["decision"] = rule["decision"]
        out["source"] = "rule"
    out["latency_ms"] = round((time.perf_counter() - t0) * 1000, 2)
    return out


def reason_text(res: dict[str, Any]) -> str:
    parts: list[str] = []
    if res.get("rule"):
        r = res["rule"]
        parts.append(f"rule '{r['rule']}'" + (f": {r['reason']}" if r.get("reason") else ""))
    return "Jev-Style guard: " + ("; ".join(parts) if parts else "no concern above threshold")


def hook_output(res: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any] | None:
    if cfg.get("dry_run"):
        return None
    decision = res["decision"]
    if decision == "allow" and not cfg.get("emit_allow"):
        return None
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason": reason_text(res),
        }
    }
