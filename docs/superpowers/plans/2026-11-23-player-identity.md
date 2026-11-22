# Player Identity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在本场比赛中提取人物外观、找出最后触球者、建立可命名身份，并在不覆盖人工纠正的前提下传播球员名。

**Architecture:** 纯 Python 算法层消费结构化检测和本地图像，SQLite 保存身份原型、自动证据与人工覆盖。YOLO Pose 通过窄适配器接入；实际分析管线、Flutter 界面和真实视频验证属于后续独立计划。

**Tech Stack:** Python 3.11+、NumPy、Pillow、Ultralytics YOLO、SQLite、pytest。

## Global Constraints

- 预训练 Pose 不是本项目训练的通用球员识别器。
- 无可靠触球或身份证据时返回 `review`，不强制命名。
- 人工指定和人工清除标签优先于自动传播。
- 真实球员图像、视频、原型和本机路径不进入 Git。
- 所有新代码先写失败测试并观察预期失败，再写最小实现。
- 测试从仓库根目录运行，使用工作区现有虚拟环境。

---

## 文件结构与实际接口

- `src/basketball_highlight/appearance.py`
  - `appearance_vector(regions, qualities)` 归一化区域向量，丢弃零质量证据。
  - `appearance_distance(left, right)` 返回共同有效区域的加权余弦距离和权重。
  - `image_appearance(image, bbox, quality=1.0, head_bbox=None)` 提取头发、弱脸部形状、肤色、上下装和鞋袜特征。
- `src/basketball_highlight/last_touch.py`
  - `select_last_touch(frames, rim=None)` 返回 `identified` 或 `review`、局部 track、触球时间、置信度及候选。
- `src/basketball_highlight/identity_model.py`
  - `LocalIdentityModel.assign/observe/to_dict/from_dict` 提供可增量保存、可拒判的本场身份原型。
- `src/basketball_highlight/pose.py`
  - `normalize_pose_result(result, time_ms)` 保留源像素人物框和 COCO 双腕。
  - `PoseDetector` 延迟加载模型，不让单元测试依赖原生推理。
- `engine/python/basketball_engine/storage.py`
  - `create_identity/list_identities/upsert_identity_assignment/name_identity`。
  - `candidate_reviews.player_id` 继续承载有效展示标签；新增表保存身份和人工覆盖。
- `engine/python/basketball_engine/service.py`、`server.py`
  - 新增 `name_identity` 命令。
- `docs/architecture/SQLITE_SCHEMA_V1.sql`
  - 与运行时迁移一致的新表和索引。

未额外创建没有独立职责的 `identity.py`；存储事务集中在现有 `ProjectStore`，避免两套标签写入路径。

### Task 1: 质量加权外观特征

- [x] 在 `tests/test_appearance.py` 写相同/不同颜色、缺失区域、无共同证据、非有限值、零质量、人物区域和过小裁片测试。
- [x] 首次运行 `../.venv/bin/python -m pytest tests/test_appearance.py -v`，观察到 `ModuleNotFoundError: basketball_highlight.appearance`。
- [x] 实现区域归一化、共同掩码距离、HSV 直方图、相对 RGB、肤色支持度和弱形状特征。首次颜色测试暴露相同区域稀释差异后，增加相对颜色分量；未降低测试阈值。
- [x] 运行 `../.venv/bin/python -m pytest tests/test_appearance.py tests/test_tracking.py -q`，结果 `13 passed`。

### Task 2: 最后触球者与冲突拒判

- [x] 在 `tests/test_last_touch.py` 写释放前最后接触、静止近球、较晚接触、并列冲突、低置信腕点、单帧接触、球遮挡和空输入测试。
- [x] 首次运行 `../.venv/bin/python -m pytest tests/test_last_touch.py -v`，观察到 `ModuleNotFoundError`。
- [x] 实现连续接触段、至少 50 ms 接触支持、随后离手、时间优先和同时冲突拒判。
- [x] 运行 `../.venv/bin/python -m pytest tests/test_last_touch.py tests/test_appearance.py tests/test_tracking.py -q`，结果 `21 passed`。

### Task 3: 可保存、可拒判的本场身份模型

- [x] 在 `tests/test_identity_model.py` 写序列化重识别、无共同区域、空输入、新建不同身份、相似身份拒判、非法观测和版本不兼容测试。
- [x] 首次运行 `../.venv/bin/python -m pytest tests/test_identity_model.py -v`，观察到 `ModuleNotFoundError`。
- [x] 实现阈值与第二名间隔、增量归一化原型、版本化 JSON；模型不保存图片。
- [x] 运行 `../.venv/bin/python -m pytest tests/test_identity_model.py tests/test_last_touch.py tests/test_appearance.py tests/test_tracking.py -q`，结果 `28 passed`。

### Task 4: YOLO Pose 归一化适配器

- [x] 在 `tests/test_pose.py` 用轻量结果对象验证源坐标、双腕、缺失置信度、缺失关键点和延迟加载。
- [x] 首次运行 `../.venv/bin/python -m pytest tests/test_pose.py -v`，观察到 `ModuleNotFoundError`。
- [x] 实现 torch/numpy/list 值归一化，修正测试 fake 对 `None` 的表示后复测；未用 fake 的异常代替生产断言。
- [x] 运行 `../.venv/bin/python -m pytest tests/test_pose.py tests/test_identity_model.py tests/test_last_touch.py tests/test_appearance.py -q`，结果 `27 passed`。

### Task 5: 自动身份、人工覆盖与命名传播

- [x] 在 `tests/test_player_identity_storage.py` 建立三候选项目，其中两个自动同身份、一个人工改派。
- [x] 首次运行 `../.venv/bin/python -m pytest tests/test_player_identity_storage.py -v`，八个 fixture 均观察到缺少 `create_identity`。
- [x] 新增 `player_identities` 与 `candidate_player_assignments`；命名事务只传播 `automatic`，单条/批量人工操作和人工清除都写 `manual`。
- [x] 首次实现后的七项通过，重新分析测试失败并显示身份变为 `None`；随后让候选替换按相同或唯一邻近匹配迁移身份记录，人工来源不变。
- [x] 运行 `../.venv/bin/python -m pytest tests/test_player_identity_storage.py tests/test_export_by_player.py tests/test_multi_video_project.py -q`，结果 `29 passed`。

## 已执行完成检查

- [x] `../.venv/bin/python -m pytest tests/test_appearance.py tests/test_last_touch.py tests/test_identity_model.py tests/test_pose.py tests/test_player_identity_storage.py tests/test_tracking.py -q`：`40 passed`。
- [x] `git diff --check`：无输出。
- [x] 自动身份与人工决定分别存储，跨项目身份/球员 ID 做项目校验。
- [x] 旧库连接时获得新表，公开 SQL 与运行时迁移一致。

## 本计划未覆盖的后续工作

实际视频帧读取、短时人物跟踪、分析管线调用、身份原型更新、Flutter 命名入口、封面/BGM、跨项目导出、真实视频准确率、macOS 打包和 Release 均需后续计划与测试。本计划的单元测试不能推导真实比赛识别准确率。
