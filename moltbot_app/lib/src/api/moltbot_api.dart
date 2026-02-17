import 'dart:async';
import 'dart:convert';
import 'package:http/http.dart' as http;

class MoltbotApi {
  MoltbotApi(this.baseUrl, {this.useApiPrefix = false});

  final String baseUrl;
  /// true = пути с префиксом /api/ (для подключения через веб-интерфейс, порт 18079)
  final bool useApiPrefix;

  String get _base => baseUrl.endsWith('/') ? baseUrl : '$baseUrl/';
  String get _path => useApiPrefix ? '${_base}api/' : _base;

  Future<bool> healthz() async {
    try {
      final r = await http.get(Uri.parse('${_path}healthz')).timeout(
        const Duration(seconds: 5),
      );
      return r.statusCode == 200;
    } catch (_) {
      return false;
    }
  }

  Future<Map<String, dynamic>> chat({
    required String text,
    String sessionId = 'flutter',
    String mode = 'auto',
  }) async {
    final r = await http.post(
      Uri.parse('${_path}v1/chat'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'text': text,
        'session_id': sessionId,
        'mode': mode,
      }),
    );
    if (r.statusCode != 200) {
      final body = r.body;
      final isHtml = body.trimLeft().toLowerCase().startsWith('<!doctype') ||
          body.trimLeft().toLowerCase().startsWith('<html');
      final String msg = isHtml
          ? 'HTTP ${r.statusCode}: сервер вернул HTML вместо JSON. '
            'Если подключаешься по порту 18079 (веб-интерфейс), включи «Через веб-интерфейс» в настройках сервера.'
          : (body.length > 300 ? 'HTTP ${r.statusCode}: ${body.substring(0, 300)}…' : 'HTTP ${r.statusCode}: $body');
      throw Exception(msg);
    }
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  /// GET /api/v1/system/status → { ok, ts, services: { name: "ok"|"error:..." }, models: { fast, chat } }
  Future<Map<String, dynamic>> getSystemStatus() async {
    final r = await http
        .get(Uri.parse('${_path}v1/system/status'))
        .timeout(const Duration(seconds: 10));
    if (r.statusCode != 200) {
      throw Exception('HTTP ${r.statusCode}: ${r.body}');
    }
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  /// POST /v1/chat/stream → Server-Sent Events: { chunk } or { done, reply_text, intent, used_model, sources, timings_ms }
  Stream<Map<String, dynamic>> chatStream({
    required String text,
    String sessionId = 'flutter',
    String mode = 'auto',
  }) async* {
    final request = http.Request('POST', Uri.parse('${_path}v1/chat/stream'));
    request.headers['Content-Type'] = 'application/json';
    request.body = jsonEncode({
      'text': text,
      'session_id': sessionId,
      'mode': mode,
    });
    final client = http.Client();
    try {
      final response = await client.send(request);
      if (response.statusCode != 200) {
        final body = await response.stream.bytesToString();
        final isHtml = body.trimLeft().toLowerCase().startsWith('<!doctype') ||
            body.trimLeft().toLowerCase().startsWith('<html');
        final String msg = isHtml
            ? 'HTTP ${response.statusCode}: сервер вернул HTML вместо потока. '
              'Если подключаешься по порту 18079, включи «Через веб-интерфейс» в настройках.'
            : (body.length > 300 ? 'HTTP ${response.statusCode}: ${body.substring(0, 300)}…' : 'HTTP ${response.statusCode}: $body');
        throw Exception(msg);
      }
      String buffer = '';
      await for (final chunk in response.stream.transform(utf8.decoder)) {
        buffer += chunk;
        int idx;
        while ((idx = buffer.indexOf('\n\n')) >= 0) {
          final part = buffer.substring(0, idx);
          buffer = buffer.substring(idx + 2);
          final dataIdx = part.indexOf('data: ');
          if (dataIdx >= 0) {
            final jsonStr = part.substring(dataIdx + 6).trim();
            if (jsonStr.isEmpty) continue;
            try {
              final data = jsonDecode(jsonStr) as Map<String, dynamic>?;
              if (data != null) yield data;
            } catch (_) {}
          }
        }
      }
    } finally {
      client.close();
    }
  }

  /// POST /api/v1/system/services with [{ name, url }] → { ok, ts, services: { name: "ok"|"error:..." } }
  Future<Map<String, dynamic>> probeServices(
      List<Map<String, String>> items) async {
    final r = await http
        .post(
          Uri.parse('${_path}v1/system/services'),
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode(items),
        )
        .timeout(const Duration(seconds: 15));
    if (r.statusCode != 200) {
      throw Exception('HTTP ${r.statusCode}: ${r.body}');
    }
    return jsonDecode(r.body) as Map<String, dynamic>;
  }
}
