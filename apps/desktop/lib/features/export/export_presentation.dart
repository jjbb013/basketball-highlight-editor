import 'package:bhe_l10n/bhe_l10n.dart';
import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/native_file_dialog.dart';
import '../../theme/tokens.dart';

Map<String, dynamic> defaultExportPresentation() => <String, dynamic>{
  'cover': <String, dynamic>{
    'enabled': true,
    'duration_ms': 3000,
    'style': 'court',
    'title': null,
    'subtitle': null,
    'background_path': null,
    'accent_color': '#F97316',
  },
  'audio': <String, dynamic>{
    'enabled': true,
    'track': 'electronic_drive',
    'custom_path': null,
    'volume': 0.2,
  },
};

Map<String, dynamic> updateExportPresentation(
  Map<String, dynamic> value, {
  Map<String, dynamic>? cover,
  Map<String, dynamic>? audio,
}) => <String, dynamic>{
  'cover': <String, dynamic>{...value['cover'] as Map, ...?cover},
  'audio': <String, dynamic>{...value['audio'] as Map, ...?audio},
};

final presentationAssetPickerProvider = Provider<PresentationAssetPicker>(
  (ref) => PresentationAssetPicker(),
);

class PresentationAssetPicker {
  Future<String?> image() async {
    await prepareFileDialog();
    final file = await openFile(
      acceptedTypeGroups: const [
        XTypeGroup(label: 'Images', extensions: ['jpg', 'jpeg', 'png', 'webp']),
      ],
    );
    return file?.path;
  }

  Future<String?> audio() async {
    await prepareFileDialog();
    final file = await openFile(
      acceptedTypeGroups: const [
        XTypeGroup(
          label: 'Audio',
          extensions: ['wav', 'mp3', 'm4a', 'aac', 'flac', 'ogg'],
        ),
      ],
    );
    return file?.path;
  }
}

final exportSourcePickerProvider = Provider<ExportSourcePicker>(
  (ref) => ExportSourcePicker(),
);

class ExportSourcePicker {
  Future<String?> projectDirectory({required String confirmLabel}) async {
    await prepareFileDialog();
    return getDirectoryPath(confirmButtonText: confirmLabel);
  }
}

class ExportPresentationPanel extends ConsumerWidget {
  const ExportPresentationPanel({
    required this.value,
    required this.onChanged,
    super.key,
  });

  final Map<String, dynamic> value;
  final ValueChanged<Map<String, dynamic>> onChanged;

  Map<String, dynamic> get _cover => value['cover'] as Map<String, dynamic>;
  Map<String, dynamic> get _audio => value['audio'] as Map<String, dynamic>;

  void _coverUpdate(String key, Object? next) {
    onChanged(updateExportPresentation(value, cover: {key: next}));
  }

  void _audioUpdate(String key, Object? next) {
    onChanged(updateExportPresentation(value, audio: {key: next}));
  }

  Future<void> _pickBackground(WidgetRef ref) async {
    final path = await ref.read(presentationAssetPickerProvider).image();
    if (path != null) _coverUpdate('background_path', path);
  }

  Future<void> _pickAudio(WidgetRef ref) async {
    final path = await ref.read(presentationAssetPickerProvider).audio();
    if (path != null) _audioUpdate('custom_path', path);
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final coverEnabled = _cover['enabled'] == true;
    final audioEnabled = _audio['enabled'] == true;
    final durationMs = _cover['duration_ms'] as int? ?? 3000;
    final volume = (_audio['volume'] as num?)?.toDouble() ?? 0.2;
    final background = _cover['background_path']?.toString();
    final customAudio = _audio['custom_path']?.toString();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _PresentationToggle(
          switchKey: const Key('export-cover-enabled'),
          title: context.bheText('添加人物封面'),
          subtitle: context.bheText('合并后的视频只添加一次封面'),
          value: coverEnabled,
          onChanged: (next) => _coverUpdate('enabled', next),
        ),
        Row(
          children: [
            Expanded(
              child: DropdownButtonFormField<String>(
                key: const Key('export-cover-style'),
                initialValue: _cover['style']?.toString() ?? 'court',
                decoration: InputDecoration(labelText: context.bheText('封面样式')),
                items: [
                  DropdownMenuItem(
                    value: 'court',
                    child: Text(context.bheText('球场')),
                  ),
                  DropdownMenuItem(
                    value: 'poster',
                    child: Text(context.bheText('海报')),
                  ),
                  DropdownMenuItem(
                    value: 'photo',
                    child: Text(context.bheText('照片')),
                  ),
                ],
                onChanged: (next) {
                  if (next != null) _coverUpdate('style', next);
                },
              ),
            ),
            const SizedBox(width: Spacing.md),
            Expanded(
              child: TextFormField(
                key: const Key('export-cover-accent'),
                initialValue: _cover['accent_color']?.toString() ?? '#F97316',
                decoration: InputDecoration(
                  labelText: context.bheText('强调色（HEX）'),
                ),
                onChanged: (next) => _coverUpdate('accent_color', next),
              ),
            ),
          ],
        ),
        const SizedBox(height: Spacing.sm),
        Text(context.bheText('封面时长 ${(durationMs / 1000).round()} 秒')),
        Slider(
          key: const Key('export-cover-duration'),
          min: 0,
          max: 10,
          divisions: 10,
          label: '${(durationMs / 1000).round()} s',
          value: durationMs / 1000,
          onChanged: (next) =>
              _coverUpdate('duration_ms', (next * 1000).round()),
        ),
        TextFormField(
          key: const Key('export-cover-title'),
          initialValue: _cover['title']?.toString(),
          decoration: InputDecoration(
            labelText: context.bheText('自定义标题（留空使用球员名）'),
          ),
          onChanged: (next) =>
              _coverUpdate('title', next.trim().isEmpty ? null : next),
        ),
        const SizedBox(height: Spacing.sm),
        TextFormField(
          key: const Key('export-cover-subtitle'),
          initialValue: _cover['subtitle']?.toString(),
          decoration: InputDecoration(labelText: context.bheText('自定义副标题')),
          onChanged: (next) =>
              _coverUpdate('subtitle', next.trim().isEmpty ? null : next),
        ),
        const SizedBox(height: Spacing.sm),
        Wrap(
          spacing: Spacing.sm,
          runSpacing: Spacing.xs,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            OutlinedButton.icon(
              key: const Key('export-cover-background'),
              onPressed: () => _pickBackground(ref),
              icon: const Icon(Icons.image_outlined),
              label: Text(context.bheText('选择封面背景图')),
            ),
            if (background != null) ...[
              Flexible(
                child: Text(
                  _fileName(background),
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              IconButton(
                key: const Key('export-clear-cover-background'),
                tooltip: context.bheText('清除背景图'),
                onPressed: () => _coverUpdate('background_path', null),
                icon: const Icon(Icons.close),
              ),
            ],
          ],
        ),
        const Divider(height: Spacing.xl),
        _PresentationToggle(
          switchKey: const Key('export-audio-enabled'),
          title: context.bheText('添加运动背景音乐'),
          subtitle: context.bheText('保留现场原声，背景音乐默认 20% 音量'),
          value: audioEnabled,
          onChanged: (next) => _audioUpdate('enabled', next),
        ),
        DropdownButtonFormField<String>(
          key: const Key('export-bgm-track'),
          initialValue: _audio['track']?.toString() ?? 'electronic_drive',
          decoration: InputDecoration(labelText: context.bheText('音乐类型')),
          items: const [
            DropdownMenuItem(
              value: 'electronic_drive',
              child: Text('Electronic drive'),
            ),
            DropdownMenuItem(
              value: 'hip_hop_bounce',
              child: Text('Hip-hop bounce'),
            ),
            DropdownMenuItem(value: 'rock_pulse', child: Text('Rock pulse')),
          ],
          onChanged: (next) {
            if (next != null) {
              onChanged(
                updateExportPresentation(
                  value,
                  audio: {'track': next, 'custom_path': null},
                ),
              );
            }
          },
        ),
        const SizedBox(height: Spacing.sm),
        Wrap(
          spacing: Spacing.sm,
          runSpacing: Spacing.xs,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            OutlinedButton.icon(
              key: const Key('export-custom-bgm'),
              onPressed: () => _pickAudio(ref),
              icon: const Icon(Icons.music_note_outlined),
              label: Text(context.bheText('选择本地音乐')),
            ),
            if (customAudio != null) ...[
              Flexible(
                child: Text(
                  _fileName(customAudio),
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              IconButton(
                key: const Key('export-clear-custom-bgm'),
                tooltip: context.bheText('清除本地音乐'),
                onPressed: () => _audioUpdate('custom_path', null),
                icon: const Icon(Icons.close),
              ),
            ],
          ],
        ),
        Text(context.bheText('背景音乐音量 ${(volume * 100).round()}%')),
        Slider(
          key: const Key('export-bgm-volume'),
          min: 0,
          max: 1,
          divisions: 20,
          label: '${(volume * 100).round()}%',
          value: volume,
          onChanged: (next) => _audioUpdate('volume', next),
        ),
      ],
    );
  }
}

class _PresentationToggle extends StatelessWidget {
  const _PresentationToggle({
    required this.switchKey,
    required this.title,
    required this.subtitle,
    required this.value,
    required this.onChanged,
  });

  final Key switchKey;
  final String title;
  final String subtitle;
  final bool value;
  final ValueChanged<bool> onChanged;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(title, style: Theme.of(context).textTheme.bodyLarge),
              const SizedBox(height: 4),
              Text(subtitle, style: Theme.of(context).textTheme.bodySmall),
            ],
          ),
        ),
        Switch(key: switchKey, value: value, onChanged: onChanged),
      ],
    );
  }
}

class ExportProjectSources extends ConsumerWidget {
  const ExportProjectSources({
    required this.roots,
    required this.onChanged,
    super.key,
  });

  final List<String> roots;
  final ValueChanged<List<String>> onChanged;

  Future<void> _add(WidgetRef ref) async {
    final path = await ref
        .read(exportSourcePickerProvider)
        .projectDirectory(confirmLabel: 'Select project');
    if (path != null && !roots.contains(path)) onChanged([...roots, path]);
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          context.bheText('可把不同日期的同名球员一起导出；历史项目只读，不会被修改。'),
          style: Theme.of(context).textTheme.bodySmall,
        ),
        const SizedBox(height: Spacing.sm),
        Wrap(
          spacing: Spacing.sm,
          runSpacing: Spacing.sm,
          children: [
            for (var index = 0; index < roots.length; index++)
              Tooltip(
                message: roots[index],
                child: InputChip(
                  label: Text(_fileName(roots[index])),
                  onDeleted: () => onChanged([...roots]..removeAt(index)),
                  deleteIcon: const Icon(Icons.close),
                  key: Key('export-remove-source-project-$index'),
                ),
              ),
            OutlinedButton.icon(
              key: const Key('export-add-source-project'),
              onPressed: roots.length >= 15 ? null : () => _add(ref),
              icon: const Icon(Icons.create_new_folder_outlined),
              label: Text(context.bheText('添加历史项目')),
            ),
          ],
        ),
      ],
    );
  }
}

String _fileName(String path) =>
    path.split(RegExp(r'[/\\]')).where((part) => part.isNotEmpty).lastOrNull ??
    path;
