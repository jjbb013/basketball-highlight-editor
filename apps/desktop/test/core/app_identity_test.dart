import 'dart:io';

import 'package:bhe_l10n/bhe_l10n.dart';
import 'package:desktop/core/app_identity.dart';
import 'package:desktop/core/app_log.dart';
import 'package:desktop/core/project_session.dart';
import 'package:desktop/features/about/about_dialog.dart';
import 'package:desktop/providers/update_provider.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('only macOS uses the BHE Pro display name', () {
    expect(appDisplayName(isMacOS: true), 'BHE Pro');
    expect(appDisplayName(isMacOS: false), 'BHE');
  });

  test(
    'macOS directories are independent and other platforms are unchanged',
    () {
      const env = <String, String>{
        'HOME': '/Users/test',
        'LOCALAPPDATA': r'C:\Users\test\AppData\Local',
        'XDG_DATA_HOME': '/home/test/.local/share',
        'XDG_STATE_HOME': '/home/test/.local/state',
        'XDG_CACHE_HOME': '/home/test/.cache',
      };
      expect(
        fallbackProjectsRoot(env, isMacOS: true, isWindows: false),
        '/Users/test/Library/Application Support/BHE Pro/Projects',
      );
      expect(
        engineLogDirectory(env, isMacOS: true, isWindows: false),
        '/Users/test/Library/Logs/BHE Pro',
      );
      expect(
        updateDownloadDirectory(env, isMacOS: true, isWindows: false),
        '/Users/test/Library/Caches/BHE Pro/updates',
      );
      expect(
        fallbackProjectsRoot(env, isMacOS: false, isWindows: true),
        r'C:\Users\test\AppData\Local\BHE\Projects',
      );
      expect(
        engineLogDirectory(env, isMacOS: false, isWindows: true),
        r'C:\Users\test\AppData\Local\BHE\logs',
      );
      expect(
        updateDownloadDirectory(env, isMacOS: false, isWindows: true),
        r'C:\Users\test\AppData\Local\BHE\updates',
      );
      expect(
        fallbackProjectsRoot(env, isMacOS: false, isWindows: false),
        '/home/test/.local/share/bhe/projects',
      );
      expect(
        engineLogDirectory(env, isMacOS: false, isWindows: false),
        '/home/test/.local/state/bhe/logs',
      );
      expect(
        updateDownloadDirectory(env, isMacOS: false, isWindows: false),
        '/home/test/.cache/bhe/updates',
      );
    },
  );

  test('default project roots preserve non-macOS behavior', () {
    const env = <String, String>{
      'HOME': '/Users/test',
      'USERPROFILE': r'C:\Users\test',
    };
    expect(
      defaultProjectsRoot(env, isMacOS: true, isWindows: false),
      '/Users/test/Library/Application Support/BHE Pro/Projects',
    );
    expect(
      defaultProjectsRoot(env, isMacOS: false, isWindows: true),
      r'C:\Users\test/Videos/BasketballProjects',
    );
    expect(
      defaultProjectsRoot(env, isMacOS: false, isWindows: false),
      '/Users/test/Movies/BasketballProjects',
    );
  });

  for (final locale in const [Locale('zh'), Locale('en')]) {
    for (final isMacOS in [true, false]) {
      testWidgets(
        'real localizations use injected identity ($locale, $isMacOS)',
        (tester) async {
          final name = appDisplayName(isMacOS: isMacOS);
          final chinese = locale.languageCode == 'zh';
          final about = chinese ? '关于 $name' : 'About $name';
          final exit = chinese ? '退出 $name？' : 'Exit $name?';
          final instructions = chinese
              ? '下载完成。退出 $name，打开安装包把 $name 拖进「应用程序」替换旧版本，再重新打开。项目保存在别的位置，不会丢。'
              : 'Download complete. Quit $name, open the installer, drag $name into Applications to replace the old version, then reopen it. Projects are stored elsewhere and will not be lost.';
          await tester.pumpWidget(
            MaterialApp(
              locale: locale,
              localizationsDelegates: BheLocalizations.localizationsDelegates,
              supportedLocales: BheLocalizations.supportedLocales,
              home: Builder(
                builder: (context) {
                  final l10n = BheLocalizations.of(context);
                  return SingleChildScrollView(
                    child: Column(
                      children: [
                        Text(l10n.about(name)),
                        Text(l10n.confirmExit(name)),
                        Text(l10n.updateMacInstallInstructions(name)),
                      ],
                    ),
                  );
                },
              ),
            ),
          );
          await tester.pumpAndSettle();
          expect(find.text(about), findsOneWidget);
          expect(find.text(exit), findsOneWidget);
          expect(find.text(instructions), findsOneWidget);
        },
      );
    }
  }

  testWidgets('about page uses the shared display name', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Builder(
          builder: (context) => TextButton(
            onPressed: () => showCourtsideAboutDialog(context),
            child: const Text('open-about'),
          ),
        ),
      ),
    );
    await tester.tap(find.text('open-about'));
    await tester.pumpAndSettle();
    expect(find.text(appDisplayName()), findsOneWidget);
    expect(
      find.textContaining(engineLogDirectory(Platform.environment)),
      findsOneWidget,
    );
  });
}
