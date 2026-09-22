#!/bin/zsh
# 產生「轉檔工具.app」。
#
#   ./make_app.sh                 # 產生在專案資料夾裡
#   ./make_app.sh ~/Applications  # 產生在指定的資料夾（install.sh 用這個）
#
# App 本身只是一個啟動器，程式碼仍然在這個專案資料夾裡執行，
# 所以專案資料夾搬家或改名後，要重新執行一次這個腳本。
set -euo pipefail

PROJECT="${0:A:h}"
DEST="${1:-$PROJECT}"
APP="${DEST:A}/轉檔工具.app"
cd "$PROJECT"

echo "安裝相依套件（uv sync）…"
# 固定用 uv 管理的 Python（版本見 .python-version）：啟動器要連結它的 libpython，
# 系統內建或 Homebrew 的 Python 目錄結構不同，會編譯失敗。
uv sync --quiet --managed-python

echo "產生圖示…"
.venv/bin/python make_icon.py icon.svg AppIcon.icns

echo "打包 $APP …"
mkdir -p "$DEST"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp AppIcon.icns "$APP/Contents/Resources/"

cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>轉檔工具</string>
  <key>CFBundleDisplayName</key><string>轉檔工具</string>
  <key>CFBundleIdentifier</key><string>local.fileconv.app</string>
  <key>CFBundleExecutable</key><string>launcher</string>
  <key>CFBundleIconFile</key><string>AppIcon</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>0.1.0</string>
  <key>CFBundleVersion</key><string>1</string>
  <key>LSMinimumSystemVersion</key><string>12.0</string>
  <key>NSHighResolutionCapable</key><true/>
  <key>NSDownloadsFolderUsageDescription</key>
  <string>轉檔工具會讀取「待轉檔」資料夾，並把結果存到「已轉檔」。</string>
  <key>NSDesktopFolderUsageDescription</key>
  <string>轉檔工具的程式或「待轉檔」資料夾放在桌面上，需要讀寫這些檔案。</string>
  <key>NSDocumentsFolderUsageDescription</key>
  <string>轉檔工具的程式或「待轉檔」資料夾放在文件裡，需要讀寫這些檔案。</string>
  <key>NSAppleEventsUsageDescription</key>
  <string>轉檔工具需要控制 Microsoft Word、Excel、PowerPoint，才能把文件另存成 PDF。</string>
</dict>
</plist>
PLIST

echo "編譯啟動器…"
# 啟動器把 Python 載進自己的程序執行，系統才會把它認成「轉檔工具」而不是 python
BUILD="$(mktemp -d)"
trap 'rm -rf "$BUILD"' EXIT
if [[ "$PROJECT" == *[\"\\]* ]]; then
  echo "錯誤: 專案路徑不能含有 \" 或 \\ 字元：$PROJECT" >&2; exit 1
fi
printf '#define PROJECT_DIR "%s"\n' "$PROJECT" > "$BUILD/config.h"
read -r PY_INCLUDE PY_LIBDIR PY_LDVERSION < <(.venv/bin/python -c \
  "import sysconfig as s; print(s.get_config_var('INCLUDEPY'), s.get_config_var('LIBDIR'), s.get_config_var('LDVERSION'))")
clang -O2 -mmacosx-version-min=12.0 -Wall \
  -I"$BUILD" -I"$PY_INCLUDE" launcher.c \
  -L"$PY_LIBDIR" -lpython"$PY_LDVERSION" -Wl,-rpath,"$PY_LIBDIR" \
  -o "$APP/Contents/MacOS/launcher"

# 讓 Finder 重新讀取圖示
touch "$APP"
echo "完成：$APP"
