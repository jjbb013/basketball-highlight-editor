# Presentation Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 给最终导出视频添加可配置人物封面和运动 BGM，默认封面 3 秒、BGM 音量 20%。

**Architecture:** 独立 `adapters/presentation.py` 负责配置、Pillow 封面和 FFmpeg 后处理；现有剪辑与合并器只负责生成基础成品。音乐由可复现脚本生成，封面字体随运行时打包并保留 OFL。

**Tech Stack:** Python、Pillow、NumPy、FFmpeg、pytest。

## Global Constraints

- 默认 `cover.enabled=true`、`duration_ms=3000`、`audio.enabled=true`、`volume=0.2`。
- `court`、`poster`、`photo` 三样式；标题、副标题、强调色和背景图可自定义。
- `electronic_drive`、`hip_hop_bounce`、`rock_pulse` 三类原创循环，另允许本地音乐。
- 原声不自动衰减，`amix=normalize=0`；无原声与静音都能处理。
- 合并后的最终文件只加一次封面；重试不叠加。
- 输出先写临时文件并校验，失败不覆盖基础成品。

### Task 1: 配置与封面渲染

**Files:** Create `engine/python/basketball_engine/adapters/presentation.py`, `tests/test_presentation_cover.py`; add `assets/fonts/NotoSansSC-Regular.ttf`, `assets/fonts/OFL.txt`; modify `requirements.txt`.

**Interfaces:** `normalize_presentation(config) -> dict`、`render_cover(path, size, config, title, subtitle=None) -> Path`。

- [x] 写默认值、范围/样式校验、三样式 RGB 尺寸、中文长标题、自定义背景及配色测试。
- [x] 运行 `../.venv/bin/python -m pytest tests/test_presentation_cover.py -v`，确认模块缺失。
- [x] 实现严格配置和 Pillow 渲染；不使用机器字体作为唯一中文回退。
- [x] 重跑测试，确认全部通过，并检查字体文件与 OFL 均存在。

### Task 2: 原创运动 BGM

**Files:** Create `scripts/generate_sports_bgm.py`, `assets/bgm/*.wav`, `assets/bgm/README.md`, `tests/test_sports_bgm.py`。

**Interfaces:** 脚本 `main(output_dir)` 仅写三个已知名称；`resolve_bgm(config) -> Path | None` 返回内置或本地音乐。

- [x] 写三轨道非静音、峰值不削波、可复现哈希、内置查找和自定义路径测试。
- [x] 运行测试确认资源/实现缺失，再实现确定性合成，不使用第三方采样。
- [x] 重跑测试，记录实际资源哈希；来源说明随资源保存。

### Task 3: FFmpeg 增强与原子失败语义

**Files:** Modify `presentation.py`; create `tests/test_presentation_ffmpeg.py`。

**Interfaces:** `enhance_video(path, config, title, subtitle=None, cancel_check=None, process_callback=None) -> dict`。

- [x] 写真实 64×64 视频测试：默认增加 3 秒、可禁用、三秒封面音频、现场声不降低、无原声补 BGM、本地音乐、无效配置、失败保留原文件。
- [x] 运行测试确认 `enhance_video` 缺失，再实现流探测、统一 fps/尺寸/48kHz 立体声、循环音乐、原子编码和成品校验。
- [x] 重跑新增测试及 `test_export_audio_mixed.py`、`test_hdr_export.py`，确认无回归。

### Task 4: 导出编排接入

**Files:** Modify `service.py`, `tests/test_export_by_player.py`, `tests/test_export_start_cleanup.py`。

**Interfaces:** `start_export` 快照保存规范化 `presentation`；按球员输出用球员名作为默认封面标题，普通合并用“进球集锦”，分别导出使用已有标签。

- [x] 写合并只加一次、每组标题、关闭增强保持原行为、重试配置相同及失败清理测试。
- [x] 先观察失败，再以最终输出为边界接入；不把增强应用到内部原始片段。
- [x] 重跑完整导出测试；后续 Flutter 计划只消费已稳定的 `presentation` JSON。
