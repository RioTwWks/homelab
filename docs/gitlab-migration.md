# GitLab в homelab

GitLab (CE) и GitLab Runner поднимаются профилем `gitlab`. **Grafana** и standalone **Prometheus** — профиль `monitoring` (`docs/monitoring.md`). Ниже — что делать после первого запуска и как перенести старый инстанс.

---

## Что делать после первого запуска

Ты уже выполнил `docker compose --profile gitlab up -d` из `~/homelab`. Дальше зависит от ситуации.

### Сценарий А: старый GitLab не переносишь (чистый старт)

1. **Открой в браузере:** `http://localhost:18090` (или свой IP, если заходишь с другого компа).
2. При первом заходе GitLab попросит задать пароль для пользователя **root** — задай и запомни.
3. Залогинься (root + пароль). Создавай проекты, пуши — всё как обычно.
4. **Runner (чтобы пайплайны заработали):**
   - В GitLab: **Admin** (иконка галочки) → **CI/CD** → **Runners** → **Register an instance runner**. Скопируй токен.
   - В homelab на хосте:
     ```bash
     cd ~/homelab
     cp gitlab-runner-config/config.toml.example gitlab-runner-config/config.toml
     ```
   - Открой `gitlab-runner-config/config.toml`, найди строку `token = "ВСТАВЬТЕ_ТОКЕН_ИЗ_GITLAB"` и замени на скопированный токен.
   - Перезапусти runner: `docker compose --profile gitlab up -d gitlab-runner`
   - В GitLab в разделе Runners должен появиться runner со статусом «online».

**Где что лежит:**

| Что | Куда / URL |
|-----|------------|
| Веб GitLab | `http://localhost:18090` |
| Grafana | `http://localhost:18091` — `docker compose --profile monitoring up -d` (см. `docs/monitoring.md`) |
| Конфиг Runner | `~/homelab/gitlab-runner-config/config.toml` |

---

### Сценарий Б: переносишь старый GitLab из `~/gitlab`

**Важно:** данные GitLab (репозитории, пользователи, БД) лежат **не в папке** `~/gitlab`, а в **томах Docker**. Просто скопировать папку `~/gitlab` в `~/homelab` бесполезно — переносятся только конфиги и скрипты. Сами данные нужно переносить из старых Docker-томов в новые (или переиспользовать старые тома). Ниже — по шагам.

---

## Перенос: по шагам (из ~/gitlab в homelab)

### 1. Остановить оба GitLab

```bash
# Остановить GitLab в homelab (тот, что ты уже поднял)
cd ~/homelab
docker compose --profile gitlab down

# Остановить старый GitLab
cd ~/gitlab
docker compose down
```

### 2. Узнать имена томов

Тома называются так: **имя_проекта** + **имя из compose**. Проект — это имя папки, откуда запускали `docker compose`.

```bash
docker volume ls | grep gitlab
```

Пример вывода: `gitlab_gitlab_config`, `gitlab_gitlab_data`, `gitlab_gitlab_logs` (старый, из ~/gitlab) и `homelab_gitlab_config`, `homelab_gitlab_data`, `homelab_gitlab_logs` (новый, из ~/homelab). Запомни свои имена: старые — **старые**, новые — **homelab_...** (если homelab в папке homelab).

### 3. Скопировать данные из старых томов в новые

В выводе `docker volume ls | grep gitlab` у тебя:
- **старые** (из ~/gitlab): `gitlab_gitlab_config`, `gitlab_gitlab_logs`, `gitlab_gitlab_data`
- **новые** (из ~/homelab): `homelab_gitlab_config`, `homelab_gitlab_logs`, `homelab_gitlab_data`

Ничего подставлять не нужно — просто выполни по порядку три команды (копируем из старых в новые):

```bash
docker run --rm -v gitlab_gitlab_config:/from -v homelab_gitlab_config:/to alpine sh -c "cp -a /from/. /to/"
docker run --rm -v gitlab_gitlab_logs:/from -v homelab_gitlab_logs:/to alpine sh -c "cp -a /from/. /to/"
docker run --rm -v gitlab_gitlab_data:/from -v homelab_gitlab_data:/to alpine sh -c "cp -a /from/. /to/"
```

Копирование тома `data` может занять несколько минут.

Если имена томов у тебя другие (другой префикс) — в каждой команде замени `gitlab_` на префикс старых томов и `homelab_` на префикс новых (как в выводе `docker volume ls`).

### 4. Скопировать конфиг Runner (один файл)

Из папки `~/gitlab` в homelab нужен только файл конфига runner:

```bash
cp ~/gitlab/gitlab-runner-config/config.toml ~/homelab/gitlab-runner-config/config.toml
```

Потом открой `~/homelab/gitlab-runner-config/config.toml` и замени в нём:
- `url = "http://gitlab:8080"` → `url = "http://gitlab"`
- `clone_url = "http://gitlab:8080"` → `clone_url = "http://gitlab"`

(Внутри сети homelab GitLab слушает порт 80, не 8080.)

### 5. Настроить .env в homelab (по желанию)

Если заходишь по IP или домену, в `~/homelab/.env` добавь или поправь:

```
GITLAB_EXTERNAL_URL=http://ТВОЙ_IP_ИЛИ_ДОМЕН:18090
GITLAB_REGISTRY_EXTERNAL_URL=http://ТВОЙ_IP_ИЛИ_ДОМЕН:5005
```

### 6. Запустить GitLab в homelab

```bash
cd ~/homelab
docker compose --profile gitlab up -d
```

Открой в браузере `http://localhost:18090` (или свой URL). Залогинься — должны быть старые проекты и пользователи. Runner подхватит конфиг из `gitlab-runner-config/config.toml`; в GitLab → Admin → CI/CD → Runners проверь, что runner online.

---

## Запуск GitLab в homelab (без переноса)

Если старый GitLab не переносишь — просто:

```bash
cd ~/homelab
docker compose --profile gitlab up -d
```

Веб: `http://localhost:18090`, SSH: порт 2222, Registry: 5005. Grafana: профиль `monitoring` — `docs/monitoring.md`.

## Перенос GitLab Runner

Runner добавлен в homelab как сервис `gitlab-runner` (профиль `gitlab`). Конфиг — каталог `gitlab-runner-config/`, файл `config.toml`.

### Вариант 1: копировать старый конфиг

1. Скопировать конфиг из старого места:
   ```bash
   cp /home/ivan/gitlab/gitlab-runner-config/config.toml /path/to/homelab/gitlab-runner-config/
   ```

2. **Обязательно поправить URL:** внутри сети Docker GitLab слушает порт 80, не 8080. В `config.toml` заменить:
   - `url = "http://gitlab:8080"` → `url = "http://gitlab"`
   - `clone_url = "http://gitlab:8080"` → `clone_url = "http://gitlab"`

3. Если переносите те же данные GitLab (те же тома), старый токен runner обычно продолжает работать. Запустить runner:
   ```bash
   cd /path/to/homelab
   docker compose --profile gitlab up -d gitlab-runner
   ```

4. В GitLab: **Admin → CI/CD → Runners** — runner должен появиться как online. Если статус «offline» или в логах ошибка авторизации, перерегистрировать runner (см. вариант 2).

### Вариант 2: новый runner (или перерегистрация)

1. В homelab положить конфиг по примеру:
   ```bash
   cp /path/to/homelab/gitlab-runner-config/config.toml.example /path/to/homelab/gitlab-runner-config/config.toml
   ```

2. В GitLab: **Admin → CI/CD → Runners → Register an instance runner**. Скопировать токен (или для существующего runner — сбросить токен и взять новый).

3. В `gitlab-runner-config/config.toml` вставить токен в поле `token = "..."`.

4. Запустить:
   ```bash
   docker compose --profile gitlab up -d gitlab-runner
   ```

### Важно

- `config.toml` содержит токен — не коммитить в репозиторий. В `gitlab-runner-config/` уже есть `.gitignore`, исключающий `config.toml` (или добавьте его в корневой `.gitignore`).
- Runner использует Docker executor и монтирует `/var/run/docker.sock`, чтобы запускать job-контейнеры на хосте. Для пайплайнов, которые собирают образы или запускают `docker`, этого достаточно.

## Переменные окружения ( .env )

| Переменная | Описание | По умолчанию |
|------------|----------|--------------|
| `GITLAB_EXTERNAL_URL` | URL веб-интерфейса GitLab | `http://localhost:18090` |
| `GITLAB_HOSTNAME` | hostname контейнера | `gitlab` |
| `GITLAB_HTTP_PORT` | Порт веб-интерфейса на хосте | `18090` |
| `GITLAB_SSH_PORT` | Порт Git over SSH | `2222` |
| `GITLAB_REGISTRY_PORT` | Порт Container Registry | `5005` |
| `GITLAB_REGISTRY_EXTERNAL_URL` | Внешний URL Registry | `http://localhost:5005` |
| `GITLAB_PROMETHEUS_PORT` | Порт Prometheus (мониторинг) | `9090` |
| `GRAFANA_PORT` | Порт Grafana на хосте | `18091` |
| `GRAFANA_ADMIN_PASSWORD` | Пароль admin Grafana | `admin` |
