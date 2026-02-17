# Торренты: фильмы, сериалы, музыка

Два сценария:

- **Скачать и смотреть** — qBittorrent загружает торренты, Kodi воспроизводит из папки загрузок.
- **Стриминг без скачивания** — Stremio стримит торренты через аддон Torrentio (Rutracker, RuTor и др.) без отдельного индексера.

## Архитектура

```
Голос / Браузер
       │
       ▼
  ┌─────────────┐   поиск торрентов   ┌────────────┐
  │   Stremio   │────────────────────▶│  Torrentio │ (Rutor, Rutracker, 1337x…)
  │  Web / App  │                     └────────────┘
  │             │   стриминг  ┌──────────────┐
  │             │────────────▶│Stremio Server│
  └─────────────┘             └──────────────┘
                                    │
       Скачивание:                  │ (или)
  ┌──────────────┐                  │
  │ qBittorrent  │◀─────────────────┘
  │  /downloads  │
  └──────┬───────┘
         │
    ┌────▼────┐
    │  Kodi   │
    └─────────┘
```

## Запуск

Все сервисы торрент-стека в одном профиле:

```bash
docker compose --profile torrents up -d
```

Это поднимет: **qBittorrent**, **Stremio Server**.

## Запуск qBittorrent

```bash
docker compose --profile torrents up -d
```

Веб-интерфейс: http://localhost:18084 (порт задаётся `QBITTORRENT_WEB_PORT` в `.env`). Логин: **admin**, пароль — **временный**, генерируется при первом запуске. Посмотрите его в логах контейнера:

```bash
docker logs homelab-qbittorrent-1 2>&1 | grep "temporary password"
```

После входа установите постоянный пароль: **Settings → Web UI → Authentication**.

## Связка с Kodi (воспроизведение из загрузок)

Чтобы смотреть скачанное в Kodi, Kodi должен видеть папку загрузок qBittorrent.

**Вариант A: папка на хосте.** Примонтируйте каталог хоста в контейнер qBittorrent и добавьте этот же каталог в Kodi как источник видео:

В `docker-compose.override.yml` (или в основном compose для профиля torrents):

```yaml
services:
  qbittorrent:
    volumes:
      - qbittorrent_config:/config
      - /path/on/host/torrents_downloads:/downloads
```

В Kodi: Настройки → Медиа → Видео → Добавить источник → укажите `/path/on/host/torrents_downloads` (или подкаталог, куда qBittorrent складывает файлы). Сканирование библиотеки — по желанию.

**Вариант B: только Docker-том.** Том `qbittorrent_downloads` лежит в каталоге Docker (например `/var/lib/docker/volumes/homelab_qbittorrent_downloads/_data`). В Kodi можно добавить этот путь как источник, если Kodi имеет к нему доступ (тот же хост). На практике удобнее Вариант A с явной папкой на хосте.

## Настройка Stremio

Stremio Server (контейнер): http://localhost:11480

**Рекомендуется:** установите **десктоп-приложение** Stremio и войдите тем же аккаунтом, что в веб-версии — все аддоны синхронизируются автоматически. Голосовая команда «открой стремио» будет открывать десктоп-приложение.

**Установка:**

- **Flatpak** (рекомендуется для Ubuntu 24.04+):
  ```bash
  sudo apt install flatpak
  sudo flatpak remote-add --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo
  sudo flatpak install flathub com.stremio.Stremio
  ```
  После установки создайте обработчик протокола `stremio://`:
  ```bash
  mkdir -p ~/.local/share/applications
  cat > ~/.local/share/applications/stremio-url.desktop << 'EOF'
  [Desktop Entry]
  Version=1.0
  Type=Application
  Name=Stremio (URL Handler)
  Exec=flatpak run com.stremio.Stremio %u
  Icon=com.stremio.Stremio
  Terminal=false
  MimeType=x-scheme-handler/stremio;
  EOF
  update-desktop-database ~/.local/share/applications
  xdg-mime default stremio-url.desktop x-scheme-handler/stremio
  ```
  **Если Flatpak даёт чёрный экран** (ошибки `qt.qpa.qgnomeplatform: Could not find color scheme`, `QSocketNotifier`) — на Ubuntu 24.04 лучше поставить **нативный .deb** (официальный .deb требует libmpv1, в 24.04 есть только libmpv2). Вариант:
  ```bash
  # Удалить Flatpak-версию (опционально)
  flatpak uninstall com.stremio.Stremio

  # Установить Stremio с исправленными зависимостями для Ubuntu 24.04
  wget -O - https://raw.githubusercontent.com/Kabir5296/Stremio-Ubuntu24.04-Fix/refs/heads/main/install_stremio.sh | bash
  ```
  После установки создайте обработчик протокола для нативного Stremio:
  ```bash
  mkdir -p ~/.local/share/applications
  cat > ~/.local/share/applications/stremio-url.desktop << 'EOF'
  [Desktop Entry]
  Version=1.0
  Type=Application
  Name=Stremio (URL Handler)
  Exec=stremio %u
  Icon=stremio
  Terminal=false
  MimeType=x-scheme-handler/stremio;
  EOF
  update-desktop-database ~/.local/share/applications
  xdg-mime default stremio-url.desktop x-scheme-handler/stremio
  ```
  Если при запуске Stremio Desktop видишь в терминале ошибки:
  - `Error: listen EADDRINUSE ... port: 11470` и/или `12470`
  - затем `qml: initShellComm is not defined`

  значит **порты 11470/12470 заняты**, чаще всего контейнером `stremio-server` из этого `docker-compose.yml`.
  Решение: **остановить контейнер** или изменить порты контейнера (по умолчанию в compose уже стоят 11480/12480).
  Быстрая проверка:
  ```bash
  docker ps --format '{{.Names}}\t{{.Ports}}' | grep stremio
  ```
  Быстро остановить:
  ```bash
  docker stop homelab-stremio-server-1
  ```
  Если `xdg-open 'stremio:///board'` выдаёт **«gio: The specified location is not supported»**, явно укажите обработчик в `~/.config/mimeapps.list` в секции `[Default Applications]`:
  ```bash
  mkdir -p ~/.config
  grep -q 'x-scheme-handler/stremio=' ~/.config/mimeapps.list 2>/dev/null || echo 'x-scheme-handler/stremio=stremio-url.desktop' >> ~/.config/mimeapps.list
  ```
  Голосовой скрипт при «открой стремио» сам пробует запуск: сначала `stremio`, затем Flatpak, затем xdg-open — без зависимости от gio.

  **Если скрипт Ubuntu 24.04 Fix не смог скачать .deb** (SSL/сеть): скачайте [stremio_4.4.168-1_amd64.deb](https://dl.strem.io/shell-linux/v4.4.168/stremio_4.4.168-1_amd64.deb) вручную (или новую версию с [stremio.com](https://www.stremio.com/downloads)), пересоберите зависимости (замена libmpv1→libmpv2) по инструкции в [Stremio-Ubuntu24.04-Fix](https://github.com/Kabir5296/Stremio-Ubuntu24.04-Fix) или поставьте **AppImage** / снова **Flatpak**.

- **AppImage:** скачайте с [stremio.com/downloads](https://www.stremio.com/downloads) → Linux → AppImage, сделайте исполняемым (`chmod +x Stremio-*.AppImage`) и запустите — при первом запуске предложит интеграцию (создаст ярлык и зарегистрирует протокол).

**Альтернатива:** веб-версия https://app.stremio.com (укажет на локальный сервер автоматически).

### Аддон Torrentio (русский контент)

Torrentio поддерживает **Rutor** и **Rutracker** из коробки (без авторизации):

1. Откройте https://torrentio.strem.fun/configure
2. В разделе **Providers** включите **Rutor** и **Rutracker**
3. Нажмите **Install** → аддон добавится в Stremio

### Русские названия и каталоги

Чтобы видеть названия фильмов и сериалов на русском и русский контент во вкладках Home и Discover:

1. **Язык интерфейса:** в Stremio откройте **Settings → Interface Language → Russian**.
2. **Аддон TMDB** (русские названия, описания, постеры):
   - Получите бесплатный **TMDB API Key:** зарегистрируйтесь на [themoviedb.org](https://www.themoviedb.org), откройте [Настройки → API](https://www.themoviedb.org/settings/api), запросите API Key (тип «Developer»).
   - Откройте страницу настройки аддона TMDB (через Stremio: Addons → Community → The Movie Database Addon, или найдите «TMDB» в [каталоге аддонов](https://stremio-addons.netlify.app/)) и укажите **API Key** и язык **Russian (ru)** → **Install**.
3. **Каталоги на Home/Discover** — варианты:
   - **KinoPub** — русский контент (фильмы и сериалы) в Stremio. Требует **подписку на [kino.pub](https://kino.pub)**. Установка: откройте [страницу настройки KinoPub](https://0a5433015240-stremio-kinopub.baby-beamup.club/configure), затем перейдите на [kino.pub/device](https://kino.pub/device) и введите код с страницы настройки — после активации аддон появится в Stremio и будет отдавать стримы с kino.pub. Каталог на Home/Discover зависит от того, как KinoPub предоставляет метаданные.
   - **Trakt** — бесплатно: аддон [Trakt Tv](https://stremio-addons.netlify.app/) + публичные списки на [trakt.tv](https://trakt.tv) (например «Russian») могут добавить каталоги на Home; эффект зависит от списков и не гарантирует русификацию всего интерфейса.
   - Встроенный **Cinemeta** при языке Russian частично подтягивает русские названия; полностью русифицировать каталоги и Home/Discover в Stremio нельзя. Для «полноценной» русской медиатеки удобнее связка qBittorrent + Kodi.

После установки TMDB и смены языка интерфейса названия и описания подтягиваются на русском там, где это поддерживает источник метаданных.

## Голосовое управление

- **«Открой торренты»**, **«торренты»**, **«qbittorrent»** — веб-интерфейс qBittorrent.
- **«Открой стремио»**, **«стремио»**, **«stremio»** — открывает десктоп-приложение Stremio (или веб, если десктоп не установлен).

## Переменные окружения

| Переменная | Описание | По умолчанию |
|------------|----------|--------------|
| `QBITTORRENT_WEB_PORT` | Порт веб-интерфейса qBittorrent | 18084 |
| `QBITTORRENT_WEB_URL` | URL для голосовой команды | http://localhost:18084 |
| `TORRSERVER_PORT` | Порт TorrServer | 18086 |
| `STREMIO_HTTP_PORT` | HTTP-порт контейнера `stremio-server` | 11480 |
| `STREMIO_HTTPS_PORT` | HTTPS-порт контейнера `stremio-server` | 12480 |
| `STREMIO_WEB_URL` | URL для голосовой команды «стремио» (для десктоп: `stremio://`, для веб: `https://app.stremio.com`) | `stremio://` |

## Дальше (по желанию)

- **Radarr / Sonarr** — автоматический поиск и загрузка фильмов/сериалов; папка загрузок — та же, что смотрит Kodi.
