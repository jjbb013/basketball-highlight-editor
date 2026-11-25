import 'dart:async';

import 'package:bhe_l10n/bhe_l10n.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/engine_session.dart' show JsonMap;
import '../../providers/project_state.dart';
import '../../theme/app_colors.dart';
import '../../theme/tokens.dart';
import 'candidate_cover.dart';
import 'people_review.dart';

enum _PeopleFilter { all, review, named }

/// 人物复核页：按当场身份（identity_id）分组 review 自动识别结果。
///
/// 命名走 [ProjectNotifier.nameIdentity]：同名身份的自动候选一次性标成该球员，
/// 人工改派的片段不会被覆盖。单条修正走 [ProjectNotifier.setCandidatePlayer]。
class PeopleReviewScreen extends ConsumerStatefulWidget {
  const PeopleReviewScreen({super.key});

  @override
  ConsumerState<PeopleReviewScreen> createState() =>
      _PeopleReviewScreenState();
}

class _PeopleReviewScreenState extends ConsumerState<PeopleReviewScreen> {
  _PeopleFilter _filter = _PeopleFilter.all;

  /// 封面加载与审核页同一套边界：最多 2 个并发，结果按候选+时刻缓存。
  final Map<String, Future<String?>> _coverCache = <String, Future<String?>>{};
  final List<Future<void> Function()> _coverQueue = <Future<void> Function()>[];
  int _activeCoverLoads = 0;

  @override
  void dispose() {
    _coverQueue.clear();
    _coverCache.clear();
    super.dispose();
  }

  Future<String?> _loadCover(PeopleReviewCandidate candidate) {
    final timeMs = candidate.coverTimeMs ?? 0;
    final key = '${candidate.id}:$timeMs';
    return _coverCache.putIfAbsent(key, () {
      final completer = Completer<String?>();
      _coverQueue.add(() async {
        if (!mounted) {
          completer.complete(null);
          return;
        }
        try {
          final path = await ref
              .read(projectProvider.notifier)
              .loadCandidatePreview(candidate.id, timeMs);
          if (!completer.isCompleted) completer.complete(path);
        } catch (_) {
          // 封面只是复核辅助：引擎忙或取图失败时显示占位图，不影响命名与修正。
          if (!completer.isCompleted) completer.complete(null);
        }
      });
      _drainCoverQueue();
      return completer.future;
    });
  }

  void _drainCoverQueue() {
    if (!mounted) {
      _coverQueue.clear();
      return;
    }
    while (_activeCoverLoads < 2 && _coverQueue.isNotEmpty) {
      final request = _coverQueue.removeAt(0);
      _activeCoverLoads++;
      unawaited(
        request().whenComplete(() {
          _activeCoverLoads--;
          _drainCoverQueue();
        }),
      );
    }
  }

  /// 跳到投篮审核并选中该候选，审核页会自动播放对应片段。
  void _openCandidate(PeopleReviewCandidate candidate) {
    if (candidate.id.isEmpty) return;
    ref.read(projectProvider.notifier).requestReviewFocus(candidate.id);
    context.go('/review');
  }

  Future<void> _nameGroup(PeopleReviewGroup group) async {
    final name = await showDialog<String>(
      context: context,
      builder: (_) => const _PeopleNameDialog(),
    );
    if (!mounted || name == null || name.isEmpty) return;
    await ref
        .read(projectProvider.notifier)
        .nameIdentity(group.identityId, name);
  }

  Future<void> _applyCandidateValue(
    PeopleReviewCandidate candidate,
    String value,
  ) async {
    // 空值表示「清除修正」，恢复为自动归属。
    await ref
        .read(projectProvider.notifier)
        .setCandidatePlayer(candidate.id, value.isEmpty ? null : value);
  }

  @override
  Widget build(BuildContext context) {
    final c = AppColors.of(context);
    final state = ref.watch(projectProvider);
    final allGroups = buildPeopleReviewGroups(state.candidates);
    final groups = switch (_filter) {
      _PeopleFilter.all => allGroups,
      _PeopleFilter.review => allGroups.where((g) => g.needsReview).toList(),
      _PeopleFilter.named => allGroups.where((g) => g.hasNamedPlayer).toList(),
    };
    final busy = state.busy || state.hydrating;

    return Padding(
      padding: const EdgeInsets.symmetric(
        horizontal: Spacing.xl,
        vertical: Spacing.md,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Wrap(
            spacing: Spacing.sm,
            runSpacing: Spacing.xs,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              SegmentedButton<_PeopleFilter>(
                key: const Key('people-filter'),
                showSelectedIcon: false,
                style: const ButtonStyle(
                  visualDensity: VisualDensity.compact,
                ),
                segments: [
                  ButtonSegment(
                    value: _PeopleFilter.all,
                    label: Text(context.bheText('全部身份')),
                  ),
                  ButtonSegment(
                    value: _PeopleFilter.review,
                    label: Text(context.bheText('待复核')),
                  ),
                  ButtonSegment(
                    value: _PeopleFilter.named,
                    label: Text(context.bheText('已命名')),
                  ),
                ],
                selected: {_filter},
                onSelectionChanged: busy
                    ? null
                    : (selection) =>
                          setState(() => _filter = selection.first),
              ),
              Text(
                context.bheText(
                  '自动按当场外观（体型、发型、衣着）分组，命名后会标出同身份的进球；请人工复核后再导出。',
                ),
                style: Theme.of(context).textTheme.bodySmall?.copyWith(
                  color: c.textSecondary,
                ),
              ),
            ],
          ),
          const SizedBox(height: Spacing.sm),
          Expanded(
            child: allGroups.isEmpty
                ? Center(
                    child: Text(
                      context.bheText(
                        '这段视频还没有人物识别结果。分析时开启人物识别后，这里会按身份分组展示。',
                      ),
                      style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                        color: c.textSecondary,
                      ),
                    ),
                  )
                : groups.isEmpty
                ? Center(
                    child: Text(
                      context.bheText('当前筛选下没有身份组。'),
                      style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                        color: c.textSecondary,
                      ),
                    ),
                  )
                : ListView.separated(
                    key: const Key('people-group-list'),
                    itemCount: groups.length,
                    separatorBuilder: (_, _) => const SizedBox(
                      height: Spacing.sm,
                    ),
                    itemBuilder: (context, index) => _PeopleGroupCard(
                      group: groups[index],
                      players: state.players,
                      busy: busy,
                      onName: () => _nameGroup(groups[index]),
                      coverLoader: _loadCover,
                      onOpenCandidate: _openCandidate,
                      onReassignCandidate: _applyCandidateValue,
                    ),
                  ),
          ),
        ],
      ),
    );
  }
}

class _PeopleGroupCard extends StatelessWidget {
  const _PeopleGroupCard({
    required this.group,
    required this.players,
    required this.busy,
    required this.onName,
    required this.coverLoader,
    required this.onOpenCandidate,
    required this.onReassignCandidate,
  });

  final PeopleReviewGroup group;
  final List<JsonMap> players;
  final bool busy;
  final VoidCallback onName;
  final Future<String?> Function(PeopleReviewCandidate candidate) coverLoader;
  final void Function(PeopleReviewCandidate candidate) onOpenCandidate;
  final void Function(PeopleReviewCandidate candidate, String value)
  onReassignCandidate;

  @override
  Widget build(BuildContext context) {
    final c = AppColors.of(context);
    final theme = Theme.of(context);
    final name = group.playerName;
    final title = name ?? context.bheText('自动推测');
    final firstTouch = group.firstTouchTimeMs;
    final lastTouch = group.candidates.last.touchTimeMs;

    return Container(
      decoration: BoxDecoration(
        color: c.surface,
        borderRadius: BorderRadius.circular(CsRadius.lg),
        border: Border.all(color: c.border),
      ),
      padding: const EdgeInsets.symmetric(
        horizontal: Spacing.md,
        vertical: Spacing.sm,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              CandidateCover(
                key: Key('people-group-cover-${group.identityId}'),
                future: coverLoader(group.candidates.first),
              ),
              const SizedBox(width: Spacing.sm),
              Container(
                width: 26,
                height: 26,
                alignment: Alignment.center,
                decoration: BoxDecoration(
                  color: (name == null ? c.orange : c.goal)
                      .withValues(alpha: 0.14),
                  borderRadius: BorderRadius.circular(CsRadius.sm),
                ),
                child: Icon(
                  name == null
                      ? Icons.person_search_rounded
                      : Icons.person_pin_outlined,
                  size: 15,
                  color: name == null ? c.orange : c.goal,
                ),
              ),
              const SizedBox(width: Spacing.sm),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Flexible(
                          child: Text(
                            title,
                            style: theme.textTheme.titleSmall?.copyWith(
                              fontWeight: FontWeight.w600,
                            ),
                            overflow: TextOverflow.ellipsis,
                          ),
                        ),
                        if (name == null) ...[
                          const SizedBox(width: Spacing.xs),
                          Text(
                            context.bheText('身份待复核'),
                            style: theme.textTheme.labelSmall?.copyWith(
                              color: c.orange,
                            ),
                          ),
                        ],
                        if (group.hasManualAssignment) ...[
                          const SizedBox(width: Spacing.xs),
                          Text(
                            context.bheText('含人工标记'),
                            style: theme.textTheme.labelSmall?.copyWith(
                              color: c.textTertiary,
                            ),
                          ),
                        ],
                      ],
                    ),
                    Text(
                      context.bheText(
                        '${group.count} 个进球 · 触球 ${formatTouchTime(firstTouch)}'
                        '${lastTouch != firstTouch ? ' ~ ${formatTouchTime(lastTouch)}' : ''}',
                      ),
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: c.textSecondary,
                      ),
                    ),
                  ],
                ),
              ),
              TextButton.icon(
                key: Key('people-name-${group.identityId}'),
                onPressed: busy ? null : onName,
                icon: const Icon(Icons.label_outline, size: 15),
                label: Text(
                  context.bheText(name == null ? '命名为球员' : '重命名'),
                  style: const TextStyle(fontSize: 12),
                ),
              ),
              TextButton.icon(
                key: Key('people-open-${group.identityId}'),
                onPressed: () => onOpenCandidate(group.candidates.first),
                icon: const Icon(Icons.play_circle_outline, size: 15),
                label: Text(
                  context.bheText('查看投篮片段'),
                  style: const TextStyle(fontSize: 12),
                ),
              ),
            ],
          ),
          const Divider(height: 1),
          for (final candidate in group.candidates)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 2),
              child: Row(
                children: [
                  GestureDetector(
                    onTap: () => onOpenCandidate(candidate),
                    child: CandidateCover(
                      key: Key('people-cover-${candidate.id}'),
                      future: coverLoader(candidate),
                      width: 64,
                      height: 36,
                    ),
                  ),
                  const SizedBox(width: Spacing.sm),
                  Icon(
                    candidate.isManuallyAssigned
                        ? Icons.person_pin_outlined
                        : Icons.sports_basketball_outlined,
                    size: 13,
                    color: c.textTertiary,
                  ),
                  const SizedBox(width: Spacing.xs),
                  Text(
                    context.bheText('触球 ${formatTouchTime(candidate.touchTimeMs)}'),
                    style: theme.textTheme.bodySmall,
                  ),
                  const Spacer(),
                  Text(
                    candidate.playerName ??
                        context.bheText('待复核'),
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: candidate.playerName == null
                          ? c.orange
                          : c.textSecondary,
                    ),
                  ),
                  IconButton(
                    key: Key('people-play-${candidate.id}'),
                    onPressed: () => onOpenCandidate(candidate),
                    icon: const Icon(Icons.play_circle_outline, size: 16),
                    color: c.textSecondary,
                    tooltip: context.bheText('播放此片段'),
                    visualDensity: VisualDensity.compact,
                    constraints: const BoxConstraints(
                      minWidth: 28,
                      minHeight: 28,
                    ),
                    padding: EdgeInsets.zero,
                  ),
                  PopupMenuButton<String>(
                    key: Key('people-candidate-${candidate.id}'),
                    icon: Icon(
                      Icons.tune_rounded,
                      size: 15,
                      color: c.textSecondary,
                    ),
                    tooltip: context.bheText('修正此条'),
                    onSelected: (value) => onReassignCandidate(candidate, value),
                    itemBuilder: (menuContext) => [
                      for (final player in players)
                        PopupMenuItem(
                          value: player['id']?.toString() ?? '',
                          child: Text(player['name']?.toString() ?? ''),
                        ),
                      PopupMenuItem(
                        value: '',
                        child: Text(context.bheText('清除修正')),
                      ),
                    ],
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }
}

class _PeopleNameDialog extends StatefulWidget {
  const _PeopleNameDialog();

  @override
  State<_PeopleNameDialog> createState() => _PeopleNameDialogState();
}

class _PeopleNameDialogState extends State<_PeopleNameDialog> {
  final _controller = TextEditingController();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Text(context.bheText('命名为球员')),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            context.bheText(
              '将这一当场身份的所有自动进球标记为同一名球员；人工改派的片段不会被覆盖。',
            ),
          ),
          const SizedBox(height: Spacing.md),
          TextField(
            key: const Key('people-name-field'),
            controller: _controller,
            autofocus: true,
            maxLength: 40,
            decoration: InputDecoration(
              hintText: context.bheText('例如：Will'),
            ),
            onSubmitted: (value) => Navigator.pop(context, value.trim()),
          ),
        ],
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: Text(context.bheText('取消')),
        ),
        FilledButton(
          key: const Key('people-name-confirm'),
          onPressed: () => Navigator.pop(context, _controller.text.trim()),
          child: Text(context.bheText('确认命名')),
        ),
      ],
    );
  }
}
