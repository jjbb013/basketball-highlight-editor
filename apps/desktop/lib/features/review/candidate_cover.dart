import 'dart:io';

import 'package:flutter/material.dart';

import '../../theme/app_colors.dart';
import '../../theme/tokens.dart';

/// 候选封面缩略图：渲染 [future] 给出的本地图片路径。
///
/// 加载中、无路径或图片解码失败时都显示人物占位图标；封面只是复核辅助，
/// 永远不因为缺图阻断页面。调用方负责用有界并发加载（参考审核页预览队列）。
class CandidateCover extends StatelessWidget {
  const CandidateCover({required this.future, super.key, this.width = 96, this.height = 56});

  final Future<String?>? future;
  final double width;
  final double height;

  @override
  Widget build(BuildContext context) {
    final c = AppColors.of(context);
    return FutureBuilder<String?>(
      future: future,
      builder: (context, snapshot) {
        final path = snapshot.data;
        return SizedBox(
          width: width,
          height: height,
          child: ClipRRect(
            borderRadius: BorderRadius.circular(CsRadius.sm),
            child: path != null
                ? Image.file(
                    File(path),
                    fit: BoxFit.cover,
                    errorBuilder: (_, _, _) => _placeholder(c),
                  )
                : _placeholder(c),
          ),
        );
      },
    );
  }

  Widget _placeholder(AppColors c) => Container(
    color: c.surface2,
    alignment: Alignment.center,
    child: Icon(Icons.person_outline, size: 18, color: c.textTertiary),
  );
}
