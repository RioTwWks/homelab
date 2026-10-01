# Homelab redesign — волна 1 (A1–A8, без A9)

Интеграционная ветка: `cursor/homelab-redesign-wave1-62e2`  
Заменяет отдельные draft PR #5–#7, #9–#13 одним merge в `main`.

## Рекомендуемый порядок слияния (минимизация конфликтов)

| Шаг | PR | Агент | Ветка | Примечание |
|-----|-----|-------|-------|------------|
| 1 | #12 | A1 | `cursor/hermes-migration-skills-62e2` | **База:** Hermes skills, homelab modes UI/API, CI `hermes-tools` |
| 2 | #5 | A4 | `cursor/opencode-ollama-setup-62e2` | Доки + `config/opencode/` (конфликт только `AGENTS.md`) |
| 3 | #6 | A7 | `cursor/vpn-headscale-amnezia-cf-62e2` | Ansible remote access (`AGENTS.md`, `README.md`) |
| 4 | #7 | A6 | `cursor/monitoring-grafana-npu-62e2` | Profile `monitoring`, Grafana/Prometheus |
| 5 | #13 | A3 | `cursor/hermes-jev-hooks-62e2` | Jev hooks + CI job `hermes-jev-hooks` |
| 6 | #9 | A2+A4 NPU | `cursor/hermes-voice-npu-stt-62e2` | Voice Ansible, FLM NPU (`Makefile`, `AGENTS.md`) |
| 7 | #11 | A5 | `cursor/hermes-qdrant-rag-62e2` | RAG scripts, compose/env |
| 8 | #10 | A8 | `cursor/ai-gaming-media-modes-ui-62e2` | Уже в #12 (A1); отдельный merge не даёт diff |

**Вывод:** 8 последовательных merge в main дали бы те же конфликты в `AGENTS.md`, `README.md`, `ci.yml`, `Makefile`, `docker-compose.yml`. **Один integration PR** — оптимально.

## Чеклист применения на хосте (после merge в main)

```bash
cd ~/homelab   # или ваш путь к клону
git pull origin main

# Docker Compose офлайн (Agent B1): default, ui, monitoring, search + raid overlays
bash scripts/verify/compose-config.sh
# exit 0; последняя строка: OK: docker compose config (default, ui, monitoring, search, raid overlays)

# Hermes офлайн (Agent B1)
bash scripts/hermes-install-skills.sh   # 6 symlink в ~/.hermes/skills/homelab/
set -a && source scripts/hermes-env.sh && set +a
# REDIS_URL=redis://127.0.0.1:6379/0 MEDIA_API_BASE_URL=http://127.0.0.1:8090 SEARXNG_BASE_URL=http://127.0.0.1:18081
bash scripts/hermes-validate-tools.sh   # 8 passed; OK: Hermes homelab tools (offline pytest)
python3 -m venv .venv-ci && .venv-ci/bin/pip install -q -r moltbot_api/requirements.txt -r moltbot_api/requirements-dev.txt
.venv-ci/bin/python -m pytest hermes/tests/test_tool_parsers.py -v   # 4 passed

# Валидация (репозиторий; NPU не нужен)
make check
python3 -m pytest moltbot_api/tests/test_homelab_mode.py -q
python3 -m pytest hermes/tests/ -q
bash scripts/test_jev_hooks.sh
# Хостовые шаги voice/NPU/monitoring: docs/runbook-voice-monitoring.md

# Compose (по необходимости)
docker compose --profile ui up -d --build
docker compose --profile monitoring up -d   # Phase 7
docker compose --profile search up -d

# Ansible presets (из local.yml)
make configure          # если ещё нет local.yml
make install-voice      # Hermes voice
make install-voice-npu  # + FastFlowLM NPU STT
make remote-access      # Headscale + cloudflared

# RAG (опционально)
cp .env.example .env    # QDRANT_*, при необходимости
bash scripts/rag/ingest.sh

# OpenCode (хост, не Docker)
# docs/opencode.md — qwen3-coder:30b, Modelfile 64K

# Homelab modes (UI + executor)
sudo cp scripts/systemd/homelab-mode-*.service scripts/systemd/homelab-mode-sync.path /etc/systemd/system/
sudo systemctl daemon-reload
# runtime/homelab-mode/state.json — см. docs/homelab-modes.md
```

**Compose-профили (ориентир по `config --services`):** default — 5 сервисов; `--profile ui` — 6; `--profile monitoring` — 9; `--profile search` — 6. Подробнее: `docs/hermes-phase1-runbook.md`, CI job **Docker Compose validate**.

## Связанные draft PR (закрыть после merge wave PR)

- #12 A1, #13 A3, #9 A2, #11 A5, #10 A8, #5 A4, #6 A7, #7 A6

**Не включено:** A9 / 128GB phase.
