# 模型目录

模型权重是独立的发布对象。提交或分发前必须确认权重、训练数据、推理框架和导出格式的授权，不能因为源码采用 MIT 就默认模型也可以公开。

## 桌面端

Engine 默认查找：

```text
models/bball_model.pt
```

也可以通过 `scripts/check_runtime.py --model /path/to/model.pt` 指定自定义路径。模型需要兼容当前检测脚本使用的类别和输入输出格式。

球员身份实验还需要 `yolo11n-pose.pt`，仅做人物框、手腕和外观特征提取，不是跨天人脸识别模型。

| 文件 | 来源与版本 | SHA-256 | 权利状态 |
|---|---|---|---|
| `bball_model.pt` | 原项目已有权重，实际文件 SHA-256 见下 | `40f3e596652a427ba290b3f72384e49aed12caf1a8ae41beaef4a8fffcf09fa3` | 权重与训练数据的再分发权尚未完整核验，不能按 MIT 推定 |
| `yolo11n-pose.pt` | [Ultralytics 官方 v8.4.0 发布资产](https://github.com/ultralytics/assets/releases/download/v8.4.0/yolo11n-pose.pt) | `869e83fcdffdc7371fa4e34cd8e51c838cc729571d1635e5141e3075e9319dc0` | AGPL-3.0；见 `docs/licenses/AGPL-3.0.txt` 和根目录 `NOTICE` |

macOS 构建只从仓库内已固定并校验哈希的文件复制姿态模型，运行时不得临时下载。`scripts/check_packaged_models.py` 用安装包内的 Python 分别加载两个模型；文件存在不等于模型可用。

## 移动端

移动端可能需要 ONNX 模型和对应的 Rust/ONNX Runtime。模型转换入口见 [`../scripts/export_mobile_model.py`](../scripts/export_mobile_model.py)，Android/iOS 原生构建边界见 [`../docs/architecture/MOBILE_RUNTIME_V1.md`](../docs/architecture/MOBILE_RUNTIME_V1.md)。

## 公开发布前

请保留模型来源、版本、哈希、许可证和训练数据授权记录。没有明确再分发许可时，只要求使用者自行准备模型，不要在 Release 附件或文档中提供未经核验的下载地址。
