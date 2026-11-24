# 人物分析区 + 人物复核页 实现计划

设计文档：`docs/superpowers/specs/2026-11-25-player-analysis-zone-people-review-design.md`（提交 `3ef2a99`）。

分支：`feature/player-analysis-zone-people-review`。

## 勘察结论（已验证）

- Engine `service.py`：1695–1703 解析 `net_roi`；1979 调 `_identify_players(source_roi=source_roi)`；2156–2163 身份缓存 key 含 `"roi": source_roi`。
- `identify_players.py`：`--roi` 必填，`main()` 里 `expanded_roi(args.roi, *source_size)` 作为 scan_window 的搜索框。加 `--person-roi`（可选）即可在不改行为的前提下换搜索框。
- `build_player_identification_command`（`engine/python/basketball_engine/adapters/analysis.py:320`）构造 CLI，加可选 `person_roi` 参数透传 `--person-roi`。
- `ProjectState`（`apps/desktop/lib/providers/project_state.dart`）：字段区 80–169；`applyWorkflowDraft` 697–780（calibration 组装在 735–751）；`openProject` 恢复 1153–1169；`saveRoi` 1863–1913（**每次重建 calibration**，person_roi 必须作参数透传，否则重存投篮区会丢人物区）。
- 草稿：`version: 4` 无读取端校验，`person_roi` 作为可选键加入即可，不升版本。
- 导入页 `_DetectionStep`（2168–2559）：`editingNet: bool` 二态切换；`_RoiCanvas`（4268+）= `roi` + `secondaryRoi` 双框，绘制用叠加 `_RoiPainter`（4716+，单框 painter），加第三框只需叠加第三个 `_RoiPainter`。
- 球员指派公开 API：`createPlayer(name, candidateIds:)`（2715）、`setCandidatePlayer(candidateId, playerId)`（2790，playerId 可空 = 清除）。
- l10n：`packages/bhe_l10n`，template `app_zh.arb`，`flutter gen-l10n` 生成到 `lib/src/generated`。新文案走 ARB getter（`bhe_text.dart` 头部注释明确要求）。
- 审核页选择状态是 `ReviewScreen` 私有 `_selectedCandidateId`，跨页预选需要改状态机 → 第一版人物页「查看投篮片段」只 `context.go('/review')`，不做预选（已在设计中声明）。
- 主题无现成紫色，用 `Color(0xFFB388FF)`（浅紫）作为人物区颜色常量。

## 步骤

### Task 1: Engine — person_roi 解析、透传、回退

文件：
- `engine/python/basketball_engine/service.py`
- `engine/python/basketball_engine/adapters/analysis.py`
- `scripts/identify_players.py`

改动：
1. `service.py` 新增模块级 helper `_parse_person_roi(raw, source_width, source_height)`：非 dict / 缺键 / 非数值 / `x2<=x1` / `y2<=y1` / 越出源画面 → 返回 `None`；合法返回 `[x1,y1,x2,y2]`（float）。在 net_roi 解析后（约 1703 行）解析 `calibration.get('person_roi')`。
2. 调 `_identify_players` 时传 `person_roi=person_roi`；回退决策放在 `_identify_players` 内：`effective_roi = person_roi or source_roi`，person_roi 为 None 且 source_roi 存在时写 `pipeline["logs"]` 回退日志（人物区无效/未配置，回退投篮分析区扩展范围）。
3. `_identify_players` 签名加 `person_roi=None`；缓存 key payload 加 `"person_roi": person_roi`；`build_player_identification_command(..., person_roi=person_roi)`。
4. `analysis.py`：`build_player_identification_command` 加可选 keyword `person_roi: Iterable[float] | None = None`，非空时追加 `["--person-roi", *args]`。
5. `identify_players.py`：`--person-roi nargs=4 type=int`；`main()` 里 `search_roi = args.person_roi or args.roi`，`expanded_roi(search_roi, ...)`。

测试（先写）：
- `engine/python/tests/test_person_roi_parsing.py`（新）：`_parse_person_roi` 合法/缺键/反序/越界/类型错 → 各分支。
- 现有 command 构建测试文件（查找 `build_player_identification_command` 既有测试）追加 person_roi 参数用例。
- `identify_players` 参数解析：若无现成测试文件，给 `parse_args` 加最小用例（`--person-roi` 缺省为 None、传入四值生效）。

### Task 2: ProjectState — personRoi 字段

文件：`apps/desktop/lib/providers/project_state.dart`

改动：
1. `ProjectState` 加 `final Rect? personRoi;` + 构造参数 + copyWith。
2. `openProject`：1153–1169 处用 `_normalizeRoi` 恢复 `calibration['person_roi']` → `restoredPersonRoi`，copyWith 进 state。
3. `applyWorkflowDraft`：735–751 处解析 `draft['person_roi']`（`_draftRect` 已是归一化），写入 `calibration['person_roi']`（源像素）。
4. `saveRoi`：加 `Rect? personRoi` 参数 → calibration 加 `person_roi`；copyWith 存 state。
5. 检查 `propagateHoopToFollowingParts` 复制 calibration 的路径无需改动（整包复制）。

测试：`apps/desktop/test/providers/` 找现有 project_state / saveRoi 测试，追加：
- saveRoi 传 personRoi → session.saveRoi 收到的 calibration 含 person_roi 源像素坐标。
- openProject 恢复 person_roi → state.personRoi 归一化正确。
- applyWorkflowDraft 带 person_roi → calibration 透传。

### Task 3: 导入页 — 紫色人物区

文件：`apps/desktop/lib/features/import_video/import_video_screen.dart`

改动：
1. 状态字段：`_personRoi`（`Rect?`）、`_personUserEdited`（bool）。`_loadFromState` 从 `state.personRoi` 恢复。
2. 草稿：`_draft()`/`_backendDraft()` 加 `person_roi`（`_rectMap` 归一化）与 `person_roi_source: 'manual'|'none'`；保存路径（`onChanged`）在编辑人物区时写 `_personRoi`/`_personUserEdited`。
3. `_DetectionStep`：`editingNet: bool` → `editingRegion` enum（`_CalibrationRegion { shot, net, person }`）；调用点 1476–1530 同步改。
4. `_RoiCanvas` 加 `tertiaryRoi/tertiaryColor/tertiaryLabel`，build 里叠加第三个 `_RoiPainter`（transparent hit-test，仅绘制）。
5. 区域按钮行加第三个 `_CalibrationTargetButton`（序号 3，紫色，「人物分析区」）；编辑提示文案、恢复按钮按三态切换。
6. `_SummaryStep` 汇总区显示「人物分析区（可选）：已设置/未设置」。
7. 人物区不做自动识别（v1），无 `_autoPersonRoi`。

测试：找 `detection_step_entry_test.dart` / `import_video_screen_test.dart` 的现有 harness，追加：
- 三个区域按钮都存在，点「人物分析区」后 canvas active label 为人物区。
- 编辑人物区后 `_draft()` 含 person_roi。
- 汇总步骤显示人物区状态。

### Task 4: 人物复核页 + 审核页切换

新文件：
- `apps/desktop/lib/features/review/people_review.dart` — 纯模型：`PeopleReviewGroup`（identityId、displayName、assignmentSource、candidateIds、touchTimeMs、confidence 展示值）+ `buildPeopleReviewGroups(candidates, players)` 分组排序（组内按 touch_time_ms，组间按最早触球）。
- `apps/desktop/lib/features/review/people_review_screen.dart` — ConsumerStatefulWidget：分组列表；每组头部显示「自动推测 #N / 已命名球员名 + 自动推测徽标」、候选数、触球时间；操作：命名为球员（输入框 → `createPlayer(name, candidateIds: 组内候选)`）、单条修正（`setCandidatePlayer`）、清除修正（`setCandidatePlayer(id, null)`）、查看投篮片段（`context.go('/review')`）；筛选（全部/待复核/已命名）。
- `review_screen.dart`：content Column 状态栏下加「投篮 / 人物」SegmentedButton；切到人物时渲染 `PeopleReviewScreen`，不渲染视频+队列（保留状态栏）。

测试（新文件）：
- `people_review_test.dart`（纯模型）：分组、排序、命名后 displayName。
- `people_review_screen_test.dart`（widget，ProviderScope + fake notifier）：渲染组、命名按钮调 createPlayer、清除修正调 setCandidatePlayer(id, null)、筛选切换。
- `review_screen_test.dart` 追加：切换按钮存在，切到人物后视频 pane 消失、人物列表出现。

### Task 5: 文案

`packages/bhe_l10n/lib/l10n/app_zh.arb` + `app_en.arb` 新增键（约 15 个）：
人物分析区 / 人物检测区 / 可选项，覆盖画面中球员活动范围… / 恢复人物区 / 当前编辑紫色人物分析区域… / 投篮 / 人物 / 命名为球员 / 自动推测 / 身份待复核 / 已命名 / 清除修正 / 查看投篮片段 / 待复核 / 全部身份 …
运行 `flutter gen-l10n`（在 packages/bhe_l10n）重新生成。

### Task 6: README

- 新 `README-BHE-PRO.md`（中文）：独立应用名 BHE Pro、bundle id、独立数据目录；相对原版全部增量（macOS 支持、封面、BGM、人物识别与人物分析区/复核页、多项目导出）；安装与首次打开、Ad Hoc 未公证说明；指向 `v0.1.16-macos.3` 预发布（注明新功能尚未发布新 tag）。
- 根 `README.md` 顶部加链接段，不覆盖原文。

### Task 7: 验证、提交、推送

```bash
PATH=/opt/homebrew/bin:$PATH /Users/will/Coding/BasketBall-Video-System/.venv/bin/python -m pytest -q
/Users/will/Coding/BasketBall-Video-System/.tooling/flutter-3.44.8/bin/flutter test --concurrency=1
```

analyze 用 `--no-fatal-infos`（既有弃用 info）。提交按 Task 分批（engine / provider / import / review / l10n+readme），最后 `git push -u origin feature/player-analysis-zone-people-review`。不建 tag/Release/PR。

## Assumptions

- 人物区 v1 无自动识别，紫色框纯手动、可选；不设置时一切行为与现状一致。
- 人物页「查看投篮片段」v1 只跳转审核页，不预选候选。
- 人物区坐标独立校验（源画面内、非空），不与投篮区求交。
- 新 UI 文案走 ARB getter；人物区颜色用 `Color(0xFFB388FF)`。
