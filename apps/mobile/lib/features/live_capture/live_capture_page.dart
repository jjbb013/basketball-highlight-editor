import 'dart:async';
import 'dart:developer' as developer;
import 'dart:io';

import 'package:camera/camera.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:path_provider/path_provider.dart';

/// 实时拍摄页：打开相机边录边分析，实时提示进球（音效+比分计数），
/// 录完的视频走现有项目/审核导出流程。
///
/// 复用 packages/bhe_runtime 的 coarse_mode 流式会话：Rust 端保存球轨迹
/// 滑动窗口并在线估计篮筐位置（hoop 检测中位数），进球候选经 2s 去重后
/// 随 pushFrame 响应返回；Kotlin 层再做 0.8s 提示去抖并播放提示音。
/// 实时提示标记 needsPostReview=true，赛后复核以完整分析为准。
class LiveCapturePage extends StatefulWidget {
  const LiveCapturePage({super.key});

  static const _channel = MethodChannel('com.bhe.bhe/live_analysis');
  static const _eventsChannel = EventChannel(
    'com.bhe.bhe/live_analysis_events',
  );

  /// 将 ONNX 模型从 asset 物化到应用目录（与 NativeAnalysisEngine 同路径，
  /// 已物化则直接复用）。
  static Future<String> materializeModel() async {
    final directory = await getApplicationSupportDirectory();
    final file = File('${directory.path}/models/bball_model.onnx');
    final data = await rootBundle.load('assets/models/bball_model.onnx');
    final bytes = data.buffer.asUint8List(
      data.offsetInBytes,
      data.lengthInBytes,
    );
    if (await file.exists() && await file.length() == bytes.length) {
      return file.path;
    }
    await file.parent.create(recursive: true);
    await file.writeAsBytes(bytes, flush: true);
    return file.path;
  }

  @override
  State<LiveCapturePage> createState() => _LiveCapturePageState();
}

class _LiveCapturePageState extends State<LiveCapturePage> {
  CameraController? _controller;
  StreamSubscription<dynamic>? _eventsSubscription;
  CameraDescription? _camera;

  bool _initializing = true;
  bool _analyzing = false;
  bool _recording = false;
  bool _stopping = false;
  String? _error;
  String _statusMessage = '正在准备相机…';

  int _goals = 0;
  int? _lastGoalMs;
  bool _goalFlash = false;
  int _analysisFps = 0;
  int _droppedFrames = 0;

  // 手动标定的篮筐（normalized 0..1，display 坐标系）；null 则自动估计。
  Rect? _manualRim;

  DateTime? _recordingStartedAt;

  @override
  void initState() {
    super.initState();
    _eventsSubscription = LiveCapturePage._eventsChannel
        .receiveBroadcastStream()
        .listen(_onLiveEvent);
    unawaited(_setup());
  }

  Future<void> _setup() async {
    try {
      final cameras = await availableCameras();
      _camera = cameras.firstWhere(
        (c) => c.lensDirection == CameraDirection.back,
        orElse: () => cameras.first,
      );
      final controller = CameraController(
        _camera!,
        ResolutionPreset.medium,
        enableAudio: true,
        imageFormatGroup: ImageFormatGroup.yuv420,
      );
      await controller.initialize();
      if (!mounted) {
        await controller.dispose();
        return;
      }
      setState(() {
        _controller = controller;
        _initializing = false;
        _statusMessage = '相机就绪';
      });
      await _startAnalysis();
    } on CameraException catch (error) {
      _fail('相机初始化失败：${error.description ?? error.code}');
    } on Object catch (error) {
      _fail('相机初始化失败：$error');
    }
  }

  Future<void> _startAnalysis() async {
    final controller = _controller;
    if (controller == null || !controller.value.isInitialized) return;
    try {
      final modelPath = await LiveCapturePage.materializeModel();
      if (!mounted) return;
      await LiveCapturePage._channel.invokeMethod('start', {
        'modelPath': modelPath,
        // 画面中心区域作为球搜索 ROI；篮筐未手动标定时由 runtime 在线估计。
        'analysisRoi': _manualRim?.letRimAsAnalysisRoi() ?? const {
          'left': 0.2,
          'top': 0.05,
          'right': 0.8,
          'bottom': 0.75,
        },
        if (_manualRim != null) 'rim': _manualRim!.toRoiMap(),
        'confidence': 0.10,
        'executionProvider': 'cpu',
        'intraThreads': 4,
      });
      if (!mounted) return;
      var lastPush = DateTime.fromMillisecondsSinceEpoch(0);
      var pushCount = 0;
      var fpsWindowStart = DateTime.now();
      await controller.startImageStream((image) {
        final now = DateTime.now();
        // 中低端机录制+分析并发时限制分析帧率，约 5fps。
        if (now.difference(lastPush).inMilliseconds < 200) return;
        lastPush = now;
        unawaited(_pushFrame(image, now));
        pushCount += 1;
        if (now.difference(fpsWindowStart).inSeconds >= 2) {
          if (mounted) {
            setState(() => _analysisFps = pushCount ~/ 2);
          }
          pushCount = 0;
          fpsWindowStart = now;
        }
      });
      if (mounted) setState(() => _analyzing = true);
    } on PlatformException catch (error) {
      _fail('实时分析启动失败：${error.message ?? error.code}');
    } on Object catch (error) {
      _fail('实时分析启动失败：$error');
    }
  }

  Future<void> _pushFrame(CameraImage image, DateTime now) async {
    final controller = _controller;
    if (controller == null || _stopping) return;
    try {
      final rotation = _camera?.sensorOrientation ?? 90;
      final result = await LiveCapturePage._channel.invokeMethod('pushFrame', {
        'timeMs': now.millisecondsSinceEpoch,
        'width': image.width,
        'height': image.height,
        'rotationDegrees': rotation,
        'y': _planeMap(image.planes[0]),
        'u': _planeMap(image.planes[1]),
        'v': _planeMap(image.planes[2]),
      });
      final dropped = (result as Map?)?['dropped'] as int?;
      if (dropped != null && dropped != _droppedFrames && mounted) {
        setState(() => _droppedFrames = dropped);
      }
    } on PlatformException catch (error) {
      developer.log('live pushFrame failed: $error', name: 'BHE-Live');
    }
  }

  Map<String, Object> _planeMap(Plane plane) => {
    'bytes': plane.bytes,
    'rowStride': plane.rowStride,
    'pixelStride': plane.pixelStride,
    'offset': 0,
  };

  void _onLiveEvent(dynamic event) {
    if (event is! Map || !mounted) return;
    if (event['type'] == 'goal') {
      setState(() {
        _goals = (event['goals'] as num?)?.toInt() ?? _goals + 1;
        _lastGoalMs = (event['eventMs'] as num?)?.toInt();
        _goalFlash = true;
      });
      HapticFeedback.mediumImpact();
      Timer(const Duration(milliseconds: 900), () {
        if (mounted) setState(() => _goalFlash = false);
      });
    }
  }

  Future<void> _toggleRecording() async {
    final controller = _controller;
    if (controller == null || !controller.value.isInitialized) return;
    if (_recording) {
      await _stopRecording();
    } else {
      try {
        await controller.startVideoRecording();
        _recordingStartedAt = DateTime.now();
        if (mounted) setState(() => _recording = true);
      } on CameraException catch (error) {
        _fail('开始录制失败：${error.description ?? error.code}');
      }
    }
  }

  Future<void> _stopRecording() async {
    final controller = _controller;
    if (controller == null || _stopping) return;
    setState(() {
      _stopping = true;
      _statusMessage = '正在保存录像…';
    });
    String? videoPath;
    try {
      final xfile = await controller.stopVideoRecording();
      videoPath = xfile.path;
    } on CameraException catch (error) {
      _fail('停止录制失败：${error.description ?? error.code}');
      setState(() => _stopping = false);
      return;
    }
    try {
      await controller.stopImageStream();
    } on Object {
      // 忽略：流可能已停止。
    }
    try {
      await LiveCapturePage._channel.invokeMethod('stop');
    } on Object {
      // 会话停止失败不阻塞录像保存。
    }
    setState(() {
      _analyzing = false;
      _recording = false;
      _stopping = false;
    });
    if (mounted && videoPath != null) {
      Navigator.of(context).pop<String>(videoPath);
    }
  }

  Future<void> _cancel() async {
    final controller = _controller;
    if (controller != null && controller.value.isRecordingVideo) {
      try {
        await controller.stopVideoRecording();
      } on Object {
        // 放弃本次录像。
      }
    }
    try {
      await controller?.stopImageStream();
    } on Object {}
    try {
      await LiveCapturePage._channel.invokeMethod('stop');
    } on Object {}
    if (mounted) Navigator.of(context).pop<String>(null);
  }

  Future<void> _calibrateRim(TapDownDetails details, BoxConstraints area) async {
    // 手动点选篮筐兜底：tap 位置映射为 normalized 坐标，重启分析会话。
    final size = area.biggest;
    final center = Offset(
      (details.localPosition.dx / size.width).clamp(0.05, 0.95),
      (details.localPosition.dy / size.height).clamp(0.05, 0.95),
    );
    setState(() {
      _manualRim = Rect.fromCenter(
        center: center,
        width: 0.16,
        height: 0.10,
      );
      _analyzing = false;
    });
    try {
      await _controller?.stopImageStream();
    } on Object {}
    await _startAnalysis();
  }

  void _fail(String message) {
    developer.log(message, name: 'BHE-Live');
    if (mounted) setState(() => _error = message);
  }

  @override
  void dispose() {
    unawaited(_eventsSubscription?.cancel());
    final controller = _controller;
    if (controller != null && controller.value.isRecordingVideo) {
      unawaited(controller.stopVideoRecording().catchError((_) {}));
    }
    try {
      if (controller != null && controller.value.isStreamingImages) {
        unawaited(controller.stopImageStream());
      }
    } on Object {}
    unawaited(
      LiveCapturePage._channel.invokeMethod('stop').catchError((_) {}),
    );
    unawaited(controller?.dispose());
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final controller = _controller;
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        title: const Text('实时拍摄'),
        backgroundColor: Colors.black,
        foregroundColor: Colors.white,
        actions: [
          if (!_recording && !_stopping)
            IconButton(
              tooltip: '放弃并返回',
              icon: const Icon(Icons.close),
              onPressed: _cancel,
            ),
        ],
      ),
      body: _error != null
          ? _ErrorView(message: _error!, onRetry: () {
              setState(() {
                _error = null;
                _initializing = true;
              });
              unawaited(_setup());
            })
          : _initializing || controller == null
          ? Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const CircularProgressIndicator(),
                  const SizedBox(height: 16),
                  Text(
                    _statusMessage,
                    style: const TextStyle(color: Colors.white70),
                  ),
                ],
              ),
            )
          : _buildCameraView(context, controller),
    );
  }

  Widget _buildCameraView(BuildContext context, CameraController controller) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final recordingSeconds = _recordingStartedAt == null
            ? 0
            : DateTime.now().difference(_recordingStartedAt!).inSeconds;
        return Stack(
          fit: StackFit.expand,
          children: [
            GestureDetector(
              onTapDown: _recording
                  ? null
                  : (details) => _calibrateRim(details, constraints),
              child: controller.value.isInitialized
                  ? CameraPreview(controller)
                  : const ColoredBox(color: Colors.black),
            ),
            // 篮筐标定引导框（中心区域；手动 tap 后出现精确 rim 框）。
            IgnorePointer(
              child: Center(
                child: Container(
                  width: constraints.maxWidth * 0.6,
                  height: constraints.maxHeight * 0.7,
                  decoration: BoxDecoration(
                    border: Border.all(
                      color: _manualRim == null
                          ? Colors.white38
                          : Colors.orangeAccent,
                      width: 1.5,
                    ),
                    borderRadius: BorderRadius.circular(8),
                  ),
                ),
              ),
            ),
            if (_manualRim != null)
              IgnorePointer(
                child: Align(
                  alignment: Alignment(
                    (_manualRim!.center.dx - 0.5) * 2,
                    (_manualRim!.center.dy - 0.5) * 2,
                  ),
                  child: Container(
                    width: constraints.maxWidth * _manualRim!.width,
                    height: constraints.maxHeight * _manualRim!.height,
                    decoration: BoxDecoration(
                      border: Border.all(color: Colors.orange, width: 2),
                      borderRadius: BorderRadius.circular(4),
                    ),
                  ),
                ),
              ),
            // 顶部状态栏：比分/计时/分析帧率。
            SafeArea(
              child: Align(
                alignment: Alignment.topCenter,
                child: Padding(
                  padding: const EdgeInsets.all(12),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      _StatChip(
                        icon: Icons.sports_basketball,
                        label: '进球 $_goals',
                        flash: _goalFlash,
                      ),
                      const SizedBox(width: 8),
                      if (_recording)
                        _StatChip(
                          icon: Icons.fiber_manual_record,
                          label: _formatDuration(recordingSeconds),
                          color: Colors.redAccent,
                        ),
                      const SizedBox(width: 8),
                      _StatChip(
                        icon: Icons.memory,
                        label: _analyzing
                            ? '分析 ${_analysisFps}fps'
                            : '分析未运行',
                        color: _analyzing ? Colors.greenAccent : Colors.orange,
                      ),
                      if (_droppedFrames > 10) ...[
                        const SizedBox(width: 8),
                        const _StatChip(
                          icon: Icons.warning_amber,
                          label: '负载高',
                          color: Colors.orange,
                        ),
                      ],
                    ],
                  ),
                ),
              ),
            ),
            // 进球闪光提示。
            if (_goalFlash)
              IgnorePointer(
                child: Container(
                  color: Colors.orange.withValues(alpha: 0.18),
                  child: const Center(
                    child: Text(
                      '进球！',
                      style: TextStyle(
                        color: Colors.white,
                        fontSize: 64,
                        fontWeight: FontWeight.bold,
                        shadows: [
                          Shadow(blurRadius: 24, color: Colors.orange),
                        ],
                      ),
                    ),
                  ),
                ),
              ),
            // 底部操作区。
            SafeArea(
              child: Align(
                alignment: Alignment.bottomCenter,
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(24, 0, 24, 28),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      if (!_recording)
                        Padding(
                          padding: const EdgeInsets.only(bottom: 12),
                          child: Text(
                            '把篮筐放进中间方框内；也可直接点按篮筐进行标定。'
                            '实时判定仅供参考，赛后将复核。',
                            textAlign: TextAlign.center,
                            style: TextStyle(
                              color: Colors.white.withValues(alpha: 0.75),
                              fontSize: 12,
                            ),
                          ),
                        ),
                      FilledButton.icon(
                        onPressed: _stopping
                            ? null
                            : (_recording ? _stopRecording : _toggleRecording),
                        style: FilledButton.styleFrom(
                          backgroundColor: _recording
                              ? Colors.redAccent
                              : Colors.orange,
                          padding: const EdgeInsets.symmetric(
                            horizontal: 32,
                            vertical: 14,
                          ),
                        ),
                        icon: Icon(_recording ? Icons.stop : Icons.videocam),
                        label: Text(
                          _stopping
                              ? '正在保存…'
                              : (_recording ? '停止并生成项目' : '开始录制'),
                          style: const TextStyle(fontSize: 16),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ],
        );
      },
    );
  }

  static String _formatDuration(int seconds) {
    final m = (seconds ~/ 60).toString().padLeft(2, '0');
    final s = (seconds % 60).toString().padLeft(2, '0');
    return '$m:$s';
  }
}

extension on Rect {
  Map<String, double> toRoiMap() => {
    'left': left.clamp(0.0, 1.0),
    'top': top.clamp(0.0, 1.0),
    'right': right.clamp(0.0, 1.0),
    'bottom': bottom.clamp(0.0, 1.0),
  };

  Map<String, double> letRimAsAnalysisRoi() => {
    'left': (left - 0.2).clamp(0.0, 1.0),
    'top': (top - 0.2).clamp(0.0, 1.0),
    'right': (right + 0.2).clamp(0.0, 1.0),
    'bottom': (bottom + 0.25).clamp(0.0, 1.0),
  };
}

class _StatChip extends StatelessWidget {
  const _StatChip({
    required this.icon,
    required this.label,
    this.color = Colors.white70,
    this.flash = false,
  });

  final IconData icon;
  final String label;
  final Color color;
  final bool flash;

  @override
  Widget build(BuildContext context) => AnimatedContainer(
    duration: const Duration(milliseconds: 150),
    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
    decoration: BoxDecoration(
      color: flash
          ? Colors.orange.withValues(alpha: 0.9)
          : Colors.black.withValues(alpha: 0.55),
      borderRadius: BorderRadius.circular(20),
    ),
    child: Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, size: 14, color: flash ? Colors.white : color),
        const SizedBox(width: 4),
        Text(
          label,
          style: TextStyle(
            color: flash ? Colors.white : color,
            fontSize: 12,
            fontWeight: FontWeight.w600,
          ),
        ),
      ],
    ),
  );
}

class _ErrorView extends StatelessWidget {
  const _ErrorView({required this.message, required this.onRetry});

  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) => Center(
    child: Padding(
      padding: const EdgeInsets.all(24),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Icon(Icons.error_outline, color: Colors.redAccent, size: 48),
          const SizedBox(height: 16),
          Text(
            message,
            textAlign: TextAlign.center,
            style: const TextStyle(color: Colors.white70),
          ),
          const SizedBox(height: 16),
          FilledButton(onPressed: onRetry, child: const Text('重试')),
        ],
      ),
    ),
  );
}
