# OpenCode — кодинг-ассистент рядом с homelab

[OpenCode](https://opencode.ai/docs) — open-source агент для терминала (TUI), который читает репозиторий, правит файлы и запускает команды. В стеке homelab он дополняет **Hermes / moltbot-api**: голос и бытовые сценарии остаются в ассистенте, а разработка и рефакторинг — в OpenCode с локальной моделью через **Ollama на хосте** (порт `11434`, как в [architecture.md](./architecture.md)).

Фаза плана: [homelab redesign — фаза 5](../.cursor/plans/homelab_redesign_plan.md).

---

## Требования

| Компонент | Значение |
|-----------|----------|
| ОС | Ubuntu Desktop 26.04 LTS (как у homelab) |
| Ollama | На **хосте**, не в Docker |
| Модель | `qwen3-coder:30b` (или свой тег MoE, см. таблицу моделей в плане) |
| Контекст | **≥ 64 000 токенов** — [требование OpenCode + Ollama](https://docs.ollama.com/integrations/opencode) |
| RAM | ~19 ГБ под Q4 для 30B; на 32 ГБ оставьте запас под ОС и iGPU |

---

## Установка OpenCode

```bash
curl -fsSL https://opencode.ai/install | bash
```

Альтернатива: `npm install -g opencode-ai`.

Проверка:

```bash
opencode --version
```

Быстрый старт с подсказкой модели от Ollama (не перезаписывает ваш `opencode.json`):

```bash
ollama launch opencode
```

Только сгенерировать конфиг без TUI:

```bash
ollama launch opencode --config
```

---

## Где лежит конфиг

| Расположение | Назначение |
|--------------|------------|
| **`~/.config/opencode/opencode.json`** | Глобальные настройки пользователя (провайдеры, модель по умолчанию) |
| `~/.config/opencode/tui.json` | Только настройки TUI |
| `opencode.json` в корне git-репозитория | Проектные переопределения (можно коммитить) |
| `OPENCODE_CONFIG` | Путь к произвольному файлу конфигурации |
| Linux (managed) | `/etc/opencode/opencode.json` — политики организации |

Файлы **мержатся** по приоритету: проект и env-переменные перекрывают глобальный конфиг только по конфликтующим ключам. Подробнее: [Config | OpenCode](https://opencode.ai/docs/config).

**Пример из репозитория** (скопировать на хост):

```bash
mkdir -p ~/.config/opencode
cp config/opencode/opencode.json ~/.config/opencode/opencode.json
```

Исходник в git: [`config/opencode/opencode.json`](../config/opencode/opencode.json).

Проверка JSON в репозитории (без установки OpenCode):

```bash
jq empty config/opencode/opencode.json
make check   # включает remote_access.yml и opencode.json — см. docs/remote-access.md
bash scripts/verify-runbook-remote-access-opencode.sh
```

---

## Ollama: модель и контекст ≥64K

OpenCode ходит в Ollama через **OpenAI-compatible** endpoint (`http://localhost:11434/v1`). Параметр `num_ctx` в `opencode.json` **не задаёт** размер окна на этом пути — контекст нужно зафиксировать **в Ollama**.

### 1. Базовая модель

```bash
ollama pull qwen3-coder:30b
```

Имя тега проверьте: `ollama list`. Для MoE-варианта из плана может быть, например, `qwen3-coder:30b-a3b` — подставьте его в Modelfile вместо `qwen3-coder:30b`.

### 2. Вариант с `num_ctx 65536`

В репозитории лежит готовый Modelfile:

[`config/opencode/Modelfile.qwen3-coder-30b-64k`](../config/opencode/Modelfile.qwen3-coder-30b-64k)

```bash
cd ~/homelab   # или путь к клону репозитория
ollama create qwen3-coder-30b-64k -f config/opencode/Modelfile.qwen3-coder-30b-64k
```

Проверка контекста:

```bash
ollama show qwen3-coder-30b-64k --modelfile | grep -i num_ctx
# ожидается: PARAMETER num_ctx 65536
```

У модели в таблице плана заявлен контекст **256K+**; для OpenCode достаточно **64K**. На 32 ГБ RAM не поднимайте `num_ctx` выше необходимого — растёт KV-cache и нагрузка на iGPU.

### 3. Пример `opencode.json` (Ollama + qwen3-coder)

Содержимое совпадает с [`config/opencode/opencode.json`](../config/opencode/opencode.json):

```json
{
  "$schema": "https://opencode.ai/config.json",
  "model": "ollama/qwen3-coder-30b-64k",
  "provider": {
    "ollama": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "Ollama (homelab)",
      "options": {
        "baseURL": "http://localhost:11434/v1"
      },
      "models": {
        "qwen3-coder-30b-64k": {
          "name": "Qwen3-Coder 30B (64k)"
        }
      }
    }
  }
}
```

Ключ `model` задаёт модель по умолчанию в формате `ollama/<имя в Ollama>`. Имя в `models` должно совпадать с тегом после `ollama create`.

---

## Первый запуск и проверка

1. Убедитесь, что Ollama слушает порт 11434: `curl -s http://localhost:11434/api/tags | jq`.
2. Скопируйте конфиг в `~/.config/opencode/` (см. выше).
3. Перейдите в каталог проекта и запустите TUI:

```bash
cd ~/homelab
opencode
```

4. В сессии: `/init` — создать или обновить `AGENTS.md` в корне проекта (имеет смысл закоммитить).
5. Неблокирующая проверка из shell:

```bash
opencode run "Кратко: какой файл docker-compose в этом репозитории?"
```

6. Разрешённая конфигурация:

```bash
opencode debug config
```

В выводе должны быть провайдер `ollama`, `baseURL` на `11434/v1` и модель `qwen3-coder-30b-64k`.

### Acceptance (фаза 5)

- `opencode` стартует без ошибки провайдера.
- Ответ на простой вопрос по репозиторию приходит от локальной модели.
- `ollama show qwen3-coder-30b-64k` содержит `num_ctx 65536` (или больше).

---

## Соседство с homelab

- **Ollama один на хосте** — и moltbot-api (`host.docker.internal:11434`), и OpenCode (`localhost:11434`) используют один сервер; следите за VRAM при параллельной нагрузке.
- **Режим AI / Gaming** (фаза 9 плана): в gaming mode LLM часто останавливают — перед сессией OpenCode проверьте, что нужная модель загружена: `ollama ps`.
- Документация по установке стека: [install.md](./install.md). Резервные копии: [backup.md](./backup.md) — при бэкапе homelab имеет смысл архивировать и `~/.config/opencode/`.

---

## Rollback

```bash
rm -rf ~/.config/opencode
# опционально: ollama rm qwen3-coder-30b-64k
curl -fsSL https://opencode.ai/install | bash -s -- uninstall   # или: opencode uninstall
```

---

## Ссылки

- [OpenCode — Intro](https://opencode.ai/docs)
- [OpenCode — Config](https://opencode.ai/docs/config)
- [Ollama — OpenCode integration](https://docs.ollama.com/integrations/opencode)
