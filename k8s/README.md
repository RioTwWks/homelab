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

## Фаза 2 — опциональные профили (community-чарты)

По одному сервису на релиз, в порядке роста риска (план §5). Для каждого:
values в `k8s/values/<service>.yaml`, параллельный запуск, проверка,
выключение compose-профиля. Данные stateful-сервисов мигрируют на PVC
(или hostPath по `docs/storage-raid.md`), бэкап — перед каждым сервисом.

### SearXNG (первый)

```bash
helm repo add searxng https://techpipe-io.github.io/searxng-helm-chart
kubectl apply -f k8s/namespaces/
helm install searxng searxng/searxng -n search -f k8s/values/searxng.yaml

# Smoke (NodePort выделяется автоматически)
kubectl -n search get svc searxng
curl -s "http://localhost:<nodePort>/search?q=test&format=json" | jq '.results | length'
```

Переключение: в `.env` moltbot-api `WEB_SEARCH_PROVIDER=searxng`,
`SEARXNG_BASE_URL=http://localhost:<nodePort>` (пока moltbot-api на хосте),
smoke «новости»/веб-поиск по README, затем `docker compose stop searxng`.
Когда moltbot-api переедет в кластер — `http://searxng.search.svc:8080`.
Данных, кроме кэша, нет — миграция данных не требуется.

### qBittorrent (второй)

```bash
kubectl apply -f k8s/namespaces/   # namespace media

# 1. Миграция данных: остановить compose-сервис, скопировать тома на будущие PV.
#    local-path кладёт данные в /var/lib/rancher/k3s/storage — после install
#    найти каталоги PVC (kubectl -n media get pvc → pv → local path) и rsync'нуть
#    содержимое docker-томов qbittorrent_config и qbittorrent_downloads.
docker compose stop qbittorrent

# 2. Установка
helm install qbittorrent oci://ghcr.io/bjw-s-labs/helm-charts/app-template \
  --version 5.3.0 -n media -f k8s/values/qbittorrent.yaml

# 3. Smoke: веб-UI и API версии
curl -s http://localhost:30084/api/v2/app/version
```

Проверить очередь загрузок/раздач на месте, затем `docker compose rm -s qbittorrent`
(тома не удалять до конца фазы 5 — путь отката). TorrServer в compose продолжает
читать docker-том `qbittorrent_downloads` — его миграция отдельным релизом,
shared-том см. комментарий в `k8s/values/qbittorrent.yaml`.

### Nextcloud (третий)

Самый рискованный из тройки: stateful + БД + версионность. Перед началом — бэкап
(`scripts/backup.sh`).

```bash
kubectl apply -f k8s/namespaces/   # namespace storage

# 1. Секреты (в Git не хранятся; фаза 3 заменит на Sealed Secrets)
kubectl -n storage create secret generic nextcloud-admin \
  --from-literal=nextcloud-username=admin \
  --from-literal=nextcloud-password='<NEXTCLOUD_ADMIN_PASSWORD из .env>'
kubectl -n storage create secret generic nextcloud-db \
  --from-literal=db-username=nextcloud \
  --from-literal=db-password='<NEXTCLOUD_DB_PASSWORD из .env>'
kubectl -n storage create secret generic nextcloud-mariadb \
  --from-literal=mariadb-root-password='<NEXTCLOUD_DB_ROOT_PASSWORD из .env>' \
  --from-literal=mariadb-replication-password='<случайный>' \
  --from-literal=mariadb-password='<NEXTCLOUD_DB_PASSWORD из .env>'

# 2. Версия: выставить image.tag в k8s/values/nextcloud.yaml под версию из compose
#    (Nextcloud не умеет пропускать мажорные версии при апгрейде данных!)
docker compose exec nextcloud occ status

# 3. Миграция данных
docker compose stop nextcloud nextcloud_db
#    - том nextcloud_data → rsync на local-path PV (как в qBittorrent);
#    - БД: mysqldump из контейнера nextcloud_db, импорт в под mariadb
#      (kubectl exec -i nextcloud-mariadb-0 -- mysql ... < dump.sql).

# 4. Установка и smoke
helm repo add nextcloud https://nextcloud.github.io/helm/
helm install nextcloud nextcloud/nextcloud -n storage -f k8s/values/nextcloud.yaml
curl -s -o /dev/null -w '%{http_code}' http://localhost:30082/status.php  # 200 + JSON
```

Проверить логин админом, файлы на месте, версия совпадает с compose. Затем
`docker compose rm -s nextcloud nextcloud_db` (тома — не удалять до фазы 5).
Cron-задачи в кластере выполняет sidecar (в compose их не было).

### Immich (четвёртый)

Чарт [immich-app/immich-charts](https://github.com/immich-app/immich-charts) БД не
содержит — Postgres (vectorchord) разворачивается отдельным релизом app-template.
Порядок важен: PVC библиотеки и секрет → БД → сам Immich.

```bash
kubectl apply -f k8s/namespaces/                    # namespace photos

# 1. Секрет БД (в Git не хранится) + PVC библиотеки
kubectl -n photos create secret generic immich-db \
  --from-literal=password='<IMMICH_DB_PASSWORD из .env>'
kubectl apply -f k8s/manifests/immich-library-pvc.yaml

# 2. Версия: image.tag в k8s/values/immich.yaml должен совпадать с compose
#    (server и ML — строго одной версии; смотреть docker images | grep immich)

# 3. БД, затем Immich
helm install immich-db oci://ghcr.io/bjw-s-labs/helm-charts/app-template \
  --version 5.3.0 -n photos -f k8s/values/immich-db.yaml
helm repo add immich https://immich-app.github.io/immich-charts
helm install immich immich/immich --version 0.12.0 -n photos -f k8s/values/immich.yaml

# 4. Smoke
curl -s http://localhost:30083/api/server/ping     # {"res":"pong"}
```

Миграция данных: `docker compose stop immich-server immich-machine-learning immich_db immich_redis`,
том `immich_upload` → rsync на PV `immich-library`; БД — `pg_dump` из контейнера
`immich_db` → restore в под `immich-db-0`. Очередь (compose `immich_redis`) —
stateless, в кластере её заменяет valkey с emptyDir, миграция не нужна.
После проверки веб-UI и мобильного приложения — `docker compose rm -s` для
сервисов профиля photos (тома не удалять до фазы 5).

### Home Assistant (пятый)

Чарт [pajikos/home-assistant-helm-chart](https://github.com/pajikos/home-assistant-helm-chart)
(автообновляемый, образ тот же `home-assistant:stable`). Секретов нет.

```bash
kubectl apply -f k8s/namespaces/   # namespace home
helm repo add home-assistant https://pajikos.github.io/home-assistant-helm-chart/
helm install home-assistant home-assistant/home-assistant \
  -n home -f k8s/values/home-assistant.yaml

# Smoke
curl -s -o /dev/null -w '%{http_code}' http://localhost:30123/  # 200
```

Миграция: `docker compose stop homeassistant`, том `homeassistant_config` → rsync
на PV пода (`/config`). Проверить, что интеграции/устройства на месте.

**Discovery (mDNS/SSDP)** — единственный функциональный нюанс: работает только
в `hostNetwork`. В параллельной фазе он выключен (порт 8123 занят compose).
При переключении: выставить в values `hostNetwork: true` +
`dnsPolicy: ClusterFirstWithHostNet`, освободить порт (`docker compose stop homeassistant`),
`helm upgrade`. moltbot-api ходит в HA по `HOME_ASSISTANT_URL` — после переключения
это `http://localhost:8123` (hostNetwork) или `http://localhost:30123` до него.

### GitLab + Runner (шестой, самый тяжёлый)

Официальный чарт `gitlab/gitlab` **9.5.4** — appVersion **18.5.4**, точно как
`gitlab/gitlab-ce:18.5.4-ce.0` в compose. Версия критична: restore бэкапа GitLab
возможен только на ту же версию. Обновление — отдельной процедурой после миграции.

**Ресурсы:** полный чарт при минимальных репликах — ~6–8 ГБ RAM. Учитывая headroom
≥8 ГБ для Ollama (план §5, фаза 4), проверить `free -g` перед install; при
нехватке — не запускать параллельно с compose-профилем gitlab (миграция через
backup/restore это позволяет).

```bash
kubectl apply -f k8s/namespaces/   # namespace gitlab
helm repo add gitlab https://charts.gitlab.io/
helm install gitlab gitlab/gitlab --version 9.5.4 \
  -n gitlab -f k8s/values/gitlab.yaml --timeout 15m

# Smoke (параллельная фаза)
curl -s -o /dev/null -w '%{http_code}' http://gitlab.localhost:30090/users/sign_in  # 200
```

**Миграция — только backup/restore, не rsync** (реляционные данные + репозитории
согласованы только в бэкапе):

```bash
# 1. Бэкап в compose
docker exec gitlab gitlab-backup create STRATEGY=copy

# 2. Копия бэкапа в под toolbox и restore (той же версии!)
kubectl -n gitlab cp <host_backup.tar> gitlab/$(kubectl -n gitlab get pod -l app=toolbox -o name | cut -d/ -f2):/tmp/
kubectl -n gitlab exec deploy/gitlab-toolbox -- backup-utility --restore /tmp/<backup.tar>
#    + восстановить секреты из /etc/gitlab/gitlab-secrets.json (см. docs GitLab)
```

**Runner:** чарт ставит gitlab-runner с **kubernetes executor** (каждая задача —
под). В compose был docker executor через docker.sock: пайплайны с `docker build`/
dind напрямую не заработают — переводить на kaniko/buildkit или оставить такие
задачи на host-runner (профиль gitlab в compose до фазы 5). Регистрацию runner'а
чарт выполняет сам.

**Переключение портов:** параллельная фаза — web `gitlab.localhost:30090`,
registry `registry.localhost:30090`, ssh `:30222`. Финальные порты/домены
(18090/2222/5005 или единый ingress) — решение фазы 3; clone-URL изменятся,
предупредить в README проекта. Внутренний Prometheus GitLab выключен —
мониторинг придёт в фазе 4.

## Валидация чартов

```bash
scripts/k8s-validate.sh   # нужны helm и kubeconform в PATH
```

## Правила

- Секреты — только `.env` / Sealed Secrets (фаза 3), в values.yaml секретов нет.
- Stateful-сервисы — PVC на `local-path`; бэкап перед каждой фазой (`scripts/backup.sh`).
- Манифесты compose не удаляем до фазы 5 — это путь отката.
