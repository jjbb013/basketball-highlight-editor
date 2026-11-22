import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../providers/project_state.dart';
import '../../theme/app_colors.dart';
import '../../theme/tokens.dart';

Map<String, dynamic>? _identityEvidence(Map<String, dynamic> candidate) {
  final raw = candidate['identity_evidence_json'];
  try {
    final decoded = raw is String ? jsonDecode(raw) : raw;
    return decoded is Map ? decoded.cast<String, dynamic>() : null;
  } on FormatException {
    return null;
  }
}

/// Same-game appearance evidence, never a cross-day biometric assertion.
class IdentityReviewChip extends ConsumerWidget {
  const IdentityReviewChip({
    required this.candidate,
    this.onNameIdentity,
    super.key,
  });

  final Map<String, dynamic> candidate;
  final Future<void> Function(String identityId, String playerName)?
  onNameIdentity;

  Future<void> _promptAndName(
    BuildContext context,
    WidgetRef ref,
    String identityId,
  ) async {
    final name = await showDialog<String>(
      context: context,
      builder: (_) => const _IdentityNameDialog(),
    );
    if (!context.mounted || name == null || name.isEmpty) return;
    final save =
        onNameIdentity ??
        (String id, String playerName) =>
            ref.read(projectProvider.notifier).nameIdentity(id, playerName);
    await save(identityId, name);
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final identityId = candidate['identity_id']?.toString();
    final evidence = _identityEvidence(candidate);
    if (identityId == null || identityId.isEmpty || evidence == null) {
      return const SizedBox.shrink();
    }
    final isManual = candidate['assignment_source'] == 'manual';
    final identity = evidence['identity'];
    final needsReview =
        evidence['needs_review'] == true ||
        (identity is Map && identity['needs_review'] == true);
    final label = isManual
        ? '人工标记优先'
        : needsReview
        ? '身份待复核'
        : '同身份自动推测';
    final touchMs = candidate['touch_time_ms'];
    final confidence = candidate['identity_confidence'];
    final c = AppColors.of(context);
    return Tooltip(
      message: '依据当场外观和最后触球关联，不是跨天生物识别；证据不足时请人工复核。',
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
        decoration: BoxDecoration(
          color: c.surface2,
          borderRadius: BorderRadius.circular(CsRadius.sm),
          border: Border.all(color: c.border),
        ),
        child: Wrap(
          spacing: 8,
          runSpacing: 2,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(
                  isManual
                      ? Icons.person_pin_outlined
                      : Icons.person_search_rounded,
                  size: 14,
                  color: needsReview && !isManual ? c.orange : c.textSecondary,
                ),
                const SizedBox(width: 4),
                Text(
                  label,
                  style: TextStyle(fontSize: 11, color: c.textSecondary),
                ),
              ],
            ),
            if (touchMs is num)
              Text(
                '最后触球 ${(touchMs / 1000).toStringAsFixed(2)} 秒',
                style: TextStyle(fontSize: 11, color: c.textTertiary),
              ),
            if (!isManual && !needsReview && confidence is num)
              Text(
                '身份置信度 ${(confidence * 100).round()}%',
                style: TextStyle(fontSize: 11, color: c.textTertiary),
              ),
            if (!isManual)
              TextButton.icon(
                key: const Key('name-identity-button'),
                onPressed: () => _promptAndName(context, ref, identityId),
                icon: const Icon(Icons.label_outline, size: 14),
                label: const Text('命名此身份'),
                style: TextButton.styleFrom(
                  padding: const EdgeInsets.symmetric(horizontal: 4),
                  minimumSize: const Size(0, 28),
                  tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                  textStyle: const TextStyle(fontSize: 11),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class _IdentityNameDialog extends StatefulWidget {
  const _IdentityNameDialog();

  @override
  State<_IdentityNameDialog> createState() => _IdentityNameDialogState();
}

class _IdentityNameDialogState extends State<_IdentityNameDialog> {
  final _controller = TextEditingController();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('命名此身份'),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text('将同一当场身份的自动候选标记为同一球员；人工改派的片段不会被覆盖。'),
          const SizedBox(height: Spacing.md),
          TextField(
            key: const Key('identity-name-field'),
            controller: _controller,
            autofocus: true,
            maxLength: 40,
            decoration: const InputDecoration(hintText: '例如：Will'),
            onSubmitted: (value) => Navigator.pop(context, value.trim()),
          ),
        ],
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('取消'),
        ),
        FilledButton(
          key: const Key('confirm-identity-name'),
          onPressed: () => Navigator.pop(context, _controller.text.trim()),
          child: const Text('确认命名'),
        ),
      ],
    );
  }
}
