#!/usr/bin/env bash
#
# Автоматическое резервное копирование всей системы homelab (по типу RAID для файлов/фото).
# Сохраняет: репозиторий + критические тома Docker в каталог с датой.
#
# Использование:
#   BACKUP_DIR=/mnt/raid/backups ./scripts/backup.sh
#   Или по расписанию: systemd timer (см. scripts/systemd/) или cron.
#
# Переменные:
#   BACKUP_DIR     — корень каталога бэкапов (по умолчанию /backup/homelab).
#   COMPOSE_PROJECT_NAME — префикс имён томов (по умолчанию homelab).
#   BACKUP_RETENTION_DAYS — хранить последние N дней (0 = не удалять старые).
#
set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="${BACKUP_DIR:-/backup/homelab}"
DATE="$(date +%Y%m%d-%H%M)"
DEST="${BACKUP_DIR}/${DATE}"
COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-homelab}"
BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-0}"

mkdir -p "$DEST"
echo "[backup] Destination: $DEST"

# 1. Репозиторий (без .git, кешей; .env — отдельный архив)
tar --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' --exclude='nohup.out' \
  --exclude='.env' \
  -C "$REPO_ROOT" -czf "$DEST/homelab-repo.tar.gz" .
echo "[backup] Repo archived"

if [ -f "$REPO_ROOT/.env" ]; then
  tar -C "$REPO_ROOT" -czf "$DEST/homelab-env.tar.gz" .env
  echo "[backup] .env archived (store securely)"
fi

# 2. Критические тома Docker (экспорт в архив)
export_volume() {
  local vol=$1
  local name="${COMPOSE_PROJECT_NAME}_${vol}"
  if docker volume inspect "$name" &>/dev/null; then
    docker run --rm -v "${name}:/data" -v "$DEST:/backup" alpine \
      tar czf "/backup/${vol}.tar.gz" -C /data .
    echo "[backup] Volume $vol done"
  else
    echo "[backup] Skip $vol (volume not found)"
  fi
}

export_volume redis_data
export_volume qdrant_data
export_volume homeassistant_config
export_volume nextcloud_data
export_volume nextcloud_db_data
export_volume immich_upload
export_volume immich_db_data
export_volume qbittorrent_config
# Опционально (часто большие): qbittorrent_downloads, immich_ml_cache, mosquitto_data, mosquitto_log, searxng_data
# export_volume qbittorrent_downloads
# export_volume mosquitto_data
# export_volume mosquitto_log
# export_volume searxng_data

# 3. Удаление старых бэкапов (если задано)
if [ -n "$BACKUP_RETENTION_DAYS" ] && [ "$BACKUP_RETENTION_DAYS" -gt 0 ]; then
  find "$BACKUP_DIR" -maxdepth 1 -type d -name "20*" -mtime +"$BACKUP_RETENTION_DAYS" -exec rm -rf {} \;
  echo "[backup] Pruned backups older than $BACKUP_RETENTION_DAYS days"
fi

echo "[backup] Done: $DEST"
echo "Restore repo: tar -xzf homelab-repo.tar.gz -C /path/to/restore"
echo "Restore volume: docker run --rm -v VOLUME_NAME:/data -v DEST:/b alpine sh -c 'tar xzf /b/VOLUME_NAME.tar.gz -C /data'"
