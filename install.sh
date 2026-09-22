#!/bin/zsh
# 轉檔工具：安裝／更新／解除安裝
#
#   安裝或更新:  /bin/zsh -c "$(curl -fsSL https://raw.githubusercontent.com/Jimmy0219/dropconvert/main/install.sh)"
#   解除安裝:    /bin/zsh -c "$(curl -fsSL https://raw.githubusercontent.com/Jimmy0219/dropconvert/main/install.sh)" -- --uninstall
#
# 會做的事：
#   1. 確認有 Xcode Command Line Tools（編譯 App 的啟動器需要）
#   2. 確認有 Homebrew，並安裝 ffmpeg、pandoc、poppler、uv（已經有的會跳過）
#   3. 下載程式到 ~/Library/Application Support/dropconvert/
#   4. 產生「轉檔工具.app」放進 ~/Applications（Launchpad、Spotlight 都找得到）
#
# 整份包在 main() 裡：確保整個檔案下載完才開始執行，網路中斷不會只跑一半。

main() {
  set -euo pipefail

  local GITHUB_REPO="Jimmy0219/dropconvert"
  local NAME="${GITHUB_REPO:t}"
  local TARBALL="${FILECONV_TARBALL:-https://github.com/$GITHUB_REPO/archive/refs/heads/main.tar.gz}"
  local INSTALL_DIR="$HOME/Library/Application Support/$NAME"
  local APP_DIR="$HOME/Applications"
  local APP="$APP_DIR/轉檔工具.app"

  say()  { print -P "%B%F{blue}==>%f %b$*"; }
  warn() { print -P "%B%F{yellow}注意:%f%b $*"; }
  die()  { print -P "%B%F{red}錯誤:%f%b $*" >&2; exit 1; }

  [[ "$(uname)" == Darwin ]] || die "這個工具只能在 macOS 上使用"

  if [[ "${1:-}" == --uninstall ]]; then
    say "移除 $APP"
    rm -rf "$APP"
    say "移除 $INSTALL_DIR"
    rm -rf "$INSTALL_DIR"
    say "完成。你的 ~/Downloads/待轉檔、已轉檔、已處理 資料夾都保留著，不需要可以自己刪掉。"
    say "Homebrew 裝的 ffmpeg、pandoc、poppler、uv 也保留著（其他程式可能會用到）。"
    return
  fi

  # ── 1. Xcode Command Line Tools ──
  if ! xcode-select -p >/dev/null 2>&1; then
    say "需要先安裝 Xcode Command Line Tools，接下來會跳出安裝視窗"
    xcode-select --install || true
    die "請在跳出的視窗按「安裝」，裝好之後再執行一次這個指令"
  fi

  # ── 2. Homebrew 與命令列工具 ──
  local brew=""
  for candidate in /opt/homebrew/bin/brew /usr/local/bin/brew; do
    [[ -x "$candidate" ]] && { brew="$candidate"; break; }
  done
  if [[ -z "$brew" ]]; then
    say "安裝 Homebrew（macOS 的套件管理工具，過程中會要求輸入你的 Mac 登入密碼）"
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    for candidate in /opt/homebrew/bin/brew /usr/local/bin/brew; do
      [[ -x "$candidate" ]] && { brew="$candidate"; break; }
    done
    [[ -n "$brew" ]] || die "Homebrew 安裝失敗"
  fi
  eval "$("$brew" shellenv)"
  export PATH="$HOME/.local/bin:$PATH"   # 用官方安裝程式裝的 uv 在這裡

  local -a missing=()
  local tool formula
  for tool formula in ffmpeg ffmpeg pandoc pandoc pdftoppm poppler uv uv; do
    command -v "$tool" >/dev/null || missing+=("$formula")
  done
  if (( ${#missing} )); then
    say "安裝 ${missing[*]}（第一次會比較久）"
    "$brew" install "${missing[@]}"
  else
    say "ffmpeg、pandoc、poppler、uv 都已經安裝"
  fi

  [[ -d "/Applications/Microsoft Word.app" ]] ||
    warn "找不到 Microsoft Word：Office 轉 PDF 需要 Microsoft Office，其他功能不受影響"

  # ── 3. 下載程式 ──
  say "下載最新版程式"
  local tmp; tmp="$(mktemp -d)"
  trap "rm -rf '$tmp'" EXIT
  curl -fsSL "$TARBALL" | tar -xz -C "$tmp" --strip-components 1
  [[ -f "$tmp/make_app.sh" ]] || die "下載的檔案不完整，請稍後再試一次"
  mkdir -p "$INSTALL_DIR"
  # 保留 .venv，更新時不用重新下載 Python 套件
  rsync -a --delete --exclude .venv "$tmp/" "$INSTALL_DIR/"

  # ── 4. 產生 App ──
  say "產生 轉檔工具.app"
  "$INSTALL_DIR/make_app.sh" "$APP_DIR"

  say "預先下載 Markdown 轉換套件（避免第一次轉 Markdown 時要等）"
  (cd "$INSTALL_DIR" && .venv/bin/python -c \
    "import engines, subprocess; subprocess.run([*engines.MARKITDOWN, '--help'], capture_output=True, check=True)") ||
    warn "預先下載失敗，第一次轉 Markdown 時會自動再下載"

  print
  say "%F{green}安裝完成！%f"
  print "   打開方式：Launchpad 或 Spotlight 搜尋「轉檔工具」"
  print "   第一次打開時 macOS 會詢問兩種權限，都請按「允許」："
  print "     ・存取「下載項目」資料夾（待轉檔、已轉檔都在這裡）"
  print "     ・控制 Microsoft Word／Excel／PowerPoint（轉 PDF 用，第一次轉時才會問）"
  print "   之後要更新，再執行一次同一個安裝指令就好"

  # 在終端機裡執行時才直接打開，讓權限詢問出現在使用者面前
  [[ -t 1 ]] && open "$APP"
  return 0
}

main "$@"
