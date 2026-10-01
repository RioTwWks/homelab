# AGENTS.md — homelab / Moltbot voice hub

Персональный homelab: голосовой ассистент на базе **moltbot-api** (FastAPI), **media-api**, веб/Flutter UI, Docker Compose и host-скрипты (Whisper, TTS, Ollama).

## Карта репозитория

| Путь | Назначение |
|------|------------|
| `moltbot_api/` | Оркестратор: чат, intent routing, tools, Ollama, Redis |
| `media_api/` | Прокси медиа-команд на host executor |
| `moltbot_app/` | Flutter-клиент (Android/iOS/Desktop) |
| `moltbot_ui/` | Статический веб-UI (nginx, профиль `ui`) |
| `scripts/` | Host: голос, backup, media executor, timer worker, systemd |
| `docs/` | Операционная документация |
| `hermes/` | Hermes Agent: skills + CLI (миграция с moltbot-api, фаза 1+) |
| `docker-compose.yml` | Основной стек |
| `docker-compose.raid*.example.yml` | **Override**, не standalone |
| `.cursor/rules/` | Cursor project rules (`.mdc`) |
| `.cursor/plans/` | Архитектурный план (исторический контекст) |

**Не путать:** `context.md` в корне — заметки из чата, не операционная документация. Ориентир: `README.md` + `docs/`.

## Быстрые команды

```bash
# Core stack
docker compose up -d --build
curl -s http://localhost:18080/healthz | jq

# Тесты (как в CI)
cd moltbot_api && pip install -r requirements.txt -r requirements-dev.txt && python -m pytest tests/ -v
cd media_api && pip install -r requirements.txt -r requirements-dev.txt && python -m pytest tests/ -v
cd moltbot_app && flutter pub get && flutter analyze && flutter test

# Compose validate (RAID-файлы — только с базовым compose)
docker compose -f docker-compose.yml config --quiet
docker compose -f docker-compose.yml -f docker-compose.raid.example.yml config --quiet
```

## Архитектура (критично для агентов)

```
Host: Ollama, Whisper, TTS, media executor (8091), timer_worker
Docker: moltbot-api:18080, media-api:8090, redis, qdrant, mqtt + optional profiles
```

- **Ollama на хосте**, не в Docker. Контейнер ходит на `host.docker.internal:11434`.
- **Профили** (`ha`, `ui`, `storage`, `photos`, `torrents`, `gitlab`, `monitoring`, `search`) не стартуют без `--profile`.
- **Media:** нужен `MEDIA_EXECUTOR_URL` + скрипт на хосте (`scripts/media_executor_example.py`).
- **Таймеры:** API пишет в Redis, на хосте нужен `scripts/timer_worker.py`.
- **SearXNG из контейнера:** `SEARXNG_BASE_URL=http://searxng:8080`, не `localhost`.

## Порты по умолчанию

| Порт | Сервис |
|------|--------|
| 18080 | moltbot-api |
| 18079 | moltbot-ui (profile `ui`) |
| 8090 | media-api |
| 8091 | media executor (host) |
| 8092 | homelab mode executor (host) |
| 11434 | Ollama (host) |
| 8123 | Home Assistant (profile `ha`) |

## Конвенции разработки

- Python **3.12**, FastAPI, Pydantic v2, type hints обязательны.
- Пользовательские фразы и intent detection — **на русском**.
- Секреты только в `.env` (gitignored). Не коммитить ключи API, HA token, пароли.
- Минимальный diff: не трогать несвязанный код.
- Тесты: pytest в `*/tests/`, моки для Redis/httpx/Ollama.
- CI: `.github/workflows/ci.yml` на `main`.

## Документация по темам

| Документ | Тема |
|----------|------|
| `docs/voice-mvp.md` | Hermes voice + legacy push-to-talk |
| `docs/hermes-voice-npu.md` | FastFlowLM NPU STT, `flm validate` |
| `docs/wake-word.md` | Hermes wake word + legacy openWakeWord |
| `docs/media-control.md` | media-api, executor, Kodi |
| `docs/home-assistant.md` | HA, голосовые команды |
| `docs/web-search.md` | SearXNG, WEB_SEARCH_PROVIDER |
| `docs/timers.md` | Таймеры, timer_worker |
| `docs/storage-raid.md` | RAID override-файлы |
| `docs/backup.md` | backup.sh, systemd timer |
| `docs/hermes-phase1-runbook.md` | Hermes: установка, config ≥64K, skills |
| `docs/rag-qdrant.md` | Qdrant RAG ingest, Hermes integration |
| `docs/homelab-modes.md` | AI / Gaming / Media, executor, Steam/Proton |
| `docs/opencode.md` | OpenCode + Ollama (кодинг, `~/.config/opencode`) |
| `docs/monitoring.md` | Prometheus, Grafana, all-smi |
| `docs/runbook-voice-monitoring.md` | B2 runbook: voice/NPU + monitoring validate & host steps |
| `docs/remote-access.md` | AmneziaWG, Headscale, Cloudflare Tunnel |
| `docs/jev-hooks.md` | Jev PreToolUse gate, quality logging (фаза 3) |

## Подсказки для изменений

1. Новый tool в moltbot-api → `moltbot_api/app/tools/`, подключить в `main.py`, добавить тест.
2. Новый Docker-сервис → `docker-compose.yml` + профиль + env в README/docs.
3. Flutter UI → `moltbot_app/lib/`, обновить `moltbot_api.dart` при новых эндпоинтах.
4. Веб-UI → `moltbot_ui/app.js` (без сборки).
