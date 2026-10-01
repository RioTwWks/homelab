# Установка: Makefile + Ansible

Гибридный установщик: **Makefile** — короткие команды, **Ansible** — идемпотентная настройка хоста, шаблоны `.env` и systemd.

## Требования

- Ubuntu 22.04/24.04 (или Debian-подобная ОС)
- `sudo` для пакетов, Docker и systemd
- `make`, `ansible-core` (`sudo apt install -y make ansible-core`)
- Для голоса: микрофон, ALSA (`arecord` / `aplay`)

## Быстрый старт

```bash
git clone <repo-url> homelab && cd homelab

make configure      # wizard → ansible/group_vars/local.yml
make install        # deps + docker compose + health check
```

Пресеты без wizard (переопределяют `moltbot_preset`):

```bash
make install-minimal   # ui
make install-voice
make install-voice-npu
make install-full      # все профили + backup timer
```

## Структура

```
Makefile                          # точка входа
ansible/
  inventory/hosts.yml             # localhost по умолчанию
  group_vars/all.yml              # дефолты
  group_vars/local.yml            # ваш конфиг (не в git)
  playbooks/site.yml              # полный deploy
  playbooks/voice.yml             # только голос
  roles/
    common/                       # apt, Docker
    ollama/                       # Ollama + модели
    moltbot_compose/              # .env + docker compose
    voice/                        # whisper.cpp, TTS, voice_mvp.env
    systemd/                      # whisper-server, backup timer
scripts/configure-wizard.sh       # интерактивный выбор
```

## Команды Makefile

| Команда | Описание |
|---------|----------|
| `make help` | Список целей |
| `make configure` | Wizard → `local.yml` |
| `make deploy` | Ansible site playbook |
| `make install` | configure (если нет local.yml) + deploy + health |
| `make voice` | Только голосовой стек |
| `make systemd` | Только systemd-юниты |
| `make up` / `make down` | Быстрый docker compose без Ansible |
| `make health` | `curl /healthz` |
| `make backup-timer` | Включить ежедневный бэкап |
| `make check` | `ansible-playbook --syntax-check` |

## Профили Docker Compose

Задаются через `moltbot_preset` или явный список `moltbot_profiles` в `local.yml`:

| Preset | Профили |
|--------|---------|
| `minimal` | ui |
| `voice` | ui, search |
| `storage` | ui, storage |
| `photos` | ui, photos |
| `full` | ui, ha, storage, photos, torrents, search, gitlab |

Пример явного списка:

```yaml
moltbot_profiles:
  - ui
  - ha
  - search
```

## Удалённый хост (mini PC)

1. Отредактируйте `ansible/inventory/hosts.yml`:

```yaml
homelab:
  hosts:
    mini-pc:
      ansible_host: 192.168.1.50
      ansible_user: ivan
      ansible_connection: ssh
```

2. На control machine: `make configure && make deploy`

Для установки с самого mini PC оставьте `ansible_connection: local`.

## Секреты

- `ansible/group_vars/local.yml` — локальный файл (в `.gitignore`), может содержать токены HA.
- Для production рассмотрите **Ansible Vault**:

```bash
ansible-vault encrypt ansible/group_vars/local.yml
make deploy  # ANSIBLE_VAULT_PASSWORD_FILE=...
```

## Что остаётся ручным

- API-ключи погоды (опционально в `local.yml`)
- Первый вход Home Assistant, Immich, Nextcloud, GitLab
- Скачивание Piper ONNX-модели в `~/.local/share/piper/`
- Media executor на хосте с GUI (`scripts/media_executor_example.py`)

## Повторный запуск

Ansible идемпотентен — безопасно запускать `make deploy` после изменения `local.yml`.

## Диагностика

```bash
make check
ansible-playbook -i ansible/inventory/hosts.yml ansible/playbooks/site.yml --list-tasks
make ps
make logs
```
