import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import '../src/models/chat_models.dart';

class ChatMessageBubble extends StatelessWidget {
  const ChatMessageBubble({
    super.key,
    required this.message,
    this.showMeta = false,
  });

  final ChatMessage message;
  final bool showMeta;

  static String _formatTime(int? ts) {
    if (ts == null) return '';
    final d = DateTime.fromMillisecondsSinceEpoch(ts);
    return '${d.hour.toString().padLeft(2, '0')}:${d.minute.toString().padLeft(2, '0')}';
  }

  @override
  Widget build(BuildContext context) {
    final isUser = message.role == 'user';
    final theme = Theme.of(context);

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisAlignment: isUser ? MainAxisAlignment.end : MainAxisAlignment.start,
        children: [
          if (!isUser) _avatar(isUser),
          if (!isUser) const SizedBox(width: 10),
          Flexible(
            child: Column(
              crossAxisAlignment: isUser ? CrossAxisAlignment.end : CrossAxisAlignment.start,
              children: [
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                  decoration: BoxDecoration(
                    color: isUser
                        ? theme.colorScheme.primaryContainer.withValues(alpha: 0.4)
                        : theme.colorScheme.surfaceContainerHighest,
                    borderRadius: BorderRadius.circular(14),
                    border: Border(
                      left: isUser
                          ? BorderSide.none
                          : BorderSide(color: theme.colorScheme.primary.withValues(alpha: 0.35), width: 2),
                      right: isUser
                          ? BorderSide(color: theme.colorScheme.primary.withValues(alpha: 0.3), width: 2)
                          : BorderSide.none,
                    ),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      isUser
                          ? Text(message.text, style: theme.textTheme.bodyLarge)
                          : MarkdownBody(
                              data: message.text,
                              styleSheet: MarkdownStyleSheet(
                                p: theme.textTheme.bodyLarge,
                                listBullet: theme.textTheme.bodyLarge,
                                code: theme.textTheme.bodyMedium?.copyWith(
                                  fontFamily: 'monospace',
                                  backgroundColor: theme.colorScheme.surfaceContainerLow,
                                ),
                              ),
                            ),
                      if (showMeta && message.meta != null && message.meta!.isNotEmpty) ...[
                        const SizedBox(height: 6),
                        _buildMeta(theme, message.meta!),
                      ],
                    ],
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  _formatTime(message.ts),
                  style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant),
                ),
              ],
            ),
          ),
          if (isUser) const SizedBox(width: 10),
          if (isUser) _avatar(isUser),
        ],
      ),
    );
  }

  Widget _avatar(bool isUser) {
    return Container(
      width: 28,
      height: 28,
      decoration: BoxDecoration(
        color: isUser
            ? Colors.blue.withValues(alpha: 0.2)
            : Colors.cyan.withValues(alpha: 0.2),
        borderRadius: BorderRadius.circular(8),
      ),
      alignment: Alignment.center,
      child: Text(isUser ? '👤' : '🤖', style: const TextStyle(fontSize: 14)),
    );
  }

  Widget _buildMeta(ThemeData theme, Map<String, dynamic> meta) {
    final parts = <String>[];
    if (meta['intent'] != null) parts.add('intent=${meta['intent']}');
    if (meta['used_model'] != null) parts.add('model=${meta['used_model']}');
    if (meta['timings_ms'] != null) parts.add('timings=${meta['timings_ms']}');
    if (parts.isEmpty) return const SizedBox.shrink();
    return Text(
      parts.join(' · '),
      style: theme.textTheme.bodySmall?.copyWith(
        color: theme.colorScheme.onSurfaceVariant,
        fontFamily: 'monospace',
      ),
    );
  }
}
