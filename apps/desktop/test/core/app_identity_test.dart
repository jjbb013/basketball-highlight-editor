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
      find.textContaining('/Library/Logs/${appDisplayName()}'),
      findsOneWidget,
    );
  });
}
