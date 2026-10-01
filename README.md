# Moltbot voice hub (MVP)

Домашний голосовой хаб на Linux: локальный ассистент (Moltbot + Ollama), умный дом, медиа на HDMI (Kodi, Stremio, браузер) и серверные сервисы в Docker. Целевая платформа — mini PC **AMD Ryzen AI 9 HX 370**, **Radeon 890M**, **32 GB RAM**, **Ubuntu 26.04 LTS Desktop**.

Подробнее:

- [docs/architecture.md](docs/architecture.md) — слои системы, голосовой контур, Docker vs host, режимы ресурсов
- [docs/platform.md](docs/platform.md) — выбор ОС, установка хоста, драйверы

**Разделение по слоям:**

- **Docker:** `moltbot-api` (оркестратор), Redis, Qdrant, MQTT, `media-api`, `moltbot-ui`; опционально Home Assistant, Nextcloud, Immich, GitLab, qBittorrent, SearxNG (профили в `docker-compose.yml`)
- **Host (вне Docker):** Ollama (`qwen3:4b` / `qwen3:8b`), Whisper STT, TTS, wake word, media executor, Kodi/Stremio/браузер на HDMI

## Быстрый старт

### Вариант A: Makefile + Ansible (рекомендуется)

```bash
sudo apt install -y make ansible-core
make configure    # wizard → ansible/group_vars/local.yml
make install      # Docker, Ollama, compose, health check
```

Пресеты: `make install-minimal` | `make install-voice` | `make install-full`.  
Подробно: [`docs/install.md`](docs/install.md).

### Вариант B: вручную (docker compose)

1) Скопируйте `.env.example` в `.env` и при необходимости отредактируйте.

2) Поднимите контейнеры:

```bash
docker compose up -d --build
```

3) Проверьте здоровье сервиса:

```bash
curl -s http://localhost:18080/healthz | jq
```

4) Тест «обычный диалог» (через ваш Ollama):

```bash
curl -s http://localhost:18080/v1/chat \
  -H 'content-type: application/json' \
  -d '{"text":"Привет! Скажи коротко, что ты умеешь?","session_id":"demo"}' | jq
```

5) Тест «новости России» (RSS источники по умолчанию):

```bash
curl -s http://localhost:18080/v1/chat \
  -H 'content-type: application/json' \
  -d '{"text":"Какие последние новости в России? 5 пунктов.","session_id":"demo"}' | jq
```

6) Тест «погода»:

- без ключей будет использован бесплатный fallback (Open‑Meteo + геокодер)
- с ключом `OPENWEATHER_API_KEY` — OpenWeatherMap
- с ключом `YANDEX_WEATHER_API_KEY` — Yandex Weather (если ключ рабочий)

```bash
curl -s http://localhost:18080/v1/chat \
  -H 'content-type: application/json' \
  -d '{"text":"Какая погода сейчас в Москве?","session_id":"demo"}' | jq
```

### Настройки локации для погоды (город + район)

Можно задать дефолтную локацию на сессию (будет использоваться, если в запросе нет города):

```bash
curl -s http://localhost:18080/v1/settings/weather \
  -H 'content-type: application/json' \
  -d '{"session_id":"demo","city":"Москва","district":"Таганский район"}' | jq
```

Также можно задать **глобальные дефолты** в `.env` (используются, если не настроена сессия):

- `DEFAULT_WEATHER_CITY`
- `DEFAULT_WEATHER_DISTRICT`

Проверить настройки:

```bash
curl -s "http://localhost:18080/v1/settings/weather?session_id=demo" | jq
```

### Погода по времени

- Через час:

```bash
curl -s http://localhost:18080/v1/chat \
  -H 'content-type: application/json' \
  -d '{"text":"Какая погода через час?","session_id":"demo"}' | jq
```

- Завтра:

```bash
curl -s http://localhost:18080/v1/chat \
  -H 'content-type: application/json' \
  -d '{"text":"Какая погода завтра в Москве?","session_id":"demo"}' | jq
```

- На неделю:

```bash
curl -s http://localhost:18080/v1/chat \
  -H 'content-type: application/json' \
  -d '{"text":"Погода на неделю в Новосибирске","session_id":"demo"}' | jq
```

## Home Assistant (опционально)

Home Assistant включён профилем `ha` (тяжёлый сервис):

```bash
docker compose --profile ha up -d
```

UI по умолчанию будет на `http://localhost:8123`.

**Голосовое управление:** если заданы `HOME_ASSISTANT_URL` и `HOME_ASSISTANT_TOKEN` в `.env`, Moltbot по командам «включи свет», «выключи свет в гостиной», «температура 22» вызывает API HA (REST). Токен создаётся в HA: Профиль → внизу «Токены» → Long-Lived Access Token. Подробнее: `docs/home-assistant.md`.

## Файловое хранилище (Nextcloud)

Аналог Google Drive / Яндекс.Диск: веб-интерфейс, синхронизация на ПК, мобильные приложения. Включение профилем `storage`:

```bash
docker compose --profile storage up -d
```

В `.env` задайте `NEXTCLOUD_ADMIN_PASSWORD` (и при необходимости `NEXTCLOUD_TRUSTED_DOMAINS` для доступа по IP/домену). Веб-интерфейс: http://localhost:18082. Подробнее: `docs/file-storage.md`.

## Фото- и видеохранилище (Immich)

Аналог Google Фото: веб + мобильные приложения (iOS/Android), автозагрузка с телефона, лица, альбомы. Профиль `photos`:

```bash
docker compose --profile photos up -d
```

Веб-интерфейс: http://localhost:18083. Первый пользователь при регистрации становится админом. Подробнее: `docs/photos-storage.md`.

## GitLab (CI/CD)

Репозитории, пайплайны, Container Registry. Включение профилем `gitlab` (тяжёлый сервис):

```bash
docker compose --profile gitlab up -d
```

По умолчанию: веб `http://localhost:18090`, SSH порт 2222, Registry порт 5005. В `.env` можно задать `GITLAB_EXTERNAL_URL`, `GITLAB_HTTP_PORT` и др.

Grafana и Prometheus — профиль **`monitoring`** (не `gitlab`): `docker compose --profile monitoring up -d`, дашборды и all-smi — `docs/monitoring.md`.

Вместе с профилем поднимается **GitLab Runner** (конфиг в `gitlab-runner-config/config.toml`; пример — `config.toml.example`). Перенос существующего GitLab и Runner из другой директории: `docs/gitlab-migration.md`.

## Media Control (голосовое управление медиа)

- **media-api** принимает команды (открыть URL, пауза, громкость и т.д.) и при настройке пересылает их на хост (executor).
- Голос: «включи ютуб», «пауза», «вк видео» и др. — см. `docs/media-control.md` и маппинг в `moltbot_api/app/tools/media_control.py`.
- **Чтобы браузер открывался:** (1) в `.env` задать `MEDIA_EXECUTOR_URL=http://host.docker.internal:8091`, (2) на хосте запустить `python scripts/media_executor_example.py`, (3) перезапустить контейнеры.

## Следующие шаги

- Архитектура и платформа: `docs/architecture.md`, `docs/platform.md`.
- Голосовой MVP (push-to-talk): см. `docs/voice-mvp.md`.
- Web-search fallback (SearxNG + DuckDuckGo): см. `docs/web-search.md`.
- Media Control API и варианты плееров: см. `docs/media-control.md`.
- Подключить Whisper (STT) и TTS на хосте.
- Умный дом голосом: `docs/home-assistant.md`.
- Хранилище на RAID (3+ HDD для Nextcloud и Immich): `docs/storage-raid.md`, пример override: `docker-compose.raid.example.yml`.
- Торренты (фильмы/сериалы/музыка из загрузок): qBittorrent (профиль `torrents`), папка загрузок — источник в Kodi; голос: «открой торренты». `docs/torrents.md`.
- Черновики статей (Habr, Telegram): `docs/drafts/`.
- Резервное копирование всей системы (как RAID для файлов/фото): вся система на RAID — `docker-compose.raid-full.example.yml` (см. `docs/storage-raid.md`); автоматический бэкап по расписанию — `scripts/backup.sh` + systemd timer в `scripts/systemd/`. Подробно: `docs/backup.md`.
- Кодинг-ассистент OpenCode + Ollama (`qwen3-coder:30b`, контекст ≥64K): `docs/opencode.md`, пример конфига — `config/opencode/opencode.json`.
- Удалённый доступ (AmneziaWG, Headscale, Cloudflare Tunnel): `docs/remote-access.md`, Ansible: `make remote-access`.

