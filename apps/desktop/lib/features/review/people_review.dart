import '../../core/engine_session.dart' show JsonMap;

/// 人物复核页用到的一个候选的扁平视图。
class PeopleReviewCandidate {
  PeopleReviewCandidate._({
    required this.id,
    required this.touchTimeMs,
    required this.playerId,
    required this.playerName,
    required this.assignmentSource,
    required this.videoId,
    required this.eventTimeMs,
    required this.previewPath,
  });

  factory PeopleReviewCandidate.fromJson(JsonMap candidate) => PeopleReviewCandidate._(
    id: candidate['id']?.toString() ?? '',
    touchTimeMs: (candidate['touch_time_ms'] as num?)?.toInt(),
    playerId: candidate['player_id']?.toString(),
    playerName: candidate['player_name']?.toString(),
    assignmentSource: candidate['assignment_source']?.toString() ?? '',
    videoId: candidate['video_id']?.toString(),
    eventTimeMs: (candidate['event_time_ms'] as num?)?.toInt(),
    previewPath: candidate['preview_path']?.toString(),
  );

  final String id;
  final int? touchTimeMs;
  final String? playerId;
  final String? playerName;
  final String assignmentSource;
  final String? videoId;
  final int? eventTimeMs;

  /// 分析时已生成的候选封面（进球时刻静帧）；可能不存在或已被清理。
  final String? previewPath;

  /// 封面取图时刻：优先最后触球（人持球、最容易认出是谁），否则用进球时刻。
  int? get coverTimeMs => touchTimeMs ?? eventTimeMs;

  /// 人工改派的片段永远优先于自动身份，不会被自动命名覆盖。
  bool get isManuallyAssigned => assignmentSource == 'manual';
}

/// 同一当场身份（identity_id）的一组候选，按触球时间排序。
class PeopleReviewGroup {
  PeopleReviewGroup({required this.identityId, required this.candidates});

  final String identityId;
  final List<PeopleReviewCandidate> candidates;

  int get count => candidates.length;

  int? get firstTouchTimeMs => candidates.first.touchTimeMs;

  /// 组内第一个已被命名/改派的球员名；没有人命名过时为 null。
  String? get playerName {
    for (final candidate in candidates) {
      final name = candidate.playerName;
      if (name != null && name.isNotEmpty) return name;
    }
    return null;
  }

  bool get hasNamedPlayer => candidates.any((c) => c.playerId != null);

  /// 还有候选没有归属球员 → 命名传播后仍待人工看一眼。
  bool get needsReview => candidates.any((c) => c.playerId == null);

  bool get hasManualAssignment =>
      candidates.any((c) => c.isManuallyAssigned);
}

/// 把候选按 identity_id 分组：组间按最早触球时间排序，组内按触球时间排序。
/// 没有 identity_id 的候选（身份分析未覆盖）不进人物复核页。
List<PeopleReviewGroup> buildPeopleReviewGroups(List<JsonMap> candidates) {
  final byIdentity = <String, List<PeopleReviewCandidate>>{};
  for (final raw in candidates) {
    final identityId = raw['identity_id']?.toString();
    if (identityId == null || identityId.isEmpty) continue;
    byIdentity
        .putIfAbsent(identityId, () => <PeopleReviewCandidate>[])
        .add(PeopleReviewCandidate.fromJson(raw));
  }
  final groups = <PeopleReviewGroup>[
    for (final entry in byIdentity.entries)
      PeopleReviewGroup(
        identityId: entry.key,
        candidates: entry.value
          ..sort(
            (a, b) => (a.touchTimeMs ?? 0).compareTo(b.touchTimeMs ?? 0),
          ),
      ),
  ];
  groups.sort(
    (a, b) => (a.firstTouchTimeMs ?? 0).compareTo(b.firstTouchTimeMs ?? 0),
  );
  return groups;
}

String formatTouchTime(int? touchTimeMs) {
  if (touchTimeMs == null) return '时间未知';
  final totalSeconds = touchTimeMs / 1000;
  final minutes = totalSeconds ~/ 60;
  final seconds = (totalSeconds % 60).toStringAsFixed(1).padLeft(4, '0');
  return '$minutes:$seconds';
}
