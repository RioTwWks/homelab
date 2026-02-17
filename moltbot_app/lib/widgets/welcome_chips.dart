import 'package:flutter/material.dart';

final List<Map<String, String>> kWelcomeSuggestions = [
  {'text': 'Какая погода?', 'label': '🌤 погода'},
  {'text': 'Последние новости', 'label': '📰 новости'},
  {'text': 'поставь таймер на 3 минуты', 'label': '⏱ таймер'},
  {'text': 'ютуб', 'label': '▶ ютуб'},
  {'text': 'включи свет в гостиной', 'label': '💡 свет'},
  {'text': 'режим кино', 'label': '🎬 кино'},
];

class WelcomeChips extends StatelessWidget {
  const WelcomeChips({
    super.key,
    required this.onChipTap,
  });

  final void Function(String text) onChipTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Column(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        Container(
          padding: const EdgeInsets.all(20),
          decoration: BoxDecoration(
            color: theme.colorScheme.primaryContainer.withValues(alpha: 0.3),
            borderRadius: BorderRadius.circular(16),
            boxShadow: [
              BoxShadow(
                color: theme.colorScheme.primary.withValues(alpha: 0.15),
                blurRadius: 40,
                spreadRadius: 0,
              ),
            ],
          ),
          child: const Text('🤖', style: TextStyle(fontSize: 48)),
        ),
        const SizedBox(height: 16),
        Text(
          'Привет! Я Moltbot.',
          style: theme.textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.bold),
        ),
        const SizedBox(height: 8),
        Text(
          'Голосовой ассистент для твоего homelab. Задай вопрос, дай команду или попробуй что-нибудь из подсказок:',
          style: theme.textTheme.bodyMedium?.copyWith(color: theme.colorScheme.onSurfaceVariant),
          textAlign: TextAlign.center,
        ),
        const SizedBox(height: 16),
        Wrap(
          alignment: WrapAlignment.center,
          spacing: 8,
          runSpacing: 8,
          children: kWelcomeSuggestions.map((s) {
            return ActionChip(
              label: Text(s['label']!),
              onPressed: () => onChipTap(s['text']!),
            );
          }).toList(),
        ),
      ],
    );
  }
}
