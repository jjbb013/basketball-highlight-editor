# BHE Pro 最终审查修复报告

日期：2026-11-23
基线：`15f7e2ea0f2f3edb40f1befb1f00314a1a991e91`
范围：`.superpowers/sdd/final-review-fixes-brief.md` 的 2 Critical、2 Important、4 Minor。

## 结论

全部八项要求均已落地。macOS 的正常新建与最近项目默认根已隔离到 BHE Pro；macOS 更新检查 fail-closed；正式 Release 能下载新 macOS artifacts；真实中英文界面使用统一展示名；旧 OSS 更新清单明确拒绝 BHE Pro/macOS 资产。Windows、Android 的既有生产逻辑未扩展或改写，未启用或发布 OSS。

## 逐项修改与 TDD 证据

### Critical 1：正常项目根目录和首页扫描隔离

修改：

- `apps/desktop/lib/core/project_session.dart` 新增可注入平台参数的 `defaultProjectsRoot`。
- macOS 默认根为 `$HOME/Library/Application Support/BHE Pro/Projects`。
- Windows 保持 `USERPROFILE/Videos/BasketballProjects`；其他平台保持 `$HOME/Movies/BasketballProjects`。
- `apps/desktop/lib/providers/project_state.dart` 新增 `defaultProjectsRootProvider`，`_projectsRoot` 保持 `BHE_PROJECTS_ROOT > knownProjectsRoot > 平台默认根`。
- 正常创建与 `loadRecentProjects()` 共用该根；显式历史项目路径和环境覆盖逻辑未改。
- `apps/desktop/test/providers/project_state_test.dart` 用记录型 fake session 验证真实创建及扫描路径，不启动 Engine、不读取真实目录。
- `apps/desktop/test/core/app_identity_test.dart` 验证三个平台的默认根纯函数。

RED（在 `apps/desktop`）：

```sh
../../../.tooling/flutter/bin/flutter test test/providers/project_state_test.dart --plain-name 'macOS BHE Pro 独立项目目录'
```

实际结果：2 项失败；创建和扫描均实际使用 `/Users/will/Movies/BasketballProjects`，而非 BHE Pro 独立目录。

GREEN：

```sh
../../../.tooling/flutter/bin/flutter test test/providers/project_state_test.dart --plain-name 'macOS BHE Pro 独立项目目录'
```

实际结果：`00:00 +2: All tests passed!`。最终五点文件组合回归及 629 项全量回归也均通过。

### Critical 2：Release 下载过滤器覆盖新 macOS artifacts

修改：

- `.github/workflows/release-packages.yml` 的 `jobs.release` / `Download all packages` 从 `BHE-*` 改为 `BHE*`。
- `tests/test_platform_patch_workflows.py` 直接检查该 job，并用 `fnmatchcase` 覆盖 macOS arm64、x86_64、Windows、Android artifact 名称。

RED：

```sh
PATH="/opt/homebrew/opt/openssl@3/bin:$PATH" .test-venv/bin/python -m pytest tests/test_platform_patch_workflows.py::test_release_job_download_pattern_covers_all_platform_artifacts -q
```

实际结果：`1 failed`，关键差异为 `'BHE-*' != 'BHE*'`。

GREEN：同一命令实际结果为 `1 passed in 0.05s`；最终 Python 全组为 137 项通过。

### Important 1：macOS BHE Pro 不消费原版更新通道

修改：

- `apps/desktop/lib/providers/update_provider.dart` 新增 `updateChecksEnabledProvider`，生产默认值为 `!Platform.isMacOS`。
- `check()` 在禁用时直接返回；`autoCheck()` 在禁用时返回 `false`，因此不会 fetch 原版 `latest.json`。
- 服务接口、Windows 安装与签名协议保持不变。
- `apps/desktop/test/update_test.dart` 对禁用分支验证 fetch、download、install 均未发生；既有更新用例显式注入 `true`，不依赖 macOS 主机偶然通过。
- `apps/desktop/test/ui_log_2_test.dart` 的既有更新日志用例同样显式开启检查。

RED（在 `apps/desktop`）：

```sh
../../../.tooling/flutter/bin/flutter test test/update_test.dart --plain-name 'macOS BHE Pro'
```

实际结果：手动检查为 `Expected: <0> Actual: <1>` 次 fetch；自动检查为 `Expected: false Actual: true`。

GREEN：同一命令实际结果为 `00:00 +2: All tests passed!`。

全量补充证据：第一次 Flutter 全量为 `+627 -2`，两项失败均在 `ui_log_2_test.dart`，日志实际为空，根因是既有更新用例未显式开启检查。补齐注入后，定点 `ui_log_2_test.dart` 为 `+4: All tests passed!`，最终全量为 `+629: All tests passed!`。

### Important 2：真实本地化和 macOS 更新说明使用统一品牌

修改：

- 真实 ARB 来源 `packages/bhe_l10n/lib/l10n/app_zh.arb`、`app_en.arb` 中，`about`、`confirmExit` 改为 `{appName}` 占位符；新增 `updateMacInstallInstructions`。
- 使用仓库 Flutter SDK 执行 `cd packages/bhe_l10n && ../../../.tooling/flutter/bin/flutter gen-l10n`，同步三个 `lib/src/generated/bhe_localizations*.dart`。
- `app.dart`、`cs_scaffold.dart`、`cs_sidebar_shell.dart` 调用 `confirmExit(appDisplayName())` / `about(appDisplayName())`。
- `update_dialog.dart` 的 macOS 安装说明使用 `updateMacInstallInstructions(appDisplayName())`；Windows 安装说明原样保留。
- `app_router_test.dart`、`widget_test.dart`、`update_test.dart`、`app_identity_test.dart` 均使用真实中英文 delegates；纯函数矩阵验证 macOS 为 BHE Pro、其他平台为 BHE。

RED：

- 关于入口定向 widget 测试：`flutter test test/router/app_router_test.dart --plain-name 'localized about entry uses the shared display name'`（在 `apps/desktop` 使用上述 SDK 前缀），实际找不到预期的 BHE Pro 中文关于文案。
- 退出确认定向 widget 测试：`flutter test test/widget_test.dart --plain-name 'localized exit confirmation uses shared name'`，实际找不到预期的 BHE Pro 中文退出文案。
- macOS 更新说明定向测试：`flutter test test/update_test.dart --plain-name 'the dialog downloads the package and opens it'`，实际找不到预期的 BHE Pro 中文安装说明。

上述 RED 均观察到预期文案 finder 数量为 0。测试校正没有冒充 GREEN：关于文案修复后侧栏与菜单各出现一次，断言据实改为 `findsNWidgets(2)`；退出测试改为显式 zh/en locale，避免宿主 locale 干扰；更新说明最终使用 `appDisplayName()`，避免非 macOS 主机误判。

GREEN：

- 更新说明单独命令实际结果：`00:00 +1: All tests passed!`。
- 以下五点文件组合命令实际结果：`00:01 +93: All tests passed!`，覆盖真实中英文关于、退出、macOS 更新说明和跨平台展示名。

```sh
../../../.tooling/flutter/bin/flutter test test/core/app_identity_test.dart test/router/app_router_test.dart test/widget_test.dart test/update_test.dart test/providers/project_state_test.dart
```

### Minor 1：打包测试环境污染隔离

修改：

- `tests/test_macos_bhe_pro_packaging.py` 用 `monkeypatch` 向父进程注入 `BHE_APP_NAME`、`BHE_SKIP_PACKAGE`、`BHE_SKIP_DMG`、`BHE_CODESIGN_IDENTITY` 污染值。
- 构造打包子进程 env 时显式移除这四个键，其余 fake-tools 隔离保持不变。

RED：

```sh
PATH="/opt/homebrew/opt/openssl@3/bin:$PATH" .test-venv/bin/python -m pytest tests/test_macos_bhe_pro_packaging.py::test_build_packages_space_named_app_with_isolated_fake_tools -q
```

实际结果：`1 failed`；污染导致 fake `ditto` 调用路径不含 `BHE Pro.app`。

GREEN：同一命令实际结果为 `1 passed in 1.79s`。

### Minor 2：两个 workflow 的完整资产 pattern 回归

修改：

- `tests/test_platform_patch_workflows.py` 提取 `_assert_release_download_patterns` 共用 fake-gh 精确参数断言。
- 同一测试循环覆盖 `release-packages.yml` / `oss-upload` 与 `upload-release-assets-oss.yml` / `upload`。
- 两者都验证 all、macos、windows、android 的完整有序 `--pattern` 列表，并核对 tag 与 `--repo`；没有脆弱数字索引或恒真断言。

说明：两份生产脚本的这些 pattern 在基线中已经正确，本项是覆盖增强，无独立生产 RED，也未制造失败。

GREEN：

```sh
PATH="/opt/homebrew/opt/openssl@3/bin:$PATH" .test-venv/bin/python -m pytest tests/test_platform_patch_workflows.py::test_release_asset_download_patterns_and_manual_lock -q
```

实际结果：`1 passed in 0.67s`。

### Minor 3：OSS 半适配 fail-closed

修改：

- `scripts/build_update_manifest.py` 的 `package_entries()` 发现任何 `BHE-Pro-macos-` 文件即抛出 `ValueError('BHE Pro/macOS 新资产禁止进入旧更新通道')`。
- 仅守卫生成旧更新清单的入口；GitHub Release job 未被该门禁阻断，tag-push 的 `publish_oss=false` 保持。
- `tests/test_build_update_manifest.py` 对 arm64、x86_64 均验证拒绝行为；不调用 OSS。

RED：

```sh
PATH="/opt/homebrew/opt/openssl@3/bin:$PATH" .test-venv/bin/python -m pytest tests/test_build_update_manifest.py -q -k bhe_pro_macos_assets
```

实际结果：`2 failed, 3 deselected`；两种架构均 `DID NOT RAISE ValueError`。

GREEN：同一命令实际结果为 `2 passed, 3 deselected in 0.21s`。

### Minor 4：Flutter 测试不依赖 macOS 主机

修改：

- `app_identity_test.dart` 的展示名使用 `appDisplayName(isMacOS: ...)` 注入矩阵；日志路径断言使用 `engineLogDirectory(Platform.environment)`。
- `app_router_test.dart` 的展示名使用生产纯函数；仅在当前展示名不是 BHE 时额外排除旧的“关于 BHE”，避免非 macOS 正确行为失败。
- `update_test.dart` 更新说明同样使用 `appDisplayName()`。
- 真实 delegates 测试覆盖 zh/en × macOS/非 macOS；默认目录纯函数覆盖三平台。

说明：本项是测试可移植性修正，无独立生产 RED。初版关于测试出现两处文案、退出测试受系统 locale 影响、英文文案测试容器出现 RenderFlex 溢出，均据实修正测试设施后才计入 GREEN；最终结果由上述 93 项定点测试和 629 项全量测试确认。

## 完整验证结果

### Python 相关全组

在仓库根目录执行：

```sh
PATH="/opt/homebrew/opt/openssl@3/bin:$PATH" .test-venv/bin/python -m pytest \
  tests/test_macos_bhe_pro_identity.py \
  tests/test_macos_bhe_pro_packaging.py \
  tests/test_macos_dmg.py \
  tests/test_identity_packaging.py \
  tests/test_platform_patch_workflows.py \
  tests/test_publish_release_update.py \
  tests/test_platform_patch_manifest.py \
  tests/test_build_update_manifest.py
```

实际末行：`============================= 137 passed in 10.49s =============================`。
共收集 137 项，0 失败；包含新增 OSS 门禁测试。

### Flutter 全量

在 `apps/desktop` 执行：

```sh
../../../.tooling/flutter/bin/flutter test
```

第一次实际结果：`00:35 +627 -2: Some tests failed.`，仅两项 `ui_log_2_test.dart` 更新日志测试因未显式开启检查而失败。修复测试注入后再次完整执行，最终实际末行：`00:34 +629: All tests passed!`。
最终 629 项通过，0 失败。输出仍含既有 `media_kit` native 依赖提示，但测试进程退出码为 0，未为消除提示安装应用或改动依赖。

### 格式、生成与清理

- Dart formatter 已运行于全部本次修改的 Dart 文件；最终格式化无额外变化。
- l10n 由项目 `flutter gen-l10n` 流程生成，ARB 与生成文件一致。
- `git diff --check` 最终退出码为 0。
- Flutter 自动改写的 `apps/desktop/pubspec.lock`、macOS/Windows 插件生成文件已全部 `git restore`，不进入提交。
- 一次性 `.test-venv`、`.uv-test-cache` 和测试输出目录仅用于本地验证，不进入提交。

## 自审

- 逐项对照 brief：2 Critical、2 Important、4 Minor 均有对应生产和/或测试修改及最终 GREEN。
- macOS 默认创建与扫描均经过同一个可注入根；显式 `BHE_PROJECTS_ROOT` 优先级未变。
- 没有新增读取、扫描或删除原版默认目录的代码；显式历史项目行为未扩展。
- Windows/Android 无生产文件差异；其默认目录、下载 pattern、更新协议由相关测试继续覆盖。
- 更新禁用同时覆盖手动和自动入口；既有更新测试全部显式注入开启状态。
- 真实 ARB 与生成代码同步；关于、退出和 macOS 安装说明均传入共享展示名。
- Release 的 `BHE*` 与两条 OSS workflow 的精确 fake-gh pattern 覆盖相互独立；没有启用 OSS 或改变 tag-push 发布门禁。
- 未创建标签、Release 或推送，未安装应用，未修改 `/Applications`，未读取真实原版项目数据。

## 文件清单

生产与工作流：

- `.github/workflows/release-packages.yml`
- `apps/desktop/lib/app.dart`
- `apps/desktop/lib/components/cs_scaffold.dart`
- `apps/desktop/lib/components/cs_sidebar_shell.dart`
- `apps/desktop/lib/core/project_session.dart`
- `apps/desktop/lib/features/update/update_dialog.dart`
- `apps/desktop/lib/providers/project_state.dart`
- `apps/desktop/lib/providers/update_provider.dart`
- `packages/bhe_l10n/lib/l10n/app_en.arb`
- `packages/bhe_l10n/lib/l10n/app_zh.arb`
- `packages/bhe_l10n/lib/src/generated/bhe_localizations.dart`
- `packages/bhe_l10n/lib/src/generated/bhe_localizations_en.dart`
- `packages/bhe_l10n/lib/src/generated/bhe_localizations_zh.dart`
- `scripts/build_update_manifest.py`

测试：

- `apps/desktop/test/core/app_identity_test.dart`
- `apps/desktop/test/providers/project_state_test.dart`
- `apps/desktop/test/router/app_router_test.dart`
- `apps/desktop/test/ui_log_2_test.dart`
- `apps/desktop/test/update_test.dart`
- `apps/desktop/test/widget_test.dart`
- `tests/test_build_update_manifest.py`
- `tests/test_macos_bhe_pro_packaging.py`
- `tests/test_platform_patch_workflows.py`

## 顾虑与后续边界

- macOS BHE Pro 的自动和手动更新检查在独立更新通道出现前会有意保持关闭。
- 本次只通过 fake tools、fake services 和 workflow 脚本测试验证发布/打包逻辑，没有执行真实 Release、OSS 上传或应用安装。
