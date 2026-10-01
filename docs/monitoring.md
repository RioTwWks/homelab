# Мониторинг (Prometheus + Grafana)

Чеклист валидации и host-only шаги (Agent B2): [runbook-voice-monitoring.md](./runbook-voice-monitoring.md).

Отдельный Docker Compose профиль **`monitoring`**: метрики хоста (CPU, RAM, диск), энергопотребление **iGPU/NPU** через [all-smi](https://github.com/lablup/all-smi) на хосте, задержки **Ollama** и **moltbot-api** через blackbox-exporter.

Grafana и standalone Prometheus **не** входят в профиль `gitlab` (фаза 7 homelab redesign). Встроенный Prometheus GitLab Omnibus по-прежнему доступен на порту `9090`, только если поднят `gitlab`.

---

## Быстрый старт

```bash
cd ~/homelab

# 1) Стек метрик в Docker
docker compose --profile monitoring up -d

# 2) all-smi на хосте (см. ниже)
sudo cp scripts/systemd/all-smi-api.service.example /etc/systemd/system/all-smi-api.service
# отредактируйте путь к бинарнику all-smi при необходимости
sudo systemctl daemon-reload
sudo systemctl enable --now all-smi-api.service
```

| Сервис | URL по умолчанию |
|--------|------------------|
| Grafana | http://localhost:18091 (admin / `GRAFANA_ADMIN_PASSWORD` из `.env`) |
| Prometheus | http://localhost:19090 |
| all-smi metrics | http://localhost:19095/metrics (на хосте) |

Дашборд **Homelab overview** подхватывается из `monitoring/grafana/dashboards/` (папка Grafana: *Homelab*).

---

## all-smi (NPU / iGPU power)

План homelab предлагает `pip install all-smi` — **официальная установка через pip не поддерживается**. Используйте релиз с GitHub, Debian-пакет или Homebrew (см. README репозитория).

### Установка (Linux, Ryzen AI + Radeon iGPU)

1. Скачайте **glibc**-бинарник и `liball_smi_amd.so` с [releases](https://github.com/lablup/all-smi/releases).
2. Убедитесь, что установлены ROCm/драйверы AMD и доступ к `/dev/dri` (пользователь в группах `video` / `render`).
3. Для **Ryzen AI NPU** установите XRT / Ryzen AI driver (фаза 0 плана) и проверьте `flm validate` после фазы 4.

### API / Prometheus exporter

```bash
# Порт 19095 — как в monitoring/prometheus/prometheus.yml (не конфликтует с GitLab :9090)
ALL_SMI_API_PORT=19095 all-smi api --port 19095
```

Метрики в формате Prometheus: `GET http://localhost:19095/metrics`.

Полезные серии:

| Метрика | Назначение |
|---------|------------|
| `all_smi_gpu_power_consumption_watts` | Мощность iGPU (Radeon 890M и др.) |
| `all_smi_gpu_utilization` | Загрузка GPU |
| `all_smi_gpu_temperature_celsius` | Температура |

NPU может отображаться в all-smi как отдельное устройство с теми же префиксами `all_smi_gpu_*` или платформенными `all_smi_*` — зависит от версии all-smi и драйверов.

### Зависимость панелей NPU от фазы 4 (агент A2)

Панель **NPU power** в дашборде `homelab-overview` показывает данные только когда:

1. Установлены драйверы Ryzen AI / XRT (фаза 0).
2. NPU виден в `all-smi` (после интеграции **FastFlowLM** для STT — **фаза 4**, работа агента **A2**).

До этого scrape `job=all-smi` может быть `up=0`, а NPU-графики пустые — это ожидаемо.

Пример unit-файла: `scripts/systemd/all-smi-api.service.example`.

---

## Что собирает Prometheus

Файл: `monitoring/prometheus/prometheus.yml`

| job | Источник | Метрики |
|-----|----------|---------|
| `node` | `node-exporter` | CPU, RAM, диск, сеть |
| `all-smi` | хост `:19095` | энергия/температура GPU и NPU |
| `blackbox` | Ollama `11434/api/tags`, moltbot `18080/healthz` | `probe_duration_seconds` (латентность), `probe_success` |

Латентность **генерации токенов** LLM blackbox не измеряет — только доступность и RTT HTTP до Ollama. Для глубокой диагностики смотрите логи Ollama или добавьте отдельный exporter позже.

### Перезагрузка конфига

```bash
curl -X POST http://localhost:19090/-/reload
```

---

## Переменные окружения (`.env`)

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `GRAFANA_PORT` | `18091` | Веб Grafana |
| `GRAFANA_ADMIN_PASSWORD` | `admin` | Пароль admin |
| `PROMETHEUS_PORT` | `19090` | Веб Prometheus |

Порт **all-smi** задаётся в unit-файле и в `prometheus.yml` (`19095`); при смене порта обновите оба места.

---

## Rollback

Вернуть Grafana в профиль `gitlab` (как до фазы 7): откатить коммит или вручную перенести сервис `grafana` обратно в `profiles: ["gitlab"]` и убрать профиль `monitoring`.

```bash
docker compose --profile monitoring down
```

---

## Связанные документы

- `docs/gitlab-migration.md` — GitLab без standalone Grafana
- `.cursor/plans/homelab_redesign_plan.md` — фаза 7
