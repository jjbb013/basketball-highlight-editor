import 'dart:convert';

import 'package:desktop/features/review/identity_review_chip.dart';
import 'package:desktop/theme/app_theme.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

Map<String, dynamic> _candidate({
  String source = 'automatic',
  bool needsReview = true,
  double confidence = 0,
}) => {
  'id': 'c1',
  'identity_id': 'identity-1',
  'assignment_source': source,
  'touch_time_ms': 59800,
  'touch_confidence': 0.8,
  'identity_confidence': confidence,
  'identity_evidence_json': jsonEncode({
    'needs_review': needsReview,
    'identity': {'needs_review': needsReview},
  }),
};

Future<void> _pump(
  WidgetTester tester,
  Map<String, dynamic> candidate, {
  Future<void> Function(String, String)? onNameIdentity,
}) async {
  await tester.pumpWidget(
    ProviderScope(
      child: MaterialApp(
        theme: appTheme(Brightness.light),
        home: Scaffold(
          body: IdentityReviewChip(
            candidate: candidate,
            onNameIdentity: onNameIdentity,
          ),
        ),
      ),
    ),
  );
}

void main() {
  testWidgets('无身份证据时不显示自动推测', (tester) async {
    await _pump(tester, {'id': 'c1'});
    expect(find.byType(IdentityReviewChip), findsOneWidget);
    expect(find.text('命名此身份'), findsNothing);
    expect(find.textContaining('自动'), findsNothing);
    expect(find.textContaining('待复核'), findsNothing);
  });

  testWidgets('显示最后触球证据并用一次身份请求命名', (tester) async {
    final calls = <(String, String)>[];
    await _pump(
      tester,
      _candidate(),
      onNameIdentity: (identityId, name) async => calls.add((identityId, name)),
    );
    expect(find.text('身份待复核'), findsOneWidget);
    expect(find.textContaining('59.80'), findsOneWidget);
    await tester.tap(find.text('命名此身份'));
    await tester.pumpAndSettle();
    await tester.enterText(
      find.byKey(const Key('identity-name-field')),
      'Will',
    );
    await tester.tap(find.byKey(const Key('confirm-identity-name')));
    await tester.pumpAndSettle();
    expect(calls, [('identity-1', 'Will')]);
  });

  testWidgets('自动归属显示推测置信度而不是确定身份', (tester) async {
    await _pump(tester, _candidate(needsReview: false, confidence: .82));
    expect(find.text('同身份自动推测'), findsOneWidget);
    expect(find.textContaining('82%'), findsOneWidget);
  });

  testWidgets('人工归属优先且不允许自动命名覆盖', (tester) async {
    await _pump(tester, _candidate(source: 'manual', needsReview: false));
    expect(find.text('人工标记优先'), findsOneWidget);
    expect(find.text('命名此身份'), findsNothing);
  });
}
