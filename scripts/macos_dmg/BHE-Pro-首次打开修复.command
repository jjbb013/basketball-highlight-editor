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
