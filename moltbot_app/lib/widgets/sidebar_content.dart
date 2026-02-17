import 'package:flutter/material.dart';
import '../src/models/chat_models.dart';

/// Quick command chips (same as web: Команды)
final List<Map<String, String>> kQuickCommands = [
  {'text': 'Какая погода сейчас?', 'label': 'погода'},
  {'text': 'Какие последние новости? 5 пунктов.', 'label': 'новости'},
  {'text': 'поставь таймер на 5 минут', 'label': 'таймер'},
  {'text': 'ютуб', 'label': 'ютуб'},
  {'text': 'пауза', 'label': 'пауза'},
  {'text': 'включи коди', 'label': 'kodi'},
  {'text': 'открой торренты', 'label': 'торренты'},
];

/// HA / smart home chips
final List<Map<String, String>> kHaChips = [
  {'text': 'включи свет в гостиной', 'label': '💡 гостиная'},
  {'text': 'выключи свет', 'label': 'выкл свет'},
  {'text': 'включи свет в кухне', 'label': '💡 кухня'},
  {'text': 'температура 22', 'label': '🌡 22°'},
  {'text': 'режим кино', 'label': '🎬 кино'},
  {'text': 'режим сон', 'label': '🌙 сон'},
];

class SidebarContent extends StatelessWidget {
  const SidebarContent({
    super.key,
    required this.sessions,
    required this.activeSessionId,
    required this.mode,
    required this.showMeta,
    required this.onSessionTap,
    required this.onNewSession,
    required this.onDeleteSession,
    required this.onModeChanged,
    required this.onShowMetaChanged,
    required this.onChipTap,
    required this.onClearChat,
    required this.onClearAll,
  });

  final List<ChatSession> sessions;
  final String? activeSessionId;
  final String mode;
  final bool showMeta;
  final void Function(String id) onSessionTap;
  final VoidCallback onNewSession;
  final void Function(String id) onDeleteSession;
  final void Function(String value) onModeChanged;
  final void Function(bool value) onShowMetaChanged;
  final void Function(String text) onChipTap;
  final VoidCallback onClearChat;
  final VoidCallback onClearAll;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return ListView(
      padding: const EdgeInsets.all(8),
      children: [
        _Card(
          icon: '💬',
          title: 'Сессии',
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              ...sessions.map((s) {
                final isActive = s.id == activeSessionId;
                return ListTile(
                  dense: true,
                  title: Text(
                    s.name,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontWeight: isActive ? FontWeight.w600 : null,
                    ),
                  ),
                  trailing: IconButton(
                    icon: const Icon(Icons.close, size: 18),
                    onPressed: () => onDeleteSession(s.id),
                  ),
                  selected: isActive,
                  onTap: () => onSessionTap(s.id),
                );
              }),
              const SizedBox(height: 4),
              OutlinedButton.icon(
                onPressed: onNewSession,
                icon: const Icon(Icons.add, size: 18),
                label: const Text('Новая сессия'),
                style: OutlinedButton.styleFrom(
                  padding: const EdgeInsets.symmetric(vertical: 8),
                ),
              ),
              const SizedBox(height: 8),
              DropdownButtonFormField<String>(
                initialValue: mode,
                decoration: const InputDecoration(
                  labelText: 'mode',
                  isDense: true,
                  contentPadding: EdgeInsets.symmetric(
                    horizontal: 12,
                    vertical: 8,
                  ),
                ),
                items: const [
                  DropdownMenuItem(value: 'auto', child: Text('auto')),
                  DropdownMenuItem(value: 'fast', child: Text('fast')),
                  DropdownMenuItem(value: 'chat', child: Text('chat')),
                ],
                onChanged: (v) {
                  if (v != null) onModeChanged(v);
                },
              ),
            ],
          ),
        ),
        _Card(
          icon: '⚡',
          title: 'Команды',
          child: Wrap(
            spacing: 4,
            runSpacing: 4,
            children: kQuickCommands.map((c) {
              return ActionChip(
                label: Text(c['label']!, style: const TextStyle(fontSize: 11)),
                onPressed: () => onChipTap(c['text']!),
              );
            }).toList(),
          ),
        ),
        _Card(
          icon: '🏠',
          title: 'Умный дом',
          child: Wrap(
            spacing: 4,
            runSpacing: 4,
            children: kHaChips.map((c) {
              return ActionChip(
                label: Text(c['label']!, style: const TextStyle(fontSize: 11)),
                onPressed: () => onChipTap(c['text']!),
              );
            }).toList(),
          ),
        ),
        _Card(
          icon: '🔧',
          title: 'Отладка',
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              CheckboxListTile(
                value: showMeta,
                onChanged: (v) => onShowMetaChanged(v ?? false),
                title: Text(
                  'intent / timings',
                  style: theme.textTheme.bodySmall,
                ),
                controlAffinity: ListTileControlAffinity.leading,
                dense: true,
                contentPadding: EdgeInsets.zero,
              ),
              const SizedBox(height: 4),
              Row(
                children: [
                  Expanded(
                    child: OutlinedButton(
                      onPressed: onClearChat,
                      style: OutlinedButton.styleFrom(
                        padding: const EdgeInsets.symmetric(vertical: 6),
                        visualDensity: VisualDensity.compact,
                      ),
                      child: const Text('Очистить'),
                    ),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: OutlinedButton(
                      onPressed: onClearAll,
                      style: OutlinedButton.styleFrom(
                        padding: const EdgeInsets.symmetric(vertical: 6),
                        visualDensity: VisualDensity.compact,
                      ),
                      child: const Text('Удалить всё'),
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class _Card extends StatelessWidget {
  const _Card({required this.icon, required this.title, required this.child});

  final String icon;
  final String title;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: Padding(
        padding: const EdgeInsets.all(10),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Text(icon, style: const TextStyle(fontSize: 14)),
                const SizedBox(width: 6),
                Text(
                  title,
                  style: theme.textTheme.labelLarge?.copyWith(
                    fontWeight: FontWeight.bold,
                    color: theme.colorScheme.onSurfaceVariant,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            child,
          ],
        ),
      ),
    );
  }
}
