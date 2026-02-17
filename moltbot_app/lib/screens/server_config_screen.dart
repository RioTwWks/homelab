import 'package:flutter/material.dart';
import '../src/api/moltbot_api.dart';
import '../src/settings/settings_service.dart';
import 'home_screen.dart';

class ServerConfigScreen extends StatefulWidget {
  const ServerConfigScreen({super.key, this.fromSettings = false});

  /// true = открыто из настроек Home (после сохранения — pop). false = первый запуск (после сохранения — pushReplacement на Home).
  final bool fromSettings;

  @override
  State<ServerConfigScreen> createState() => _ServerConfigScreenState();
}

class _ServerConfigScreenState extends State<ServerConfigScreen> {
  final _formKey = GlobalKey<FormState>();
  final _hostController = TextEditingController(text: '');
  final _portController = TextEditingController(text: '18080');
  bool _useApiPrefix = false;
  bool _loading = false;
  bool _checking = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    Future(() async {
      final url = await SettingsService.getBaseUrl();
      final usePrefix = await SettingsService.getUseApiPrefix();
      if (!mounted) return;
      setState(() {
        _useApiPrefix = usePrefix;
        if (url != null && (url.contains(':18079') || url.endsWith('18079'))) {
          _useApiPrefix = true;
        }
        if (url != null) {
          final uri = Uri.tryParse(url);
          if (uri != null) {
            _hostController.text = uri.host;
            _portController.text = uri.port.toString();
          }
        }
      });
    });
  }

  @override
  void dispose() {
    _hostController.dispose();
    _portController.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    setState(() {
      _error = null;
      _loading = true;
    });
    final host = _hostController.text.trim();
    final port = _portController.text.trim();
    if (host.isEmpty) {
      setState(() {
        _error = 'Введите IP или домен сервера';
        _loading = false;
      });
      return;
    }
    final portNum = int.tryParse(port);
    if (portNum == null || portNum <= 0 || portNum > 65535) {
      setState(() {
        _error = 'Введите корректный порт (1–65535)';
        _loading = false;
      });
      return;
    }
    final baseUrl = 'http://$host:$portNum';
    try {
      await SettingsService.setBaseUrl(baseUrl);
      await SettingsService.setUseApiPrefix(_useApiPrefix);
      if (!mounted) return;
      if (widget.fromSettings) {
        Navigator.of(context).pop();
      } else {
        Navigator.of(context).pushReplacement(
          MaterialPageRoute(builder: (_) => const HomeScreen()),
        );
      }
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.toString();
        _loading = false;
      });
    }
    setState(() => _loading = false);
  }

  Future<void> _checkConnection() async {
    final host = _hostController.text.trim();
    final port = _portController.text.trim();
    if (host.isEmpty) {
      setState(() => _error = 'Введите хост');
      return;
    }
    final portNum = int.tryParse(port);
    if (portNum == null || portNum <= 0 || portNum > 65535) {
      setState(() => _error = 'Введите корректный порт');
      return;
    }
    setState(() {
      _error = null;
      _checking = true;
    });
    final baseUrl = 'http://$host:$portNum';
    final api = MoltbotApi(baseUrl, useApiPrefix: _useApiPrefix);
    final ok = await api.healthz();
    if (!mounted) return;
    setState(() => _checking = false);
    if (ok) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: const Text('Подключение успешно'),
          backgroundColor: Colors.green,
        ),
      );
    } else {
      setState(() => _error = 'Нет ответа от сервера. Порт 18079 — включи «Через веб-интерфейс». Порт 18080 — выключи.');
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Moltbot — настройка сервера'),
      ),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(24.0),
          child: Form(
            key: _formKey,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                const Text(
                  'Введите адрес сервера Moltbot (IP или домен и порт). Данные сохраняются локально.',
                  style: TextStyle(fontSize: 14),
                ),
                const SizedBox(height: 24),
                TextFormField(
                  controller: _hostController,
                  decoration: const InputDecoration(
                    labelText: 'IP или домен',
                    hintText: '192.168.1.5 или server.local',
                    border: OutlineInputBorder(),
                  ),
                  keyboardType: TextInputType.url,
                  textInputAction: TextInputAction.next,
                ),
                const SizedBox(height: 16),
                TextFormField(
                  controller: _portController,
                  decoration: const InputDecoration(
                    labelText: 'Порт',
                    hintText: '18080',
                    border: OutlineInputBorder(),
                  ),
                  keyboardType: TextInputType.number,
                  textInputAction: TextInputAction.done,
                  onFieldSubmitted: (_) => _save(),
                ),
                const SizedBox(height: 16),
                CheckboxListTile(
                  value: _useApiPrefix,
                  onChanged: (v) => setState(() => _useApiPrefix = v ?? false),
                  title: const Text('Через веб-интерфейс (порт 18079)'),
                  subtitle: const Text('Включи, если указываешь адрес веб-версии Moltbot'),
                  controlAffinity: ListTileControlAffinity.leading,
                  contentPadding: EdgeInsets.zero,
                ),
                if (_error != null) ...[
                  const SizedBox(height: 16),
                  Text(
                    _error!,
                    style: TextStyle(color: Theme.of(context).colorScheme.error),
                  ),
                ],
                const SizedBox(height: 16),
                OutlinedButton.icon(
                  onPressed: (_loading || _checking) ? null : _checkConnection,
                  icon: _checking
                      ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2))
                      : const Icon(Icons.wifi_tethering, size: 20),
                  label: const Text('Проверить подключение'),
                ),
                const SizedBox(height: 8),
                FilledButton(
                  onPressed: _loading ? null : _save,
                  child: _loading
                      ? const SizedBox(
                          height: 24,
                          width: 24,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Text('Сохранить и войти'),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
