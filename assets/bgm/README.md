# 内置运动背景音乐

这些 WAV 文件由 `scripts/generate_sports_bgm.py` 以固定随机种子直接合成，不使用第三方录音、采样或参考成片音轨。它们作为本项目的原创资源随项目发布。

- `electronic_drive.wav`：128 BPM，电子驱动。
- `hip_hop_bounce.wav`：92 BPM，嘻哈律动。
- `rock_pulse.wav`：140 BPM，摇滚脉冲。

生成器使用 NumPy，输出 22050 Hz、单声道、16-bit PCM。导出时 FFmpeg 转为 48 kHz 立体声，并默认按 0.2 音量与现场声混合。循环边界有短淡入淡出以降低爆音。

字体的来源与许可见 `assets/fonts/`。这些音乐资源与 Ultralytics 模型、用户导入音乐的授权边界互不替代。
