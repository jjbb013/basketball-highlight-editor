# BHE Pro macOS 独立应用设计

日期：2026-11-23  
基线：`71a787036539bd56636d564744d0df24cf4e152f`  
分支：`feature/macos-player-identity-enhanced-export`  
状态：用户已确认采用“BHE Pro + 完全独立数据”方案。

## 1. 背景与目标

用户电脑已经安装原版 `BHE.app`。二次开发版本必须与原版清楚区分并独立安装，不能覆盖原版，也不能让用户无法判断当前打开的是哪个版本。

本次目标：

1. macOS 应用、窗口和关于页面统一显示 `BHE Pro`。
2. 使用独立的 bundle identifier、偏好设置、项目目录、日志和更新缓存。
3. DMG 及其安装辅助工具只处理 BHE Pro，不关闭、替换或删除原版 BHE。
4. 继续交付 Apple Silicon 和 Intel DMG，并发布新标签，保留已有 Release。
5. 用自动化测试和实际发布文件验证名称、隔离边界和安装行为。

## 2. 命名约定

| 用途 | 值 |
| --- | --- |
| 用户可见名称 | `BHE Pro` |
| 应用 bundle | `BHE Pro.app` |
| 可执行文件 | `BHE Pro` |
| bundle identifier | `com.courtside.bhepro` |
| 下载资产前缀 | `BHE-Pro-macos-` |
| 目标预发布标签 | `v0.1.16-macos.3` |

应用名和 bundle 中的空格必须始终作为路径或参数的一部分正确引用。下载资产使用 `BHE-Pro`，避免下载链接和脚本中的不必要空格。

内部 Python 包、Flutter package、MethodChannel、数据库表和任务协议继续使用现有名称；这些技术标识不是用户界面品牌，不做批量替换。

## 3. 完全独立的数据边界

| 数据 | BHE Pro 位置或作用域 |
| --- | --- |
| 偏好设置 | 由 `com.courtside.bhepro` 隔离 |
| 备用项目目录 | `~/Library/Application Support/BHE Pro/Projects` |
| 日志目录 | `~/Library/Logs/BHE Pro` |
| 更新缓存 | `~/Library/Caches/BHE Pro/updates` |

规则：

1. 不读取、迁移、复制或删除原版偏好设置和项目数据。
2. 不在失败时回退到原版 `BHE` 数据目录。
3. 不自动导入原版项目；首次启动按全新应用处理。
4. 用户以后可通过现有跨项目导出功能按需选择历史项目；该流程继续保持只读，不因本次命名变更而修改历史数据库。
5. Windows、Android 和其他平台的名称与数据目录保持原样。

## 4. 应用与界面修改范围

macOS 原生配置负责应用身份：

- `AppInfo.xcconfig` 设置 `PRODUCT_NAME = BHE Pro` 和新的 bundle identifier。
- `Info.plist` 的 `CFBundleDisplayName` 使用 `BHE Pro`，其余值继续引用 Xcode 构建设置。
- 原生窗口标题显示 `BHE Pro`。

Flutter 侧只在 macOS 显示 BHE Pro：应用标题、侧边栏品牌和关于页面使用同一显示名来源；其他平台继续显示 BHE。内部业务逻辑、路由和识别/导出协议不改。

本次不重新设计图标，不修改原版应用，也不改变签名、公证或自动更新通道的现有发布边界。

## 5. 构建与安装包

`build_macos_release.sh` 的产品名和 DMG 默认文件名与 BHE Pro 对齐，保留现有环境变量覆盖入口和版本传递逻辑。所有包含空格的应用路径均使用引用。

DMG 包含：

- `BHE Pro.app`；
- `Applications` 快捷方式；
- BHE Pro 使用说明；
- BHE Pro 安装与验证辅助脚本。

辅助脚本的目标固定为 `/Applications/BHE Pro.app`：

- 找不到 BHE Pro 时明确失败，不回退到 `BHE.app`；
- 进程操作只匹配 `BHE Pro`，不使用 `pkill -x BHE`；
- 替换、隔离属性处理和签名验证只针对 BHE Pro；
- 不读取或修改原版 BHE 的文件、设置或数据目录。

GitHub Actions 的构建路径、包内检查、Release 文件名和实际挂载验证统一使用新名称。新标签为 `v0.1.16-macos.3`，不覆盖 `.1` 或 `.2`，不合并 `main`，不启用 OSS 自动更新发布。

## 6. 错误处理与兼容性

- 应用或运行时路径处理必须支持空格，不能按空白拆分参数。
- 新数据目录不可写时沿用现有错误提示，不得静默写回原版目录。
- 安装辅助工具只操作明确目标；目标缺失或签名验证失败时停止。
- 现有视频、项目数据库结构、身份识别算法和导出配置语义不因品牌修改而变化。
- ad-hoc 签名和未公证提示继续保留，不能把改名包描述为 Apple 已公证。

## 7. 测试与验收

实施采用测试先行，至少覆盖：

1. macOS 配置中的产品名、显示名和 bundle identifier。
2. macOS 项目、日志、更新缓存和偏好设置的隔离边界；其他平台路径不变。
3. macOS 窗口及 Flutter 可见品牌名称。
4. 构建脚本对 `BHE Pro.app` 和含空格路径的处理。
5. 辅助脚本不包含对原版 `BHE.app` 或进程 `BHE` 的操作。
6. CI 和发布资产使用 `BHE-Pro` 前缀，并保留现有版本号及运行时检查。
7. Python 全量测试、Flutter 全量测试和静态检查。
8. Apple Silicon 与 Intel CI 构建、包内模型加载、签名和 DMG 完整性检查。
9. 重新下载正式 Release 后核对 SHA-256、`hdiutil verify`、`Info.plist`、应用架构和包内声明。

最终验收标准：`BHE.app` 与 `BHE Pro.app` 可作为两个不同应用并存；BHE Pro 的窗口和关于页面可明确识别；首次启动使用独立数据；安装辅助工具不会触碰原版；两个架构的正式 DMG 均可从 GitHub Release 下载并通过各自适用的验证。

## 8. 非目标

- 不自动迁移原版项目或设置。
- 不修改 Windows、Android 的品牌和数据目录。
- 不重构内部模块、协议或数据库命名。
- 不新增图标设计、Apple Developer ID 签名或公证。
- 不发布 OSS 自动更新通道，不合并 `main`。
