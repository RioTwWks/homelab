# Голосовой стек homelab

## Hermes (Phase 2)

`микрофон → wake → STT → Hermes + Ollama → TTS`

```bash
make install-voice
make install-voice-npu   # FastFlowLM NPU STT
hermes doctor && hermes run "Привет"
```

См. [hermes-voice-npu.md](./hermes-voice-npu.md), [wake-word.md](./wake-word.md). Rollback: `voice_backend: legacy`.

---

## Legacy MVP (push-to-talk, moltbot-api)

Цель: минимальная голосовая цепочка:

`микрофон → STT → moltbot-api (/v1/chat) → TTS → колонки`

По умолчанию используется **push-to-talk** (запуск скрипта = начало записи). Опционально можно включить **wake word**: при произнесении ключевой фразы автоматически запускается этот же контур. См. [Wake word (документация)](./wake-word.md) и переменные в `scripts/voice_mvp.env.example` (секция Wake word).

## 1) Зависимости ОС

```bash
sudo apt update
sudo apt install -y build-essential cmake git alsa-utils jq curl sox
```

## 2) STT: whisper.cpp (локально, CPU)

1) Склонировать и собрать:

```bash
mkdir -p "$HOME/.local/src" && cd "$HOME/.local/src"
git clone https://github.com/ggerganov/whisper.cpp
cd whisper.cpp
cmake -B build
cmake --build build -j
```

2) Скачать модель (пример — large-v3, можно заменить на medium для скорости):

```bash
cd "$HOME/.local/src/whisper.cpp"
./models/download-ggml-model.sh large-v3
```

Примечание по скорости:
- `large-v3` на CPU может быть заметно медленнее реального времени (например, 6 секунд аудио → десятки секунд обработки).
- для голосового ассистента обычно хватает `medium` или `small` (в разы быстрее).

```bash
cd "$HOME/.local/src/whisper.cpp"
./models/download-ggml-model.sh medium
```

## 3) TTS: Piper (локально)

Вариант A (через пакет pip):

```bash
python3 -m venv "$HOME/.venvs/piper"
source "$HOME/.venvs/piper/bin/activate"
pip install --upgrade pip
pip install piper-tts
# В некоторых версиях piper-tts может не подтянуть зависимость:
pip install pathvalidate
```

Дальше нужно скачать RU модель Piper (голос). У Piper модели зависят от выпуска, поэтому проще выбрать по списку в репозитории Piper или через готовые сборки. В скрипте ниже путь к модели задаётся переменной `PIPER_MODEL`.

## 3b) TTS: Silero (локально, альтернатива Piper)

Silero TTS работает локально через PyTorch Hub. Установка в отдельный venv:

```bash
python3 -m venv "$HOME/.venvs/silero"
source "$HOME/.venvs/silero/bin/activate"
pip install -U pip

# CPU-only PyTorch (быстрее/проще поставить, чем ROCm)
pip install --index-url https://download.pytorch.org/whl/cpu torch torchaudio

# Доп. зависимости, которые рекомендует Silero hub
pip install omegaconf

# Для нормализации чисел (чтобы "2.14" произносилось словами)
pip install num2words
```

В `scripts/voice_mvp.env` переключи движок:

```bash
TTS_ENGINE=silero
SILERO_PY=$HOME/.venvs/silero/bin/python
SILERO_LANGUAGE=ru
SILERO_SPEAKER_MODEL=v3_1_ru
SILERO_VOICE=kseniya
SILERO_NORMALIZE_RU=true
TTS_PAD_MS=120
```

Быстро посмотреть доступные голоса (для `v3_1_ru` обычно: `aidar`, `baya`, `kseniya`, `xenia`, `eugene`, `random`):

```bash
$HOME/.venvs/silero/bin/python scripts/silero_tts.py --list-voices --output /tmp/_dummy.wav --language ru --speaker-model v3_1_ru
```

Справка по API/моделям: [Silero TTS на PyTorch Hub](https://pytorch.org/hub/snakers4_silero-models_tts).

## 4) Запуск

Скопируй `scripts/voice_mvp.env.example` в `scripts/voice_mvp.env` и отредактируй пути.

### Запись “пока не замолчишь” (рекомендуется)

По умолчанию в примере включено `RECORD_UNTIL_SILENCE=true` — запись остановится, когда ты замолчишь, и не будет ждать фиксированные 6 секунд.

Если нужно отключить, поставь `RECORD_UNTIL_SILENCE=false` и будет запись фиксированной длины `RECORD_SECONDS`.

### Быстрый STT через `whisper-server` (рекомендуется)

Чтобы не загружать модель при каждом запуске, держим сервер распознавания “прогретым”.

#### Установка как systemd сервис (рекомендуется)

Автоматический запуск при загрузке системы и автоперезапуск при падении:

```bash
# 1) Отредактируй пути в scripts/systemd/whisper-server.service (User, WorkingDirectory, ExecStart)
# 2) Скопируй unit файл
sudo cp scripts/systemd/whisper-server.service /etc/systemd/system/

# 3) Опционально: переопределить переменные (например, модель или количество потоков)
sudo mkdir -p /etc/systemd/system/whisper-server.service.d
echo -e "[Service]\nEnvironment=WHISPER_SERVER_THREADS=10" | sudo tee /etc/systemd/system/whisper-server.service.d/override.conf

# 4) Загрузи конфигурацию и запусти
sudo systemctl daemon-reload
sudo systemctl enable --now whisper-server.service

# 5) Проверь статус
sudo systemctl status whisper-server
curl -sS http://127.0.0.1:8099/health

# Логи
sudo journalctl -u whisper-server -f
```

Управление:
```bash
sudo systemctl start whisper-server    # запустить
sudo systemctl stop whisper-server     # остановить
sudo systemctl restart whisper-server   # перезапустить
sudo systemctl status whisper-server    # статус
```

#### Ручной запуск (для тестирования)

Если нужно запустить вручную для отладки:

```bash
bash scripts/whisper_server_run.sh
```

Остановить:
```bash
pkill -f whisper-server || true
```

Если хочешь ускорить распознавание — в `scripts/voice_mvp.env` поставь `WHISPER_MODEL` на `ggml-medium.bin` и перезапусти сервис: `sudo systemctl restart whisper-server`.

2) В `scripts/voice_mvp.env` выставь:

- `WHISPER_SERVER_URL=http://127.0.0.1:8099`

После этого `voice_mvp.sh` будет отправлять WAV на `whisper-server` и получать текст быстрее.

Затем:

```bash
bash scripts/voice_mvp.sh
```

### Режим с wake word (опционально)

Чтобы не нажимать запуск вручную, можно держать включённым слушатель wake word — при срабатывании он запустит `voice_mvp.sh`:

```bash
source scripts/voice_mvp.env
python scripts/wakeword_openwakeword.py
```

Подробнее: установка openWakeWord, обучение своей (в т.ч. русской) фразы, сравнение с VOSK/PocketSphinx — в [docs/wake-word.md](./wake-word.md).

## 5) Отладка микрофона

Посмотреть устройства:

```bash
arecord -L
```

Проверить запись:

```bash
arecord -f S16_LE -r 16000 -c 1 -d 3 /tmp/test.wav && aplay /tmp/test.wav
```

