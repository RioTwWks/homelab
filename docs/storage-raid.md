# RAID-подобное хранилище для файлов и фото/видео

План развёртывания избыточного хранилища на **3+ HDD** для данных Nextcloud и Immich: отказ одного (или двух) дисков не ведёт к потере данных.

## Варианты

| Вариант | Плюсы | Минусы | Ёмкость при 3×4 TB |
|--------|--------|--------|---------------------|
| **mdadm RAID5** | Встроен в ядро, просто, один диск на парати | Перестроение массива нагружает диск | ~8 TB |
| **mdadm RAID6** | Допускает отказ двух дисков | Меньше полезной ёмкости | ~4 TB |
| **ZFS raidz1** | Целостность данных, снапшоты, сжатие | Нужен пакет, больше RAM | ~8 TB |
| **ZFS raidz2** | Два диска на парати (как RAID6) | Ещё меньше ёмкости | ~4 TB |
| **Btrfs RAID1** | Встроен, гибкость | RAID5/6 долго были экспериментальными | зависит от профиля |

Рекомендация для homelab: **mdadm RAID5** (3 диска) или **ZFS raidz1** при желании снапшотов и сжатия. Ниже — пошагово для **mdadm** и кратко для **ZFS**.

---

## 1. mdadm RAID5 (3 диска)

### Требования

- Минимум 3 диска (желательно одного размера).
- На сервере: `mdadm`, `lvm2` (опционально), `uuid-runtime`.

```bash
# Debian/Ubuntu
sudo apt install mdadm lvm2
```

### 1.1. Разметка дисков

Каждый диск — одна партиция с типом **Linux RAID (FD)**. Замените `/dev/sdX` на ваши устройства (например `/dev/sdb`, `/dev/sdc`, `/dev/sdd`).

```bash
# Проверить диски (НЕ системный!)
lsblk -o NAME,SIZE,MODEL,TRAN

# Для каждого диска под массив (пример: sdb, sdc, sdd)
for d in /dev/sdb /dev/sdc /dev/sdd; do
  sudo parted -s "$d" mklabel gpt
  sudo parted -s "$d" mkpart primary 1MiB 100%
  sudo parted -s "$d" set 1 raid on
done
```

Или через `fdisk`: создать одну партицию, тип **FD** (Linux RAID).

### 1.2. Создание массива RAID5

```bash
# Партиции: sdb1, sdc1, sdd1 (подставьте свои)
sudo mdadm --create /dev/md0 --level=5 --raid-devices=3 /dev/sdb1 /dev/sdc1 /dev/sdd1

# Ответить yes на создание массива. Синхронизация займёт время (смотреть: cat /proc/mdstat).
```

### 1.3. Файловая система и точка монтирования

```bash
# Файловая система (ext4)
sudo mkfs.ext4 -L raid5-data /dev/md0

# Каталог для монтирования
sudo mkdir -p /mnt/raid
sudo mount /dev/md0 /mnt/raid

# Подкаталоги для сервисов
sudo mkdir -p /mnt/raid/nextcloud /mnt/raid/immich
sudo chown -R 33:33 /mnt/raid/nextcloud   # www-data для Nextcloud
# Immich: по умолчанию контейнер пишет от root — оставьте root:root или задайте того же UID/GID, что в PUID/PGID Immich
sudo chown -R root:root /mnt/raid/immich
```

### 1.4. Сохранение конфигурации и автозапуск

```bash
# Сохранить конфигурацию массива (чтобы собирать после перезагрузки)
sudo mdadm --detail --scan | sudo tee -a /etc/mdadm/mdadm.conf
# или на дистрибутивах без mdadm.conf: sudo tee /etc/mdadm.conf

# Добавить в fstab (UUID после первой проверки: blkid /dev/md0)
UUID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx  /mnt/raid  ext4  defaults,nofail  0  2
```

Проверить UUID: `sudo blkid /dev/md0`. После перезагрузки массив должен собраться автоматически (`mdadm --assemble --scan` или systemd unit).

### 1.5. Подключение к Docker (Nextcloud и Immich)

Вместо именованных томов используйте **bind mount** каталогов с RAID.

**Вариант A: override-файл** (рекомендуется). В репозитории есть пример: `docker-compose.raid.example.yml`. Скопируйте его в `docker-compose.override.yml`:

```bash
cp docker-compose.raid.example.yml docker-compose.override.yml
```

Содержимое override задаёт bind mount: `/mnt/raid/nextcloud` → Nextcloud, `/mnt/raid/immich` → Immich. Затем: `docker compose --profile storage --profile photos up -d`. Данные Nextcloud окажутся в `/mnt/raid/nextcloud`, Immich — в `/mnt/raid/immich`.

**Вариант B: переменные в .env.** Можно вынести пути в переменные и использовать их в `volumes` (в основном compose или в override), например `STORAGE_RAID_PATH=/mnt/raid`.

### 1.6. Миграция существующих данных

Если Nextcloud и Immich уже работают на именованных томах:

1. Остановить контейнеры: `docker compose --profile storage --profile photos stop nextcloud immich-server`.
2. Скопировать данные с тома на RAID (пример для Nextcloud):
   ```bash
   sudo docker run --rm -v homelab_nextcloud_data:/from -v /mnt/raid/nextcloud:/to alpine sh -c "cp -a /from/. /to/"
   ```
   Для Immich: том `homelab_immich_upload`, целевой каталог `/mnt/raid/immich`.
3. Настроить override (bind mount) и запустить контейнеры. Проверить доступ к файлам.
4. Именованные тома можно удалить после проверки: `docker volume rm homelab_nextcloud_data homelab_immich_upload`.

---

## 2. ZFS raidz1 (альтернатива)

Установка (Debian/Ubuntu): `sudo apt install zfsutils-linux`. Затем:

```bash
# Создать пул с одним parity-диском (аналог RAID5). Диски — целые, без партиций (или по партиции на диск).
sudo zpool create -f -o ashift=12 raidpool raidz /dev/sdb /dev/sdc /dev/sdd

# Файловая система и каталоги
sudo zfs create -o mountpoint=/mnt/raid raidpool/data
sudo zfs create raidpool/data/nextcloud
sudo zfs create raidpool/data/immich
sudo chown 33:33 /mnt/raid/nextcloud
sudo chown root:root /mnt/raid/immich
```

Пул монтируется автоматически. В docker-compose.override используйте те же пути `/mnt/raid/nextcloud` и `/mnt/raid/immich`. Дополнительно можно включить сжатие: `sudo zfs set compression=lz4 raidpool/data`.

---

## 3. Мониторинг и замена диска

### mdadm

```bash
# Статус
cat /proc/mdstat
sudo mdadm --detail /dev/md0

# При отказе диска: пометить как failed, удалить, добавить новый
sudo mdadm --manage /dev/md0 --fail /dev/sdb1
sudo mdadm --manage /dev/md0 --remove /dev/sdb1
# После замены диска (новая партиция с типом FD):
sudo mdadm --manage /dev/md0 --add /dev/sde1
# Синхронизация начнётся автоматически (смотреть /proc/mdstat).
```

### ZFS

```bash
sudo zpool status
# Замена: zpool replace raidpool /dev/sdb /dev/sde
```

---

## 4. Вся система на RAID (как файлы и фото)

Чтобы **все** данные homelab (не только Nextcloud и Immich) лежали на RAID и имели ту же избыточность при отказе диска:

1. На уже смонтированном RAID создайте каталог под все тома Docker:
   ```bash
   sudo mkdir -p /mnt/raid/docker/{redis_data,qdrant_data,mosquitto_data,mosquitto_log,homeassistant_config,\
     nextcloud_data,nextcloud_db_data,immich_upload,immich_db_data,immich_ml_cache,\
     qbittorrent_config,qbittorrent_downloads,searxng_data}
   sudo chown 33:33 /mnt/raid/docker/nextcloud_data
   ```
   Остальные каталоги по умолчанию могут быть root; при первом запуске контейнеры создадут нужные файлы. При необходимости поправьте владельца (например 999:999 для redis, 1000:1000 для qdrant — смотрите UID в образах).

2. Используйте полный override для всех томов:
   ```bash
   cp docker-compose.raid-full.example.yml docker-compose.override.yml
   ```
   В нём все тома переопределены на `/mnt/raid/docker/<имя_тома>`.

3. Запустите стек с нужными профилями. Данные Redis, Qdrant, Home Assistant, Nextcloud, Immich, qBittorrent, SearxNG будут на RAID.

Дополнительно настройте **автоматическое резервное копирование** (репо + снимки/архивы) по расписанию — см. `docs/backup.md` и `scripts/backup.sh` с systemd timer.

---

## 5. Резюме

- **3 HDD** — mdadm RAID5 или ZFS raidz1: полезный объём ≈ 2 диска, переживает отказ одного диска.
- **4+ HDD** — можно RAID6 / raidz2 (отказ двух дисков) или оставить RAID5/raidz1 для большей ёмкости.
- **Только файлы/фото:** `docker-compose.raid.example.yml` — Nextcloud и Immich на `/mnt/raid/nextcloud` и `/mnt/raid/immich`.
- **Вся система на RAID:** `docker-compose.raid-full.example.yml` — все тома Docker в `/mnt/raid/docker/<том>`.
- После разметки и создания массива сохраните конфиг mdadm и fstab, чтобы после перезагрузки RAID монтировался автоматически.
- Автобэкап по расписанию: `docs/backup.md`, `scripts/backup.sh`, systemd timer.
