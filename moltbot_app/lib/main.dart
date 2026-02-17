import 'package:flutter/material.dart';
import 'screens/home_screen.dart';
import 'src/settings/settings_service.dart';

void main() {
  runApp(const MoltbotApp());
}

class MoltbotApp extends StatefulWidget {
  const MoltbotApp({super.key});

  @override
  State<MoltbotApp> createState() => _MoltbotAppState();
}

class _MoltbotAppState extends State<MoltbotApp> {
  ThemeMode _themeMode = ThemeMode.dark;

  @override
  void initState() {
    super.initState();
    _loadTheme();
  }

  Future<void> _loadTheme() async {
    final t = await SettingsService.getTheme();
    if (mounted) {
      setState(() => _themeMode = t == 'light' ? ThemeMode.light : ThemeMode.dark);
    }
  }

  void _onThemeChanged() {
    _loadTheme();
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Moltbot',
      themeMode: _themeMode,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: Colors.blue, brightness: Brightness.light),
        useMaterial3: true,
      ),
      darkTheme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: Colors.blue, brightness: Brightness.dark),
        useMaterial3: true,
      ),
      home: _InitialScreen(onThemeChanged: _onThemeChanged),
    );
  }
}

class _InitialScreen extends StatelessWidget {
  const _InitialScreen({required this.onThemeChanged});

  final VoidCallback onThemeChanged;

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<Widget>(
      future: getInitialScreen(onThemeChanged: onThemeChanged),
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.done && snapshot.hasData) {
          return snapshot.data!;
        }
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
      },
    );
  }
}
