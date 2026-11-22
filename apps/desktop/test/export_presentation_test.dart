import 'package:bhe_l10n/bhe_l10n.dart';
import 'package:desktop/features/export/export_presentation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test(
    'defaults are a fresh three-second cover and twenty-percent soundtrack',
    () {
      final first = defaultExportPresentation();
      final second = defaultExportPresentation();
      expect(first['cover'], {
        'enabled': true,
        'duration_ms': 3000,
        'style': 'court',
        'title': null,
        'subtitle': null,
        'background_path': null,
        'accent_color': '#F97316',
      });
      expect(first['audio'], {
        'enabled': true,
        'track': 'electronic_drive',
        'custom_path': null,
        'volume': 0.2,
      });
      first['cover']['enabled'] = false;
      expect(second['cover']['enabled'], isTrue);
    },
  );

  test(
    'updates preserve unrelated settings and never mutate the prior snapshot',
    () {
      final before = defaultExportPresentation();
      final after = updateExportPresentation(
        before,
        cover: {'style': 'poster', 'title': 'Will'},
        audio: {'track': 'hip_hop_bounce'},
      );
      expect(before['cover']['style'], 'court');
      expect(after['cover']['style'], 'poster');
      expect(after['cover']['duration_ms'], 3000);
      expect(after['audio']['track'], 'hip_hop_bounce');
      expect(after['audio']['volume'], 0.2);
    },
  );

  testWidgets('controls update cover and soundtrack configuration', (
    tester,
  ) async {
    var value = defaultExportPresentation();
    await tester.pumpWidget(
      MaterialApp(
        localizationsDelegates: BheLocalizations.localizationsDelegates,
        supportedLocales: BheLocalizations.supportedLocales,
        home: Scaffold(
          body: StatefulBuilder(
            builder: (context, setState) {
              return SingleChildScrollView(
                child: ExportPresentationPanel(
                  value: value,
                  onChanged: (next) => setState(() => value = next),
                ),
              );
            },
          ),
        ),
      ),
    );
    expect(
      tester
          .widget<Switch>(find.byKey(const Key('export-cover-enabled')))
          .value,
      isTrue,
    );
    expect(
      tester
          .widget<Switch>(find.byKey(const Key('export-audio-enabled')))
          .value,
      isTrue,
    );
    await tester.tap(find.byKey(const Key('export-cover-enabled')));
    await tester.pump();
    expect(value['cover']['enabled'], isFalse);
    await tester.enterText(find.byKey(const Key('export-cover-title')), 'Will');
    expect(value['cover']['title'], 'Will');
    await tester.tap(find.byKey(const Key('export-bgm-track')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Hip-hop bounce').last);
    await tester.pumpAndSettle();
    expect(value['audio']['track'], 'hip_hop_bounce');
  });

  testWidgets('multiple historical project folders can be added and removed', (
    tester,
  ) async {
    final roots = <String>[];
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          exportSourcePickerProvider.overrideWithValue(_FakeSourcePicker()),
        ],
        child: MaterialApp(
          localizationsDelegates: BheLocalizations.localizationsDelegates,
          supportedLocales: BheLocalizations.supportedLocales,
          home: Scaffold(
            body: StatefulBuilder(
              builder: (context, setState) {
                return ExportProjectSources(
                  roots: roots,
                  onChanged: (next) => setState(() {
                    roots
                      ..clear()
                      ..addAll(next);
                  }),
                );
              },
            ),
          ),
        ),
      ),
    );
    await tester.tap(find.byKey(const Key('export-add-source-project')));
    await tester.pumpAndSettle();
    expect(roots, ['/tmp/day-two']);
    await tester.tap(find.byKey(const Key('export-add-source-project')));
    await tester.pumpAndSettle();
    expect(roots, ['/tmp/day-two']);
    await tester.tap(
      find.descendant(
        of: find.byKey(const Key('export-remove-source-project-0')),
        matching: find.byIcon(Icons.close),
      ),
    );
    await tester.pump();
    expect(roots, isEmpty);
  });
}

class _FakeSourcePicker extends ExportSourcePicker {
  @override
  Future<String?> projectDirectory({required String confirmLabel}) async =>
      '/tmp/day-two';
}
