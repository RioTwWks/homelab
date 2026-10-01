# Runbook — Agent B2: voice / NPU + monitoring

Операционный чеклист после merge **wave 1** (ветки A2 voice/NPU, A6 monitoring).  
Связанные документы: [hermes-voice-npu.md](./hermes-voice-npu.md), [voice-mvp.md](./voice-mvp.md), [monitoring.md](./monitoring.md), [homelab-redesign-wave1-merge.md](./homelab-redesign-wave1-merge.md).

---

## 1) Проверки в репозитории (облако / CI, NPU не нужен)

Выполняйте из корня клона (`~/homelab`).

| Проверка | Команда |
|----------|---------|
| Ansible (voice + site + remote_access) | `make check` |
| Compose профиль `monitoring` | `docker compose --profile monitoring config --quiet` |
| YAML/JSON в `monitoring/` | входит в `make check` (см. ниже) |
| Синтаксис `flm_validate.sh` | `bash -n scripts/flm_validate.sh` |

Одной командой (как в CI после правок):

```bash
make check
docker compose --profile monitoring config --quiet
bash -n scripts/flm_validate.sh
```

**Важно:** `ansible-playbook --syntax-check ansible/playbooks/voice.yml` из корня репозитория **не** находит роли — в Makefile задан `ANSIBLE_CONFIG=ansible/ansible.cfg`. Используйте `make check` или:

```bash
export ANSIBLE_CONFIG=ansible/ansible.cfg
cd ansible && ansible-playbook --syntax-check playbooks/voice.yml
```

`bash scripts/flm_validate.sh` и `flm validate` — **только на хосте** с установленным [FastFlowLM](https://pypi.org/project/fastflowlm/) и драйверами NPU (см. §3).

---

## 2) Только на homelab-хосте — голос Hermes (фаза 2)

Требуются: микрофон/ALSA, Ollama на хосте, Docker core stack.

```bash
cd ~/homelab
git pull origin main
make configure          # если ещё нет ansible/group_vars/local.yml
make install-voice      # Hermes voice (Ansible preset voice)
```

Проверка:

```bash
hermes doctor
hermes run "Привет, что ты умеешь?"
```

Подробности и rollback: [voice-mvp.md](./voice-mvp.md), [hermes-voice-npu.md](./hermes-voice-npu.md) (Phase 2).

---

## 3) Только на homelab-хосте — NPU STT (фаза 4)

Требуются: **Ryzen AI / XRT**, `pip install fastflowlm`, приёмка по плану A2.

```bash
pip install fastflowlm
bash scripts/flm_validate.sh
bash scripts/flm_validate.sh --json
```

В `ansible/group_vars/local.yml` (или через `make install-voice-npu`):

```yaml
hermes_enable_npu_stt: true
moltbot_enable_systemd_flm_asr: true
flm_pmode: powersaver   # опционально
```

```bash
make install-voice-npu
sudo systemctl status flm-asr
```

Hermes STT endpoint: `http://127.0.0.1:52625/v1` (модель `whisper-large-v3-turbo`).  
Rollback: `hermes_enable_npu_stt: false`, `sudo systemctl stop flm-asr`.

В облачном агенте без NPU **не** ожидайте успеха `flm validate` — достаточно `bash -n scripts/flm_validate.sh` и `make check`.

---

## 4) Только на homelab-хосте — мониторинг (фаза 7)

### Docker (профиль `monitoring`)

```bash
cd ~/homelab
docker compose --profile monitoring up -d
```

| Сервис | URL |
|--------|-----|
| Grafana | http://localhost:18091 |
| Prometheus | http://localhost:19090 |

Пароль Grafana: `GRAFANA_ADMIN_PASSWORD` в `.env` (по умолчанию `admin`).

### all-smi (энергия iGPU / NPU) — хост, не контейнер

1. Установите бинарник **all-smi** с [GitHub releases](https://github.com/lablup/all-smi/releases) (не `pip install all-smi`).
2. Скопируйте и отредактируйте unit:

```bash
sudo cp scripts/systemd/all-smi-api.service.example /etc/systemd/system/all-smi-api.service
sudo systemctl daemon-reload
sudo systemctl enable --now all-smi-api.service
curl -sf http://localhost:19095/metrics | head
```

Порт `19095` должен совпадать с `monitoring/prometheus/prometheus.yml` (`job: all-smi`).

Панель **NPU power** в Grafana заполнится только после фазы 4 и видимости NPU в all-smi — до этого `up=0` для `job=all-smi` нормален. См. [monitoring.md](./monitoring.md).

### Перезагрузка Prometheus после правки конфига

```bash
curl -X POST http://localhost:19090/-/reload
```

Rollback: `docker compose --profile monitoring down` ([monitoring.md](./monitoring.md)).

---

## 5) Сводка: облако vs хост

| Действие | Облако / CI | Homelab-хост |
|----------|-------------|--------------|
| `make check` | да | да |
| `docker compose --profile monitoring config` | да | да |
| `bash -n scripts/flm_validate.sh` | да | да |
| `flm validate` / `make install-voice-npu` | нет | да |
| `make install-voice`, `hermes run` | нет | да |
| `docker compose --profile monitoring up -d` | опционально | да |
| all-smi systemd | нет | да |

---

## 6) После wave 1 merge (полный хостовый чеклист)

См. [homelab-redesign-wave1-merge.md](./homelab-redesign-wave1-merge.md); для B2 достаточно секций §2–§4 выше плюс repo-валидация из §1.
