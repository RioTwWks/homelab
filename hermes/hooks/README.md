# Hermes × Jev-Style hooks (Phase 3)

Shell hooks wired from `~/.hermes/config.yaml` (`hooks:` block). See [docs/jev-hooks.md](../../docs/jev-hooks.md).

| File | Hermes event | Role |
|------|----------------|------|
| `jev_pre_tool_call.sh` | `pre_tool_call` | PreToolUse gate → block / human approval |
| `jev_post_response.sh` | `post_llm_call` | Quality score → `quality.jsonl` |
| `guard_config.homelab.json` | — | Guard thresholds + homelab hard rules |

Install runtime:

```bash
python3 -m venv ~/.venvs/jev-style
~/.venvs/jev-style/bin/pip install 'jev-style>=0.3'
~/.venvs/jev-style/bin/jev-style download --release 2b-v3
```

Optional long-running scorer (lower latency for guard):

```bash
JEV_STYLE_RELEASE=2b-v3 bash scripts/jev_style_serve.sh
```
