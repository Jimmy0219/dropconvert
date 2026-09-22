"""各種轉換引擎，以及「目標格式 → 可接受的來源 → 引擎」的對照表。

每個引擎都是 engine(src, dst) -> list[Path]：
- dst 是呼叫端算好、保證不會撞名的輸出路徑
- 回傳實際產生的檔案（多頁 PDF 轉圖片會有好幾個）
- 失敗時丟 ConvertError，訊息直接給人看
"""

from __future__ import annotations

import os
import re
import shutil
import signal
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Callable

import wmv2mp4


class ConvertError(Exception):
    pass


Engine = Callable[[Path, Path], "list[Path]"]


def unique_path(path: Path) -> Path:
    """已存在就改成「名稱 (2).ext」，和 Finder 的做法一樣。"""
    if not path.exists():
        return path
    # 資料夾沒有副檔名：「2026.09 收據」要變成「2026.09 收據 (2)」，
    # 不能被當成「2026」＋「.09 收據」
    stem, suffix = (path.name, "") if path.is_dir() else (path.stem, path.suffix)
    n = 2
    while True:
        candidate = path.with_name(f"{stem} ({n}){suffix}")
        if not candidate.exists():
            return candidate
        n += 1


def natural_key(path: Path) -> list:
    """依檔名的「自然順序」排序：2.png 排在 10.png 前面。"""
    return [int(part) if part.isdigit() else part.lower()
            for part in re.split(r"(\d+)", path.name)]


def require(tool: str, install_hint: str) -> str:
    path = shutil.which(tool)
    if not path:
        raise ConvertError(f"找不到 {tool}，請先執行: {install_hint}")
    return path


def run(cmd: list[str], timeout: float | None = None) -> str:
    # 開新的 process group：uvx 這類工具會再開孫程序，逾時或 Ctrl+C 時
    # 只殺直接子程序的話，孫程序會繼續跑，在我們清掉半成品之後才寫出檔案。
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, start_new_session=True)
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except BaseException as e:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.wait()
        if isinstance(e, subprocess.TimeoutExpired):
            raise ConvertError(f"{Path(cmd[0]).name} 超過 {timeout:.0f} 秒沒有完成")
        raise
    if proc.returncode != 0:
        lines = (stderr or stdout).strip().splitlines()
        raise ConvertError(lines[-1] if lines else
                           f"{Path(cmd[0]).name} 回傳 {proc.returncode}")
    return stdout


def expect_output(path: Path) -> list[Path]:
    """有些工具失敗也回傳 0，所以一律確認檔案真的生出來了。"""
    if not path.exists() or path.stat().st_size == 0:
        path.unlink(missing_ok=True)
        raise ConvertError("轉換工具沒有產生輸出檔")
    return [path]


# ── Office → PDF ────────────────────────────────────────────────────────────
# 用使用者已安裝的 MS Office 透過 AppleScript 匯出，排版與在 Office 裡看到的
# 完全一致，新細明體、標楷體等 Office 內建字型也會正確嵌入。
#
# 開檔用 `open -a`：走 LaunchServices，系統會自動授權沙盒內的 Office 讀取
# 該檔案。直接用 AppleScript 的 open 則會被沙盒擋下，文件開不起來。
#
# 匯出先寫到 /private/tmp 再搬走：Office 沙盒可以直接寫這裡，不會跳出
# 「授與檔案存取權」視窗；寫到 ~/Downloads 之類的位置則可能會跳。

OFFICE_STAGING = Path("/private/tmp") / f"fileconv-{os.getuid()}"

# app 名稱、文件集合名稱、匯出 PDF 的指令（theDoc 是文件、outHFS 是輸出路徑）
OFFICE_APPS = {
    "word": ("Microsoft Word", "documents",
             "save as theDoc file name outHFS file format format PDF"),
    "excel": ("Microsoft Excel", "workbooks",
              "save workbook as theDoc filename outHFS file format PDF file format"),
    "powerpoint": ("Microsoft PowerPoint", "presentations",
                   "save theDoc in outHFS as save as PDF"),
}

# 參數: 輸出路徑, 來源路徑的各種寫法...
# 三個程式回報 full name 的格式都不一樣（實測）：Word 給 HFS 且已解析 symlink
# （Macintosh HD:private:tmp:…），Excel 與 PowerPoint 給 POSIX 且是 /tmp/…
# 而非 /private/tmp/…。所以把可能的寫法全列出來，比對到任何一個就算。
OFFICE_SCRIPT = """
on run argv
  set outHFS to (POSIX file (item 1 of argv)) as string
  set accepted to {{}}
  repeat with p in (rest of argv)
    set end of accepted to (contents of p)
    set end of accepted to ((POSIX file (contents of p)) as string)
  end repeat
  tell application "{app}"
    -- 依完整路徑找「我們開的那份」，不能用 active document：
    -- 使用者可能同時開著別的文件。
    -- 變數名稱避開 x、d 這類短名：PowerPoint 字典把 x 定義成常數。
    -- 集合要先 get 成清單：Word/Excel 不接受直接對集合 repeat。
    set theDoc to missing value
    repeat 120 times
      repeat with candidate in (get {collection})
        if accepted contains (full name of candidate) then set theDoc to contents of candidate
      end repeat
      if theDoc is not missing value then exit repeat
      delay 0.5
    end repeat
    if theDoc is missing value then error "Office 在 60 秒內沒有開啟這個檔案"
    try
      {save}
    on error errMsg number errNum
      close theDoc saving no   -- 失敗也要關掉，不然文件會一直開在 Office 裡
      error errMsg number errNum
    end try
    close theDoc saving no
  end tell
end run
"""

# 這次執行才被我們叫起來的 Office，全部做完後要關掉，不要留在背景吃記憶體。
_launched_office: set[str] = set()


def _path_variants(src: Path) -> list[str]:
    real = str(src.resolve())
    variants = [real]
    if real.startswith("/private/"):     # /tmp、/var 這類 symlink 的原始寫法
        variants.append(real.removeprefix("/private"))
    return variants


def _osascript(script: str, *args: str, timeout: float = 30) -> str:
    return run(["osascript", "-e", script, *args], timeout=timeout).strip()


def _office_to_pdf(kind: str) -> Engine:
    app, collection, save = OFFICE_APPS[kind]
    script = OFFICE_SCRIPT.format(app=app, collection=collection, save=save)

    def engine(src: Path, dst: Path) -> list[Path]:
        if not Path(f"/Applications/{app}.app").exists():
            raise ConvertError(f"找不到 {app}，這個格式需要 MS Office 才能轉 PDF")

        if _osascript(f'application "{app}" is running') == "false":
            _launched_office.add(app)

        OFFICE_STAGING.mkdir(exist_ok=True)
        # 暫存檔用 ASCII 名稱，避開 AppleScript 與 HFS 路徑對特殊字元的各種問題
        staged = OFFICE_STAGING / f"{uuid.uuid4().hex}.pdf"
        try:
            run(["open", "-g", "-a", app, str(src.resolve())], timeout=30)
            # 大檔或第一次啟動 Office 會比較久；若 Office 跳出對話框
            # （例如文件有密碼），也會在這裡逾時而不是永遠卡住。
            _osascript(script, str(staged), *_path_variants(src), timeout=300)
            expect_output(staged)
            shutil.move(staged, dst)
        finally:
            staged.unlink(missing_ok=True)
        return [dst]

    return engine


def office_cleanup() -> None:
    """關掉這次才被叫起來、而且已經沒有開著任何文件的 Office。"""
    for app in _launched_office:
        collection = next(c for a, c, _ in OFFICE_APPS.values() if a == app)
        try:
            if _osascript(f'tell application "{app}" to count of {collection}') == "0":
                _osascript(f'tell application "{app}" to quit saving no')
        except ConvertError:
            pass
    _launched_office.clear()


word_to_pdf = _office_to_pdf("word")
excel_to_pdf = _office_to_pdf("excel")
powerpoint_to_pdf = _office_to_pdf("powerpoint")


# ── Markdown ────────────────────────────────────────────────────────────────

# 只裝用得到的格式；markitdown[all] 會多拉語音辨識、Azure 等一大堆套件。
MARKITDOWN = ["uvx", "--quiet", "--from",
              "markitdown[docx,pptx,xlsx,xls,pdf]", "markitdown"]


def to_markdown(src: Path, dst: Path) -> list[Path]:
    require("uvx", "brew install uv")
    # 第一次執行 uvx 要下載套件，網路慢時可能好幾分鐘
    run([*MARKITDOWN, str(src), "-o", str(dst)], timeout=900)
    return expect_output(dst)


def markdown_to_docx(src: Path, dst: Path) -> list[Path]:
    pandoc = require("pandoc", "brew install pandoc")
    # resource-path 讓 Markdown 裡用相對路徑引用的圖片找得到
    run([pandoc, str(src), "-o", str(dst), "--resource-path", str(src.parent)])
    return expect_output(dst)


# ── 圖片 ────────────────────────────────────────────────────────────────────

SIPS_FORMATS = {".jpg": "jpeg", ".png": "png", ".pdf": "pdf"}
JPEG_QUALITY = 92
PDF_RENDER_DPI = 200


def image_via_sips(src: Path, dst: Path) -> list[Path]:
    """macOS 內建的 sips，JPG/PNG/HEIC/TIFF/WebP 之間互轉，或單張圖轉 PDF。"""
    cmd = ["sips", "-s", "format", SIPS_FORMATS[dst.suffix]]
    if dst.suffix == ".jpg":
        cmd += ["-s", "formatOptions", str(JPEG_QUALITY)]
    run([*cmd, str(src), "--out", str(dst)])
    return expect_output(dst)


def pdf_to_images(src: Path, dst: Path) -> list[Path]:
    """PDF 每頁轉成一張圖。單頁直接輸出成 dst；多頁放進同名資料夾。"""
    pdftoppm = require("pdftoppm", "brew install poppler")
    pdfinfo = require("pdfinfo", "brew install poppler")

    pages = 0
    for line in run([pdfinfo, str(src)]).splitlines():
        if line.startswith("Pages:"):
            pages = int(line.split()[1])
    if pages == 0:
        raise ConvertError("讀不到 PDF 頁數，檔案可能損毀或有密碼")

    if dst.suffix == ".png":
        fmt = ["-png"]
    else:
        fmt = ["-jpeg", "-jpegopt", f"quality={JPEG_QUALITY}"]
    base = [pdftoppm, *fmt, "-r", str(PDF_RENDER_DPI)]

    if pages == 1:
        run([*base, "-singlefile", str(src), str(dst.with_suffix(""))])
        return expect_output(dst)

    folder = unique_path(dst.with_suffix(""))
    folder.mkdir(parents=True)
    try:
        run([*base, str(src), str(folder / dst.stem)])
    except ConvertError:
        shutil.rmtree(folder)   # 只刪這次剛建的資料夾，不留半成品
        raise
    return sorted(folder.iterdir())


# ── 影片 ────────────────────────────────────────────────────────────────────

def video_to_mp4(src: Path, dst: Path) -> list[Path]:
    """沿用 wmv2mp4.py 的邏輯與預設值：相容就無損重封裝，否則硬體編碼。"""
    ffmpeg = require("ffmpeg", "brew install ffmpeg")
    ffprobe = require("ffprobe", "brew install ffmpeg")
    args = wmv2mp4.build_parser().parse_args([])

    info = wmv2mp4.probe(ffprobe, src)
    video, audio = wmv2mp4.first_streams(info)
    if not info or not video:
        raise ConvertError("無法讀取，檔案可能損毀或不含視訊")

    duration, codecs = wmv2mp4.describe(info, video, audio)
    copy_video, copy_audio = wmv2mp4.plan(video, audio, args)
    encoder = wmv2mp4.pick_encoder(args, wmv2mp4.list_encoders(ffmpeg))
    mode = "無損重封裝" if copy_video else f"重新編碼 {encoder}"
    print(f"  來源: {codecs}  長度 {wmv2mp4.human_time(duration)}  模式: {mode}")

    cmd = wmv2mp4.build_command(ffmpeg, src, dst, args, video, audio,
                                copy_video, copy_audio, encoder)
    if not wmv2mp4.convert(ffmpeg, cmd, dst, duration):
        raise ConvertError("ffmpeg 轉換失敗（詳細訊息見上方）")
    return [dst]


# ── 合併成一份 PDF ─────────────────────────────────────────────────────────
# 待轉檔/合併pdf/<批次名稱>/ 裡的檔案依檔名排序，合併成 已轉檔/合併pdf/<批次名稱>.pdf

MERGE_TARGET = "合併pdf"
MERGE_SCRIPT = Path(__file__).with_name("merge_pdf.py")
VENV_PYTHON = Path(__file__).with_name(".venv") / "bin" / "python"


def merge_inputs(folder: Path) -> tuple[list[Path], list[Path]]:
    """回傳 (可以合併的檔案（已排序）, 不能合併的檔案)。"""
    accepted, rejected = [], []
    for f in sorted(folder.iterdir(), key=natural_key):
        if f.name.startswith((".", "~$")):
            continue
        (accepted if f.is_file() and f.suffix.lower() in ROUTES[MERGE_TARGET]
         else rejected).append(f)
    return accepted, rejected


def merge_to_pdf(src: Path, dst: Path) -> list[Path]:
    # 合併要用 pyobjc（在 .venv 裡）；App 本身就是用 .venv 的 Python 執行，
    # 指令版 ./convert.py 則是系統的 Python，所以一律交給 .venv 的 Python 跑。
    python = VENV_PYTHON if VENV_PYTHON.exists() else Path(sys.executable)
    files, _ = merge_inputs(src)
    if not files:
        raise ConvertError("資料夾裡沒有可以合併的圖片或 PDF")
    run([str(python), str(MERGE_SCRIPT), str(dst), *map(str, files)], timeout=600)
    return expect_output(dst)


# ── 對照表：待轉檔/<目標>/ 底下，每種副檔名交給哪個引擎 ─────────────────────

_IMAGES_IN = (".jpg", ".jpeg", ".png", ".heic", ".tif", ".tiff", ".webp")


def _images_to(target: str) -> dict[str, Engine]:
    same = {".jpg", ".jpeg"} if target == "jpg" else {f".{target}"}
    routes: dict[str, Engine] = {ext: image_via_sips for ext in _IMAGES_IN
                                 if ext not in same}
    routes[".pdf"] = pdf_to_images
    return routes


ROUTES: dict[str, dict[str, Engine]] = {
    "pdf": {
        ".doc": word_to_pdf, ".docx": word_to_pdf, ".rtf": word_to_pdf,
        ".xls": excel_to_pdf, ".xlsx": excel_to_pdf,
        ".ppt": powerpoint_to_pdf, ".pptx": powerpoint_to_pdf,
        **{ext: image_via_sips for ext in _IMAGES_IN},
    },
    "md": {ext: to_markdown for ext in
           (".docx", ".pptx", ".xlsx", ".xls", ".pdf", ".html", ".htm")},
    "docx": {".md": markdown_to_docx, ".markdown": markdown_to_docx},
    "jpg": _images_to("jpg"),
    "png": _images_to("png"),
    "mp4": {ext: video_to_mp4 for ext in sorted(wmv2mp4.VIDEO_SUFFIXES)},
    # 合併的單位是「一個子資料夾」，這裡列的是資料夾裡可以放的檔案
    MERGE_TARGET: {ext: merge_to_pdf for ext in (*_IMAGES_IN, ".pdf")},
}

# 輸出檔的副檔名：預設就是目標資料夾的名稱
OUTPUT_SUFFIX = {MERGE_TARGET: "pdf"}
