# Moltbot App

Кроссплатформенное приложение (Flutter) для доступа к Moltbot API: чат, команды, дашборд сервисов. Один код — Android, iOS, Windows, macOS, Linux.

## Первый запуск

При первом запуске откроется экран **настройки сервера**: введи IP (или домен) и порт сервера Moltbot (по умолчанию порт 18090). Адрес сохраняется локально и используется для всех запросов к API.

Изменить сервер потом можно через иконку настроек на главном экране.

## Запуск и сборка

```bash
# Зависимости
flutter pub get

# Запуск (выбери устройство/эмулятор)
flutter run

# Сборка под платформу
flutter build apk          # Android
flutter build ios          # iOS (на macOS)
flutter build windows      # Windows
flutter build macos        # macOS
flutter build linux        # Linux
```

## Структура

- `lib/screens/server_config_screen.dart` — экран ввода IP:порт, сохранение в SharedPreferences.
- `lib/screens/home_screen.dart` — главный экран (заглушка; дальше — чат и дашборд).
- `lib/src/settings/settings_service.dart` — чтение/запись базового URL сервера.
- `lib/src/api/moltbot_api.dart` — клиент API (healthz, chat); baseUrl задаётся из настроек.

Дальше: экран чата с вызовом `MoltbotApi(baseUrl).chat(text: ...)`, экран дашборда (вызов `/api/v1/system/services` и т.д.).
