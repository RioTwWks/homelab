"""Offline tests for Jev × Hermes hook adapters (hard rules + fake quality)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HOOKS = REPO / "hermes" / "hooks"
PY = Path(os.environ.get("JEV_STYLE_PYTHON", sys.executable))


def _run_pre(payload: dict) -> dict:
    env = os.environ.copy()
    env.setdefault("JEV_STYLE_GUARD_CONFIG", str(HOOKS / "guard_config.homelab.json"))
    proc = subprocess.run(
        [str(PY), str(HOOKS / "jev_pre_tool_call.py")],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    out = proc.stdout.strip()
    return json.loads(out) if out else {}


def test_rm_rf_root_blocked():
    out = _run_pre(
        {
            "hook_event_name": "pre_tool_call",
            "tool_name": "terminal",
            "tool_input": {"command": "rm -rf /"},
        }
    )
    assert out.get("action") == "block"


def test_sudo_requires_approval():
    out = _run_pre(
        {
            "hook_event_name": "pre_tool_call",
            "tool_name": "terminal",
            "tool_input": {"command": "sudo systemctl restart docker"},
        }
    )
    assert out.get("action") == "approve"


def test_docker_prune_all_blocked():
    out = _run_pre(
        {
            "hook_event_name": "pre_tool_call",
            "tool_name": "terminal",
            "tool_input": {"command": "docker system prune -a -f"},
        }
    )
    assert out.get("action") == "block"


def test_quality_hook_writes_log(tmp_path):
    log = tmp_path / "quality.jsonl"
    env = os.environ.copy()
    env["JEV_STYLE_QUALITY_FAKE"] = "1"
    env["JEV_QUALITY_LOG_PATH"] = str(log)
    payload = json.dumps(
        {
            "session_id": "pytest",
            "extra": {
                "user_message": "Привет",
                "assistant_response": "Здравствуйте! Чем помочь?",
            },
        }
    )
    subprocess.run(
        [str(PY), str(HOOKS / "jev_post_response.py")],
        input=payload,
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )
    lines = log.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["session_id"] == "pytest"
    assert "score" in rec
