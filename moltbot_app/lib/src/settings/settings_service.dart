import 'dart:convert';
import 'package:shared_preferences/shared_preferences.dart';

const _keyBaseUrl = 'moltbot_base_url';
const _keyUseApiPrefix = 'moltbot_use_api_prefix'; // true = через веб-прокси (порт 18079)
const _keyTheme = 'moltbot_theme'; // 'dark' | 'light'
const _keySessions = 'moltbot_sessions';
const _keyActiveSessionId = 'moltbot_active_sess';

class SettingsService {
  static Future<String?> getBaseUrl() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(_keyBaseUrl);
  }

  static Future<void> setBaseUrl(String url) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_keyBaseUrl, url);
  }

  static Future<void> clearBaseUrl() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_keyBaseUrl);
  }

  /// true = запросы идут на /api/healthz, /api/v1/chat (для веб-прокси на порту 18079)
  static Future<bool> getUseApiPrefix() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getBool(_keyUseApiPrefix) ?? false;
  }

  static Future<void> setUseApiPrefix(bool value) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(_keyUseApiPrefix, value);
  }

  static Future<String> getTheme() async {
    final prefs = await SharedPreferences.getInstance();
    final t = prefs.getString(_keyTheme);
    return (t == 'light' || t == 'dark') ? t! : 'dark';
  }

  static Future<void> setTheme(String theme) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_keyTheme, theme);
  }

  static Future<List<Map<String, dynamic>>> getSessionsJson() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_keySessions);
    if (raw == null) return [];
    try {
      final list = jsonDecode(raw) as List<dynamic>;
      return list.map((e) => e as Map<String, dynamic>).toList();
    } catch (_) {
      return [];
    }
  }

  static Future<void> saveSessionsJson(List<Map<String, dynamic>> list) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_keySessions, jsonEncode(list));
  }

  static Future<String?> getActiveSessionId() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(_keyActiveSessionId);
  }

  static Future<void> setActiveSessionId(String? id) async {
    final prefs = await SharedPreferences.getInstance();
    if (id == null) {
      await prefs.remove(_keyActiveSessionId);
    } else {
      await prefs.setString(_keyActiveSessionId, id);
    }
  }
}
