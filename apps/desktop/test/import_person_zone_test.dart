import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:desktop/features/import_video/import_video_screen.dart';
import 'package:desktop/providers/onboarding_provider.dart';
import 'package:desktop/providers/project_state.dart';

class _PersonZoneNotifier extends ProjectNotifier {
  _PersonZoneNotifier({this.seedPersonRoi});

  final Rect? seedPersonRoi;
  Map<String, dynamic>? savedDraft;

  @override
  ProjectState build() => ProjectState(
    video: const <String, dynamic>{
      'id': 'v1',
      'duration_ms': 60000,
      'width': 1920,
      'height': 1080,
      'source_path': '/tmp/sample.mp4',
    },
    suggestedRoi: const Rect.fromLTWH(0.3, 0.3, 0.4, 0.4),
    netRoi: const Rect.fromLTWH(0.4, 0.1, 0.2, 0.1),
    personRoi: seedPersonRoi,
  );

  @override
  Future<Map<String, dynamic>?> loadWorkflowDraft() async => null;

  @override
  Future<void> saveWorkflowDraft(Map<String, dynamic> draft) async {
    savedDraft = draft;
  }
}

Future<_PersonZoneNotifier> _pumpToDetectionStep(
  WidgetTester tester, {
  Rect? seedPersonRoi,
}) async {
  tester.view.physicalSize = const Size(1400, 1300);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  final notifier = _PersonZoneNotifier(seedPersonRoi: seedPersonRoi);
  final container = ProviderContainer(
    overrides: [projectProvider.overrideWith(() => notifier)],
  );
  addTearDown(container.dispose);

  await tester.pumpWidget(
    UncontrolledProviderScope(
      container: container,
      child: const MaterialApp(home: Scaffold(body: ImportVideoScreen())),
    ),
  );
  await tester.pumpAndSettle();
  await tester.tap(find.textContaining('下一步').last);
  await tester.pumpAndSettle();
  return notifier;
}

void main() {
  // 默认当作已看过引导，免得遮罩挡住别的用例；引导本身在专门的用例里测。
  setUp(
    () => SharedPreferences.setMockInitialValues({
      onboardingStepsPrefsKey: allOnboardingStepIds,
    }),
  );

  testWidgets('检测区域步骤有三个区域按钮，人物区按钮可切换编辑目标', (tester) async {
    await _pumpToDetectionStep(tester);

    expect(find.text('投篮分析区'), findsOneWidget);
    expect(find.text('篮网检测区'), findsOneWidget);
    expect(find.text('人物分析区'), findsOneWidget);
    // 默认编辑投篮区。
    expect(find.textContaining('当前编辑橙色投篮分析区域'), findsOneWidget);

    await tester.ensureVisible(find.text('人物分析区'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('人物分析区'));
    await tester.pumpAndSettle();
    expect(find.textContaining('当前编辑紫色人物分析区域'), findsOneWidget);
    // 恢复按钮文案随目标切换。
    expect(find.text('清除人物区'), findsOneWidget);
  });

  testWidgets('拖动人物区后草稿包含 person_roi 且标记为手动', (tester) async {
    final notifier = await _pumpToDetectionStep(tester);

    await tester.ensureVisible(find.text('人物分析区'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('人物分析区'));
    await tester.pumpAndSettle();
    // 在画布上拖出一个矩形（画布是 AspectRatio 16:9）。
    // 用分步手势：单次大位移不会触发 pan 识别器的 slop 声明。
    final canvas = find.byWidgetPredicate(
      (widget) => widget is GestureDetector && widget.onPanStart != null,
    );
    expect(canvas, findsOneWidget);
    final rect = tester.getRect(canvas);
    final gesture = await tester.startGesture(
      rect.centerLeft + Offset(rect.width * 0.1, 0),
    );
    for (var i = 0; i < 6; i++) {
      await gesture.moveBy(Offset(rect.width * 0.05, rect.height * 0.04));
      await tester.pump(const Duration(milliseconds: 16));
    }
    await gesture.up();
    await tester.pumpAndSettle();
    // 草稿防抖 400ms。
    await tester.pump(const Duration(milliseconds: 600));
    await tester.pumpAndSettle();

    final draft = notifier.savedDraft;
    expect(draft, isNotNull);
    expect(draft!['person_roi_source'], 'manual');
    final personRoi = draft['person_roi'] as Map<String, dynamic>;
    expect((personRoi['x2'] as num) > (personRoi['x1'] as num), isTrue);
    expect((personRoi['y2'] as num) > (personRoi['y1'] as num), isTrue);
    // 投篮区/篮网区不受人物区编辑影响。
    expect(draft.containsKey('roi'), isTrue);
    expect(draft.containsKey('net_roi'), isTrue);
  });

  testWidgets('汇总步骤显示人物分析区状态', (tester) async {
    final notifier = await _pumpToDetectionStep(
      tester,
      seedPersonRoi: const Rect.fromLTWH(0.0, 0.25, 1.0, 0.5),
    );

    await tester.tap(find.textContaining('下一步').last);
    await tester.pumpAndSettle();

    expect(find.text('人物分析区（可选）'), findsOneWidget);
    expect(find.text('已设置'), findsWidgets);
    // 汇总草稿里同样带上人物区，便于离开后再回来恢复。
    await tester.pump(const Duration(milliseconds: 600));
    expect(notifier.savedDraft?['person_roi'], isNotNull);
  });
}
