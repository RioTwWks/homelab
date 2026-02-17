## Web search fallback (SearxNG + DuckDuckGo Instant Answer)

Цель: если LLM **не уверен** в ответе на произвольный вопрос, MoltBot может выполнить web‑поиск и ответить **строго по найденным фактам**.

Поддерживаются провайдеры:
- **SearxNG** (самохост, JSON API)
- **DuckDuckGo Instant Answer** (бесплатный knowledge/instant answers; это не полноценный web search)

### Переменные окружения

Все переменные задаются для сервиса `moltbot-api` (Docker).

- `ALLOW_INTERNET_TOOLS=true|false`
  - глобальный рубильник интернет‑tools
- `WEB_SEARCH_PROVIDER=off|searxng|ddg|both`
  - `off` (по умолчанию): web‑поиск отключён
  - `searxng`: только SearxNG
  - `ddg`: только DuckDuckGo Instant Answer
  - `both`: сначала SearxNG (если настроен), затем DDG как “добавка”
- `SEARXNG_BASE_URL`
  - базовый URL SearxNG. **Если SearxNG и moltbot-api в одном docker compose** (профиль `search`) — обязательно `http://searxng:8080`, иначе запросы из контейнера не дойдут и поиск будет пустой.
  - Если SearxNG на хосте: `http://host.docker.internal:18081` (или твой порт).
- `SEARXNG_X_FORWARDED_FOR=127.0.0.1`
- `SEARXNG_X_REAL_IP=127.0.0.1`
  - некоторые инстансы SearxNG с bot‑detection требуют `X-Forwarded-For` / `X-Real-IP` даже для локального клиента
- `WEB_SEARCH_MAX_RESULTS=6`
  - сколько результатов отдавать в FACTS
- `WEB_SEARCH_LANGUAGE=ru`
  - язык запроса/поиска (передаётся провайдеру best-effort)
- `WEB_SEARCH_CACHE_TTL_SECONDS=21600`
  - кэш web‑поиска в Redis (секунды)
- `WEB_SEARCH_TIME_RANGE=day|week|month|year`
  - ограничить поиск по времени (только SearxNG): `day` — за день, `week` — за неделю, `month` — за месяц, `year` — за год. Пустое значение — без фильтра по дате. Полезно для более свежих данных.
  - для актуальных ответов можно поставить, например, `WEB_SEARCH_TIME_RANGE=week` и уменьшить кэш: `WEB_SEARCH_CACHE_TTL_SECONDS=3600`.

Если нужны актуальные цифры по организациям (например зоопарк, музей): результат зависит от того, что возвращает SearxNG. Часто в топе оказывается Википедия со старыми данными. Чтобы чаще попадали свежие/официальные источники: включи `WEB_SEARCH_TIME_RANGE=week` или `month`, уменьши кэш; при ответе модель получает инструкцию предпочитать данные из официального источника (сайт, соцсети организации), если в фактах есть противоречивые числа.

Запрос для кэша нормализуется (регистр, пунктуация, варианты названий городов: Новосибирска/Новосибирск и т.п.), чтобы похожие вопросы отдавали один и тот же результат. Числа в ответе могут всё равно различаться: в сниппетах бывают разные источники и формулировки, LLM выбирает по контексту.

### JSON спецификация tool’а (внутренний контракт)

Tool реализован как функция `fetch_web_search(...)` в `moltbot_api/app/tools/web_search.py`.

#### Input

```json
{
  "provider": "searxng | ddg | both",
  "query": "строка запроса",
  "lang": "ru",
  "max_results": 6
}
```

#### Output

```json
{
  "provider": "searxng | ddg | both",
  "query": "строка запроса",
  "instant_answer": "строка или null",
  "results": [
    {
      "title": "…",
      "url": "…",
      "snippet": "… (опционально)",
      "engine": "… (опционально)",
      "score": 12.34 (опционально)
    }
  ],
  "fact_context": "готовый текст для FACTS",
  "sources": [
    {"type": "websearch", "provider": "searxng|ddg", "base_url": "…", "error": "… (опционально)"}
  ],
  "fetched_at_unix": 1234567890
}
```

### “Промпт‑контракт” (2‑pass)

Реализовано в `moltbot_api/app/main.py` только для `intent=chat` и только если:
- `ALLOW_INTERNET_TOOLS=true`
- `WEB_SEARCH_PROVIDER != off`

#### Pass 1: Decide

Модель возвращает **строго JSON**:

```json
{"answer":"","need_search":true,"search_query":"короткий запрос 3–12 слов","provider":"searxng|ddg|both"}
```

Правила:
- если уверена в ответе и он не требует свежих данных → `need_search=false`, `answer` заполнить, `search_query` можно пустой.
- если не уверена / нужен факт / нужен свежий контекст → `need_search=true`, `answer=""`, `search_query` обязателен.

#### Pass 2: Answer with FACTS

Система требует:
- вернуть JSON `{answer:string}`
- использовать **только** `FACTS` (web‑results)
- **не вставлять URL** в текст ответа

### Практическая рекомендация для сравнения провайдеров

- `WEB_SEARCH_PROVIDER=ddg`: хорошо для “что такое X / краткая справка”, но часто не хватает для “любого вопроса”.
- `WEB_SEARCH_PROVIDER=searxng`: ближе к универсальному web‑поиску (зависит от твоего SearxNG и включённых engines).
- `WEB_SEARCH_PROVIDER=both`: даёт и web‑результаты, и “instant answer” если он есть.

### Запуск SearxNG через docker-compose (профиль `search`)

В `docker-compose.yml` добавлен опциональный сервис SearxNG с профилем `search`:

```bash
docker compose --profile search up -d
```

SearxNG будет доступен на порту **18081** (http://localhost:18081). Для moltbot-api в `.env` задай:

- `WEB_SEARCH_PROVIDER=searxng` (или `both`)
- `SEARXNG_BASE_URL=http://searxng:8080`

Так moltbot-api будет обращаться к SearxNG по внутреннему имени контейнера. JSON API поддерживается образом по умолчанию (параметр `format=json` в запросе).

### Важно про SearxNG JSON API

По умолчанию в некоторых шаблонах `settings.yml` включён только `html` формат. Для JSON API нужно:

```yaml
search:
  formats:
    - html
    - json
```

Если при запросе `.../search?...&format=json` получаешь `403 Forbidden`, значит `json` не разрешён в `search.formats`. Официальный образ `searxng/searxng:latest` обычно уже отдаёт JSON.

