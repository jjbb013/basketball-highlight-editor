import 'dart:io';

import 'package:bhe_l10n/bhe_l10n.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:desktop/core/engine_session.dart' show JsonMap;
import 'package:desktop/features/review/people_review_screen.dart';
import 'package:desktop/features/review/review_screen.dart';
import 'package:desktop/providers/onboarding_provider.dart';
import 'package:desktop/providers/project_state.dart';

class _PeopleNotifier extends ProjectNotifier {
  _PeopleNotifier(this.initialState);

  final ProjectState initialState;
  final List<(String, String)> nameIdentityCalls = <(String, String)>[];
  final List<(String, String?)> setCandidatePlayerCalls = <(String, String?)>[];
  final List<(String, int)> loadPreviewCalls = <(String, int)>[];

  /// 非空时所有候选封面都返回这个路径；null 模拟封面不可用（显示占位图）。
  String? previewPath;

  @override
  ProjectState build() => initialState;

  @override
  Future<String?> loadCandidatePreview(String candidateId, int timeMs) async {
    loadPreviewCalls.add((candidateId, timeMs));
    return previewPath;
  }

  @override
  Future<int> nameIdentity(String identityId, String playerName) async {
    nameIdentityCalls.add((identityId, playerName));
    // 模拟引擎：同身份的自动候选全部标成该球员，人工改派的不动。
    state = state.copyWith(
      candidates: [
        for (final candidate in state.candidates)
          if (candidate['identity_id']?.toString() == identityId &&
              candidate['assignment_source'] != 'manual')
            <String, dynamic>{
              ...candidate,
              'player_id': 'p-will',
              'player_name': playerName,
            }
          else
            candidate,
      ],
    );
    return 2;
  }

  @override
  Future<void> setCandidatePlayer(String candidateId, String? playerId) async {
    setCandidatePlayerCalls.add((candidateId, playerId));
    state = state.copyWith(
      candidates: [
        for (final candidate in state.candidates)
          if (candidate['id']?.toString() == candidateId)
            <String, dynamic>{
              ...candidate,
              'player_id': playerId,
              if (playerId == null) 'player_name': null,
              'assignment_source': playerId == null ? 'auto' : 'manual',
            }
          else
            candidate,
      ],
    );
  }
}

ProjectState _peopleState() => ProjectState(
  video: const <String, dynamic>{'id': 'v1'},
  job: const <String, dynamic>{'state': 'completed'},
  players: const <JsonMap>[
    <String, dynamic>{'id': 'p1', 'name': 'Leo'},
  ],
  candidates: const <JsonMap>[
    <String, dynamic>{
      'id': 'c1',
      'identity_id': 'identity_a',
      'touch_time_ms': 3000,
      'event_time_ms': 4200,
      'video_id': 'v1',
    },
    <String, dynamic>{
      'id': 'c2',
      'identity_id': 'identity_a',
      'touch_time_ms': 9000,
      'event_time_ms': 10200,
      'video_id': 'v1',
    },
    <String, dynamic>{
      'id': 'c3',
      'identity_id': 'identity_b',
      'touch_time_ms': 5000,
      'event_time_ms': 6100,
      'video_id': 'v1',
      'player_id': 'p9',
      'player_name': 'Max',
      'assignment_source': 'manual',
    },
    <String, dynamic>{
      'id': 'c5',
      'identity_id': 'identity_c',
      'touch_time_ms': 7000,
      'event_time_ms': 8100,
      'video_id': 'v1',
      'player_id': 'p1',
      'player_name': 'Leo',
    },
    <String, dynamic>{'id': 'c4', 'touch_time_ms': 1000},
  ],
);

Future<_PeopleNotifier> _pumpPeople(
  WidgetTester tester, {
  ProjectState? state,
  String location = '/people',
  String? previewPath,
}) async {
  tester.view.physicalSize = const Size(1400, 900);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  final notifier = _PeopleNotifier(state ?? _peopleState());
  notifier.previewPath = previewPath;
  final router = GoRouter(
    initialLocation: location,
    routes: [
      GoRoute(
        path: '/people',
        builder: (_, _) => const Scaffold(body: PeopleReviewScreen()),
      ),
      GoRoute(
        path: '/review',
        builder: (_, _) => const Scaffold(body: Text('review-page')),
      ),
    ],
  );
  addTearDown(router.dispose);
  await tester.pumpWidget(
    ProviderScope(
      overrides: [projectProvider.overrideWith(() => notifier)],
      child: MaterialApp.router(
        routerConfig: router,
        locale: BheLocale.zh,
        localizationsDelegates: BheLocalizations.localizationsDelegates,
        supportedLocales: BheLocalizations.supportedLocales,
      ),
    ),
  );
  await tester.pumpAndSettle();
  return notifier;
}

void main() {
  setUp(
    () => SharedPreferences.setMockInitialValues({
      onboardingStepsPrefsKey: allOnboardingStepIds,
    }),
  );

  // testWidgets 的 fake-async 区里真实文件 IO 不会完成，封面图在真实区备好。
  Directory? coverTempDir;
  String coverImagePath = '';
  setUpAll(() async {
    coverTempDir = await Directory.systemTemp.createTemp('people_cover_test');
    final coverFile = File('${coverTempDir!.path}/cover.png');
    // 1x1 透明 PNG，保证 Image.file 解码不报错。
    await coverFile.writeAsBytes(const [
      0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0x00, 0x00, 0x00, 0x0D,
      0x49, 0x48, 0x44, 0x52, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,
      0x08, 0x06, 0x00, 0x00, 0x00, 0x1F, 0x15, 0xC4, 0x89, 0x00, 0x00, 0x00,
      0x0A, 0x49, 0x44, 0x41, 0x54, 0x78, 0x9C, 0x63, 0x00, 0x01, 0x00, 0x00,
      0x05, 0x00, 0x01, 0x0D, 0x0A, 0x2D, 0xB4, 0x00, 0x00, 0x00, 0x00, 0x49,
      0x45, 0x4E, 0x44, 0xAE, 0x42, 0x60, 0x82,
    ]);
    coverImagePath = coverFile.path;
  });
  tearDownAll(() async {
    await coverTempDir?.delete(recursive: true);
  });

  testWidgets('按身份分组渲染：未命名显示自动推测与待复核，命名显示球员名', (tester) async {
    await _pumpPeople(tester);

    expect(find.text('Leo'), findsWidgets);
    expect(find.text('Max'), findsWidgets);
    expect(find.text('自动推测'), findsOneWidget);
    expect(find.text('身份待复核'), findsOneWidget);
    expect(find.text('含人工标记'), findsOneWidget);
    // 4 个候选里 c4 没有 identity_id，不出现。
    expect(find.text('触球 0:01.0'), findsNothing);
    expect(find.text('触球 0:03.0'), findsOneWidget);
  });

  testWidgets('命名为球员调用 nameIdentity 并标记同身份自动候选', (tester) async {
    final notifier = await _pumpPeople(tester);

    await tester.tap(find.byKey(const Key('people-name-identity_a')));
    await tester.pumpAndSettle();
    await tester.enterText(find.byKey(const Key('people-name-field')), 'Will');
    await tester.tap(find.byKey(const Key('people-name-confirm')));
    await tester.pumpAndSettle();

    expect(notifier.nameIdentityCalls, [('identity_a', 'Will')]);
    // 同身份两个自动候选都被标成 Will；人工改派的 c3 和已命名的 c5 不受影响。
    final candidates = notifier.state.candidates;
    expect(candidates[0]['player_name'], 'Will');
    expect(candidates[1]['player_name'], 'Will');
    expect(candidates[2]['player_name'], 'Max');
    expect(candidates[3]['player_name'], 'Leo');
  });

  testWidgets('待复核筛选隐藏全部已命名组', (tester) async {
    await _pumpPeople(tester);

    expect(find.text('自动推测'), findsOneWidget);
    await tester.tap(
      find.descendant(
        of: find.byKey(const Key('people-filter')),
        matching: find.text('待复核'),
      ),
    );
    await tester.pumpAndSettle();
    // Max / Leo 组全部有归属 → 被过滤掉；只剩 identity_a 自动推测组。
    expect(find.text('Max'), findsNothing);
    expect(find.text('Leo'), findsNothing);
    expect(find.text('自动推测'), findsOneWidget);

    await tester.tap(
      find.descendant(
        of: find.byKey(const Key('people-filter')),
        matching: find.text('已命名'),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('Max'), findsWidgets);
    expect(find.text('Leo'), findsWidgets);
    expect(find.text('自动推测'), findsNothing);
  });

  testWidgets('单条修正：清除改派调用 setCandidatePlayer(id, null)', (tester) async {
    final notifier = await _pumpPeople(tester);

    await tester.tap(find.byKey(const Key('people-candidate-c3')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('清除修正').last);
    await tester.pumpAndSettle();

    expect(notifier.setCandidatePlayerCalls, [('c3', null)]);
  });

  testWidgets('查看投篮片段跳回审核页并请求选中该组第一个候选', (tester) async {
    final notifier = await _pumpPeople(tester);

    await tester.tap(find.byKey(const Key('people-open-identity_a')));
    await tester.pumpAndSettle();

    expect(find.text('review-page'), findsOneWidget);
    expect(notifier.state.reviewFocusCandidateId, 'c1');
  });

  testWidgets('身份组和候选行显示封面，封面取最后触球时刻', (tester) async {
    final notifier = await _pumpPeople(tester, previewPath: coverImagePath);

    // 组封面 + 每条候选的小封面都在。
    expect(find.byKey(const Key('people-group-cover-identity_a')), findsOneWidget);
    expect(find.byKey(const Key('people-cover-c1')), findsOneWidget);
    expect(find.byKey(const Key('people-cover-c2')), findsOneWidget);
    expect(
      find.descendant(
        of: find.byKey(const Key('people-cover-c1')),
        matching: find.byType(Image),
      ),
      findsOneWidget,
    );
    // 封面优先取最后触球时刻（c1: 3000ms 触球，而不是 4200ms 进球）。
    expect(notifier.loadPreviewCalls, contains(('c1', 3000)));
    expect(notifier.loadPreviewCalls, isNot(contains(('c1', 4200))));
  });

  testWidgets('封面不可用时显示占位图而不是报错', (tester) async {
    await _pumpPeople(tester); // previewPath = null

    expect(find.byKey(const Key('people-cover-c1')), findsOneWidget);
    expect(
      find.descendant(
        of: find.byKey(const Key('people-cover-c1')),
        matching: find.byIcon(Icons.person_outline),
      ),
      findsOneWidget,
    );
  });

  testWidgets('点候选行的播放按钮请求审核页播放该候选', (tester) async {
    final notifier = await _pumpPeople(tester);

    await tester.tap(find.byKey(const Key('people-play-c2')));
    await tester.pumpAndSettle();

    expect(find.text('review-page'), findsOneWidget);
    expect(notifier.state.reviewFocusCandidateId, 'c2');
  });

  testWidgets('没有身份识别结果时显示空态提示', (tester) async {
    await _pumpPeople(
      tester,
      state: ProjectState(
        video: const <String, dynamic>{'id': 'v1'},
        job: const <String, dynamic>{'state': 'completed'},
        candidates: const <JsonMap>[
          <String, dynamic>{'id': 'c1', 'touch_time_ms': 1000},
        ],
      ),
    );

    expect(
      find.textContaining('这段视频还没有人物识别结果'),
      findsOneWidget,
    );
    expect(find.byKey(const Key('people-group-list')), findsNothing);
  });

  testWidgets('审核页顶部可切换到人物复核页', (tester) async {
    tester.view.physicalSize = const Size(1400, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final notifier = _PeopleNotifier(_peopleState());
    await tester.pumpWidget(
      ProviderScope(
        overrides: [projectProvider.overrideWith(() => notifier)],
        child: const MaterialApp(home: Scaffold(body: ReviewScreen())),
      ),
    );
    await tester.pumpAndSettle();

    // 默认投篮视图：候选队列在，人物列表不在。
    expect(find.byKey(const Key('people-group-list')), findsNothing);

    await tester.tap(find.text('人物'));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('people-group-list')), findsOneWidget);
    expect(find.text('自动推测'), findsOneWidget);
    // 切回投篮视图。
    await tester.tap(find.text('投篮'));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('people-group-list')), findsNothing);
  });

  testWidgets('审核页消费人物复核页的焦点请求并清除', (tester) async {
    tester.view.physicalSize = const Size(1400, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final notifier = _PeopleNotifier(
      _peopleState().copyWith(reviewFocusCandidateId: 'c2'),
    );
    await tester.pumpWidget(
      ProviderScope(
        overrides: [projectProvider.overrideWith(() => notifier)],
        child: const MaterialApp(home: Scaffold(body: ReviewScreen())),
      ),
    );
    await tester.pumpAndSettle();

    // 焦点请求被消费：不会残留到下次进入审核页。
    expect(notifier.state.reviewFocusCandidateId, isNull);
  });
}
