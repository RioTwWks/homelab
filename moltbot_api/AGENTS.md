# moltbot_api

FastAPI-оркестратор голосового ассистента.

## Запуск локально

```bash
cd moltbot_api
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8080
curl http://localhost:8080/healthz
```

В Docker: порт **18080** (маппинг на 8080).

## Структура

- `app/main.py` — маршруты, intent routing, chat/stream
- `app/tools/` — news, weather, media_control, home_assistant, timers, web_search, versions
- `app/ollama_client.py` — клиент Ollama
- `app/redis_cache.py` — кеш и настройки сессий
- `tests/` — pytest

## Добавление tool

1. Создать `app/tools/<name>.py` с чистой функцией/fetch
2. Подключить в `detect_intent_ru()` и `chat()` в `main.py`
3. Добавить тест (моки httpx/Redis)
4. Задокументировать env vars в `README.md` или `docs/`

## Тесты

```bash
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest tests/ -v
```

## Зависимости от внешних сервисов

| Сервис | Env | Где |
|--------|-----|-----|
| Ollama | `OLLAMA_BASE_URL` | host |
| Redis | `REDIS_URL` | docker |
| media-api | `MEDIA_API_BASE_URL` | docker |
| Home Assistant | `HOME_ASSISTANT_URL`, `HOME_ASSISTANT_TOKEN` | optional |
| SearXNG | `SEARXNG_BASE_URL` | docker profile `search` |
