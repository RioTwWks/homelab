# moltbot_app

Кроссплатформенный Flutter-клиент для moltbot-api.

## Команды

```bash
cd moltbot_app
flutter pub get
flutter analyze
flutter test
flutter run -d linux   # или android, ios, windows, macos, web
```

## Структура

- `lib/screens/` — home, chat, dashboard, server_config
- `lib/src/api/moltbot_api.dart` — HTTP: healthz, chat, stream, system status
- `lib/src/settings/settings_service.dart` — URL сервера, тема (shared_preferences)
- `lib/widgets/` — chat UI components

## Подключение к серверу

При первом запуске — экран настройки IP/порта. Два режима:

1. **Прямой:** `http://192.168.x.x:18080`
2. **Через веб-UI:** `http://192.168.x.x:18079` + `useApiPrefix` (прокси `/api/`)

## Сборка

```bash
flutter build apk
flutter build linux
flutter build windows
```

## При изменении API

Обновить `moltbot_api.dart` и модели в `lib/src/models/`. Синхронизировать с `moltbot_ui/app.js` при необходимости.
