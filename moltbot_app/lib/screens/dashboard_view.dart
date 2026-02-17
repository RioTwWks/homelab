import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';
import '../src/models/dashboard_models.dart';

class DashboardView extends StatelessWidget {
  const DashboardView({
    super.key,
    required this.serviceStatus,
    required this.systemStatus,
    required this.onRefresh,
    required this.lastUpdated,
  });

  /// Result of probeServices: service id -> "ok" | "error:..." | "skip"
  final Map<String, String> serviceStatus;
  /// Result of getSystemStatus: services (name -> status), models (fast, chat)
  final Map<String, dynamic> systemStatus;
  final VoidCallback onRefresh;
  final String lastUpdated;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final services = systemStatus['services'] as Map<String, dynamic>? ?? {};
    final models = systemStatus['models'] as Map<String, dynamic>? ?? {};

    return ListView(
      padding: const EdgeInsets.all(12),
      children: [
        // Dashboard grid by category
        ...kDashboardCategories.map((cat) {
          final items = kDashboardServices.where((s) => s.cat == cat.id).toList();
          if (items.isEmpty) return const SizedBox.shrink();
          return _CategorySection(
            category: cat,
            items: items,
            statusMap: serviceStatus,
            onOpen: _openUrl,
          );
        }),
        const SizedBox(height: 12),
        // API services status
        Card(
          child: Padding(
            padding: const EdgeInsets.all(12),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    const Text('📡', style: TextStyle(fontSize: 16)),
                    const SizedBox(width: 8),
                    Text(
                      'Сервисы API',
                      style: theme.textTheme.titleSmall?.copyWith(
                        fontWeight: FontWeight.bold,
                        color: theme.colorScheme.onSurfaceVariant,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 10),
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: (services as Map).entries.map((e) {
                    final ok = e.value == 'ok';
                    return Container(
                      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
                      decoration: BoxDecoration(
                        color: theme.colorScheme.surfaceContainerLow,
                        borderRadius: BorderRadius.circular(10),
                      ),
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Container(
                            width: 8,
                            height: 8,
                            decoration: BoxDecoration(
                              shape: BoxShape.circle,
                              color: ok ? Colors.green : Colors.red,
                            ),
                          ),
                          const SizedBox(width: 6),
                          Text('${e.key}: ${e.value}', style: theme.textTheme.bodySmall),
                        ],
                      ),
                    );
                  }).toList(),
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 8),
        // LLM models
        Card(
          child: Padding(
            padding: const EdgeInsets.all(12),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    const Text('🧠', style: TextStyle(fontSize: 16)),
                    const SizedBox(width: 8),
                    Text(
                      'Модели LLM',
                      style: theme.textTheme.titleSmall?.copyWith(
                        fontWeight: FontWeight.bold,
                        color: theme.colorScheme.onSurfaceVariant,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 8),
                Text('fast: ${models['fast'] ?? '—'}', style: theme.textTheme.bodySmall),
                Text('chat: ${models['chat'] ?? '—'}', style: theme.textTheme.bodySmall),
              ],
            ),
          ),
        ),
        const SizedBox(height: 12),
        Row(
          children: [
            FilledButton.tonal(onPressed: onRefresh, child: const Text('Обновить')),
            const SizedBox(width: 12),
            Text(
              lastUpdated,
              style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant),
            ),
          ],
        ),
        const SizedBox(height: 24),
      ],
    );
  }

  Future<void> _openUrl(String? url) async {
    if (url == null || url.isEmpty) return;
    final uri = Uri.tryParse(url);
    if (uri != null && await canLaunchUrl(uri)) {
      await launchUrl(uri, mode: LaunchMode.externalApplication);
    }
  }
}

class _CategorySection extends StatelessWidget {
  const _CategorySection({
    required this.category,
    required this.items,
    required this.statusMap,
    required this.onOpen,
  });

  final DashboardCategory category;
  final List<ServiceItem> items;
  final Map<String, String> statusMap;
  final void Function(String? url) onOpen;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
            child: Text(
              category.label.toUpperCase(),
              style: theme.textTheme.labelMedium?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
                fontWeight: FontWeight.bold,
              ),
            ),
          ),
          const Divider(height: 1),
          Padding(
            padding: const EdgeInsets.all(10),
            child: Wrap(
              spacing: 8,
              runSpacing: 8,
              children: items.map((s) {
                final st = statusMap[s.id];
                final isOk = st == 'ok';
                final isUnknown = st == null || st == 'skip';
                return InkWell(
                  onTap: s.url != null ? () => onOpen(s.url) : null,
                  borderRadius: BorderRadius.circular(12),
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                    decoration: BoxDecoration(
                      border: Border.all(
                        color: isOk
                            ? Colors.green.withValues(alpha: 0.5)
                            : theme.colorScheme.outline.withValues(alpha: 0.3),
                      ),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(s.icon, style: const TextStyle(fontSize: 20)),
                        const SizedBox(width: 8),
                        Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Text(
                              s.name,
                              style: theme.textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w600),
                            ),
                            Row(
                              children: [
                                Container(
                                  width: 6,
                                  height: 6,
                                  decoration: BoxDecoration(
                                    shape: BoxShape.circle,
                                    color: isOk
                                        ? Colors.green
                                        : isUnknown
                                            ? theme.colorScheme.outline
                                            : Colors.red,
                                  ),
                                ),
                                const SizedBox(width: 4),
                                Text(
                                  isOk ? 'online' : isUnknown ? '—' : 'offline',
                                  style: theme.textTheme.bodySmall?.copyWith(
                                    color: theme.colorScheme.onSurfaceVariant,
                                  ),
                                ),
                              ],
                            ),
                            if (s.url != null)
                              Text(
                                'Открыть',
                                style: theme.textTheme.labelSmall?.copyWith(
                                  color: theme.colorScheme.primary,
                                  fontWeight: FontWeight.w600,
                                ),
                              ),
                          ],
                        ),
                      ],
                    ),
                  ),
                );
              }).toList(),
            ),
          ),
        ],
      ),
    );
  }
}
