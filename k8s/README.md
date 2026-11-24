# Kubernetes (K3s) — ядро homelab

Миграция с Docker Compose на K3s + Helm по плану `docs/k8s-helm-plan.md`.
Здесь — репозиторная часть фаз 0–1: кластерная площадка и чарт ядра
(Redis, Qdrant, MQTT, media-api, moltbot-ui). **moltbot-api в чарт не входит**
до acceptance Hermes (план §3.1) — он остаётся в compose на хосте.

## Структура

```
k8s/
  charts/moltbot/    # собственный чарт ядра (см. values.yaml — все ручки там)
  namespaces/        # namespace-манифесты
  values/            # values для community-чартов (фаза 2, пока пусто)
scripts/
  k8s-install.sh     # фаза 0: установка K3s + helm на хост
  k8s-validate.sh    # helm lint + kubeconform + helm template
```

## Фаза 0 — площадка (на хосте)

```bash
# Бэкап перед любыми изменениями (docs/backup.md)
scripts/backup.sh

# Установка K3s (сервер, без Traefik) + helm; K3s ≥ v1.30 нужен для host.k3s.internal
sudo scripts/k8s-install.sh
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml

# Критерий выхода: узел Ready, compose-стек не пострадал
kubectl get nodes
curl -s http://localhost:18080/healthz | jq
```

Compose и K3s живут параллельно: порты compose (6379, 6333, 1883, 8090, 18080,
18079) не пересекаются с K3s (API :6443, NodePort 30xxx).

## Фаза 1 — запуск чарта рядом с compose

```bash
# 1. Образы собираются локально и импортируются в containerd k3s
docker build -t homelab/media-api:latest ./media_api
docker build -t homelab/moltbot-ui:latest -f moltbot_ui/Dockerfile .
docker save homelab/media-api:latest | sudo k3s ctr images import -
docker save homelab/moltbot-ui:latest | sudo k3s ctr images import -

# 2. Namespace и релиз
kubectl apply -f k8s/namespaces/
helm install moltbot k8s/charts/moltbot -n moltbot

# 3. Smoke (NodePort-порты, compose не трогаем)
kubectl -n moltbot get pods
curl -s http://localhost:30090/healthz | jq        # media-api в кластере
curl -s http://localhost:30079/ | head             # moltbot-ui в кластере
curl -s http://localhost:30333/healthz             # qdrant в кластере
```

Параллельный прогон голосового контура: moltbot-api в compose временно
направляется на кластерные Redis/Qdrant/MQTT (`REDIS_URL=redis://localhost:30379`,
`QDRANT_URL=http://localhost:30333`, `MQTT_URL=mqtt://localhost:30183` в `.env`),
затем smoke по README (диалог, новости, погода). После проверки — `docker compose
stop redis qdrant mqtt media-api moltbot-ui`, порты освобождаются.

**Откат** в любой момент: `helm uninstall moltbot -n moltbot` + `docker compose up -d`.

## Переключение (после smoke)

В `k8s/charts/moltbot/values.yaml` меняем NodePort на порты compose
(6379/6333/1883/8090; UI — 18079 через `nodePort` вне диапазона нельзя —
оставляем NodePort и пробрасываем через ingress в фазе 3) или переводим
сервисы в `ClusterIP` + ingress (фаза 3).

## Связность кластер ↔ хост

- Кластер → хост: `host.k3s.internal` (K3s ≥ v1.30 резолвит на хост; иначе —
  статический IP хоста). Так ходят: media-api → media executor (:8091),
  UI → moltbot-api (:18080, пока он в compose).
- Хост → кластер: NodePort-порты 30xxx (Hermes, host tools, smoke).

## Валидация чартов

```bash
scripts/k8s-validate.sh   # нужны helm и kubeconform в PATH
```

## Правила

- Секреты — только `.env` / Sealed Secrets (фаза 3), в values.yaml секретов нет.
- Stateful-сервисы — PVC на `local-path`; бэкап перед каждой фазой (`scripts/backup.sh`).
- Манифесты compose не удаляем до фазы 5 — это путь отката.
