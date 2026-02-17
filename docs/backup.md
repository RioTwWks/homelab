# Резервное копирование всей системы (как для файлов и фото)

Для **файлов и фото** избыточность реализована через **RAID** (данные Nextcloud и Immich на массиве). Для **всей системы** делаем то же по сути: (1) **все данные на RAID** — одна точка отказа закрыта; (2) **автоматическое резервное копирование** по расписанию — вторая копия в отдельном каталоге (на том же RAID, на втором диске или на NAS).

---

## 1. Избыточность: вся система на RAID

Как для файлов и фото — все данные homelab можно разместить на RAID, чтобы отказ одного диска не терял ни репо, ни тома.

- **Шаг 1:** разверните RAID и смонтируйте в `/mnt/raid` (см. `docs/storage-raid.md`).
- **Шаг 2:** создайте каталоги под все тома и подключите их через override:
  ```bash
  sudo mkdir -p /mnt/raid/docker/{redis_data,qdrant_data,mosquitto_data,mosquitto_log,homeassistant_config,\
    nextcloud_data,nextcloud_db_data,immich_upload,immich_db_data,immich_ml_cache,\
    qbittorrent_config,qbittorrent_downloads,searxng_data}
  sudo chown 33:33 /mnt/raid/docker/nextcloud_data
  cp docker-compose.raid-full.example.yml docker-compose.override.yml
  ```
- **Шаг 3:** запускайте стек как обычно. Все тома будут на RAID.

Имена томов и пути описаны в `docs/storage-raid.md`, раздел «Вся система на RAID».

---

## 2. Автоматическое резервное копирование по расписанию

Помимо RAID нужна **вторая копия** (архивы репо + томов), которая создаётся **автоматически** по расписанию.

### Что бэкапится

- **Репозиторий** — compose, код (moltbot_api, media_api), scripts, docs, searxng; без .git и кешей. Файл **.env** кладётся в отдельный архив (храните его в безопасном месте).
- **Критические тома Docker:** redis_data, qdrant_data, homeassistant_config, nextcloud_data, nextcloud_db_data, immich_upload, immich_db_data, qbittorrent_config. Остальные тома можно добавить в скрипт при необходимости.

### Скрипт и запуск

Скрипт **`scripts/backup.sh`** создаёт каталог с датой в `BACKUP_DIR` и кладёт туда:

- `homelab-repo.tar.gz` — репозиторий;
- `homelab-env.tar.gz` — .env (если есть);
- `<имя_тома>.tar.gz` — архив каждого тома.

**Переменные:**

- `BACKUP_DIR` — куда складывать бэкапы (например `/mnt/raid/backups` или второй диск).
- `BACKUP_RETENTION_DAYS` — хранить только последние N дней (например 14); 0 — не удалять старые.
- `COMPOSE_PROJECT_NAME` — префикс томов (по умолчанию homelab).

**Ручной запуск:**

```bash
BACKUP_DIR=/mnt/raid/backups BACKUP_RETENTION_DAYS=14 ./scripts/backup.sh
```

### Автозапуск по расписанию (systemd timer)

В репозитории есть юниты для ежедневного бэкапа:

```bash
sudo cp scripts/systemd/homelab-backup.service scripts/systemd/homelab-backup.timer /etc/systemd/system/
```

В сервисе замените `/path/to/homelab` на реальный путь к репозиторию. Задайте каталог бэкапов и срок хранения (через override или правку сервиса):

```bash
sudo mkdir -p /etc/systemd/system/homelab-backup.service.d
echo -e "[Service]\nWorkingDirectory=/home/user/homelab\nExecStart=/home/user/homelab/scripts/backup.sh\nEnvironment=BACKUP_DIR=/mnt/raid/backups\nEnvironment=BACKUP_RETENTION_DAYS=14" | sudo tee /etc/systemd/system/homelab-backup.service.d/override.conf
```

В `homelab-backup.service` замените оба `/path/to/homelab` на этот же путь (или оставьте только override).

Включите таймер:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now homelab-backup.timer
```

Бэкап будет запускаться раз в день (в 03:00 по умолчанию, см. `homelab-backup.timer`). Проверка: `systemctl list-timers homelab-backup.timer`, логи: `journalctl -u homelab-backup.service`.

### Альтернатива: cron

```bash
# Ежедневно в 03:00, хранить 14 дней
0 3 * * * BACKUP_DIR=/mnt/raid/backups BACKUP_RETENTION_DAYS=14 /path/to/homelab/scripts/backup.sh
```

---

## 3. Восстановление

1. Восстановить репозиторий: `tar -xzf homelab-repo.tar.gz -C /path/to/homelab`.
2. Восстановить .env: `tar -xzf homelab-env.tar.gz -C /path/to/homelab`.
3. Поднять пустой стек: `docker compose up -d` (тома пустые).
4. Остановить контейнеры, использующие нужные тома. Для каждого тома:
   `docker run --rm -v homelab_<имя_тома>:/data -v /path/to/backup/YYYYMMDD:/b alpine sh -c 'tar xzf /b/<имя_тома>.tar.gz -C /data'`.
5. Запустить контейнеры снова и проверить.

---

## 4. Краткий чек-лист

- [ ] RAID развёрнут, все данные на RAID (`docker-compose.raid-full.example.yml`) или хотя бы файлы/фото (`docker-compose.raid.example.yml`).
- [ ] `BACKUP_DIR` выбран (например `/mnt/raid/backups` или второй диск).
- [ ] Скрипт `scripts/backup.sh` проверен вручную.
- [ ] Включён systemd timer (или cron) для ежедневного бэкапа.
- [ ] Задан `BACKUP_RETENTION_DAYS` при необходимости.
- [ ] Раз в полгода/год — проверка восстановления из бэкапа.
