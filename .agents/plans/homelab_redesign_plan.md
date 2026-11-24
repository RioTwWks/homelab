# 🗺️ План переделки homelab

## 🎯 Цели

1. **Полный переход на Hermes Agent** как основной агент и оркестратор.
2. **Перенос функционала `moltbot-api`** в Hermes (навыки + ToolRegistry).
3. **Голосовой стек Hermes**: встроенные STT (faster-whisper), wake word («Привет, Хермес» / «Hey Hermes»), TTS (Silero + встроенные провайдеры).
4. **Jev-модели (local, Jev-Style-2B-Decision-v3)** для PreToolUse и оценки качества ответов.
5. **NPU (FastFlowLM)** для STT и фоновых задач.
6. **OpenCode** для кодинга (рядом с homelab).
7. **RAG на Qdrant**: код, документация, заметки.
8. **Мониторинг Grafana + Prometheus** с отслеживанием энергопотребления NPU/iGPU.
9. **VPN и доступ извне**: AmneziaWG, Headscale, Cloudflare Tunnel (все варианты).
10. **Режимы AI / Gaming / Media** через веб-интерфейс.
11. **Human-in-the-loop** для опасных операций.
12. **Ежедневные бэкапы** в 3:00.

**ОС**: Ubuntu Desktop 26.04 LTS (сохраняем Steam/Proton).
**Железо**: Ryzen AI 9 HX 370, Radeon 890M, 32 ГБ RAM (позже 128 ГБ).

---

## 📋 Фаза 0: Аудит и бэкап

**Цель**: Зафиксировать текущее состояние, создать полный бэкап, подготовить почву.

**Задачи**:
1. Полный бэкап конфигов и Docker volumes:
   ```bash
   tar -czf ~/homelab-backup-$(date +%Y%m%d).tar.gz ~/homelab/{.env,docker-compose.yml,ansible/,scripts/,docs/}
   docker run --rm -v redis_data:/data -v $(pwd):/backup alpine tar -czf /backup/redis_data.tar.gz /data
   # аналогично для qdrant_data, mosquitto_data и др.
   ```
2. Проверка версий:
   ```bash
   docker compose version
   ollama --version
   uname -r  # ≥ 6.10
   ```
3. Установка NPU-драйверов (если ещё нет):
   ```bash
   wget https://download.amd.com/opendownload/RyzenAI/Driver/RAI_1.8_Linux_NPU_XRT.zip
   unzip RAI_1.8_Linux_NPU_XRT.zip && sudo ./install.sh
   ```
4. Установка FastFlowLM:
   ```bash
   pip install fastflowlm
   flm validate
   ```

**Acceptance Criteria**:
- Бэкап создан и проверен (`tar -tzf`).
- `flm validate` показывает доступность NPU.
- `uname -r` ≥ 6.10.

**Rollback**: Восстановить бэкап, удалить NPU-драйверы.

---

## 📋 Фаза 1: Установка Hermes и миграция

**Цель**: Установить Hermes, перенести функционал `moltbot-api`, настроить базовое подключение к Ollama.

**Задачи**:
1. Установка Hermes:
   ```bash
   curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | bash
   ```
2. Миграция из Moltbot (если есть legacy-директории):
   ```bash
   hermes claw migrate --dry-run
   hermes claw migrate --yes
   ```
   Если миграция не подходит — пропустить.
3. **Перенос инструментов `moltbot-api`**:
   - Создать навыки Hermes (Markdown) для:
     - `weather` (Open-Meteo/OpenWeather/Yandex)
     - `news` (RSS)
     - `media_control` (Kodi/Stremio)
     - `home_assistant` (REST + WebSocket)
     - `timers`
     - `web_search` (SearxNG)
   - Адаптировать под ToolRegistry Hermes.
4. Настройка подключения к Ollama:
   ```yaml
   # ~/.hermes/config.yaml
   model:
     provider: ollama
     base_url: http://localhost:11434
     model: qwen3:8b
     context_length: 65536  # ≥64K
   ```
5. Тестовый запуск:
   ```bash
   hermes run "Привет, что ты умеешь?"
   ```

**Acceptance Criteria**:
- Hermes отвечает.
- Навыки для погоды, новостей, медиа, HA работают.
- Модель имеет контекст ≥64K.

**Rollback**: Удалить `~/.hermes`, вернуться к `moltbot-api`.

---

## 📋 Фаза 2: Голосовой стек Hermes

**Цель**: Полностью перейти на встроенные голосовые функции Hermes.

**Задачи**:
1. Настройка wake word:
   - Русский: «Привет, Хермес»
   - Английский: «Hey Hermes»
2. Настройка STT:
   - Встроенный `faster-whisper` (русский + английский).
3. Настройка TTS:
   - Оставить Silero для тестов.
   - Добавить встроенные провайдеры Hermes (Edge TTS, NeuTTS).
4. Отключить старые сервисы:
   - `whisper-server.service`
   - `wakeword_openwakeword.py`
   - `silero_tts.py` (оставить как fallback)
5. Интеграция с Hermes:
   ```yaml
   voice:
     wake_word:
       ru: "привет хермес"
       en: "hey hermes"
     stt:
       provider: faster-whisper
       language: ru
     tts:
       providers: ["silero", "edge-tts"]
   ```

**Acceptance Criteria**:
- Wake word срабатывает на обе фразы.
- STT распознаёт русскую и английскую речь.
- TTS работает через Silero и Edge TTS.

**Rollback**: Включить старые systemd-юниты, вернуть `moltbot-api` для голоса.

---

## 📋 Фаза 3: Jev-модели (local)

**Цель**: Внедрить Jev-Style-2B-Decision-v3 для PreToolUse и оценки качества.

**Задачи**:
1. Установка Jev-Style:
   ```bash
   pip install jev-style
   ```
2. Настройка PreToolUse hook:
   ```yaml
   # ~/.hermes/hooks/pre-tool-use.yaml
   hook: jev-use hook gate
   model: Jev-Style-2B-Decision-v3
   threshold_allow: 0.85
   threshold_deny: 0.15
   ```
3. Настройка оценки качества ответов:
   ```yaml
   # ~/.hermes/hooks/post-response.yaml
   hook: jev-quality-eval
   model: Jev-Style-2B-Decision-v3
   score_threshold: 0.7  # ниже — перегенерация
   ```
4. Тестирование:
   ```bash
   hermes run "Выключи свет"  # PreToolUse проверяет
   hermes run "Расскажи о квантовой физике"  # оценка качества
   ```

**Acceptance Criteria**:
- Jev корректно классифицирует 90% тестовых запросов.
- Опасные операции блокируются или требуют подтверждения.
- Оценка качества логируется.

**Rollback**: Отключить хуки, вернуться к прямой маршрутизации.

---

## 📋 Фаза 4: NPU для STT (FastFlowLM)

**Цель**: Задействовать NPU для энергоэффективного STT.

**Задачи**:
1. Настройка FastFlowLM:
   ```bash
   flm run --model whisper-v3-turbo
   ```
2. Интеграция с Hermes:
   ```yaml
   npu:
     enabled: true
     provider: fastflowlm
     tasks: ["stt"]
   ```
3. Тестирование:
   - Проверить энергопотребление NPU (< 4 Вт).
   - Убедиться, что iGPU свободен для LLM.

**Acceptance Criteria**:
- `flm validate` показывает активное использование NPU.
- Потребление NPU < 4 Вт.

**Rollback**: Отключить NPU в конфиге, вернуть Whisper на CPU/iGPU.

---

## 📋 Фаза 5: Кодинг-ассистент OpenCode

**Цель**: Запустить OpenCode рядом с homelab.

**Задачи**:
1. Установка OpenCode:
   ```bash
   curl -fsSL https://opencode.ai/install | bash
   ```
2. Настройка провайдера Ollama:
   ```json
   // ~/.config/opencode/opencode.json
   {
     "provider": {
       "ollama": {
         "npm": "@ai-sdk/openai-compatible",
         "options": { "baseURL": "http://localhost:11434/v1" },
         "models": { "qwen3-coder:30b": { "name": "Qwen3-Coder 30B" } }
       }
     }
   }
   ```
3. Тестирование:
   ```bash
   opencode
   ```

**Acceptance Criteria**:
- OpenCode запускается и отвечает.
- Модель имеет контекст ≥64K.

**Rollback**: Удалить `~/.config/opencode`.

---

## 📋 Фаза 6: RAG на Qdrant

**Цель**: Загрузить код и документацию в Qdrant, подключить к Hermes.

**Задачи**:
1. Загрузка документов:
   ```python
   from qdrant_client import QdrantClient
   client = QdrantClient(url="http://localhost:6333")
   client.upload_collection(
       collection_name="docs",
       vectors=embeddings,
       payload=documents
   )
   ```
2. Подключение к Hermes:
   ```yaml
   rag:
     provider: qdrant
     url: http://localhost:6333
     collection: docs
   ```
3. Тестирование:
   - Задать вопрос по загруженным документам.

**Acceptance Criteria**:
- RAG возвращает релевантные документы.
- Hermes использует RAG в ответах.

**Rollback**: Отключить RAG, очистить коллекцию.

---

## 📋 Фаза 7: Мониторинг (Grafana + Prometheus)

**Цель**: Вынести мониторинг в отдельный профиль, добавить энергопотребление NPU/iGPU.

**Задачи**:
1. Вынести Grafana и Prometheus в профиль `monitoring` в `docker-compose.yml`.
2. Установить `all-smi`:
   ```bash
   pip install all-smi
   ```
3. Настроить экспортер для Prometheus:
   - `all-smi` предоставляет API для метрик энергопотребления.
4. Дашборд в Grafana:
   - CPU, RAM, диск.
   - Энергопотребление NPU/iGPU.
   - Latency LLM.

**Acceptance Criteria**:
- Grafana доступна, дашборды отображают метрики.
- Энергопотребление NPU/iGPU видно в реальном времени.

**Rollback**: Вернуть Grafana/Prometheus в профиль `gitlab`.

---

## 📋 Фаза 8: VPN и доступ извне

**Цель**: Настроить все варианты доступа: AmneziaWG, Headscale, Cloudflare Tunnel.

**Задачи**:
1. **AmneziaWG** на VPS в Германии/Нидерландах:
   - Установить AmneziaWG, настроить обфускацию.
2. **Headscale** на VPS в РФ:
   - Развернуть контроль-сервер, настроить клиенты.
3. **Cloudflare Tunnel** как резерв:
   - Установить `cloudflared`, создать туннель.
4. Настроить профили для семьи:
   - Отдельные ключи/доступы.

**Acceptance Criteria**:
- Доступ извне работает через любой из вариантов.
- Семья может подключаться.

**Rollback**: Отключить VPN, вернуться к локальному доступу.

---

## 📋 Фаза 9: Режимы AI / Gaming / Media

**Цель**: Реализовать переключение режимов через веб-интерфейс.

**Задачи**:
1. Добавить кнопку в `moltbot-ui` (или отдельный веб-интерфейс).
2. Скрипты переключения:
   - **AI mode**: LLM приоритет, iGPU для LLM.
   - **Gaming mode**: LLM останавливается, iGPU для Steam.
   - **Media mode**: баланс.
3. Управление через systemd или Docker API.

**Acceptance Criteria**:
- Переключение работает, ресурсы перераспределяются.
- Steam/Proton запускается в Gaming mode.

**Rollback**: Отключить скрипты, вернуть ручное управление.

---

## 📋 Фаза 10: Апгрейд до 128 ГБ и тяжёлые модели (опционально)

**Цель**: После апгрейда RAM внедрить более мощные модели.

**Задачи**:
1. Установить 128 ГБ DDR5, выделить 96 ГБ под iGPU в BIOS.
2. Запустить модели:
   - `Qwen3.6-35B-A3B` (~21 ГБ Q4)
   - `Llama 3.3 70B` (~40 ГБ Q4)
   - `Qwen3-Coder-Next 80B` (~51 ГБ Q4)
3. Тестирование скорости и качества.

**Acceptance Criteria**:
- Модели загружаются и работают.
- Скорость ≥2 токенов/с для 70B.

**Rollback**: Вернуться к 32 ГБ, использовать модели 30B.

---

## 📊 Приложение: Модели для тестирования (32 ГБ)

| Модель | Размер (Q4) | Контекст | Приоритет |
|--------|-------------|----------|-----------|
| Qwen3-8B | ~5 ГБ | 32K–128K | Голос |
| Qwen3.6-27B | ~17 ГБ | 256K | Качество |
| Qwen3-Coder-30B-A3B | ~19 ГБ | 256K+ | Кодинг |
| Gemma 3 27B | ~15 ГБ | 128K | Голос/Качество |
| GLM-4.7-Flash | ~19 ГБ | 64K+ | Tool calling |
| DeepSeek-R1-Distill-Qwen-32B | ~18 ГБ | 64K+ | Reasoning |

**После 128 ГБ**: Qwen3.6-35B-A3B, Llama 3.3 70B, Qwen3-Coder-Next 80B.

---

## 🔄 Общий Rollback

1. Остановить новые сервисы:
   ```bash
   hermes stop
   docker compose down
   ```
2. Восстановить бэкап:
   ```bash
   tar -xzf ~/homelab-backup-$(date +%Y%m%d).tar.gz -C ~/homelab/
   ```
3. Перезапустить старый стек:
   ```bash
   docker compose up -d
   ```

---

## ✅ Итог

План разбит на 10 фаз, каждая с acceptance criteria и rollback. Первые 9 фаз — на 32 ГБ, последняя — после апгрейда до 128 ГБ. Hermes становится центральным агентом, Jev-модели обеспечивают безопасность и качество, NPU разгружает iGPU, OpenCode даёт кодинг, Qdrant — RAG, Grafana — мониторинг. VPN-доступ реализован через AmneziaWG, Headscale и Cloudflare Tunnel.
