import 'package:flutter_test/flutter_test.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:window_manager/window_manager.dart';

import 'package:desktop/app.dart';
import 'package:desktop/core/app_identity.dart';
import 'package:desktop/providers/locale_provider.dart';
import 'package:desktop/providers/project_state.dart';
import 'package:desktop/providers/session_provider.dart';

void main() {
  testWidgets('renders the project workspace', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: <Override>[
          engineBootstrapProvider.overrideWith(() => _StubEngine()),
          projectProvider.overrideWith(_StubProject.new),
        ],
        child: const BasketballHighlightApp(enableStartupProjectScan: false),
      ),
    );
    expect(
      find.byWidgetPredicate(
        (widget) =>
            widget is Text &&
            (widget.data == '把整场比赛，变成你的高光。' ||
                widget.data == 'Turn the whole game into your highlights.'),
      ),
      findsOneWidget,
    );
    expect(
      find.byWidgetPredicate(
        (widget) =>
            widget is Text &&
            (widget.data == '新建项目' || widget.data == 'New project'),
      ),
      findsWidgets,
    );
  });

  for (final locale in const [Locale('zh'), Locale('en')]) {
    testWidgets('localized exit confirmation uses shared name ($locale)', (
      tester,
    ) async {
      await tester.pumpWidget(
        ProviderScope(
          overrides: <Override>[
            engineBootstrapProvider.overrideWith(() => _StubEngine()),
            projectProvider.overrideWith(_StubProject.new),
            appLocaleProvider.overrideWith(() => _FixedLocale(locale)),
          ],
          child: const CourtsideApp(),
        ),
      );
      await tester.pump();

      final appState = tester.state<State<CourtsideApp>>(
        find.byType(CourtsideApp),
      );
      (appState as WindowListener).onWindowClose();
      await tester.pumpAndSettle();

      final dialog = find.byType(AlertDialog);
      final name = appDisplayName();
      expect(dialog, findsOneWidget);
      expect(
        find.descendant(
          of: dialog,
          matching: find.text(
            locale.languageCode == 'zh' ? '退出 $name？' : 'Exit $name?',
          ),
        ),
        findsOneWidget,
      );
    });
  }
}

class _FixedLocale extends LocaleNotifier {
  _FixedLocale(this.locale);

  final Locale locale;

  @override
  Locale build() => locale;
}

class _StubEngine extends EngineBootstrapNotifier {
  @override
  AsyncValue<bool> build() => const AsyncData<bool>(true);
}

class _StubProject extends ProjectNotifier {
  @override
  ProjectState build() => const ProjectState();

  @override
  Future<void> loadRecentProjects() async {}
}
