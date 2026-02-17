# Wake word (бесплатные аналоги Porcupine)

Чтобы не нажимать кнопку перед каждой фразой, используется **wake word** — при произнесении ключевой фразы запускается запись и цепочка STT → Moltbot → TTS. Ниже — бесплатные варианты с поддержкой **русского** или возможностью **обучить свою фразу**.

## Сравнение

| Решение | Русский из коробки | Обучить свою фразу | Состояние | Сложность |
|--------|--------------------|--------------------|-----------|-----------|
| **openWakeWord** | Нет (модели в основном EN) | Да (Colab, свои записи) | Активно | Низкая |
| **VOSK** | Да (модели ru) | Малая лексика / ключевые слова | Активно | Средняя |
| **PocketSphinx** | Есть акустика ru | Ключевые слова (keyphrase) | Поддержка есть | Средняя |
| **Mycroft Precise** | Нет | Да (свои примеры, TensorFlow) | Активно | Средняя |
| **Rhasspy** | Частично | Через PocketSphinx/Precise | Активно | Выше (целый фреймворк) |
| **Snowboy** | Нет | Да (устаревший API) | Заброшен | — |
| **Coqui STT** | Есть | Не про wake word | Проект в неопределённом состоянии | — |

**Рекомендация для homelab:**

- **openWakeWord** — бесплатно, можно обучить свою фразу (в т.ч. на русском) в Google Colab, получить ONNX-модель и использовать в скрипте на хосте. В репозитории есть `scripts/wakeword_openwakeword.py` и интеграция с `voice_mvp.sh`.
- **VOSK** — если нужен «из коробки» русский ключевой фразы без обучения: использовать маленькую модель VOSK с ограниченным словарём (одна–две фразы) как детектор, затем переходить к Whisper для полного распознавания.

---

## openWakeWord (рекомендуемый вариант)

### Установка на хосте

```bash
python3 -m venv "$HOME/.venvs/openwakeword"
source "$HOME/.venvs/openwakeword/bin/activate"
pip install --upgrade pip
pip install openwakeword pyaudio
# При отсутствии PortAudio: sudo apt install portaudio19-dev python3-pyaudio
```

### Как задать wake word

**Вариант 1 — встроенные английские фразы**

В пакете есть готовые модели: `alexa`, `hey_mycroft`, `hey_jarvis`, `timer`, `weather`. Список: `python scripts/wakeword_openwakeword.py --list_models`.

- **Одна фраза** — задай имя модели в env или аргументом:
  ```bash
  OPENWAKEWORD_BUILTIN=hey_mycroft python scripts/wakeword_openwakeword.py
  # или
  python scripts/wakeword_openwakeword.py --builtin hey_mycroft
  ```
  В `voice_mvp.env`: `OPENWAKEWORD_BUILTIN=hey_mycroft`.
- **Несколько фраз** — через запятую: `OPENWAKEWORD_BUILTIN=hey_mycroft,alexa`.
- **Все встроенные** — не задавай `OPENWAKEWORD_MODEL` и `OPENWAKEWORD_BUILTIN`; по умолчанию подхватываются все.

**Вариант 2 — своя фраза (в т.ч. русская)**

Обучи модель в ноутбуке openWakeWord (см. ниже), сохрани `.onnx` и укажи путь:
```bash
OPENWAKEWORD_MODEL=/path/to/my_wakeword.onnx python scripts/wakeword_openwakeword.py
```
В `voice_mvp.env`: `OPENWAKEWORD_MODEL=/path/to/my_wakeword.onnx`.

При срабатывании по умолчанию запускается `scripts/voice_mvp.sh` (путь задаётся в env или аргументом).

### Своя фраза (в т.ч. на русском)

1. В репозитории [openWakeWord](https://github.com/dscripka/openWakeWord) взять **notebooks/training_models.ipynb** (или **automatic_model_training.ipynb**).
2. Запустить ноутбук **локально** или в Google Colab:
   - **Локально** — часто быстрее: не нужно заливать данные в облако, на ПК с GPU обучение идёт быстрее. Нужны Jupyter и зависимости: `pip install openwakeword speechbrain datasets scipy matplotlib torch`. Ноутбук рассчитан и на CPU (на уменьшенных выборках), на GPU можно гнать полный объём данных.
   - **Colab** — удобно, если под рукой только браузер; бесплатный GPU лимитирован по времени.
3. Подготовить **примеры своей фразы** (например «Алиса», «Окей дом», «Слушай») — желательно 50–200 записей в тишине и с лёгким шумом. В ноутбуке описан синтез через TTS или использование своих WAV.
4. Обучить модель, сохранить **.onnx** файл.
5. Запускать с этой моделью:
   ```bash
   python scripts/wakeword_openwakeword.py --model_path /path/to/my_wakeword.onnx
   ```
   Или в `voice_mvp.env`: `OPENWAKEWORD_MODEL=/path/to/my_wakeword.onnx`.

Язык не зашит в openWakeWord — качество зависит только от обучающих записей (можно целиком русские фразы).

### Интеграция с голосовым контуром

В `scripts/voice_mvp.env.example` добавлены переменные для wake word. Скрипт **`scripts/wakeword_openwakeword.py`** при срабатывании вызывает команду (по умолчанию `scripts/voice_mvp.sh`). Запуск «с wake word»:

```bash
source scripts/voice_mvp.env  # или экспортируйте OPENWAKEWORD_* и WAKE_WORD_COMMAND
python scripts/wakeword_openwakeword.py
```

Рекомендуется держать запущенным whisper-server (через systemd: `sudo systemctl enable --now whisper-server.service`, см. [docs/voice-mvp.md](./voice-mvp.md)), чтобы после wake word запрос обрабатывался быстрее.

**Ложные срабатывания:** если wake word срабатывает от колонок (эхо ответа ассистента) или фона, подними порог и cooldown в `voice_mvp.env`: `WAKE_WORD_THRESHOLD=0.65` (или 0.7), `WAKE_WORD_COOLDOWN_SEC=10`. По умолчанию в скрипте уже 0.6 и 8 с.

При запуске скрипт может вывести предупреждения: *CUDAExecutionProvider* (CUDA только у NVIDIA — на AMD Radeon и Intel используется CPU) и сообщения ALSA/JACK при открытии микрофона. Они не мешают работе; если в конце видно «Listening…», всё в порядке.

---

## VOSK (русский без обучения)

У VOSK есть русские модели; отдельного «wake word» режима нет, но можно сделать детектор по ключевой фразе:

1. Установить [vosk-api](https://github.com/alphacep/vosk-api) и скачать маленькую модель, например `vosk-model-small-ru-0.4`.
2. Запускать распознавание с **ограниченной грамматикой** (только одна–две фразы: «Алиса», «Окей дом»). При распознавании одной из них — считать это wake word и запускать полный контур (запись → Whisper → Moltbot → TTS).

Минус: нужен свой небольшой скрипт (цикл: захват аудио → VOSK с грамматикой → при совпадении вызвать `voice_mvp.sh`). Примеры использования VOSK с грамматикой есть в документации и примерах репозитория.

---

## PocketSphinx (ключевые слова)

- Установка: `sudo apt install pocketsphinx` или через pip/virtualenv.
- Русская акустическая модель: отдельно скачать и указать в конфиге.
- Режим **keyphrase** (одна ключевая фраза) — типичный сценарий для wake word. Документация: [CMU Sphinx](https://cmusphinx.github.io/wiki/tutorialconcepts/).

Подходит, если готовы собирать зависимость и настраивать ключевую фразу вручную.

---

## Mycroft Precise

- Обучается на своих примерах (файлы WAV с произнесённой фразой и негативные примеры).
- Сохраняет модель в формате TensorFlow. Запуск: `precise-listener` или через Python.
- Ориентирован на английский, но обучать можно на любых записях (в т.ч. русских). Документация: [Mycroft Precise](https://github.com/MycroftAI/mycroft-precise).

---

## Кратко

- **Нужна своя русская фраза без программирования обучения** → обучить модель в openWakeWord (Colab) и использовать `scripts/wakeword_openwakeword.py`.
- **Нужен русский без обучения модели** → сделать простой детектор на VOSK с грамматикой из одной–двух фраз.
- **Нужна максимальная гибкость и свои данные** → openWakeWord или Mycroft Precise.

В этом репозитории настроен вариант с **openWakeWord** и скриптом, вызывающим `voice_mvp.sh` при срабатывании. Переменные окружения — в `scripts/voice_mvp.env.example` (секция Wake word).
