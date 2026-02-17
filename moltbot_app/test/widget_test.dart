// Basic Flutter widget test for MoltbotApp.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:moltbot_app/main.dart';

void main() {
  testWidgets('MoltbotApp builds', (WidgetTester tester) async {
    await tester.pumpWidget(const MoltbotApp());
    await tester.pump();

    expect(find.byType(MaterialApp), findsOneWidget);
  });
}
