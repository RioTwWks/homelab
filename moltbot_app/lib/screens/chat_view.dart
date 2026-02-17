import 'package:flutter/material.dart';
import '../src/models/chat_models.dart';
import '../widgets/chat_message_bubble.dart';
import '../widgets/chat_composer.dart';
import '../widgets/welcome_chips.dart';

class ChatView extends StatefulWidget {
  const ChatView({
    super.key,
    required this.messages,
    required this.onSend,
    required this.showMeta,
    this.typing = false,
  });

  final List<ChatMessage> messages;
  final Future<void> Function(String text) onSend;
  final bool showMeta;
  final bool typing;

  @override
  State<ChatView> createState() => _ChatViewState();
}

class _ChatViewState extends State<ChatView> {
  final _controller = TextEditingController();
  final _scrollController = ScrollController();
  bool _loading = false;

  @override
  void dispose() {
    _controller.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final text = _controller.text.trim();
    if (text.isEmpty || _loading) return;
    _controller.clear();
    setState(() => _loading = true);
    await widget.onSend(text);
    if (mounted) {
      setState(() => _loading = false);
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (_scrollController.hasClients) {
          _scrollController.animateTo(
            _scrollController.position.maxScrollExtent,
            duration: const Duration(milliseconds: 200),
            curve: Curves.easeOut,
          );
        }
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final hasMessages = widget.messages.isNotEmpty;
    final itemCount = hasMessages
        ? widget.messages.length + (widget.typing ? 1 : 0) + 1
        : 2;

    return Column(
      children: [
        Expanded(
          child: ListView.builder(
            controller: _scrollController,
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 14),
            itemCount: itemCount,
            itemBuilder: (context, index) {
              if (!hasMessages) {
                if (index == 0) return const SizedBox(height: 24);
                return Padding(
                  padding: const EdgeInsets.all(24),
                  child: WelcomeChips(onChipTap: (text) => widget.onSend(text)),
                );
              }
              if (index < widget.messages.length) {
                return ChatMessageBubble(
                  message: widget.messages[index],
                  showMeta: widget.showMeta,
                );
              }
              if (widget.typing && index == widget.messages.length) {
                return const TypingIndicator();
              }
              return const SizedBox(height: 16);
            },
          ),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(12, 0, 12, 12),
          child: ChatComposer(
            controller: _controller,
            onSubmit: _submit,
            loading: _loading,
          ),
        ),
      ],
    );
  }
}

/// Typing indicator to show while waiting for reply.
class TypingIndicator extends StatelessWidget {
  const TypingIndicator({super.key});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Row(
        children: [
          Container(
            width: 28,
            height: 28,
            decoration: BoxDecoration(
              color: Colors.cyan.withValues(alpha: 0.2),
              borderRadius: BorderRadius.circular(8),
            ),
            alignment: Alignment.center,
            child: const Text('🤖', style: TextStyle(fontSize: 14)),
          ),
          const SizedBox(width: 10),
          SizedBox(
            height: 36,
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: List.generate(3, (i) {
                return TweenAnimationBuilder<double>(
                  tween: Tween(begin: 0, end: 1),
                  duration: Duration(milliseconds: 400 + i * 150),
                  builder: (context, value, child) {
                    return Container(
                      margin: const EdgeInsets.symmetric(horizontal: 2),
                      width: 6,
                      height: 6,
                      decoration: BoxDecoration(
                        color: Theme.of(context).colorScheme.onSurfaceVariant.withValues(alpha: 0.3 + value * 0.5),
                        shape: BoxShape.circle,
                      ),
                    );
                  },
                );
              }),
            ),
          ),
        ],
      ),
    );
  }
}
