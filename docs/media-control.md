# Media Control API

Единая точка для голосового управления медиа: браузер (kiosk), Kodi, ТВ, музыка. Moltbot при командах типа «включи ютуб», «пауза» вызывает media-api; media-api при настроенном **executor** пересылает команду на хост.

## Схема

```
Голос → Moltbot (intent=command) → media-api (POST /v1/command)
                                        ↓
                        MEDIA_EXECUTOR_URL (опционально)
                                        ↓
                        Хост: скрипт/сервис (браузер, Kodi, MPRIS…)
```

## Контракт API (media-api)

**POST /v1/command** — тело запроса (JSON):

| Поле    | Тип    | Обязательное | Описание |
|---------|--------|--------------|----------|
| `action` | string | да | `open_url` \| `play` \| `pause` \| `next` \| `prev` \| `volume_set` \| `volume_up` \| `volume_down` \| `fullscreen` \| `kodi` |
| `url`   | string | для open_url | URL для открытия (или параметр для kodi) |
| `value` | int    | для volume_set | Число (например громкость 0–100) |
| `target`| string | нет (default: browser) | `browser` \| `kodi` \| `mpris` \| `ui` |
| `label` | string | нет | Подпись для логов/UI |

Примеры:

```json
{"action": "open_url", "url": "https://www.youtube.com", "target": "browser", "label": "YouTube"}
{"action": "pause", "target": "browser", "label": "Пауза"}
{"action": "volume_up", "target": "browser"}
```

**GET /v1/command/last** — последняя принятая команда (отладка).

**GET /healthz** — проверка работы сервиса.

## Переменные окружения

- **media-api**
  - `MEDIA_EXECUTOR_URL` — URL сервиса на хосте, которому пересылать команды. Пример: `http://host.docker.internal:8091`. Если не задан, команды только сохраняются (ответ 200, executor не вызывается).

- **moltbot-api**
  - `MEDIA_API_BASE_URL` — URL media-api. В docker compose: `http://media-api:8090`.

## Executor на хосте

Executor — любой HTTP-сервис на хосте, принимающий **POST** с телом в формате команды (см. контракт выше). По `action` и `target` решаешь, что сделать: открыть URL в браузере, отправить JSON-RPC в Kodi, вызвать MPRIS (playerctl) и т.д.

**Два варианта executor:**

1. **Обычный браузер** (открывает URL в текущем/системном браузере):
   ```bash
   python scripts/media_executor_example.py
   ```

2. **Kiosk (один Chromium на весь экран)** — по команде переключает этот же окно на нужный URL:
   ```bash
   pip install websocket-client   # один раз
   python scripts/media_executor_kiosk.py
   ```
   Скрипт по умолчанию сам запускает Chromium в kiosk. Если в логе «CDP: no page target» (окно есть, но переход по URL не срабатывает) — часто это значит, что команда `chromium` у вас лишь лаунчер и реально открывается другой браузер. Тогда **запустите нужный браузер вручную** с отладкой и kiosk, затем executor с флагом «не запускать»:
   ```bash
   chromium --remote-debugging-port=9222 --remote-allow-origins=* --kiosk
   # в другом терминале:
   MEDIA_KIOSK_NO_LAUNCH=1 python scripts/media_executor_kiosk.py
   ```
   Флаг `--remote-allow-origins=*` нужен, чтобы скрипт мог подключаться к CDP по WebSocket.
   Подставьте свой бинарь (`google-chrome`, `chromium`, `yandex-browser` и т.д.). Скрипт по умолчанию ищет `chromium` → `chromium-browser` → `google-chrome` → `google-chrome-stable`; если у вас нет chromium, задайте `MEDIA_KIOSK_CHROMIUM=google-chrome`. Используется отдельный профиль (`~/.cache/media-kiosk-browser`), чтобы не переиспользовать уже запущенный браузер (иначе он не откроет порт 9222). Переменные: `MEDIA_KIOSK_CHROMIUM`, `MEDIA_KIOSK_CDP_PORT=9222`, `MEDIA_KIOSK_NO_LAUNCH=1`, `MEDIA_KIOSK_USER_DATA_DIR`.

В **.env** (в корне репо, откуда поднимается docker compose) задайте:

```env
MEDIA_EXECUTOR_URL=http://host.docker.internal:8091
```

На **хосте** запустите executor (и держите его запущенным):

```bash
python scripts/media_executor_example.py
```

### Автозапуск executor в фоне при входе в систему

Чтобы не держать терминал открытым и запускать executor при входе в систему, используйте один из способов ниже. Путь к репозиторию в примерах — `/home/ivan/homelab`; при необходимости замените на свой.

**Способ 1: автозапуск через рабочий стол (XDG Autostart)**

1. Скопируйте desktop-файл в папку автозапуска:
   ```bash
   mkdir -p ~/.config/autostart
   cp /home/ivan/homelab/scripts/media-executor-kiosk.desktop ~/.config/autostart/
   ```
2. Если homelab у вас не в `~/homelab` или вы используете другой venv, отредактируйте `Exec` и `Path` в `~/.config/autostart/media-executor-kiosk.desktop` (путь к Python — по умолчанию `~/.venvs/media/bin/python`, рабочая директория — корень репо).
3. При следующем входе в сессию executor запустится в фоне (окно терминала не нужно).

**Способ 2: systemd user-сервис**

Удобно, если нужны логи (`journalctl --user -u media-executor-kiosk.service`) и перезапуск при сбое:

```bash
mkdir -p ~/.config/systemd/user
cp /home/ivan/homelab/scripts/media-executor-kiosk.service ~/.config/systemd/user/
# при другом пути к homelab или другом venv отредактируйте WorkingDirectory и ExecStart (по умолчанию Python: ~/.venvs/media/bin/python)
systemctl --user daemon-reload
systemctl --user enable media-executor-kiosk.service
systemctl --user start media-executor-kiosk.service
```

Проверка: `systemctl --user status media-executor-kiosk.service`. Логи в реальном времени: `journalctl --user -u media-executor-kiosk.service -f`.

После этого перезапустите контейнеры (`docker compose up -d`), чтобы media-api подхватил `MEDIA_EXECUTOR_URL`. Если браузер не открывается — проверьте, что executor запущен на хосте и что переменная задана в .env и перезапущен media-api.

## Голосовые фразы (moltbot → media)

Маппинг в `moltbot_api/app/tools/media_control.py`. Сейчас распознаются, в частности:

- **Открыть:** ютуб, вк видео, твитч, телеграм, вк музыка, спотифай
- **Управление:** пауза, играй, следующий/предыдущий трек, громче, тише, полный экран

Добавление новых фраз — правка списка `MEDIA_PHRASES` в этом файле.

## Kodi

Executor `media_executor_kiosk.py` умеет отправлять команды в Kodi по JSON-RPC (порт 8080 по умолчанию).

**В Kodi:** Настройки → Службы → Управление → включить «Разрешить удалённое управление приложениями по HTTP» и задать порт (например 8092). `KODI_URL` должен совпадать с этим портом.

**Важно:** адрес `KODI_URL` (например http://127.0.0.1:8092) — это **API уже запущенного** Kodi. Открытие этого URL в браузере не запускает Kodi. Чтобы **запустить** Kodi голосом, скажи «включи коди» — executor выполнит команду из `KODI_LAUNCH_CMD` (или попробует `kodi` / `kodi-standalone`). Переменные задай в `.env` в корне репо; executor при старте подхватывает их оттуда.

**Переменные окружения (в .env или на хосте):**
- `KODI_URL=http://127.0.0.1:8092` — URL уже запущенного Kodi (порт = порт в настройках Kodi).
- `KODI_LAUNCH_CMD` — команда для запуска Kodi по фразе «включи коди». Если в логе «Kodi: not found» — укажи полный путь или команду запуска:
  - Установка из пакетов: `which kodi` → например `KODI_LAUNCH_CMD=/usr/bin/kodi`
  - Flatpak: `KODI_LAUNCH_CMD=flatpak run tv.kodi.Kodi`
  - Snap: `KODI_LAUNCH_CMD=snap run kodi`

**Голосовые фразы (target=kodi):** «коди пауза», «коди играй», «коди следующий», «коди предыдущий», «включи коди» / «открой коди».

## Музыка (MPRIS)

Команды **пауза**, **играй**, **следующий трек**, **предыдущий**, **громче**, **тише** с `target=browser` выполняются через **MPRIS** (playerctl) на хосте. Так управляется любой активный плеер с поддержкой MPRIS: вкладка браузера со Spotify или VK Музыкой, VLC, Spotifyd и т.д.

**На хосте** нужен `playerctl`:
```bash
# Debian/Ubuntu
sudo apt install playerctl
```

После «открой спотифай» / «вк музыка» воспроизведение в этой вкладке можно управлять голосом: «пауза», «следующий», «громче». Если активного плеера нет, playerctl вернёт ошибку (executor запишет в лог).

## Торренты

- **qBittorrent** (профиль `torrents` в docker-compose): загрузка торрентов; папка загрузок добавляется в Kodi как источник — фильмы/сериалы/музыка воспроизводятся из «локального хранилища» после скачивания.
- Голос: **«открой торренты»**, **«торренты»** — открывается веб-интерфейс qBittorrent (URL из `QBITTORRENT_WEB_URL`, по умолчанию http://localhost:18084). Подробнее: `docs/torrents.md`.

## Дальнейшие варианты по категориям

- **Браузер kiosk:** готовый скрипт `scripts/media_executor_kiosk.py` (см. выше).
- **Kodi:** реализовано в том же executor (JSON-RPC: Player.PlayPause, Player.GoTo, запуск по «включи коди»).
- **Музыка:** MPRIS в `media_executor_kiosk.py` (playerctl) для паузы/play/next/prev/громкость при target=browser.
- **Торренты:** qBittorrent + папка загрузок как источник в Kodi; голосом открывается Web UI.
- **ТВ:** отдельный target или action (переключить канал, EPG по локальному времени) — в контракт можно добавить позже.
