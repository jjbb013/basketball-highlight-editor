# BHE Pro macOS Independent App Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 macOS 二次开发版交付为可与原版共存的 `BHE Pro.app`，隔离全部应用数据，并发布经过验证的 Apple Silicon、Intel DMG。

**Architecture:** 以 macOS 原生构建设置决定应用 bundle、可执行文件和偏好设置隔离；Flutter 通过一个轻量 `appDisplayName()` 来源统一 macOS 可见品牌，并用可注入的平台布尔值测试各平台数据目录。打包脚本继续使用现有环境变量接口，测试通过 `BHE_APP_DIR` 隔离构建目录，真实双架构编译、模型运行和签名由现有 GitHub Actions 完成。

**Tech Stack:** macOS Xcode/xcconfig/plist/Swift、Flutter/Dart、Bash、Python pytest、GitHub Actions、GitHub CLI、DMG/hdiutil。

## Global Constraints

- 用户可见名称固定为 `BHE Pro`；应用为 `BHE Pro.app`；可执行文件为 `BHE Pro`。
- macOS bundle identifier 固定为 `com.courtside.bhepro`。
- macOS 备用项目目录为 `~/Library/Application Support/BHE Pro/Projects`，日志为 `~/Library/Logs/BHE Pro`，更新缓存为 `~/Library/Caches/BHE Pro/updates`。
- 不读取、迁移、复制、删除或失败回退到原版 BHE 的偏好设置和数据目录；首次启动按全新应用处理。
- 下载资产前缀为 `BHE-Pro-macos-`，目标标签为 `v0.1.16-macos.3`，保留 `.1`、`.2` Release，不合并 `main`，不启用 OSS 更新。
- 安装辅助脚本只处理 `/Applications/BHE Pro.app` 和进程 `BHE Pro`，绝不能 `pkill -x BHE`、替换或删除原版。
- 仅 macOS 改名称和数据目录；Windows、Android、内部 Python/Flutter 包名、MethodChannel、数据库表和协议不变。
- 不改图标，不引入签名/公证；继续明确 Ad Hoc、未公证边界。
- 含空格路径必须完整引用；每个功能先写失败测试，再实现；不修改或安装本机 `/Applications` 中的应用。
- 设计依据：`docs/superpowers/specs/2026-11-23-bhe-pro-macos-design.md`。
- 命令均从仓库根目录执行；本地工具为 `../.tooling/flutter/bin/flutter` 和 `../.venv/bin/python`。

## File Structure

- `apps/desktop/lib/core/app_identity.dart`：新建；集中返回 macOS/其他平台的显示名称。
- `apps/desktop/lib/core/project_session.dart`：macOS 备用项目目录和可测试的平台参数。
- `apps/desktop/lib/core/app_log.dart`：macOS 日志目录和可测试的平台参数。
- `apps/desktop/lib/providers/update_provider.dart`：macOS 更新缓存目录和可测试的平台参数。
- `apps/desktop/lib/app.dart`、`components/cs_sidebar_shell.dart`、`components/cs_scaffold.dart`、`features/about/about_dialog.dart`：复用统一显示名称，不新增业务状态。
- `apps/desktop/test/core/app_identity_test.dart`：新建；覆盖品牌及三类目录的跨平台边界和关于页面。
- `apps/desktop/test/router/app_router_test.dart`：扩展真实侧栏测试，检查 BHE Pro 品牌。
- `apps/desktop/macos/Runner/Configs/AppInfo.xcconfig`、`Runner/Info.plist`、`Runner/MainFlutterWindow.swift`：原生应用身份。
- `tests/test_macos_bhe_pro_identity.py`：新建；静态验证原生身份，防止配置漂移。
- `scripts/build_macos_release.sh`：默认应用、DMG 和包内辅助文件名；增加仅供隔离测试/构建定位的 `BHE_APP_DIR` 覆盖入口。
- `scripts/create_macos_dmg.sh`：DMG 卷名改为 `BHE Pro`。
- `scripts/macos_dmg/BHE-首次打开修复.command` 移为 `BHE-Pro-首次打开修复.command`；只操作新应用。
- `scripts/macos_dmg/BHE-使用说明.html` 移为 `BHE-Pro-使用说明.html`；所有命令明确引用新路径。
- `tests/test_macos_bhe_pro_packaging.py`：新建；静态安全约束和隔离的假工具打包集成测试。
- `tests/test_identity_packaging.py`、`tests/test_platform_patch_workflows.py`：同步现有 macOS 路径断言，不改更新通道协议。
- `.github/workflows/release-packages.yml`、`.github/workflows/upload-release-assets-oss.yml`：macOS 构建路径和新资产名，其他平台保持不变。

---

### Task 1: 固定 macOS 原生身份和窗口名称

**Files:**
- Create: `tests/test_macos_bhe_pro_identity.py`
- Modify: `apps/desktop/macos/Runner/Configs/AppInfo.xcconfig:7-14`
- Modify: `apps/desktop/macos/Runner/Info.plist:15-16`
- Modify: `apps/desktop/macos/Runner/MainFlutterWindow.swift:10`

**Interfaces:**
- Produces: `PRODUCT_NAME=BHE Pro`、`PRODUCT_BUNDLE_IDENTIFIER=com.courtside.bhepro`，供 Flutter 偏好设置、打包和 Release 验证共同使用。

- [ ] **Step 1: 写入失败的原生配置测试**

```python
import plistlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / 'apps/desktop/macos/Runner'


def test_macos_native_bundle_is_independent_bhe_pro():
    config = {}
    for line in (RUNNER / 'Configs/AppInfo.xcconfig').read_text().splitlines():
        if '=' in line and not line.lstrip().startswith('//'):
            key, value = line.split('=', 1)
            config[key.strip()] = value.strip()
    assert config['PRODUCT_NAME'] == 'BHE Pro'
    assert config['PRODUCT_BUNDLE_IDENTIFIER'] == 'com.courtside.bhepro'
    assert config['PRODUCT_COPYRIGHT'].startswith('Copyright © 2026 BHE Pro ')
    with (RUNNER / 'Info.plist').open('rb') as stream:
        plist = plistlib.load(stream)
    assert plist['CFBundleDisplayName'] == 'BHE Pro'
    assert plist['CFBundleExecutable'] == '$(EXECUTABLE_NAME)'
    assert plist['CFBundleIdentifier'] == '$(PRODUCT_BUNDLE_IDENTIFIER)'


def test_native_window_and_method_channel_keep_their_respective_names():
    source = (RUNNER / 'MainFlutterWindow.swift').read_text()
    assert 'self.title = "BHE Pro"' in source
    assert 'name: "bhe/file_dialog"' in source
```

- [ ] **Step 2: 运行测试确认失败**

Run: `../.venv/bin/python -m pytest -q tests/test_macos_bhe_pro_identity.py`
Expected: FAIL，实际产品名仍为 `BHE`，identifier 仍为 `com.courtside.highlighteditor`。

- [ ] **Step 3: 只修改三项原生配置**

`AppInfo.xcconfig` 使用以下完整设置：

```xcconfig
// The application's name. By default this is also the title of the Flutter window.
PRODUCT_NAME = BHE Pro

// The application's bundle identifier
PRODUCT_BUNDLE_IDENTIFIER = com.courtside.bhepro

// The copyright displayed in application information
PRODUCT_COPYRIGHT = Copyright © 2026 BHE Pro (basketball-highlight-editor). All rights reserved.
```

`Info.plist` 对应键改为：

```xml
<key>CFBundleDisplayName</key>
<string>BHE Pro</string>
```

`MainFlutterWindow.swift` 只改窗口标题，保留原 MethodChannel：

```swift
self.title = "BHE Pro"
```

不修改 `project.pbxproj` 中的 RunnerTests 占位配置，也不修改 Xcode scheme。

- [ ] **Step 4: 验证测试与 plist 语法**

Run: `../.venv/bin/python -m pytest -q tests/test_macos_bhe_pro_identity.py && plutil -lint apps/desktop/macos/Runner/Info.plist`
Expected: 2 passed；plist 输出 OK。

- [ ] **Step 5: 提交原生身份**

```bash
git add apps/desktop/macos/Runner/Configs/AppInfo.xcconfig apps/desktop/macos/Runner/Info.plist apps/desktop/macos/Runner/MainFlutterWindow.swift tests/test_macos_bhe_pro_identity.py
git diff --cached --check && git commit -m "feat: give macOS app an independent BHE Pro identity"
```

### Task 2: 统一 Flutter 品牌并隔离 macOS 数据目录

**Files:**
- Create: `apps/desktop/lib/core/app_identity.dart`
- Create: `apps/desktop/test/core/app_identity_test.dart`
- Modify: `apps/desktop/lib/core/project_session.dart:17-24`
- Modify: `apps/desktop/lib/core/app_log.dart:5-10`
- Modify: `apps/desktop/lib/providers/update_provider.dart:50-55`
- Modify: `apps/desktop/lib/app.dart:155,196`
- Modify: `apps/desktop/lib/components/cs_sidebar_shell.dart:251`
- Modify: `apps/desktop/lib/components/cs_scaffold.dart:184`
- Modify: `apps/desktop/lib/features/about/about_dialog.dart:62,120`
- Modify: `apps/desktop/test/router/app_router_test.dart:71-81`

**Interfaces:**
- Produces: `String appDisplayName({bool? isMacOS})`；生产调用使用无参形式，测试传 `isMacOS`。
- Produces: `fallbackProjectsRoot(env, {bool? isWindows, bool? isMacOS})`、`engineLogDirectory(env, {bool? isWindows, bool? isMacOS})`、`updateDownloadDirectory(env, {bool? isWindows, bool? isMacOS})`；原调用保持兼容。
- Consumes: Task 1 的新 bundle identifier；SharedPreferences 通过原生插件自然隔离，不增加手动偏好迁移代码。

- [ ] **Step 1: 写入品牌、目录和关于页面的失败测试**

新建 `apps/desktop/test/core/app_identity_test.dart`：

```dart
import 'package:desktop/core/app_identity.dart';
import 'package:desktop/core/app_log.dart';
import 'package:desktop/core/project_session.dart';
import 'package:desktop/features/about/about_dialog.dart';
import 'package:desktop/providers/update_provider.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('only macOS uses the BHE Pro display name', () {
    expect(appDisplayName(isMacOS: true), 'BHE Pro');
    expect(appDisplayName(isMacOS: false), 'BHE');
  });

  test('macOS directories are independent and other platforms are unchanged', () {
    const env = <String, String>{
      'HOME': '/Users/test',
      'LOCALAPPDATA': r'C:\Users\test\AppData\Local',
      'XDG_DATA_HOME': '/home/test/.local/share',
      'XDG_STATE_HOME': '/home/test/.local/state',
      'XDG_CACHE_HOME': '/home/test/.cache',
    };
    expect(
      fallbackProjectsRoot(env, isMacOS: true, isWindows: false),
      '/Users/test/Library/Application Support/BHE Pro/Projects',
    );
    expect(
      engineLogDirectory(env, isMacOS: true, isWindows: false),
      '/Users/test/Library/Logs/BHE Pro',
    );
    expect(
      updateDownloadDirectory(env, isMacOS: true, isWindows: false),
      '/Users/test/Library/Caches/BHE Pro/updates',
    );
    expect(
      fallbackProjectsRoot(env, isMacOS: false, isWindows: true),
      r'C:\Users\test\AppData\Local\BHE\Projects',
    );
    expect(
      engineLogDirectory(env, isMacOS: false, isWindows: true),
      r'C:\Users\test\AppData\Local\BHE\logs',
    );
    expect(
      updateDownloadDirectory(env, isMacOS: false, isWindows: true),
      r'C:\Users\test\AppData\Local\BHE\updates',
    );
    expect(
      fallbackProjectsRoot(env, isMacOS: false, isWindows: false),
      '/home/test/.local/share/bhe/projects',
    );
    expect(
      engineLogDirectory(env, isMacOS: false, isWindows: false),
      '/home/test/.local/state/bhe/logs',
    );
    expect(
      updateDownloadDirectory(env, isMacOS: false, isWindows: false),
      '/home/test/.cache/bhe/updates',
    );
  });

  testWidgets('about page uses the shared display name', (tester) async {
    await tester.pumpWidget(MaterialApp(
      home: Builder(
        builder: (context) => TextButton(
          onPressed: () => showCourtsideAboutDialog(context),
          child: const Text('open-about'),
        ),
      ),
    ));
    await tester.tap(find.text('open-about'));
    await tester.pumpAndSettle();
    expect(find.text(appDisplayName()), findsOneWidget);
    expect(find.textContaining('/Library/Logs/${appDisplayName()}'), findsOneWidget);
  });
}
```

在 `app_router_test.dart` 的 `wide window renders CsSidebarShell` 末尾添加：

```dart
expect(find.text('BHE Pro'), findsOneWidget);
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd apps/desktop && ../../.tooling/flutter/bin/flutter test test/core/app_identity_test.dart test/router/app_router_test.dart`
Expected: 编译失败，找不到 `app_identity.dart`；实现部分函数后，关于页面和侧栏的 `BHE Pro` 断言必须先失败，再替换可见字符串。

- [ ] **Step 3: 新建统一显示名称和可测试目录函数**

`app_identity.dart` 完整内容：

```dart
import 'dart:io';

String appDisplayName({bool? isMacOS}) =>
    (isMacOS ?? Platform.isMacOS) ? 'BHE Pro' : 'BHE';
```

三个目录函数分别使用以下签名和分支；其他代码保持原样：

```dart
String fallbackProjectsRoot(
  Map<String, String> env, {
  bool? isWindows,
  bool? isMacOS,
}) {
  final home = env['HOME'] ?? env['USERPROFILE'] ?? Directory.systemTemp.path;
  if (isWindows ?? Platform.isWindows) {
    return '${env['LOCALAPPDATA'] ?? home}\\BHE\\Projects';
  }
  if (isMacOS ?? Platform.isMacOS) {
    return '$home/Library/Application Support/BHE Pro/Projects';
  }
  return '${env['XDG_DATA_HOME'] ?? '$home/.local/share'}/bhe/projects';
}
```

```dart
String engineLogDirectory(
  Map<String, String> env, {
  bool? isWindows,
  bool? isMacOS,
}) {
  final home = env['HOME'] ?? env['USERPROFILE'] ?? Directory.systemTemp.path;
  if (isMacOS ?? Platform.isMacOS) return '$home/Library/Logs/BHE Pro';
  if (isWindows ?? Platform.isWindows) {
    return '${env['LOCALAPPDATA'] ?? home}\\BHE\\logs';
  }
  return '${env['XDG_STATE_HOME'] ?? '$home/.local/state'}/bhe/logs';
}
```

```dart
String updateDownloadDirectory(
  Map<String, String> env, {
  bool? isWindows,
  bool? isMacOS,
}) {
  final home = env['HOME'] ?? env['USERPROFILE'] ?? Directory.systemTemp.path;
  if (isMacOS ?? Platform.isMacOS) {
    return '$home/Library/Caches/BHE Pro/updates';
  }
  if (isWindows ?? Platform.isWindows) {
    return '${env['LOCALAPPDATA'] ?? home}\\BHE\\updates';
  }
  return '${env['XDG_CACHE_HOME'] ?? '$home/.cache'}/bhe/updates';
}
```

- [ ] **Step 4: 接入所有已确认的 macOS 可见名称**

在 `app.dart` 导入 `core/app_identity.dart`，使用：

```dart
title: appDisplayName(),
```

退出对话框无翻译时的标题改为：

```dart
: '退出 ${appDisplayName()}？',
```

在 `cs_sidebar_shell.dart` 导入 `../core/app_identity.dart`，品牌文字改为：

```dart
Text(
  appDisplayName(),
  overflow: TextOverflow.ellipsis,
  style: theme.textTheme.labelLarge?.copyWith(
    color: c.textPrimary,
    fontWeight: FontWeight.w600,
    letterSpacing: -.1,
  ),
),
```

在 `cs_scaffold.dart` 导入 `../core/app_identity.dart`，无翻译时菜单文字改为：

```dart
child: Text(l10n?.about ?? '关于 ${appDisplayName()}'),
```

在 `about_dialog.dart` 导入 `../../core/app_identity.dart`，关于标题和许可页名称分别改为：

```dart
Text(appDisplayName(), style: theme.textTheme.titleLarge),
```

```dart
applicationName: appDisplayName(),
applicationVersion: 'v$appVersion',
```

保留 Windows 标题栏、更新安装器、诊断格式、反馈主题、导出文件名和内部 BHE 环境变量，不做全局替换。

- [ ] **Step 5: 格式化并运行目标测试**

Run: `cd apps/desktop && ../../.tooling/flutter/bin/dart format lib/core/app_identity.dart lib/core/project_session.dart lib/core/app_log.dart lib/providers/update_provider.dart lib/app.dart lib/components/cs_sidebar_shell.dart lib/components/cs_scaffold.dart lib/features/about/about_dialog.dart test/core/app_identity_test.dart test/router/app_router_test.dart && ../../.tooling/flutter/bin/flutter test test/core/app_identity_test.dart test/router/app_router_test.dart`
Expected: 全部 PASS；本机为 macOS，因此关于页及侧栏应显示 `BHE Pro`。

- [ ] **Step 6: 提交品牌和数据隔离**

```bash
git add apps/desktop/lib/core/app_identity.dart apps/desktop/lib/core/project_session.dart apps/desktop/lib/core/app_log.dart apps/desktop/lib/providers/update_provider.dart apps/desktop/lib/app.dart apps/desktop/lib/components/cs_sidebar_shell.dart apps/desktop/lib/components/cs_scaffold.dart apps/desktop/lib/features/about/about_dialog.dart apps/desktop/test/core/app_identity_test.dart apps/desktop/test/router/app_router_test.dart
git diff --cached --check && git commit -m "feat: isolate BHE Pro branding and macOS data"
```

### Task 3: 让 DMG 和安装辅助工具只处理 BHE Pro

**Files:**
- Create: `tests/test_macos_bhe_pro_packaging.py`
- Modify: `scripts/build_macos_release.sh:7-9,92-105`
- Modify: `scripts/create_macos_dmg.sh:20`
- Rename: `scripts/macos_dmg/BHE-首次打开修复.command` → `scripts/macos_dmg/BHE-Pro-首次打开修复.command`
- Rename: `scripts/macos_dmg/BHE-使用说明.html` → `scripts/macos_dmg/BHE-Pro-使用说明.html`
- Modify: `tests/test_macos_dmg.py`

**Interfaces:**
- Consumes: Task 1 的 `BHE Pro.app`。
- Produces: 可选 `BHE_APP_DIR=<Release 目录>`，默认仍指向 `apps/desktop/build/macos/Build/Products/Release`；产物为 `BHE-Pro-macos-<arch>-v<version>-adhoc.dmg`。
- Produces: 固定辅助脚本 `BHE-Pro-首次打开修复.command`、说明 `BHE-Pro-使用说明.html`、卷名 `BHE Pro`。

- [ ] **Step 1: 写入不会触碰原版的静态测试和空格路径集成测试**

新建 `tests/test_macos_bhe_pro_packaging.py`：

```python
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / 'scripts/macos_dmg/BHE-Pro-首次打开修复.command'
GUIDE = ROOT / 'scripts/macos_dmg/BHE-Pro-使用说明.html'
BUILD = ROOT / 'scripts/build_macos_release.sh'


def test_helper_and_guide_never_target_original_bhe():
    helper = HELPER.read_text(encoding='utf-8')
    guide = GUIDE.read_text(encoding='utf-8')
    for text in (helper, guide):
        assert '/Applications/BHE.app' not in text
        assert '/Volumes/BHE/BHE.app' not in text
        assert 'pkill -x BHE ' not in text
        assert 'open -a BHE\n' not in text
    assert 'APP_NAME="BHE Pro.app"' in helper
    assert 'DEST="/Applications/$APP_NAME"' in helper
    assert 'pkill -x "BHE Pro"' in helper
    assert 'ditto "$VOLUME_APP" "$DEST"' in helper
    assert 'codesign --verify --deep --strict "$DEST"' in helper
    assert 'ditto "/Volumes/BHE Pro/BHE Pro.app" "/Applications/BHE Pro.app"' in guide
    assert 'xattr -dr com.apple.quarantine "/Applications/BHE Pro.app"' in guide
    assert 'open "/Applications/BHE Pro.app"' in guide


@pytest.mark.skipif(os.name == 'nt', reason='macOS packaging uses Bash')
def test_build_packages_space_named_app_with_isolated_fake_tools(tmp_path):
    tools = tmp_path / 'tools'
    tools.mkdir()
    calls = tmp_path / 'calls'
    app_dir = tmp_path / 'Release With Spaces'
    runtime = tmp_path / 'Runtime With Spaces'
    python = runtime / 'python/bin/python3'
    python.parent.mkdir(parents=True)
    python.write_text(
        '#!/bin/bash\nprintf "python" >> "$CALL_LOG"\n'
        'printf " <%s>" "$@" >> "$CALL_LOG"\nprintf "\\n" >> "$CALL_LOG"\n'
    )
    python.chmod(0o755)
    flutter = tools / 'flutter'
    flutter.write_text(
        '#!/bin/bash\nset -e\nprintf "flutter" >> "$CALL_LOG"\n'
        'printf " <%s>" "$@" >> "$CALL_LOG"\nprintf "\\n" >> "$CALL_LOG"\n'
        'mkdir -p "$BHE_APP_DIR/BHE Pro.app/Contents/MacOS"\n'
        'printf executable > "$BHE_APP_DIR/BHE Pro.app/Contents/MacOS/BHE Pro"\n'
    )
    for name in ('codesign', 'ditto'):
        tool = tools / name
        tool.write_text(
            '#!/bin/bash\nprintf "' + name + '" >> "$CALL_LOG"\n'
            'printf " <%s>" "$@" >> "$CALL_LOG"\nprintf "\\n" >> "$CALL_LOG"\n'
        )
        tool.chmod(0o755)
    hdiutil = tools / 'hdiutil'
    hdiutil.write_text(
        '#!/bin/bash\nprintf "hdiutil" >> "$CALL_LOG"\n'
        'printf " <%s>" "$@" >> "$CALL_LOG"\nprintf "\\n" >> "$CALL_LOG"\n'
        'if [[ "$1" == verify ]]; then exit 0; fi\n'
        'for last; do :; done\nprintf dmg > "$last"\n'
    )
    for tool in (flutter, hdiutil):
        tool.chmod(0o755)
    output = tmp_path / 'output with spaces/BHE-Pro-test.dmg'
    result = subprocess.run(
        ['bash', str(BUILD)],
        env={
            **os.environ,
            'PATH': f'{tools}:{os.environ["PATH"]}',
            'CALL_LOG': str(calls),
            'FLUTTER_BIN': str(flutter),
            'BHE_APP_DIR': str(app_dir),
            'BHE_RUNTIME_OUT': str(runtime),
            'BHE_SKIP_RUNTIME_PREPARE': '1',
            'BHE_BUILD_NAME': '0.1.16-macos.3',
            'BHE_BUILD_NUMBER': '3',
            'BHE_ARCH': 'arm64',
            'BHE_DMG_OUT': str(output),
            'TMPDIR': str(tmp_path),
        },
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    log = calls.read_text()
    assert f'ditto <{app_dir}/BHE Pro.app> <' in log
    assert f'codesign <--deep> <--force> <--sign> <-> <{app_dir}/BHE Pro.app>' in log
    assert 'hdiutil <create> <-volname> <BHE Pro>' in log
    assert output.read_bytes() == b'dmg'
    assert output.with_suffix('.dmg.sha256').is_file()
    assert 'BHE Pro.app' in result.stdout
```

在 `tests/test_macos_dmg.py` 增加静态卷名检查：

```python
def test_dmg_volume_is_named_bhe_pro():
    script = (Path(__file__).resolve().parents[1] / 'scripts/create_macos_dmg.sh').read_text()
    assert '-volname "BHE Pro"' in script
```

- [ ] **Step 2: 运行打包测试确认失败**

Run: `../.venv/bin/python -m pytest -q tests/test_macos_bhe_pro_packaging.py tests/test_macos_dmg.py`
Expected: 新辅助文件不存在，默认应用仍为 `BHE`，卷名仍为 `BHE`；测试失败，不执行真实签名或安装。

- [ ] **Step 3: 修改构建入口并原子重命名辅助文件**

使用 `git mv` 保留历史：

```bash
git mv "scripts/macos_dmg/BHE-首次打开修复.command" "scripts/macos_dmg/BHE-Pro-首次打开修复.command"
git mv "scripts/macos_dmg/BHE-使用说明.html" "scripts/macos_dmg/BHE-Pro-使用说明.html"
```

`build_macos_release.sh` 的相关变量改为：

```bash
APP_DIR="${BHE_APP_DIR:-$ROOT/apps/desktop/build/macos/Build/Products/Release}"
APP_NAME="${BHE_APP_NAME:-BHE Pro}"
APP="$APP_DIR/$APP_NAME.app"
```

默认 DMG 改为：

```bash
DMG_OUT="$ROOT/dist/BHE-Pro-macos-${ARCH}-v${package_version}-${package_kind}.dmg"
```

包内复制、权限和签名统一使用新文件名，所有路径保持引用：

```bash
ditto "$APP" "$dmg_staging/$APP_NAME.app"
cp "$ROOT/scripts/macos_dmg/BHE-Pro-首次打开修复.command" "$dmg_staging/"
cp "$ROOT/scripts/macos_dmg/BHE-Pro-使用说明.html" "$dmg_staging/"
chmod +x "$dmg_staging/BHE-Pro-首次打开修复.command"
codesign --sign - "$dmg_staging/BHE-Pro-首次打开修复.command" >/dev/null 2>&1 || true
ln -s /Applications "$dmg_staging/Applications"
rm -f "$DMG_OUT"
bash "$ROOT/scripts/create_macos_dmg.sh" "$dmg_staging" "$DMG_OUT"
```

`create_macos_dmg.sh` 只改卷名：

```bash
if hdiutil create -volname "BHE Pro" -fs HFS+ -srcfolder "$source_directory" \
  -ov -format UDZO "$output" > "$log_file" 2>&1; then
```

- [ ] **Step 4: 固定辅助脚本目标、进程和错误路径**

将 `BHE-Pro-首次打开修复.command` 完整替换为：

```bash
#!/bin/bash
set -u

APP_NAME="BHE Pro.app"
DEST="/Applications/$APP_NAME"

pause_and_exit() {
  local code="$1"
  printf '\n按回车关闭此窗口...'
  read -r _ || true
  exit "$code"
}

show_error() {
  local message="$1"
  printf '\n错误：%s\n' "$message" >&2
  osascript -e "display dialog \"BHE Pro 修复失败：$message\" buttons {\"知道了\"} default button \"知道了\" with icon stop" >/dev/null 2>&1 || true
  pause_and_exit 1
}

find_volume_app() {
  local candidate
  for candidate in /Volumes/*/"$APP_NAME"; do
    if [[ -d "$candidate" ]]; then
      printf '%s' "$candidate"
      return 0
    fi
  done
  return 1
}

clear
echo "BHE Pro macOS 一键安装与修复"
echo "================================"
echo "双击本命令后无需其他操作：自动安装、清除首次打开拦截并启动。"
echo "本工具只处理 BHE Pro.app，不会修改原版 BHE 或其他文件。"
echo

VOLUME_APP="$(find_volume_app || true)"

if [[ -n "$VOLUME_APP" ]]; then
  echo "[1/4] 正在安装 BHE Pro 到“应用程序”..."
  pkill -x "BHE Pro" 2>/dev/null || true
  sleep 1
  if [[ -d "$DEST" ]]; then
    if rm -rf "$DEST" 2>/dev/null; then
      :
    else
      echo "已安装的 BHE Pro 暂时无法替换（应用可能正在运行），将继续修复现有版本。"
    fi
  fi
  if [[ ! -d "$DEST" ]]; then
    ditto "$VOLUME_APP" "$DEST" || show_error "无法复制 BHE Pro.app 到“应用程序”。请手动把 BHE Pro.app 拖到“应用程序”后，重新双击本命令。"
  fi
elif [[ -d "$DEST" ]]; then
  echo "[1/4] 检测到 BHE Pro 已安装在“应用程序”，跳过安装。"
else
  show_error "没有找到 BHE Pro.app。请保留本窗口，把 BHE Pro.app 拖到“应用程序”后重新双击本命令。"
fi

echo "目标应用：$DEST"
echo

echo "[2/4] 清除下载隔离属性..."
if xattr -p com.apple.quarantine "$DEST" >/dev/null 2>&1; then
  xattr -dr com.apple.quarantine "$DEST" || show_error "无法清除 macOS 下载隔离属性。"
  echo "已清除 com.apple.quarantine。"
else
  echo "未发现下载隔离属性。"
fi

echo

echo "[3/4] 验证应用签名完整性..."
if ! codesign --verify --deep --strict "$DEST" >/dev/null 2>&1; then
  show_error "应用签名验证失败，文件可能不完整。请重新下载 DMG 后再试。"
fi
echo "签名完整性验证通过。"
echo

echo "[4/4] 启动 BHE Pro..."
open "$DEST" || show_error "应用验证通过，但启动失败。可打开“应用程序”手动双击 BHE Pro 启动。"
echo
echo "完成：BHE Pro 已安装并通过本机验证，正在启动。"
osascript -e 'display dialog "BHE Pro 安装与修复完成，现在可以正常使用了。" buttons {"好的"} default button "好的" with icon note' >/dev/null 2>&1 || true
pause_and_exit 0
```

此脚本不得添加原版目录回退；目标缺失和签名失败均停止。

- [ ] **Step 5: 更新安装说明中的全部实际操作路径**

`BHE-Pro-使用说明.html` 保留现有样式和复制脚本，更新标题及正文中的 BHE 为 BHE Pro；页面主标题、一步命令和方法三分别使用以下准确内容：

```html
<title>BHE Pro macOS 使用说明</title>
<h1>BHE Pro macOS 使用说明</h1>
```

```html
<code id="fix-cmd">ditto "/Volumes/BHE Pro/BHE Pro.app" "/Applications/BHE Pro.app" &amp;&amp; xattr -dr com.apple.quarantine "/Applications/BHE Pro.app" &amp;&amp; open "/Applications/BHE Pro.app"</code>
```

```html
双击 <code>BHE-Pro-首次打开修复.command</code>，自动完成安装、清拦截和启动。双击它时如果也弹"无法验证"，同样右键 → 打开；右键也不行，就用上面的方法一。
```

方法二明确拖入 `BHE Pro.app` 并在“应用程序”中打开 `BHE Pro`；结尾明确“以上操作只处理 BHE Pro.app，不读取、迁移或删除原版 BHE 的项目和设置”。保留 Ad Hoc、未公证说明，不添加自动迁移或已公证文案。

- [ ] **Step 6: 运行静态、集成和 Bash 语法测试**

Run: `../.venv/bin/python -m pytest -q tests/test_macos_bhe_pro_packaging.py tests/test_macos_dmg.py && bash -n scripts/build_macos_release.sh scripts/create_macos_dmg.sh "scripts/macos_dmg/BHE-Pro-首次打开修复.command"`
Expected: 全部 PASS；集成测试包含 `BHE Pro.app`、`-volname BHE Pro` 的完整单参数记录，输出文件和 SHA-256 均生成。

- [ ] **Step 7: 提交安全打包变更**

```bash
git add scripts/build_macos_release.sh scripts/create_macos_dmg.sh scripts/macos_dmg tests/test_macos_bhe_pro_packaging.py tests/test_macos_dmg.py
git diff --cached --check && git commit -m "feat: package BHE Pro without touching original BHE"
```

### Task 4: 对齐 CI 路径和 Release 资产名称

**Files:**
- Modify: `.github/workflows/release-packages.yml:302-327,687`
- Modify: `.github/workflows/upload-release-assets-oss.yml:112-113`
- Modify: `tests/test_identity_packaging.py:33-40`
- Modify: `tests/test_platform_patch_workflows.py:265-278,335-342`

**Interfaces:**
- Consumes: Task 3 的 `BHE-Pro-macos-` 产物、`BHE Pro.app` 和辅助文件。
- Produces: Actions 产物 `BHE-Pro-macos-arm64`、`BHE-Pro-macos-x86_64`；GitHub Release 只增加 `.3` 文件。Windows/Android 名称和 OSS 发布门禁不变。

- [ ] **Step 1: 更新测试以锁定 CI 的新路径和保留的安全边界**

`test_identity_packaging.py` 的 CI 路径断言改为：

```python
assert 'BHE Pro.app/Contents/Resources/runtime' in script
assert 'scripts/check_packaged_models.py --runtime' in script
assert 'YOLO_AUTOINSTALL=false' in script
```

`test_platform_patch_workflows.py` 的平台用例改为：

```python
('all', 'v0.1.13', ['BHE-Pro-*.dmg', 'BHE-Pro-*.dmg.sha256', 'BHE-*.zip', 'BHE-*.zip.sha256', 'BHE-*.apk', 'BHE-*.apk.sha256']),
('macos', 'v0.1.13-macos.1', ['BHE-Pro-macos-*.dmg', 'BHE-Pro-macos-*.dmg.sha256']),
```

同一用例的 Windows、Android 行保持现有值。打包模型测试改为：

```python
assert 'BHE Pro.app/Contents/Resources/runtime/python/bin/python3' in script
assert 'scripts/check_numpy_preprocess.py --python' in script
assert script.index('scripts/build_macos_release.sh') < script.index('scripts/check_numpy_preprocess.py')
```

新增以下静态验证，禁止 CI 误用原版应用或旧 macOS 资产：

```python
def test_macos_release_uses_bhe_pro_app_and_new_asset_prefix():
    workflow = yaml.safe_load((ROOT / '.github/workflows/release-packages.yml').read_text())
    build = next(step for step in workflow['jobs']['macos']['steps'] if step.get('name') == 'Build macOS package')
    script = build['run']
    assert 'dist/BHE-Pro-macos-${ARCH}-v${version}-adhoc.dmg' in script
    assert 'Release/BHE Pro.app/Contents/MacOS/BHE Pro' in script
    assert 'Release/BHE.app' not in script
    assert 'dist/BHE-macos-' not in script
    assert 'hdiutil attach "$dmg" -readonly -nobrowse -mountpoint "$mount_point"' in script
    assert 'plutil -extract CFBundleIdentifier raw "$mount_point/BHE Pro.app/Contents/Info.plist"' in script
    assert any(
        'BHE-Pro-macos-*.dmg.sha256' in step.get('run', '')
        for step in workflow['jobs']['oss-upload']['steps']
    )
```

- [ ] **Step 2: 运行工作流测试确认失败**

Run: `../.venv/bin/python -m pytest -q tests/test_identity_packaging.py tests/test_platform_patch_workflows.py`
Expected: 旧 `BHE.app` 和 `BHE-macos` 断言失败；现有 tag-push 不进入 OSS 的测试必须继续通过。

- [ ] **Step 3: 精确修改 macOS 构建、上传和资产筛选**

`release-packages.yml` 构建段使用：

```bash
version="${TAG_NAME#v}"
dmg="$GITHUB_WORKSPACE/dist/BHE-Pro-macos-${ARCH}-v${version}-adhoc.dmg"
BHE_PYTHON_RUNTIME="$PYTHON_ROOT" \
BHE_FFMPEG="$FFMPEG_PATH" \
BHE_FFPROBE="$FFPROBE_PATH" \
BHE_BUILD_NAME="$version" \
BHE_BUILD_NUMBER="${GITHUB_RUN_NUMBER}" \
BHE_DMG_OUT="$dmg" \
FLUTTER_BIN="$(command -v flutter)" \
scripts/build_macos_release.sh
file "apps/desktop/build/macos/Build/Products/Release/BHE Pro.app/Contents/MacOS/BHE Pro"
codesign --verify --deep --strict "apps/desktop/build/macos/Build/Products/Release/BHE Pro.app"
export PYTHONDONTWRITEBYTECODE=1 YOLO_AUTOINSTALL=false
export YOLO_CONFIG_DIR="$RUNNER_TEMP/bhe-yolo-smoke"
python3 scripts/check_numpy_preprocess.py --python \
  "apps/desktop/build/macos/Build/Products/Release/BHE Pro.app/Contents/Resources/runtime/python/bin/python3"
python3 scripts/check_packaged_models.py --runtime \
  "apps/desktop/build/macos/Build/Products/Release/BHE Pro.app/Contents/Resources/runtime"
mount_point="$RUNNER_TEMP/bhe-pro-mounted"
mkdir -p "$mount_point"
hdiutil attach "$dmg" -readonly -nobrowse -mountpoint "$mount_point"
test -d "$mount_point/BHE Pro.app"
test -x "$mount_point/BHE-Pro-首次打开修复.command"
test -f "$mount_point/BHE-Pro-使用说明.html"
test "$(plutil -extract CFBundleDisplayName raw "$mount_point/BHE Pro.app/Contents/Info.plist")" = "BHE Pro"
test "$(plutil -extract CFBundleIdentifier raw "$mount_point/BHE Pro.app/Contents/Info.plist")" = "com.courtside.bhepro"
codesign --verify --deep --strict "$mount_point/BHE Pro.app"
hdiutil detach "$mount_point"
```

上传段使用：

```yaml
name: BHE-Pro-macos-${{ matrix.arch }}
path: |
  dist/BHE-Pro-macos-${{ matrix.arch }}-v*-adhoc.dmg
  dist/BHE-Pro-macos-${{ matrix.arch }}-v*-adhoc.dmg.sha256
if-no-files-found: error
```

Release 下载 Actions 的 `pattern: BHE-*` 改为 `pattern: BHE*`，同时匹配 macOS 的 `BHE-Pro-` 和其他平台的 `BHE-`。OSS 下载筛选的 macOS 行改为：

```bash
all) patterns=('BHE-Pro-*.dmg' 'BHE-Pro-*.dmg.sha256' 'BHE-*.zip' 'BHE-*.zip.sha256' 'BHE-*.apk' 'BHE-*.apk.sha256') ;;
macos) patterns=('BHE-Pro-macos-*.dmg' 'BHE-Pro-macos-*.dmg.sha256') ;;
```

`upload-release-assets-oss.yml` 同步相同的 `all` 和 `macos` 两行。不要修改 OSS `publish_oss=false` 的门禁、Release 的 prerelease 逻辑或其他平台资产。

- [ ] **Step 4: 运行工作流测试和 YAML/Bash 校验**

Run: `../.venv/bin/python -m pytest -q tests/test_identity_packaging.py tests/test_platform_patch_workflows.py tests/test_publish_release_update.py`
Expected: 全部 PASS；包含假 `gh` 对 `--pattern` 参数的逐项检查，确认未误选旧 macOS 文件。

- [ ] **Step 5: 提交 CI 和发布资产变更**

```bash
git add .github/workflows/release-packages.yml .github/workflows/upload-release-assets-oss.yml tests/test_identity_packaging.py tests/test_platform_patch_workflows.py
git diff --cached --check && git commit -m "ci: build and publish BHE Pro macOS packages"
```

### Task 5: 全量验证、推送、双架构发布与正式 DMG 验收

**Files:**
- Verify: 本计划涉及的全部文件。
- Create locally, never commit: `artifacts/bhe-pro-v0.1.16-macos.3/` 下的正式下载文件和验收记录。

**Interfaces:**
- Consumes: Tasks 1–4 的提交。
- Produces: 推送后的功能分支、标签 `v0.1.16-macos.3`、GitHub Release 中两个正式 DMG 和 SHA-256 文件。

- [ ] **Step 1: 检查变更范围并运行全量测试和静态检查**

Run:

```bash
git status --short
git diff --check
../.venv/bin/python -m pytest -q
../.tooling/flutter/bin/flutter analyze apps/desktop
../.tooling/flutter/bin/flutter test apps/desktop
```

Expected: 工作区无未提交改动；Python、Flutter 全部 PASS；分析无问题。任何失败先修复并重跑对应全量检查，不能用 `.2` 的历史结果代替。

- [ ] **Step 2: 扫描危险边界并提交剩余验证性修正**

Run:

```bash
git diff 71a787036539bd56636d564744d0df24cf4e152f..HEAD --stat
```

逐条确认：无 `pkill -x BHE`、无 `/Applications/BHE.app` 操作、无旧 identifier 的 macOS 配置、无原版数据迁移、无 Windows/Android 产品改动、无模型/视频/本机密钥提交。若检查产生代码或测试修正，运行对应测试后使用：

```bash
git add <仅已检查的修正文件>
git diff --cached --check
git commit -m "test: verify BHE Pro coexistence boundaries"
```

- [ ] **Step 3: 推送功能分支并确认新标签尚不存在**

Run:

```bash
git push -u origin feature/macos-player-identity-enhanced-export
test -z "$(git tag --list v0.1.16-macos.3)"
gh release view v0.1.16-macos.3 >/dev/null 2>&1 && exit 1 || true
git rev-parse HEAD
```

Expected: 分支推送成功；本地无 `.3` 标签；没有同名 Release；记录完整 HEAD 哈希供发布追溯。

- [ ] **Step 4: 仅在已验证 HEAD 上创建并推送新标签**

```bash
git tag -a v0.1.16-macos.3 -m "BHE Pro macOS independent app"
git push origin v0.1.16-macos.3
```

Expected: 新标签指向 Step 3 的同一 HEAD；不重写、不删除 `.1`、`.2`。标签触发 workflow 的 macOS 双架构构建，OSS 保持关闭。

- [ ] **Step 5: 等待本次提交对应的 Actions 完成**

Run:

```bash
gh run list --workflow release-packages.yml --branch v0.1.16-macos.3 --limit 5 --json databaseId,headSha,status,conclusion,url
```

选择 `headSha` 等于 Step 3 HEAD 的运行，使用真实 `<run-id>`：

```bash
gh run watch <run-id> --exit-status
gh run view <run-id> --json status,conclusion,jobs,url
```

Expected: run 为 completed/success；macOS arm64 和 x86_64 均成功；GitHub Release 上传成功。失败时读取失败 job 日志、修复并重新验证，不把旧运行当作本次成功。

- [ ] **Step 6: 重新下载正式 Release，而不是验收本地临时包**

Run:

```bash
mkdir -p artifacts/bhe-pro-v0.1.16-macos.3
gh release download v0.1.16-macos.3 \
  --pattern 'BHE-Pro-macos-*.dmg' \
  --pattern 'BHE-Pro-macos-*.dmg.sha256' \
  --dir artifacts/bhe-pro-v0.1.16-macos.3
ls -l artifacts/bhe-pro-v0.1.16-macos.3
```

Expected: 恰好有 arm64、x86_64 两个 DMG 及各自 `.sha256`；使用实际文件名继续，不能沿用 `.2` 哈希。

- [ ] **Step 7: 验证正式文件的哈希、DMG、应用身份、架构和模型**

对每个实际 DMG 执行等价的严格检查；以 arm64 为例，完整命令为：

```bash
cd artifacts/bhe-pro-v0.1.16-macos.3
shasum -a 256 -c BHE-Pro-macos-arm64-v0.1.16-macos.3-adhoc.dmg.sha256
hdiutil verify BHE-Pro-macos-arm64-v0.1.16-macos.3-adhoc.dmg
mount_point="$(mktemp -d /tmp/bhe-pro-arm64.XXXXXX)"
hdiutil attach "$PWD/BHE-Pro-macos-arm64-v0.1.16-macos.3-adhoc.dmg" -readonly -nobrowse -mountpoint "$mount_point"
app="$mount_point/BHE Pro.app"
plutil -extract CFBundleDisplayName raw "$app/Contents/Info.plist"
plutil -extract CFBundleIdentifier raw "$app/Contents/Info.plist"
plutil -extract CFBundleExecutable raw "$app/Contents/Info.plist"
file "$app/Contents/MacOS/BHE Pro"
codesign --verify --deep --strict "$app"
test -L "$mount_point/Applications"
bash -n "$mount_point/BHE-Pro-首次打开修复.command"
PYTHONDONTWRITEBYTECODE=1 YOLO_AUTOINSTALL=false YOLO_CONFIG_DIR="$mount_point-yolo" \
  "$app/Contents/Resources/runtime/python/bin/python3" \
  "$app/Contents/Resources/runtime/scripts/check_detector.py" \
  --model "$app/Contents/Resources/runtime/models/bball_model.pt" --device cpu
PYTHONDONTWRITEBYTECODE=1 YOLO_AUTOINSTALL=false YOLO_CONFIG_DIR="$mount_point-yolo" \
  "$app/Contents/Resources/runtime/python/bin/python3" \
  "$app/Contents/Resources/runtime/scripts/check_detector.py" \
  --model "$app/Contents/Resources/runtime/models/yolo11n-pose.pt" --device cpu
hdiutil detach "$mount_point"
```

Expected: SHA-256 OK；DMG 校验通过；显示名和可执行文件为 `BHE Pro`；identifier 为 `com.courtside.bhepro`；arm64 可执行文件架构正确；签名完整；两个包内模型加载成功。x86_64 用其真实文件和独立挂载点执行相同静态检查；本机不支持该架构时只采用 CI 的原生模型运行结果，明确边界，不宣称本机 Intel 运行通过。任何挂载后失败都必须先执行 `hdiutil detach "$mount_point"` 清理再排查。

- [ ] **Step 8: 最终复核交付边界**

确认 GitHub Release URL 对应 `.3`，包含两个新前缀 DMG，旧 Release 仍存在；不安装、不替换 `/Applications/BHE.app` 或 `/Applications/BHE Pro.app`。最终回复只报告实际通过的验证，并提供 `.3` Release 及适用于用户机器的 DMG 链接。识别算法准确率、公证、原版数据迁移不属于本次验收，不作额外成功声明。

## Self-Review

- Spec coverage：Task 1 覆盖应用 bundle、可执行文件、窗口和偏好设置隔离；Task 2 覆盖 Flutter 标题、侧栏、关于页、三类数据目录及其他平台不变；Task 3 覆盖空格路径、DMG 内容、安装脚本和原版保护；Task 4 覆盖双架构 CI、资产名及不启用 OSS；Task 5 覆盖全量测试、推送、新标签、正式下载、SHA-256、DMG、签名、plist、架构和模型验证。
- Placeholder scan：实现步骤提供准确文件、接口和代码；唯一命令占位 `<run-id>` 必须取自当前标签及 HEAD 对应的实际 Actions 结果，不是未定义实现。
- Type consistency：`appDisplayName({bool? isMacOS})` 在定义、测试和全部调用中一致；三个目录函数均使用 `Map<String, String>` 与可空命名布尔参数；构建环境变量 `BHE_APP_DIR` 指向 Release 目录而非 `.app` 本身。
- Safety：测试中的签名、复制和 DMG 工具均为临时目录假工具；计划不执行安装辅助脚本，不关闭任何应用，不读取或写入原版数据，不发布 OSS，不合并 main。
