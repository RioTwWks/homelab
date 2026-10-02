# Hermes: распознавание говорящего и персонализация

Фаза homelab: после wake и STT определяем **кто говорит**, выбираем профиль **child / student / adult** и передаём контекст в Hermes перед TTS.

## Цепочка

```text
микрофон → wake word → STT (Hermes local / FLM NPU)
    → POST /process_voice (middleware :8098, audio + опционально text)
        → speaker-recognition :8099 /recognize
        → personality_map + порог уверенности
    → Hermes (SOUL / /personality) + Ollama → TTS
```

На хосте Hermes обычно слушает микрофон напрямую; middleware вызывается из кастомного hook или внешнего voice-bridge, когда в `~/.hermes/config.yaml` включён `voice.middleware`.

## Docker Compose (профиль `voice`)

```bash
docker compose --profile voice up -d speaker-recognition speaker-personality-middleware
```

| Сервис | Порт | Назначение |
|--------|------|------------|
| `speaker-recognition` | 8099 | Embeddings, train/recognize API |
| `speaker-personality-middleware` | 8098 | Маппинг говорящий → personality |

Проверка здоровья:

```bash
bash scripts/speaker_recognition_health.sh
curl -s http://localhost:8098/healthz | jq
```

Обучение (на хосте, после записи сэмплов — см. ниже):

```bash
# Пример: один спикер, base64 аудио 16 kHz mono
curl -sS -X POST http://localhost:8099/train \
  -H 'Content-Type: application/json' \
  -d '{"voice_samples":[{"user":"Alice","audio_input":{"audio_data":"<BASE64>","sample_rate":16000}}]}'
```

Распознавание:

```bash
curl -sS -X POST http://localhost:8099/recognize \
  -H 'Content-Type: application/json' \
  -d '{"audio_input":{"audio_data":"<BASE64>","sample_rate":16000}}'
```

Middleware (multipart, как после STT):

```bash
curl -sS -X POST http://localhost:8098/process_voice \
  -F 'audio=@sample.wav' \
  -F 'text=Привет, какая погода?'
```

Ответ содержит `personality`, `confidence`, `hermes_personality_hint` (`/personality child` и т.д.).

## Конфигурация

Файл: `services/speaker_personality_middleware/config/speaker_personality.yaml`

Переменные окружения (см. `.env.example`):

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `SPEAKER_SERVICE_URL` | `http://speaker-recognition:8099` | API embeddings |
| `HERMES_URL` | пусто | Опциональный HTTP hook Hermes |
| `CONFIDENCE_THRESHOLD` / `SPEAKER_CONFIDENCE_THRESHOLD` | `0.7` | Ниже порога → `adult` |
| `DEFAULT_PERSONALITY` / `SPEAKER_DEFAULT_PERSONALITY` | `adult` | Безопасный fallback |
| `PERSONALITY_MAP` | JSON | `{"Alice":"child","Bob":"student"}` |

Hermes (`hermes/config/config.yaml.example`):

```yaml
voice:
  middleware:
    enabled: true
    url: http://127.0.0.1:8098   # из контейнера: http://host.docker.internal:8098
    process_path: /process_voice
```

Ansible: `hermes_speaker_middleware_enabled`, `hermes_speaker_middleware_url` в `group_vars`.

## Личности (SOUL.md)

Шаблоны в репозитории:

- `hermes/personalities/child/SOUL.md`
- `hermes/personalities/student/SOUL.md`
- `hermes/personalities/adult/SOUL.md`

Установка в `~/.hermes/personalities/`:

```bash
bash scripts/install-hermes-personalities.sh
```

### Команды Hermes CLI

В интерактивной сессии `hermes`:

| Действие | Команда |
|----------|---------|
| Ребёнок | `/personality child` |
| Ученик | `/personality student` |
| Взрослый | `/personality adult` |
| Сброс overlay | `/personality none` |

Для автоматического режима по голосу voice-bridge должен либо выполнить `/personality <name>`, либо подменить активный `~/.hermes/SOUL.md` симлинком на `~/.hermes/personalities/<profile>/SOUL.md` **до** вызова модели.

Зарегистрируйте кастомные personalities в `~/.hermes/config.yaml` (краткие описания), если CLI их не подхватывает из коробки — полный текст идёт из SOUL.

## Обучение на хосте (не в CI)

1. Запишите **3–5 минут** чистой речи **на человека** (тихая комната, один микрофон, 16 kHz mono WAV).
2. Разбейте на фрагменты 5–15 с и отправьте в `POST /train` с именем, совпадающим с ключом в `personality_map`.
3. Храните embeddings в `./speaker-embeddings` (volume Docker, не коммитить).
4. Перезапуск контейнера не стирает volume.

## Home Assistant (опционально)

Можно использовать тот же `speaker-recognition` как backend HA integration ([upstream project](https://github.com/EuleMitKeule/speaker-recognition)). Homelab-middleware остаётся независимым REST-слоем для Hermes.

## Матрица тестирования

| Условие | Ожидание |
|---------|----------|
| Тихая комната, обученный спикер | `confidence` ≥ 0.7, верный `personality` |
| Фоновый шум (ТВ, вентилятор) | Чаще fallback `adult`, лог `confidence_below_threshold` |
| Неизвестный голос | `adult`, `speaker_not_mapped` |
| Низкий порог / плохой микрофон | Стабильный `adult`, без child-ограничений по ошибке |
| Middleware без `text` | Только идентификация, без вызова `HERMES_URL` |
| `docker compose config` | Без ошибок (профиль `voice`) |

## Риски

| Риск | Влияние | Митигация |
|------|---------|-----------|
| Ложный child при шуме | Ребёнку доступны не те ответы | Порог 0.7, default `adult`, короткие ответы в child SOUL |
| Путаница близких голосов | Неверный профиль | Больше train-сэмплов, разные имена в map |
| Конфликт порта 8099 | Legacy whisper-server на хосте | Не запускать whisper-server на 8099 вместе с compose `speaker-recognition` |
| Утечка embeddings | Идентификация по голосу | Volume только на хосте, бэкапы с осторожностью |
| Нет HERMES_URL | Только маппинг | Voice-bridge читает JSON и сам переключает SOUL |

## Acceptance criteria

- [ ] `docker compose --profile voice config` проходит
- [ ] `scripts/speaker_recognition_health.sh` → `healthy`
- [ ] `curl localhost:8098/healthz` → `ok: true`
- [ ] После train curl `/recognize` возвращает ожидаемого `speaker`
- [ ] `POST /process_voice` с mock/реальным аудио возвращает `personality` по map
- [ ] При `confidence < 0.7` → `adult`
- [ ] `scripts/install-hermes-personalities.sh` копирует три SOUL в `~/.hermes/personalities/`
- [ ] pytest `services/speaker_personality_middleware` зелёный в CI
- [ ] Документирована полная цепочка wake → STT → middleware → Hermes → TTS

## Systemd (опционально)

Пример unit на хосте без Docker для middleware: `scripts/systemd/speaker-personality-middleware.service.example`.
