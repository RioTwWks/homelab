# media_api

FastAPI-сервис медиа-команд: принимает JSON-команды от moltbot-api и пересылает на host executor.

## Запуск

```bash
cd media_api
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8090
```

В Docker: порт **8090**.

## API

| Method | Path | Описание |
|--------|------|----------|
| GET | `/healthz` | Health check |
| POST | `/v1/command` | Медиа-команда |
| GET | `/v1/command/last` | Последняя команда (debug) |

**Actions:** `open_url`, `play`, `pause`, `next`, `prev`, `volume_set`, `volume_up`, `volume_down`, `fullscreen`, `kodi`

**Targets:** `browser`, `kodi`, `mpris`, `ui`

## Executor

Без `MEDIA_EXECUTOR_URL` команды только сохраняются. Для реального управления:

```bash
# .env
MEDIA_EXECUTOR_URL=http://host.docker.internal:8091

# host
python scripts/media_executor_example.py
```

Документация: `docs/media-control.md`

## Тесты

```bash
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest tests/ -v
```

## Связь с moltbot-api

Голосовые фразы парсятся в `moltbot_api/app/tools/media_control.py` → POST на `MEDIA_API_BASE_URL/v1/command`.
