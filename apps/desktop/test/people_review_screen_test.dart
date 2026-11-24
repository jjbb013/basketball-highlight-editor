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

  @override
  ProjectState build() => initialState;

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
    },
    <String, dynamic>{
      'id': 'c2',
      'identity_id': 'identity_a',
      'touch_time_ms': 9000,
    },
    <String, dynamic>{
      'id': 'c3',
      'identity_id': 'identity_b',
      'touch_time_ms': 5000,
      'player_id': 'p9',
      'player_name': 'Max',
      'assignment_source': 'manual',
    },
    <String, dynamic>{
      'id': 'c5',
      'identity_id': 'identity_c',
      'touch_time_ms': 7000,
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
}) async {
  tester.view.physicalSize = const Size(1400, 900);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  final notifier = _PeopleNotifier(state ?? _peopleState());
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

  testWidgets('查看投篮片段跳回审核页', (tester) async {
    await _pumpPeople(tester);

    await tester.tap(find.byKey(const Key('people-open-identity_a')));
    await tester.pumpAndSettle();

    expect(find.text('review-page'), findsOneWidget);
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
}
