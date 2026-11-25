import 'package:flutter_test/flutter_test.dart';

import 'package:desktop/core/engine_session.dart' show JsonMap;
import 'package:desktop/features/review/people_review.dart';

JsonMap _candidate({
  required String id,
  String? identityId,
  int? touchMs,
  String? playerId,
  String? playerName,
  String assignmentSource = 'auto',
  String? videoId,
  int? eventMs,
  String? previewPath,
}) => <String, dynamic>{
  'id': id,
  if (identityId != null) 'identity_id': identityId,
  if (touchMs != null) 'touch_time_ms': touchMs,
  if (playerId != null) 'player_id': playerId,
  if (playerName != null) 'player_name': playerName,
  'assignment_source': assignmentSource,
  if (videoId != null) 'video_id': videoId,
  if (eventMs != null) 'event_time_ms': eventMs,
  if (previewPath != null) 'preview_path': previewPath,
};

void main() {
  test('按 identity_id 分组，组间按最早触球排序，组内按触球排序', () {
    final groups = buildPeopleReviewGroups([
      _candidate(id: 'c1', identityId: 'identity_b', touchMs: 5000),
      _candidate(id: 'c2', identityId: 'identity_a', touchMs: 9000),
      _candidate(id: 'c3', identityId: 'identity_a', touchMs: 3000),
      _candidate(id: 'c4', identityId: 'identity_b', touchMs: 7000),
    ]);

    expect(groups.map((g) => g.identityId), ['identity_a', 'identity_b']);
    expect(groups[0].candidates.map((c) => c.id), ['c3', 'c2']);
    expect(groups[1].candidates.map((c) => c.id), ['c1', 'c4']);
  });

  test('没有 identity_id 的候选不进入人物复核页', () {
    final groups = buildPeopleReviewGroups([
      _candidate(id: 'c1', touchMs: 1000),
      _candidate(id: 'c2', identityId: '', touchMs: 2000),
      _candidate(id: 'c3', identityId: 'identity_a', touchMs: 3000),
    ]);
    expect(groups, hasLength(1));
    expect(groups.single.identityId, 'identity_a');
  });

  test('组显示第一个已命名球员；未命名组待复核', () {
    final groups = buildPeopleReviewGroups([
      _candidate(
        id: 'c1',
        identityId: 'identity_a',
        touchMs: 1000,
        playerId: 'p1',
        playerName: 'Will',
      ),
      _candidate(id: 'c2', identityId: 'identity_a', touchMs: 2000),
      _candidate(id: 'c3', identityId: 'identity_b', touchMs: 3000),
    ]);

    expect(groups[0].playerName, 'Will');
    expect(groups[0].hasNamedPlayer, isTrue);
    expect(groups[0].needsReview, isTrue); // c2 还没有归属
    expect(groups[1].playerName, isNull);
    expect(groups[1].needsReview, isTrue);
  });

  test('人工改派的片段标记为 manual', () {
    final groups = buildPeopleReviewGroups([
      _candidate(
        id: 'c1',
        identityId: 'identity_a',
        touchMs: 1000,
        playerId: 'p9',
        playerName: 'Leo',
        assignmentSource: 'manual',
      ),
    ]);
    expect(groups.single.hasManualAssignment, isTrue);
    expect(groups.single.candidates.single.isManuallyAssigned, isTrue);
  });

  test('formatTouchTime 输出分:秒', () {
    expect(formatTouchTime(65_200), '1:05.2');
    expect(formatTouchTime(null), '时间未知');
  });

  test('封面时刻优先取最后触球，缺触球时回退进球时刻', () {
    final groups = buildPeopleReviewGroups([
      _candidate(
        id: 'c1',
        identityId: 'identity_a',
        touchMs: 3000,
        eventMs: 5000,
        videoId: 'v1',
        previewPath: '/tmp/c1.jpg',
      ),
      _candidate(id: 'c2', identityId: 'identity_a', eventMs: 8000),
    ]);

    final byId = {
      for (final candidate in groups.single.candidates) candidate.id: candidate,
    };
    expect(byId['c1']!.coverTimeMs, 3000);
    expect(byId['c1']!.videoId, 'v1');
    expect(byId['c1']!.previewPath, '/tmp/c1.jpg');
    expect(byId['c2']!.coverTimeMs, 8000);
    expect(byId['c2']!.previewPath, isNull);
  });
}
