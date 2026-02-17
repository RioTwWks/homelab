/// One message in a chat session.
class ChatMessage {
  const ChatMessage({
    required this.role,
    required this.text,
    this.meta,
    this.ts,
  });

  final String role; // 'user' | 'assistant'
  final String text;
  final Map<String, dynamic>? meta;
  final int? ts;

  Map<String, dynamic> toJson() => {
        'role': role,
        'text': text,
        'meta': meta,
        'ts': ts ?? DateTime.now().millisecondsSinceEpoch,
      };

  static ChatMessage fromJson(Map<String, dynamic> j) => ChatMessage(
        role: j['role'] as String? ?? 'user',
        text: j['text'] as String? ?? '',
        meta: j['meta'] as Map<String, dynamic>?,
        ts: j['ts'] as int?,
      );
}

/// Chat session (same idea as web: id, name, messages).
class ChatSession {
  ChatSession({
    required this.id,
    required this.name,
    List<ChatMessage>? messages,
  }) : messages = messages ?? [];

  final String id;
  final String name;
  final List<ChatMessage> messages;

  Map<String, dynamic> toJson() => {
        'id': id,
        'name': name,
        'messages': messages.map((m) => m.toJson()).toList(),
      };

  static ChatSession fromJson(Map<String, dynamic> j) {
    final list = j['messages'] as List<dynamic>?;
    return ChatSession(
      id: j['id'] as String? ?? '',
      name: j['name'] as String? ?? 'webui',
      messages: list?.map((e) => ChatMessage.fromJson(e as Map<String, dynamic>)).toList() ?? [],
    );
  }
}
