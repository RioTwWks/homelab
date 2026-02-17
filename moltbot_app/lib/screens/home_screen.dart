import 'dart:async';
import 'package:flutter/material.dart';
import '../src/api/moltbot_api.dart';
import '../src/models/chat_models.dart';
import '../src/models/dashboard_models.dart';
import '../src/settings/settings_service.dart';
import 'server_config_screen.dart';
import 'chat_view.dart';
import 'dashboard_view.dart';
import '../widgets/sidebar_content.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key, this.onThemeChanged});

  final VoidCallback? onThemeChanged;

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  String? _baseUrl;
  MoltbotApi? _api;
  List<ChatSession> _sessions = [];
  String? _activeSessionId;
  String _mode = 'auto';
  bool _showMeta = true;
  int _currentViewIndex = 0; // 0 = chat, 1 = dashboard (для узкого экрана)
  bool _rightPanelVisible =
      false; // правый сайдбар со статусами; по умолчанию скрыт
  bool _leftSidebarVisible =
      false; // на узком экране левый сайдбар; по умолчанию скрыт
  bool _connectionOnline = false;
  Map<String, dynamic> _systemStatus = {};
  Map<String, String> _serviceStatus = {};
  String _lastUpdated = '—';
  bool _typing = false;
  Timer? _probeTimer;

  /// Статусы для карточек: probeServices + redis/ollama из getSystemStatus (API уже их проверяет).
  Map<String, String> get _mergedServiceStatus {
    final m = Map<String, String>.from(_serviceStatus);
    final sys = _systemStatus['services'];
    if (sys is Map<String, dynamic>) {
      for (final k in ['redis', 'ollama']) {
        final v = sys[k];
        if (v != null) m[k] = v.toString();
      }
    }
    return m;
  }

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _probeTimer?.cancel();
    super.dispose();
  }

  Future<void> _load() async {
    final url = await SettingsService.getBaseUrl();
    if (url == null || url.isEmpty) return;
    var useApiPrefix = await SettingsService.getUseApiPrefix();
    if (url.contains(':18079') || url.endsWith('18079')) useApiPrefix = true;
    setState(() {
      _baseUrl = url;
      _api = MoltbotApi(url, useApiPrefix: useApiPrefix);
    });
    await _loadSessions();
    _probeConnection();
    _loadDashboard();
    _probeTimer?.cancel();
    _probeTimer = Timer.periodic(
      const Duration(seconds: 15),
      (_) => _probeConnection(),
    );
  }

  Future<void> _loadSessions() async {
    final list = await SettingsService.getSessionsJson();
    final id = await SettingsService.getActiveSessionId();
    final sessions = list.map((j) => ChatSession.fromJson(j)).toList();
    String? activeId = id;
    if (sessions.isEmpty) {
      final s = ChatSession(id: _uid(), name: 'flutter');
      sessions.add(s);
      activeId = s.id;
      await _saveSessions(sessions, activeId);
    } else if (activeId == null || !sessions.any((s) => s.id == activeId)) {
      activeId = sessions.first.id;
      await SettingsService.setActiveSessionId(activeId);
    }
    if (mounted) {
      setState(() {
        _sessions = sessions;
        _activeSessionId = activeId;
      });
    }
  }

  String _uid() =>
      '${DateTime.now().millisecondsSinceEpoch.toRadixString(36)}${(DateTime.now().millisecondsSinceEpoch % 1000).toRadixString(36)}';

  Future<void> _saveSessions(
    List<ChatSession> sessions, [
    String? activeId,
  ]) async {
    await SettingsService.saveSessionsJson(
      sessions.map((s) => s.toJson()).toList(),
    );
    if (activeId != null) await SettingsService.setActiveSessionId(activeId);
  }

  ChatSession? get _activeSession => _sessions.cast<ChatSession?>().firstWhere(
    (s) => s?.id == _activeSessionId,
    orElse: () => null,
  );

  Future<void> _probeConnection() async {
    if (_api == null) return;
    final ok = await _api!.healthz();
    if (mounted) setState(() => _connectionOnline = ok);
  }

  Future<void> _loadDashboard() async {
    if (_api == null) return;
    try {
      final status = await _api!.getSystemStatus();
      final probeItems = kDashboardServices
          .where((s) => s.probeUrl != null)
          .map((s) => {'name': s.id, 'url': s.probeUrl ?? ''})
          .toList();
      Map<String, String> probeResult = {};
      if (probeItems.isNotEmpty) {
        final res = await _api!.probeServices(probeItems);
        probeResult = Map<String, String>.from(res['services'] as Map? ?? {});
      }
      if (mounted) {
        setState(() {
          _systemStatus = status;
          _serviceStatus = probeResult;
          _lastUpdated =
              'Обновлено ${DateTime.now().toString().substring(11, 19)}';
        });
      }
    } catch (_) {}
  }

  Future<void> _sendMessage(String text) async {
    final session = _activeSession;
    if (session == null || _api == null) return;
    final ts = DateTime.now().millisecondsSinceEpoch;
    session.messages.add(ChatMessage(role: 'user', text: text, ts: ts));
    await _saveSessions(_sessions);
    setState(() => _typing = true);

    final assistantTs = DateTime.now().millisecondsSinceEpoch;
    session.messages.add(
      ChatMessage(role: 'assistant', text: '', meta: null, ts: assistantTs),
    );

    try {
      String accumulated = '';
      Map<String, dynamic>? finalMeta;
      await for (final event in _api!.chatStream(
        text: text,
        sessionId: session.name,
        mode: _mode,
      )) {
        if (!mounted) return;
        if (event.containsKey('chunk')) {
          accumulated += event['chunk'] as String? ?? '';
          session.messages[session.messages.length - 1] = ChatMessage(
            role: 'assistant',
            text: accumulated,
            meta: null,
            ts: assistantTs,
          );
          setState(() {});
        } else if (event['done'] == true) {
          finalMeta = event;
          final reply = event['reply_text'] as String? ?? accumulated;
          session.messages[session.messages.length - 1] = ChatMessage(
            role: 'assistant',
            text: reply.isNotEmpty ? reply : '(пустой ответ)',
            meta: finalMeta,
            ts: assistantTs,
          );
          if (session.messages.length > 200) {
            session.messages.removeRange(0, session.messages.length - 200);
          }
          await _saveSessions(_sessions);
          break;
        }
      }
    } catch (e) {
      String err = e.toString();
      if (err.startsWith('Exception: ')) err = err.substring(11);
      if (err.contains('404') && _api != null) {
        try {
          final data = await _api!.chat(
            text: text,
            sessionId: session.name,
            mode: _mode,
          );
          final reply = data['reply_text'] as String? ?? '(пустой ответ)';
          session.messages[session.messages.length - 1] = ChatMessage(
            role: 'assistant',
            text: reply,
            meta: data,
            ts: assistantTs,
          );
          if (session.messages.length > 200) {
            session.messages.removeRange(0, session.messages.length - 200);
          }
          await _saveSessions(_sessions);
          if (mounted) setState(() {});
        } catch (_) {
          session.messages[session.messages.length - 1] = ChatMessage(
            role: 'assistant',
            text: 'Ошибка: $err',
            meta: {'intent': 'error'},
            ts: assistantTs,
          );
          await _saveSessions(_sessions);
          if (mounted) setState(() {});
        }
      } else {
        session.messages[session.messages.length - 1] = ChatMessage(
          role: 'assistant',
          text: 'Ошибка: $err',
          meta: {'intent': 'error'},
          ts: assistantTs,
        );
        await _saveSessions(_sessions);
        if (mounted) {
          final isHtmlError =
              err.contains('HTML вместо JSON') || err.contains('18079');
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text(err),
              action: isHtmlError
                  ? SnackBarAction(
                      label: 'Настройки',
                      onPressed: () async {
                        await Navigator.of(context).push(
                          MaterialPageRoute(
                            builder: (_) =>
                                const ServerConfigScreen(fromSettings: true),
                          ),
                        );
                        _load();
                      },
                    )
                  : null,
            ),
          );
        }
      }
    }
    if (mounted) setState(() => _typing = false);
  }

  void _switchSession(String id) {
    setState(() => _activeSessionId = id);
    SettingsService.setActiveSessionId(id);
  }

  void _newSession() async {
    final nameController = TextEditingController(
      text: 'сессия-${_sessions.length + 1}',
    );
    final name = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Новая сессия'),
        content: TextField(
          autofocus: true,
          decoration: const InputDecoration(labelText: 'Имя'),
          controller: nameController,
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Отмена'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(
              ctx,
              nameController.text.trim().isEmpty
                  ? 'сессия-${_sessions.length + 1}'
                  : nameController.text.trim(),
            ),
            child: const Text('Создать'),
          ),
        ],
      ),
    );
    if (name == null || name.isEmpty) return;
    final s = ChatSession(id: _uid(), name: name);
    _sessions.add(s);
    await _saveSessions(_sessions, s.id);
    setState(() => _activeSessionId = s.id);
    if (mounted) {
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text('Сессия «$name» создана')));
    }
  }

  void _deleteSession(String id) {
    _sessions.removeWhere((s) => s.id == id);
    if (_activeSessionId == id) {
      _activeSessionId = _sessions.isNotEmpty ? _sessions.first.id : null;
      if (_sessions.isEmpty) {
        final s = ChatSession(id: _uid(), name: 'flutter');
        _sessions.add(s);
        _activeSessionId = s.id;
      }
    }
    _saveSessions(_sessions, _activeSessionId);
    setState(() {});
  }

  void _clearChat() {
    final s = _activeSession;
    if (s != null) {
      s.messages.clear();
      _saveSessions(_sessions);
      setState(() {});
    }
  }

  void _clearAll() async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Удалить историю?'),
        content: const Text('Удалить историю текущей сессии?'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Отмена'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Удалить'),
          ),
        ],
      ),
    );
    if (ok == true) {
      _clearChat();
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(const SnackBar(content: Text('История очищена')));
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_baseUrl == null) {
      return const Scaffold(
        body: Center(
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              CircularProgressIndicator(),
              SizedBox(height: 16),
              Text('Загрузка…'),
            ],
          ),
        ),
      );
    }

    final theme = Theme.of(context);
    final isNarrow = MediaQuery.sizeOf(context).width < 900;
    final leftSidebarWidth = isNarrow ? 220.0 : 260.0;
    const double rightPanelWidth = 320;

    final leftSidebar = Material(
      elevation: 0,
      color: theme.colorScheme.surfaceContainerLow.withValues(alpha: 0.5),
      child: SizedBox(
        width: leftSidebarWidth,
        child: Container(
          decoration: BoxDecoration(
            border: Border(
              right: BorderSide(
                color: theme.colorScheme.outlineVariant.withValues(alpha: 0.5),
              ),
            ),
          ),
          child: SidebarContent(
            sessions: _sessions,
            activeSessionId: _activeSessionId,
            mode: _mode,
            showMeta: _showMeta,
            onSessionTap: _switchSession,
            onNewSession: _newSession,
            onDeleteSession: _deleteSession,
            onModeChanged: (v) => setState(() => _mode = v),
            onShowMetaChanged: (v) => setState(() => _showMeta = v),
            onChipTap: (text) {
              _sendMessage(text);
              setState(() => _leftSidebarVisible = false);
            },
            onClearChat: _clearChat,
            onClearAll: _clearAll,
          ),
        ),
      ),
    );

    final rightPanel = !isNarrow && _rightPanelVisible
        ? Material(
            elevation: 0,
            color: theme.colorScheme.surfaceContainerLow.withValues(alpha: 0.5),
            child: Container(
              width: rightPanelWidth,
              decoration: BoxDecoration(
                border: Border(
                  left: BorderSide(
                    color: theme.colorScheme.outlineVariant.withValues(
                      alpha: 0.5,
                    ),
                  ),
                ),
              ),
              child: DashboardView(
                serviceStatus: _mergedServiceStatus,
                systemStatus: _systemStatus,
                onRefresh: () async {
                  _probeConnection();
                  _loadDashboard();
                },
                lastUpdated: _lastUpdated,
              ),
            ),
          )
        : null;

    final centerContent = isNarrow && _currentViewIndex == 1
        ? DashboardView(
            serviceStatus: _mergedServiceStatus,
            systemStatus: _systemStatus,
            onRefresh: () async {
              _probeConnection();
              _loadDashboard();
            },
            lastUpdated: _lastUpdated,
          )
        : ChatView(
            messages: _activeSession?.messages ?? [],
            onSend: _sendMessage,
            showMeta: _showMeta,
            typing: _typing,
          );

    return Scaffold(
      appBar: AppBar(
        title: Row(
          children: [
            Container(
              width: 30,
              height: 30,
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  colors: [
                    theme.colorScheme.primary,
                    theme.colorScheme.secondary,
                  ],
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                ),
                borderRadius: BorderRadius.circular(8),
              ),
              alignment: Alignment.center,
              child: Text(
                'MB',
                style: TextStyle(
                  fontSize: 11,
                  fontWeight: FontWeight.w800,
                  color: theme.colorScheme.onPrimary,
                ),
              ),
            ),
            const SizedBox(width: 8),
            const Text('Moltbot'),
            const SizedBox(width: 6),
            Container(
              width: 8,
              height: 8,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: _connectionOnline ? Colors.green : Colors.red,
                boxShadow: [
                  BoxShadow(
                    color: (_connectionOnline ? Colors.green : Colors.red)
                        .withValues(alpha: 0.6),
                    blurRadius: 6,
                  ),
                ],
              ),
            ),
          ],
        ),
        actions: [
          if (isNarrow) ...[
            IconButton(
              icon: Icon(_leftSidebarVisible ? Icons.menu_open : Icons.menu),
              tooltip: _leftSidebarVisible ? 'Скрыть меню' : 'Показать меню',
              onPressed: () =>
                  setState(() => _leftSidebarVisible = !_leftSidebarVisible),
            ),
            SegmentedButton<int>(
              segments: const [
                ButtonSegment(
                  value: 0,
                  label: Text('Чат'),
                  icon: Icon(Icons.chat_bubble_outline, size: 18),
                ),
                ButtonSegment(
                  value: 1,
                  label: Text('Дашборд'),
                  icon: Icon(Icons.dashboard_outlined, size: 18),
                ),
              ],
              selected: {_currentViewIndex},
              onSelectionChanged: (s) =>
                  setState(() => _currentViewIndex = s.first),
            ),
          ],
          if (!isNarrow)
            IconButton(
              icon: Icon(
                _rightPanelVisible
                    ? Icons.view_sidebar
                    : Icons.view_sidebar_outlined,
              ),
              tooltip: _rightPanelVisible
                  ? 'Скрыть панель статусов'
                  : 'Показать панель статусов',
              onPressed: () =>
                  setState(() => _rightPanelVisible = !_rightPanelVisible),
            ),
          const SizedBox(width: 8),
          IconButton(
            icon: Icon(
              theme.brightness == Brightness.dark
                  ? Icons.light_mode
                  : Icons.dark_mode,
            ),
            onPressed: () async {
              final next = theme.brightness == Brightness.dark
                  ? 'light'
                  : 'dark';
              await SettingsService.setTheme(next);
              widget.onThemeChanged?.call();
            },
          ),
          IconButton(
            icon: const Icon(Icons.settings),
            tooltip: 'Изменить сервер',
            onPressed: () async {
              await Navigator.of(context).push(
                MaterialPageRoute(
                  builder: (_) => const ServerConfigScreen(fromSettings: true),
                ),
              );
              _load();
            },
          ),
        ],
      ),
      body: Row(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (!isNarrow || _leftSidebarVisible) leftSidebar,
          Expanded(child: centerContent),
          ?rightPanel,
        ],
      ),
    );
  }
}

/// Call from main: if baseUrl is null, show [ServerConfigScreen], else [HomeScreen].
Future<Widget> getInitialScreen({VoidCallback? onThemeChanged}) async {
  final baseUrl = await SettingsService.getBaseUrl();
  if (baseUrl == null || baseUrl.isEmpty) {
    return const ServerConfigScreen();
  }
  return HomeScreen(onThemeChanged: onThemeChanged);
}
