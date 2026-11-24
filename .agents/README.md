# `.agents/` — конфигурация для AI-агентов

Эта папка помогает Cloud Agents быстрее понимать репозиторий.

## Содержимое

| Путь | Назначение |
|------|------------|
| `rules/*.mdc` | Project rules: автоподключение по globs или always-apply |
| `environment.json` | Bootstrap Cloud Agent (install, Dockerfile) |
| `environment/Dockerfile` | Базовый образ для Cloud Agent |
| `plans/` | Архитектурные планы (контекст, не источник правды) |

## Связанные файлы вне `.agents/`

- `AGENTS.md` — главная инструкция для агентов (карта репо, команды, pitfalls)
- `moltbot_api/AGENTS.md`, `media_api/AGENTS.md`, `moltbot_app/AGENTS.md` — локальные заметки по пакетам

## Как добавлять правила

1. Создайте `.agents/rules/<имя>.mdc` с frontmatter (`description`, `globs`, `alwaysApply`).
2. Держите `alwaysApply: true` только для коротких repo-wide правил.
3. Детали по стеку — в glob-scoped rules (`python-api.mdc`, `flutter-app.mdc`, …).
