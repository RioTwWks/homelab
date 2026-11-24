# Kubernetes + Helm: план внедрения (K3s)

Статус: **план**. Цель — поэтапная миграция контейнеризированной части homelab с Docker Compose на Kubernetes (K3s) с управлением через Helm, без остановки голосового контура.

Текущая архитектура: `docs/architecture.md`. Установка хоста: `docs/platform.md`, `docs/install.md`. Увязка с Hermes-миграцией: §3.1.

## 1. Зачем

Docker Compose покрывает запуск сервисов на одном хосте, но с ростом числа профилей (`ha`, `storage`, `photos`, `torrents`, `gitlab`, `monitoring`, `search`, `voice`) появляются ограничения:

- **Self-healing**: K8s перезапускает упавшие контейнеры и следит за целевым состоянием (liveness/readiness probes) — важно для сервисов 24/7.
- **Декларативность и воспроизводимость**: вся конфигурация в Git (манифесты/values), восстановление с нуля — одна команда.
- **Helm как пакетный менеджер**: для Nextcloud, Home Assistant, Immich, qBittorrent, SearxNG, GitLab, Prometheus/Grafana есть зрелые community-чарты; настройка через `values.yaml` вместо ручного compose.
- **Изоляция и ресурсы**: namespaces, requests/limits, PriorityClass — контроль делёжки 32 GB RAM между LLM-нагрузкой и сервисами.

## 2. Выбор дистрибутива: K3s

Для одного mini PC (Ryzen AI 9 HX 370, 32 GB RAM) — **K3s**:

- сертифицированный CNCF, один бинарник (<100 МБ), низкое потребление RAM/CPU;
- из коробки: containerd, local-path-provisioner, Traefik (отключим или заменим), CoreDNS;
- SQLite вместо etcd по умолчанию (достаточно для single-node; на etcd можно перейти позже);
- легко ставится через существующий Ansible (`make install`-подход, см. `docs/install.md`).

Альтернативы (отклонены на старте): kubeadm — избыточно для одного узла; MicroK8s — snap-зависимость; Talos — отдельная ОС, ломает текущую модель «host-сервисы вне контейнеров».

## 3. Целевая архитектура (гибрид)

Гибрид сохраняется: часть сервисов остаётся на хосте из-за доступа к оборудованию.

### В кластер (K3s + Helm)

| Сервис | Чарт | Namespace | Профиль compose |
|---|---|---|---|
| media-api (:8090) | собственный `charts/moltbot` | `moltbot` | базовый |
| moltbot-ui | собственный `charts/moltbot` | `moltbot` | `ui` |
| Redis, Qdrant, MQTT | bitnami/qdrant/собственный subchart | `moltbot` | базовый |
| moltbot-api (:18080) | собственный `charts/moltbot` — **только после acceptance Hermes** (см. §3.1) | `moltbot` | базовый |
| Home Assistant | community | `home` | `ha` |
| Nextcloud | community | `storage` | `storage` |
| Immich | community | `photos` | `photos` |
| qBittorrent | community | `media` | `torrents` |
| SearxNG | community | `search` | `search` |
| GitLab (+ Runner) | официальный | `gitlab` | `gitlab` |
| Prometheus, Grafana, alertmanager | `kube-prometheus-stack` | `monitoring` | `monitoring` |
| ingress (Traefik или Caddy), cert-manager, Sealed Secrets | официальные | `kube-system`/`infra` | — |

### Остаётся на хосте (вне K8s)

- **Ollama** (`qwen3:4b`/`qwen3:8b`, :11434), **Whisper STT**, **TTS**, **wake word** — GPU (Radeon 890M) и аудиоустройства; проброс в K8s требует device plugin и усложняет отладку.
- **media executor** (:8091), **Kodi/Stremio/браузер на HDMI**, **timer_worker** — прямой доступ к сессии/железу.
- **Hermes Agent** (`hermes/`, CLI) — ставится на хост по `docs/hermes-phase1-runbook.md`, работает рядом с Ollama и голосовым контуром; после acceptance может заменить moltbot-api как оркестратор.

Связность «кластер → хост»: вместо `host.docker.internal` — `host.k3s.internal` (K3s ≥ v1.30 резолвит её на хост) либо `ExternalName`/статический IP хоста. Порты хостовых сервисов (11434, 8091) остаются прежними.

Связность «хост → кластер» (Hermes, host-tools): по тем же портам через NodePort/ingress (:18080, :8090); `hermes/tools/*` и skills не меняются — они работают по HTTP.

### 3.1 Увязка с Hermes-миграцией

Параллельно идёт миграция moltbot-api → Hermes (`hermes/MIGRATION.md`, `docs/hermes-phase1-runbook.md`). Правила стыковки двух миграций:

- **Две миграции не смешиваем.** Пока Hermes не прошёл acceptance, moltbot-api — рабочий оркестратор на :18080 и остаётся в compose. Переносить в K8s компонент, который может быть заменён, — лишний риск и двойная работа.
- **Оркестраторный слой — отдельным шагом.** Фаза 1 переносит только инфраструктуру и вспомогательные сервисы (Redis, Qdrant, MQTT, media-api, moltbot-ui) — они нужны обоим оркестраторам. moltbot-api переносится после acceptance Hermes; если Hermes его заменяет, перенос может вообще не потребоваться.
- **Чарт параметризует backend**: `assistant.backend: moltbot | hermes` в `values.yaml` — смена оркестратора становится сменой values, а не редизайном чарта.
- **Hermes остаётся на хосте** и после acceptance: ему нужны Ollama, аудиоконтур и host tools. В кластер он не переносится.
- **Новая функциональность ассистента** по-прежнему идёт в `hermes/skills` + `hermes/tools` — K8s-миграция это правило не меняет.

## 4. Структура репозитория (добавляется по фазам)

```
k8s/
  README.md                  # как поднять/обновить кластер
  charts/
    moltbot/                 # umbrella-чарт: redis, qdrant, mqtt, media-api, ui (+ api после §3.1)
      Chart.yaml
      values.yaml            # порты, образы, ресурсы, env-имена, assistant.backend (секреты — не здесь)
      templates/
  values/                    # values для community-чартов (ha.yaml, nextcloud.yaml, ...)
  namespaces/                # namespace-манифесты
scripts/
  k8s-install.sh             # установка K3s + helm (или ansible-роль)
  k8s-validate.sh            # helm lint + kubeconform + helm template --dry-run
```

Правила не меняются: секреты только в `.env`/Sealed Secrets (зашифрованные — в Git, открытые — нет); новые env-переменные — по образцу `.env.example`; CI-тесты (`pytest`, `flutter analyze`) не трогаем.

## 5. Поэтапный план

### Фаза 0 — площадка (без переноса сервисов)

- Установить K3s на тот же хост рядом с Docker (порты не конфликтуют: K3s API :6443, compose-порты 18080+ сохраняются).
- Установить `kubectl`, `helm` (через Ansible или `scripts/k8s-install.sh`).
- Снапшот/бэкап по `docs/backup.md` перед любыми изменениями.
- **Критерий выхода**: `kubectl get nodes` — Ready; compose-стек работает как раньше (`curl -s localhost:18080/healthz`).

### Фаза 1 — инфраструктура ядра (собственный чарт, без оркестратора)

- Создать `k8s/charts/moltbot`: Redis, Qdrant, MQTT (subchart/манифесты с PVC local-path), `media-api`, `moltbot-ui`. **moltbot-api в чарт не включаем** — он остаётся в compose до acceptance Hermes (см. §3.1).
- Миграция env: `.env` → ConfigMap + Sealed Secrets.
- Запуск **параллельно** compose (NodePort на свободных портах), прогон health check и smoke: `/healthz`, `/v1/chat` (диалог, новости, погода — как в README) с moltbot-api из compose, работающим на кластерные Redis/Qdrant/MQTT.
- Переключение: compose down для перенесённых сервисов → порты отдаёт ingress/NodePort.
- **Критерий выхода**: голосовой контур работает на кластерной инфраструктуре; откат = `docker compose up -d` (манифесты compose не удаляем).

### Фаза 1.5 — оркестраторный слой (после acceptance Hermes)

- Дождаться acceptance Hermes (`scripts/hermes-validate-tools.sh`, сценарии из runbook'а).
- Если оркестратором остаётся moltbot-api: добавить его в `charts/moltbot` и перенести по схеме Фазы 1.
- Если оркестратор — Hermes на хосте: moltbot-api выводится из compose, порт :18080 обслуживает Hermes-совместимый слой; чарт переключается через `assistant.backend: hermes`.
- **Критерий выхода**: решение зафиксировано в `docs/architecture.md`; `curl -s localhost:18080/healthz` и голосовые сценарии работают на выбранном варианте.

### Фаза 2 — опциональные профили на community-чартах

- По одному сервису на релиз, в порядке роста риска: SearxNG → qBittorrent → Nextcloud → Immich → Home Assistant → GitLab.
- Для каждого: `k8s/values/<service>.yaml`, миграция данных (PVC или hostPath по `docs/storage-raid.md`), проверка, выключение compose-профиля.
- **Критерий выхода**: соответствующий `--profile` больше не нужен; данные на месте.

### Фаза 3 — инфраструктура кластера

- Ingress (Traefik/Caddy) + единая схема портов/доменов; cert-manager при необходимости TLS (см. `docs/remote-access.md`).
- Sealed Secrets (kubeseal) — секреты в Git.
- **Критерий выхода**: все сервисы доступны через ingress; в Git нет открытых секретов.

### Фаза 4 — observability и эксплуатация

- `kube-prometheus-stack` в `monitoring` (заменяет compose-профиль `monitoring`), дашборды и алерты по образцу `docs/monitoring.md` + `docs/runbook-voice-monitoring.md`.
- Resources/limits для всех подов (приоритет — Ollama на хосте: кластеру оставляем headroom ≥8 GB RAM).
- `scripts/k8s-validate.sh` в CI: `helm lint`, `kubeconform`, `helm template` по всем чартам.
- **Критерий выхода**: метрики/алерты работают; CI зелёный.

### Фаза 5 — решение по host-сервисам и декомиссия compose

- Оценить перенос Ollama/STT/TTS в кластер: AMD GPU device plugin, проброс `/dev/kfd`, `/dev/dri`, аудио. Скорее всего — оставить на хосте вместе с Hermes (задокументировать решение).
- После стабильной работы (≥2 недели без откатов): заархивировать compose-профили, обновить README/`docs/architecture.md`.
- **Критерий выхода**: `docker-compose.yml` содержит только то, что реально осталось (или помечен legacy).

## 6. Риски и откат

| Риск | Митигация |
|---|---|
| Деградация голосового контура при миграции | Параллельный запуск (Фаза 1), откат = compose up |
| Смешение Hermes- и K8s-миграций | Оркестратор не переносим до acceptance Hermes (§3.1, Фаза 1.5); инфраструктура общая для обоих |
| Потеря данных stateful-сервисов | Бэкап перед каждой фазой (`scripts/backup.sh`); PVC с retain |
| GPU/аудио в K8s | Host-сервисы (включая Hermes) не переносим до отдельного решения (Фаза 5) |
| Рост сложности для одного узла | Фазы независимы; любую можно не делать — compose остаётся рабочим |
| Конфликт портов 18080/8090 при параллельном запуске | NodePort на других портах до переключения |

## 7. Definition of Done (весь план)

- Все контейнерные сервисы управляются Helm-релизами, конфигурация — в Git.
- Решение по оркестратору (moltbot-api vs Hermes) зафиксировано; чарт поддерживает выбранный вариант (`assistant.backend`).
- `curl -s localhost:18080/healthz` отвечает от целевого инстанса; голосовые сценарии (диалог, погода, медиа, умный дом) работают.
- Секреты — только Sealed Secrets/`.env`; в Git открытых секретов нет.
- CI валидирует чарты (`k8s-validate.sh`); документация (`k8s/README.md`, `docs/architecture.md`) актуальна.
