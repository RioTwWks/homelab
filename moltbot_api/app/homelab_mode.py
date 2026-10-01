"""Homelab resource mode (AI / Gaming / Media)."""
from __future__ import annotations
import json, os, time
from pathlib import Path
from typing import Any, Literal
import httpx
HomelabModeName = Literal["ai", "gaming", "media"]
VALID_MODES = frozenset({"ai", "gaming", "media"})

def state_path() -> Path:
    raw = os.getenv("HOMELAB_MODE_STATE_PATH", "").strip()
    return Path(raw) if raw else Path("/data/homelab-mode/state.json")

def _default_state() -> dict[str, Any]:
    return {"mode": "media", "updated_at": int(time.time()), "applied_at": None, "message": "default", "details": {}}

def read_state() -> dict[str, Any]:
    p = state_path()
    if not p.is_file():
        return _default_state()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        mode = str(data.get("mode") or "media").lower()
        if mode not in VALID_MODES:
            mode = "media"
        data["mode"] = mode
        return data
    except Exception:
        return {**_default_state(), "message": "unreadable"}

def write_state(mode: HomelabModeName, message: str = "requested") -> dict[str, Any]:
    p = state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {"mode": mode, "updated_at": int(time.time()), "applied_at": None, "message": message, "details": {}}
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload

async def request_mode_on_host(mode: HomelabModeName) -> dict[str, Any]:
    base = os.getenv("HOMELAB_MODE_EXECUTOR_URL", "").strip().rstrip("/")
    if not base:
        return {"skipped": True, "reason": "HOMELAB_MODE_EXECUTOR_URL not set"}
    try:
        async with httpx.AsyncClient(timeout=120.0) as c:
            r = await c.post(f"{base}/v1/mode", json={"mode": mode})
            body = r.json() if "json" in r.headers.get("content-type", "") else r.text
            return {"ok": r.is_success, "status_code": r.status_code, "body": body}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

async def set_mode(mode: HomelabModeName) -> dict[str, Any]:
    return {"ok": True, "state": write_state(mode, "requested via API"), "executor": await request_mode_on_host(mode)}
