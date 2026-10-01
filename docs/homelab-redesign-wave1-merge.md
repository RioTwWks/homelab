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

# Валидация
docker compose -f docker-compose.yml config --quiet
python3 -m pytest moltbot_api/tests/test_homelab_mode.py -q
python3 -m pytest hermes/tests/ -q
bash scripts/test_jev_hooks.sh
ansible-playbook --syntax-check ansible/playbooks/site.yml
ansible-playbook --syntax-check ansible/playbooks/voice.yml
ansible-playbook --syntax-check ansible/playbooks/remote_access.yml

# Hermes Phase 1
bash scripts/hermes-install-skills.sh
bash scripts/hermes-validate-tools.sh

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

## Связанные draft PR (закрыть после merge wave PR)

- #12 A1, #13 A3, #9 A2, #11 A5, #10 A8, #5 A4, #6 A7, #7 A6

**Не включено:** A9 / 128GB phase.

## Post-merge runbook — Agent B3 (RAG фаза 6 + modes фаза 9)

Ветка проверки: `cursor/runbook-rag-modes-62e2`.

| Область | Проверка | Результат (2026-10-01) |
|---------|----------|------------------------|
| Compose | `qdrant` в базовом стеке, `moltbot-api` → `QDRANT_URL`, `depends_on: qdrant`, том `runtime/homelab-mode` | OK |
| RAG ingest | `./scripts/rag/ingest.sh --dry-run` | OK (67 files, 403 chunks) |
| RAG smoke | `--fake-embeddings --limit-chunks 5` + `search` при поднятом Qdrant | OK |
| Modes API | `pytest moltbot_api/tests/test_homelab_mode.py` | 3 passed |
| Modes host | `bash -n scripts/homelab_mode.sh`; `docs/homelab-modes.md` ↔ `homelab_mode.py` / executor `:8092` | OK |

Автоматизация: `bash scripts/verify-runbook-rag-modes.sh` (без Qdrant — dry-run + pytest; с `docker compose up -d qdrant` — полный fake-embeddings smoke).
