# Платформа и выбор ОС

Целевое железо и рекомендуемая операционная система для развёртывания homelab «умной станции».

## Целевое железо

| Компонент | Спецификация |
|-----------|--------------|
| CPU | AMD Ryzen AI 9 HX 370 (12C/24T, Zen 4, AVX-512) |
| GPU | AMD Radeon 890M (RDNA3, iGPU, shared system RAM) |
| RAM | 32 GB LPDDR5 (единый пул для ОС, LLM, Docker, игр) |
| Накопитель | NVMe M.2 (система и приложения; данные — RAID/внешние диски по [storage-raid.md](./storage-raid.md)) |
| Вывод | HDMI → ТВ, микрофон и динамики |

Особенность платформы: **iGPU использует системную память**. LLM, Docker, desktop и Steam/Proton конкурируют за один пул RAM — это учитывается в [architecture.md](./architecture.md) (режимы AI / Gaming / Media).

### Ожидаемая нагрузка LLM

- **Qwen3 4B** — быстрые команды и интенты, низкая задержка.
- **Qwen3 8B** — диалог и reasoning; комфортный баланс на 32 GB.
- **Whisper** — `large-v3` на CPU приемлем по realtime; при нехватке RAM — `medium` (см. [voice-mvp.md](./voice-mvp.md)).
- Модели 30B+ на 32 GB — только с сильными компромиссами; не целевой сценарий.

Ollama на AMD: без стабильного ROCm ориентир на **CPU inference** (AVX-512 на HX 370 даёт приличную скорость для 4B/8B). Ollama устанавливается **нативно**, не в Docker.

## Рекомендуемая ОС: Ubuntu 26.04 LTS Desktop

Для сценария «сервер + голосовой AI + медиа на ТВ + **иногда Steam/Proton**» — **Ubuntu 26.04 LTS Desktop**, а не Ubuntu Server.

Почему Desktop, а не «серверный» дистрибутив:

- Steam, Proton, Vulkan/Mesa и HDMI работают в обычной графической сессии.
- Драйвер `amdgpu` и 3D-ускорение поддерживаются штатно.
- Свежий kernel (в т.ч. HWE-линейка) важен для нового железа AMD.
- Серверная часть всё равно изолирована в **Docker**; Desktop — только host OS.

Ubuntu Desktop здесь — **не «пользовательский ПК вместо сервера»**, а хост, который управляет железом, а сервисы живут в контейнерах.

### Схема на одной ОС

```text
Ubuntu 26.04 LTS Desktop
│
├── Desktop
│   ├── Steam / Proton (опционально)
│   ├── Kodi, Stremio
│   └── TV UI / браузер kiosk
│
├── Docker Compose (homelab)
│   ├── moltbot-api, media-api, moltbot-ui
│   ├── Redis, Qdrant, MQTT
│   └── профили: ha, storage, photos, gitlab, torrents, search
│
└── AI (на хосте)
    ├── Ollama (Qwen3 4B / 8B)
    ├── Whisper (whisper-server)
    └── TTS (Silero / Piper)
```

После перезагрузки: `systemd` → `docker` → сервисы homelab поднимаются до входа пользователя в GUI.

## Сравнение вариантов ОС

| Вариант | Сценарий homelab + AI + ТВ + Steam | Комментарий |
|---------|-----------------------------------|-------------|
| **Ubuntu 26.04 LTS Desktop** | Рекомендуется | Универсальный host: игры, HDMI, Docker, Ollama на bare metal |
| Ubuntu Server | Если игры не нужны | Меньше overhead GUI; Kodi/Steam потребуют отдельный графический стек |
| Debian Stable | Сервер без игр | Стабильно, но старый kernel — хуже для нового AMD |
| Proxmox / гипервизор | Не рекомендуется | iGPU passthrough и shared RAM делают VM для LLM/игр невыгодными |
| LibreELEC / OSMC | Только медиа | Нет полноценного homelab и LLM |
| SteamOS | Только игры | Не замена homelab-серверу |
| Windows + WSL | Возможно | Linux-сервисы в WSL2 теряют в простоте и интеграции с железом |

## Когда выбрать Ubuntu Server

Если mini PC **никогда** не используется для Steam/Proton и графика сведена к минимальному X11/Wayland + Kodi в fullscreen:

- Ubuntu Server + Docker + headless Ollama — допустимая альтернатива.
- Для текущего проекта (с учётом игр и Radeon 890M) приоритет остаётся за **Desktop**.

## Установка и подготовка хоста

Минимальный чеклист после установки Ubuntu 26.04 LTS Desktop:

### 1. Базовая система

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y curl git jq build-essential
```

### 2. Docker

```bash
# Официальная инструкция: https://docs.docker.com/engine/install/ubuntu/
sudo apt install -y docker.io docker-compose-v2
sudo usermod -aG docker "$USER"
# перелогиниться
```

Проверка: `docker run --rm hello-world`.

### 3. Ollama (на хосте)

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen3:4b
ollama pull qwen3:8b
curl -s http://localhost:11434/api/tags | jq
```

### 4. Аудио и HDMI

- Проверить микрофон и вывод: `pactl list sources short`, `pactl list sinks short`.
- Подключить ТВ по HDMI, выбрать дисплей в настройках Ubuntu.
- Для kiosk-режима браузера — см. [media-control.md](./media-control.md).

### 5. Клонирование homelab

```bash
git clone https://github.com/RioTwWks/homelab.git
cd homelab
cp .env.example .env
# отредактировать .env
docker compose up -d --build
curl -s http://localhost:18080/healthz | jq
```

### 6. Host-сервисы (по мере готовности)

- Whisper: [voice-mvp.md](./voice-mvp.md) → `scripts/systemd/whisper-server.service`
- Media executor: [media-control.md](./media-control.md)
- Бэкап: [backup.md](./backup.md) → `homelab-backup.timer`

### 7. Steam (опционально)

Установить Steam из магазина приложений или `.deb` с сайта Valve. Для Proton включить в настройках Steam. Перед тяжёлой игрой — см. режим **Gaming** в [architecture.md](./architecture.md).

## Драйверы и графика

- **AMD GPU:** пакет `amdgpu` в ядре Ubuntu, пользовательское пространство — Mesa.
- **Vulkan:** `sudo apt install mesa-vulkan-drivers`
- **Сессия:** Wayland по умолчанию в Ubuntu 26.04; при проблемах с kiosk/Stremio можно переключиться на X11 на экране входа.

Не требуется ручная установка проприетарного драйвера NVIDIA — платформа полностью на AMD.

## Порты (ориентир)

| Сервис | Порт по умолчанию |
|--------|-------------------|
| Ollama | 11434 |
| moltbot-api | 18080 |
| moltbot-ui | см. `docker-compose.yml` |
| Home Assistant | 8123 |
| media-api executor | 8091 (хост) |
| whisper-server | 8099 (хост) |

При конфликтах — менять в `.env` и compose.

## Отладка на другом ПК

Разработку и первичную настройку удобно вести на машине с **тем же дистрибутивом** (Ubuntu 26.04 Desktop), чтобы при переносе на mini PC не менять пути, пакеты и поведение Docker. Железо может отличаться; логика слоёв — та же.

## Связанные документы

- [architecture.md](./architecture.md) — слои, голосовой контур, режимы ресурсов.
- [../README.md](../README.md) — быстрый старт и тестовые запросы.
