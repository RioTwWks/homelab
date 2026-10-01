# Удалённый доступ к homelab

Три независимых пути к сервисам дома: **AmneziaWG** (обфусцированный VPN через VPS в EU), **Headscale** (mesh через VPS в РФ, клиенты Tailscale), **Cloudflare Tunnel** (HTTPS-прокси без открытых портов на роутере). Любой путь можно использовать отдельно; вместе они дают резерв при блокировках или падении одного канала.

**Секреты** (ключи VPN, authkey Headscale, токен Cloudflare, пароли) храните только в `ansible/group_vars/local.yml` (не в git), в `.env` или в `/etc/cloudflared/` на хосте. В репозитории — только шаблоны и примеры.

---

## Когда какой путь

| Путь | Где сервер | Тип доступа | Сильные стороны | Ограничения |
|------|------------|-------------|-----------------|-------------|
| **AmneziaWG** | VPS DE/NL | Полный L3 VPN (как WireGuard + обфускация) | Обход DPI, весь LAN homelab «как дома» | Нужен EU VPS; клиент Amnezia на телефоне/ПК |
| **Headscale** | VPS РФ | Mesh (Tailscale-протокол) | Стабильный доступ из РФ, ACL по пользователям | Контроль-сервер настраивается отдельно; не путать с Tailscale SaaS |
| **Cloudflare Tunnel** | Cloudflare edge | HTTPS к выбранным URL | Не нужен проброс портов; удобно для UI/API | Не заменяет полный VPN; зависимость от Cloudflare |

**Рекомендация:** для семьи — **Headscale** (простые клиенты + ACL); для обхода жёстких фильтров — **AmneziaWG**; для «показать веб-UI с телефона без VPN» — **Cloudflare Tunnel**.

---

## Общая схема

```text
                    Internet
                        │
        ┌───────────────┼───────────────┐
        │               │               │
   AmneziaWG        Headscale      Cloudflare
   (EU VPS)         (RU VPS)          Tunnel
        │               │               │
        └───────────────┴───────────────┘
                        │
              Ubuntu homelab (LAN)
         moltbot-api :18080, UI :18079, …
```

На homelab **не обязательно** поднимать все три сразу: EU/RU VPS и Cloudflare настраиваются по документу ниже; на самой машине обычно достаточно **клиента Tailscale/Headscale** и/или **cloudflared**.

---

## Путь 1: AmneziaWG (VPS в Германии / Нидерландах)

Цель: зашифрованный туннель с обфускацией (AmneziaWG), после подключения клиент видит homelab так же, как в домашней Wi‑Fi (маршруты задаются в профиле).

### 1.1 VPS

1. Арендуйте VPS (Ubuntu 22.04/24.04) в DE или NL, откройте UDP-порт профиля (часто **51820**, точное значение — в мастере Amnezia).
2. Установите [AmneziaVPN](https://amnezia.org/) на **админский** ПК (не в git).
3. В мастере: «Self-hosted VPN» → IP VPS → протокол **AmneziaWG** → включите **обфускацию** (параметры Jc/Jmin/Jmax/s1/s2/h1–h4 — по умолчанию мастера или ваш провайдер).
4. Экспортируйте конфиги/QR **отдельно для каждого члена семьи** (разные ключи WireGuard внутри Amnezia).

### 1.2 Доступ к homelab

- В профиле Amnezia добавьте **маршрут** к домашней подсети, например `192.168.1.0/24` (ваша LAN), или включите «full tunnel», если весь трафик должен идти через VPS (обычно для homelab достаточно split: только LAN).
- На роутере **не обязательно** пробрасывать порты — клиенты заходят в LAN через VPN.

### 1.3 Проверка

```bash
# С телефона/ноутбука после подключения Amnezia:
ping 192.168.1.10          # IP homelab в LAN
curl -s http://192.168.1.10:18080/healthz
```

### 1.4 Rollback

Отключите профиль на клиентах; при необходимости остановите VPN на VPS через панель Amnezia или переустановите сервис на VPS.

---

## Путь 2: Headscale (VPS в РФ)

Цель: self-hosted координатор, совместимый с клиентами **Tailscale** (iOS, Android, Windows, Linux, macOS). Удобно выдавать семье доступ по логинам/тегам и ACL.

### 2.1 Контроль-сервер на VPS

Официальная документация: [Headscale](https://headscale.net/). Краткий порядок (версии уточняйте по docs):

1. VPS в РФ, DNS-имя, например `headscale.example.ru`, TLS (Caddy/nginx + Let's Encrypt).
2. Установите бинарь или Docker-образ Headscale, конфиг `config.yaml` (listen, `server_url`, DERP при необходимости).
3. Создайте пользователя и pre-auth ключи:

```bash
headscale users create family
headscale preauthkeys create --user family --reusable --expiration 720h
```

Сохраните ключ в **local.yml** или менеджер паролей, не в git.

4. (Опционально) Настройте **ACL** в Headscale: кто видит homelab (`tag:homelab`), кто только интернет через exit node и т.д.

### 2.2 Homelab как узел mesh

На машине с Docker Compose:

```bash
# Установка клиента (Debian/Ubuntu) — см. tailscale.com/download/linux
curl -fsSL https://tailscale.com/install.sh | sh

sudo tailscale up \
  --login-server=https://headscale.example.ru \
  --authkey=YOUR_PREAUTH_KEY \
  --hostname=homelab \
  --accept-routes
```

Через Ansible (идемпотентно, ключ только в `local.yml`):

```bash
make remote-access EXTRA_VARS="-e remote_access_install_tailscale_client=true -e remote_access_headscale_login_server=https://headscale.example.ru"
```

Переменные: `remote_access_tailscale_authkey` в `ansible/group_vars/local.yml`.

### 2.3 Клиенты семьи

На каждом устройстве — приложение Tailscale, но **Custom control server** / login server = URL Headscale (см. док Headscale для вашей версии). Выдайте **отдельный** pre-auth key или пользователя на человека.

Проверка с телефона (в сети Tailscale):

```bash
tailscale ping homelab
curl -s http://homelab:18080/healthz
# или MagicDNS: http://homelab.your-tailnet.ts.net:18080/healthz
```

### 2.4 Rollback

```bash
sudo tailscale down
# на VPS: headscale nodes delete -i <id>
```

---

## Путь 3: Cloudflare Tunnel (резерв / веб без VPN)

Цель: публиковать только нужные HTTP-сервисы (UI, API, Grafana) через Cloudflare **без** открытия портов на домашнем роутере.

### 3.1 Подготовка в Cloudflare

1. Домен в Cloudflare DNS.
2. Zero Trust → **Networks → Tunnels** → Create tunnel.
3. Сохраните **tunnel token** или файл credentials JSON локально (например `/etc/cloudflared/tunnel.token` или `~/.cloudflared/<tunnel-id>.json`, права `600`).

### 3.2 Homelab: cloudflared

Установка вручную:

```bash
# см. https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/
sudo cloudflared service install <TOKEN>
sudo systemctl enable --now cloudflared
```

Через Ansible (конфиг из шаблона, credentials — только на диске):

```bash
make remote-access EXTRA_VARS="-e remote_access_install_cloudflared=true"
```

Задайте в `local.yml`:

- `remote_access_cloudflare_tunnel_id`
- `remote_access_cloudflare_tunnel_name`
- `remote_access_cloudflare_credentials_path` (путь к JSON от Cloudflare)
- `remote_access_cloudflare_ingress` — список hostname → `http://localhost:PORT`

Пример ingress (в `local.yml`, не коммитить реальные домены с прод-секретами):

```yaml
remote_access_cloudflare_ingress:
  - hostname: moltbot.example.com
    service: http://localhost:18079
  - hostname: api-moltbot.example.com
    service: http://localhost:18080
```

**Не публикуйте** через Tunnel без доп. защиты: Redis, MQTT, сырой Ollama, GitLab с дефолтным паролем.

### 3.3 Проверка

```bash
curl -sI https://moltbot.example.com
curl -s https://api-moltbot.example.com/healthz
```

### 3.4 Rollback

```bash
sudo systemctl disable --now cloudflared
# в Cloudflare Zero Trust — удалить или остановить tunnel
```

---

## Что открывать наружу

| Сервис | Порт (LAN) | AmneziaWG | Headscale | Cloudflare Tunnel |
|--------|------------|-----------|-----------|-------------------|
| moltbot-api | 18080 | ✓ LAN | ✓ mesh | ✓ (с auth на edge) |
| moltbot-ui | 18079 | ✓ | ✓ | ✓ предпочтительно |
| Home Assistant | 8123 | ✓ | ✓ | ⚠ только с Cloudflare Access |
| Grafana | профиль monitoring | ✓ | ✓ | ✓ + Access |
| Ollama | 11434 | ✓ LAN only | ✓ ACL | ✗ не публиковать |

---

## Ansible в репозитории

| Файл | Назначение |
|------|------------|
| `ansible/playbooks/remote_access.yml` | Клиент Tailscale/Headscale + cloudflared на homelab |
| `ansible/roles/remote_access/` | Пакеты, шаблоны `config.yml`, systemd |
| `docs/remote-access.md` | Этот документ |

Переменные по умолчанию — `ansible/group_vars/all.yml`; секреты — `ansible/group_vars/local.yml` (см. `local.yml.example`).

```bash
make check                    # syntax-check всех playbooks
make remote-access            # после configure и local.yml
```

---

## Чеклист онбординга семьи

Используйте как пошаговый лист для каждого человека (распечатка или общий документ).

### Администратор (один раз)

- [ ] Выбраны активные пути (Amnezia / Headscale / Cloudflare) и VPS/домен оплачены.
- [ ] Сделан бэкап текущих конфигов (`docs/backup.md`).
- [ ] Для Headscale: созданы пользователи/теги, ACL проверены (гости не видят GitLab/HA без нужды).
- [ ] Для Amnezia: отдельные профили/ключи на человека, split-маршрут только в LAN homelab.
- [ ] Для Cloudflare: Tunnel + Access policy (email/Google) на чувствительные hostname.
- [ ] В `local.yml` / `.env` нет коммита секретов; `git status` чистый по секретам.

### На каждое устройство члена семьи

- [ ] Установлен клиент: **AmneziaVPN** и/или **Tailscale** (с URL Headscale) — по выбранному пути.
- [ ] Выдан **личный** ключ/QR (не общий на всех).
- [ ] Проверка: открывается веб-UI (`18079` или HTTPS через Tunnel) или `healthz` API.
- [ ] (Опционально) Добавлен ярлык / закладка на домашний UI.
- [ ] Объяснено: при «не работает» — переключить VPN (Amnezia ↔ Headscale) или открыть Tunnel-URL.
- [ ] Контакт админа и что **не** делать (не пересылать ключи в мессенджеры).

### Приёмка (все три пути)

- [ ] **Amnezia:** ping/curl homelab IP из LAN после подключения.
- [ ] **Headscale:** `tailscale ping homelab`, curl `:18080/healthz` по MagicDNS.
- [ ] **Cloudflare:** HTTPS на публичный hostname, `healthz` через Tunnel.
- [ ] Семья из вне домашней Wi‑Fi успешно зашла хотя бы одним способом.

---

## Связанные документы

- `docs/architecture.md` — порты и слои homelab
- `docs/backup.md` — бэкап перед сменой сетевой схемы
- `docs/install.md` — Ansible/Makefile

---

## Rollback всей фазы

1. Остановить клиенты: Amnezia off, `sudo tailscale down`, `sudo systemctl stop cloudflared`.
2. На VPS — остановить Headscale/Amnezia или удалить tunnel в Cloudflare.
3. Восстановить доступ только из LAN; при необходимости — бэкап из `docs/backup.md`.
