# Jev-Style hooks for Hermes (Phase 3)

Local **Jev-Style-2B-Decision-v3** (`jev-style`, release `2b-v3`) gates tool calls and logs response-quality scores. Dangerous homelab operations are **blocked** or escalated to **human-in-the-loop** via Hermes `approve` directives.

Config template: [`templates/hermes-jev-hooks.yaml`](./templates/hermes-jev-hooks.yaml).  
Classification matrix: [`jev-classification-tests.md`](./jev-classification-tests.md).

## Architecture

```text
User → Hermes (Ollama) → pre_tool_call shell hook
                              └─ jev_pre_tool_call.py → jev-style guard
                                   ├─ hard_rules (instant deny/ask)
                                   └─ 2B model (destructive / exfil / secrets / risk)
                         → tool runs (or block / approval prompt)
                         → post_llm_call → jev_post_response.py → quality.jsonl
```

| Concern | Mechanism |
|---------|-----------|
| PreToolUse | `jev-style guard` adapted to Hermes JSON (`terminal` → `Bash`) |
| Human-in-the-loop | Guard `ask` → Hermes `{"action":"approve",...}` (CLI `/approve`, gateway approval) |
| Fail closed | `fail_closed: true` on `pre_tool_call` + guard `on_error: ask` |
| Quality eval | `post_llm_call` scores each turn; logs to `~/.local/state/jev-style-guard/quality.jsonl` |
| Audit | Guard decisions: `~/.local/state/jev-style-guard/guard.jsonl` |

## Install

```bash
python3 -m venv ~/.venvs/jev-style
~/.venvs/jev-style/bin/pip install 'jev-style>=0.3'
~/.venvs/jev-style/bin/jev-style download --release 2b-v3
```

Merge [`templates/hermes-jev-hooks.yaml`](./templates/hermes-jev-hooks.yaml) into `~/.hermes/config.yaml`. Expand `~/homelab` if the repo lives elsewhere.

Start the optional local server (recommended on the homelab host so hooks stay fast):

```bash
JEV_STYLE_RELEASE=2b-v3 bash ~/homelab/scripts/jev_style_serve.sh
export JEV_STYLE_URL=http://127.0.0.1:8765/v1
```

Register hook consent:

```bash
hermes hooks doctor
hermes hooks test pre_tool_call --command ~/homelab/hermes/hooks/jev_pre_tool_call.sh
```

## Manual checks

**Hard rule (no model server required):**

```bash
printf '%s' '{"hook_event_name":"pre_tool_call","tool_name":"terminal","tool_input":{"command":"rm -rf /"}}' \
  | JEV_STYLE_PYTHON=~/.venvs/jev-style/bin/python ~/homelab/hermes/hooks/jev_pre_tool_call.sh
# → {"action":"block",...}
```

**Human approval path (sudo):**

```bash
printf '%s' '{"hook_event_name":"pre_tool_call","tool_name":"terminal","tool_input":{"command":"sudo systemctl restart docker"}}' \
  | JEV_STYLE_PYTHON=~/.venvs/jev-style/bin/python ~/homelab/hermes/hooks/jev_pre_tool_call.sh
# → {"action":"approve",...}  Hermes prompts before running
```

**Quality log (fake engine for CI / offline):**

```bash
export JEV_STYLE_QUALITY_FAKE=1 JEV_QUALITY_LOG_PATH=/tmp/quality-test.jsonl
printf '%s' '{"session_id":"t1","extra":{"user_message":"Погода","assistant_response":"Сейчас +5°C"}}' \
  | JEV_STYLE_PYTHON=~/.venvs/jev-style/bin/python ~/homelab/hermes/hooks/jev_post_response.py
tail -1 /tmp/quality-test.jsonl | jq .
```

**End-to-end with Hermes:**

```bash
hermes run "Выключи свет в гостиной"    # HA tool → pre_tool_call gate
hermes run "Расскажи о квантовой физике" # post_llm_call quality line in quality.jsonl
```

## Thresholds (plan defaults)

| Setting | Value | Location |
|---------|-------|----------|
| Model | `2b-v3` (2B Decision v3) | `JEV_STYLE_RELEASE`, guard server `model` |
| Allow band | implicit when all scores below `ask` | `guard_config.homelab.json` → `thresholds` |
| Deny band | e.g. destructive ≥ 0.93 | bundled thresholds |
| Quality log threshold | 0.7 | `JEV_QUALITY_SCORE_THRESHOLD` |

Tune thresholds in `hermes/hooks/guard_config.homelab.json` or copy to `~/.config/jev-style/guard_config.json`.

## Measuring ≥90% classification

1. Label scenarios in [`jev-classification-tests.md`](./jev-classification-tests.md) (40 cases, 36+ must match on host).
2. Run offline guard replay on logged calls: `jev-style guard-replay --help`
3. Optional labelled JSONL eval: `jev-style eval docs/fixtures/jev-quality-labels.jsonl --fake` (quality head only).

```bash
bash ~/homelab/scripts/test_jev_hooks.sh
```

## Rollback

1. Remove the `hooks:` entries from `~/.hermes/config.yaml` (or set `JEV_STYLE_GUARD_DISABLE=1` for debugging).
2. `hermes hooks list` — delete allowlist entries if needed (`~/.hermes/shell-hooks-allowlist.json`).
3. Stop `jev-style serve` if running.

Hermes returns to direct tool routing without Jev scoring.
