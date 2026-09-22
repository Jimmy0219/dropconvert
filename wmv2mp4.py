#!/usr/bin/env python3
"""WMV / MOV 轉 MP4，使用 ffmpeg 與 Apple VideoToolbox 硬體編碼。

用法:
    ./wmv2mp4.py                            # 不給參數：自動轉預設資料夾（見 DEFAULT_INPUT）
    ./wmv2mp4.py input.wmv                  # 單檔，輸出 input.mp4
    ./wmv2mp4.py clip.mov                   # MOV 編碼相容時直接無損重封裝
    ./wmv2mp4.py videos/                    # 整個資料夾批次
    ./wmv2mp4.py videos/ -o out/            # 指定輸出目錄
    ./wmv2mp4.py a.wmv -q 75 --cpu          # 調品質、改用 CPU 編碼
    ./wmv2mp4.py a.mov --reencode --hevc    # 強制重新編碼成 HEVC
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

# 不給參數執行時要掃描的資料夾。想換成別的位置，改這一行就好。
DEFAULT_INPUT = Path.home() / "Downloads" / "待轉檔"

# WMV/ASF 的視訊(WMV3/VC-1)與音訊(WMA) MP4 容器都不支援，一律要重新編碼。
# MOV 是 QuickTime 容器，內容常常已經是 H.264/HEVC + AAC，可以直接搬進 MP4。
VIDEO_SUFFIXES = {".wmv", ".asf", ".mov", ".qt"}

# MP4 容器原生支援、可以 -c copy 直接搬過去的編碼。
COPYABLE_VIDEO = {"h264", "hevc"}
COPYABLE_AUDIO = {"aac", "mp3"}

# 這兩種 transfer 代表 HDR（PQ / HLG），壓成 8-bit H.264 顏色會走鐘。
HDR_TRANSFERS = {"smpte2084", "arib-std-b67"}


def die(msg: str) -> None:
    print(f"錯誤: {msg}", file=sys.stderr)
    sys.exit(1)


def check_ffmpeg() -> tuple[str, str]:
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        die("找不到 ffmpeg/ffprobe。請先執行: brew install ffmpeg")
    return ffmpeg, ffprobe


def list_encoders(ffmpeg: str) -> str:
    return subprocess.run(
        [ffmpeg, "-hide_banner", "-encoders"],
        capture_output=True, text=True, check=False,
    ).stdout


def probe(ffprobe: str, path: Path) -> dict:
    """取得時長與編碼資訊；檔案損毀時回傳空 dict。"""
    proc = subprocess.run(
        [ffprobe, "-v", "error", "-print_format", "json",
         "-show_format", "-show_streams", str(path)],
        capture_output=True, text=True, check=False,
    )
    if proc.returncode != 0:
        return {}
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {}


def first_streams(info: dict) -> tuple[dict, dict]:
    """取出第一條視訊與第一條音訊串流（沒有就是空 dict）。"""
    video: dict = {}
    audio: dict = {}
    for s in info.get("streams", []):
        if s.get("codec_type") == "video" and not video:
            video = s
        elif s.get("codec_type") == "audio" and not audio:
            audio = s
    return video, audio


def describe(info: dict, video: dict, audio: dict) -> tuple[float, str]:
    """回傳 (秒數, 人類可讀的來源編碼描述)。"""
    duration = 0.0
    try:
        duration = float(info.get("format", {}).get("duration", 0))
    except (TypeError, ValueError):
        pass

    desc = f"{video.get('codec_name', '?')} + {audio.get('codec_name', '無音訊')}"
    w, h = video.get("width"), video.get("height")
    if w and h:
        desc += f"  {w}x{h}"
    return duration, desc


def human_time(seconds: float) -> str:
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def pick_encoder(args, encoders: str) -> str:
    """選視訊編碼器：預設優先硬體，--cpu 時走 libx26x。"""
    family = "hevc" if args.hevc else "h264"
    if not args.cpu and f"{family}_videotoolbox" in encoders:
        return f"{family}_videotoolbox"
    return "libx265" if args.hevc else "libx264"


def quality_to_crf(quality: int) -> int:
    """把 1-100（越大越好）換算成 libx26x 的 CRF 40-14（越小越好）。"""
    crf = round(40 - (quality - 1) / 99 * 26)
    return max(0, min(51, crf))


def plan(video: dict, audio: dict, args) -> tuple[bool, bool]:
    """決定視訊/音訊是否可以直接 copy。回傳 (copy_video, copy_audio)。"""
    copy_video = (not args.reencode
                  and video.get("codec_name") in COPYABLE_VIDEO)
    # --reencode 只強制重壓視訊；音訊本來就相容就別再壓一次，白白掉品質。
    copy_audio = audio.get("codec_name") in COPYABLE_AUDIO
    return copy_video, copy_audio


def build_command(ffmpeg: str, src: Path, dst: Path, args,
                  video: dict, audio: dict, copy_video: bool,
                  copy_audio: bool, encoder: str) -> list[str]:
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-stats", "-y",
           "-i", str(src),
           "-map", "0:v:0", "-map", "0:a?",   # 只帶視訊與音訊，其他軌 MP4 未必收
           "-map_metadata", "0"]              # 保留拍攝時間等 metadata

    if copy_video:
        cmd += ["-c:v", "copy"]
        if video.get("codec_name") == "hevc":
            cmd += ["-tag:v", "hvc1"]         # 不加這個 QuickTime 會拒播 HEVC
    else:
        cmd += ["-c:v", encoder]
        if args.bitrate:
            cmd += ["-b:v", args.bitrate]
        elif encoder.endswith("videotoolbox"):
            # VideoToolbox 用 -q:v (1-100，越大越好)，不吃 CRF。
            cmd += ["-q:v", str(args.quality)]
        else:
            cmd += ["-crf", str(quality_to_crf(args.quality))]

        if not encoder.endswith("videotoolbox"):
            cmd += ["-preset", args.preset]

        if args.hevc:
            cmd += ["-tag:v", "hvc1"]
            # 來源是 10-bit 就維持 10-bit，漸層不會出現色帶。
            depth10 = "10" in (video.get("pix_fmt") or "")
            cmd += ["-pix_fmt", "yuv420p10le" if depth10 else "yuv420p"]
        else:
            cmd += ["-pix_fmt", "yuv420p"]    # 確保 QuickTime / iOS 能播

        # 重壓時把色彩描述原樣帶過去，否則播放器會猜錯、顏色偏掉。
        for flag, key in (("-color_primaries", "color_primaries"),
                          ("-color_trc", "color_transfer"),
                          ("-colorspace", "color_space"),
                          ("-color_range", "color_range")):
            value = video.get(key)
            if value and value != "unknown":
                cmd += [flag, value]

    if copy_audio:
        cmd += ["-c:a", "copy"]
    else:
        cmd += ["-c:a", "aac", "-b:a", args.audio_bitrate]

    cmd += ["-movflags", "+faststart",  # moov atom 移到檔頭，邊下載邊播放用得到
            str(dst)]
    return cmd


def convert(ffmpeg: str, cmd: list[str], dst: Path, duration: float) -> bool:
    """執行轉換並即時顯示進度。回傳是否成功。"""
    started = time.monotonic()

    proc = subprocess.Popen(cmd, stderr=subprocess.PIPE, text=True, bufsize=1)
    time_re = re.compile(r"time=(\d+):(\d+):(\d+\.?\d*)")
    tail: list[str] = []

    assert proc.stderr is not None
    for line in proc.stderr:
        tail.append(line)
        del tail[:-15]
        m = time_re.search(line)
        if m and duration > 0:
            h, mnt, sec = m.groups()
            done = int(h) * 3600 + int(mnt) * 60 + float(sec)
            pct = min(100.0, done / duration * 100)
            elapsed = time.monotonic() - started
            speed = done / elapsed if elapsed > 0 else 0
            eta = (duration - done) / speed if speed > 0 else 0
            bar = "█" * int(pct / 4) + "░" * (25 - int(pct / 4))
            print(f"\r  {bar} {pct:5.1f}%  {speed:4.1f}x  剩餘 {human_time(eta)}",
                  end="", flush=True)

    proc.wait()
    print("\r" + " " * 70 + "\r", end="")

    if proc.returncode != 0:
        print(f"  ✗ 轉換失敗 (ffmpeg 回傳 {proc.returncode})")
        for line in tail:
            if line.strip():
                print(f"    {line.rstrip()}")
        dst.unlink(missing_ok=True)   # 不要留下半成品
        return False

    elapsed = time.monotonic() - started
    size = dst.stat().st_size / 1024 / 1024
    print(f"  ✓ 完成  {size:.1f} MB  耗時 {human_time(elapsed)}")
    return True


def collect(target: Path, recursive: bool) -> list[Path]:
    if target.is_file():
        return [target]
    pattern = "**/*" if recursive else "*"
    return sorted(
        p for p in target.glob(pattern)
        if p.is_file() and p.suffix.lower() in VIDEO_SUFFIXES
    )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="WMV/ASF/MOV 轉 MP4（H.264/HEVC + AAC），"
                    "編碼相容時直接無損重封裝，否則用 VideoToolbox 硬體編碼。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("input", type=Path, nargs="?",
                   help=f"來源檔案或資料夾（省略時用 {DEFAULT_INPUT}）")
    p.add_argument("-o", "--output-dir", type=Path,
                   help="輸出目錄（預設與來源同目錄）")
    p.add_argument("-q", "--quality", type=int, default=60,
                   help="品質 1-100，越大越好也越大檔（預設 60）")
    p.add_argument("-b", "--bitrate",
                   help="指定視訊位元率如 8M，設了就用固定位元率取代 --quality")
    p.add_argument("--hevc", action="store_true",
                   help="重新編碼時用 H.265/HEVC，同畫質檔案更小（舊裝置可能不支援）")
    p.add_argument("--reencode", action="store_true",
                   help="即使來源編碼相容也強制重新編碼視訊")
    p.add_argument("--cpu", action="store_true",
                   help="強制使用 CPU 的 libx264/libx265，不用硬體編碼")
    p.add_argument("--preset", default="medium",
                   help="libx26x preset，僅在 --cpu 時有效（預設 medium）")
    p.add_argument("--audio-bitrate", default="192k",
                   help="音訊位元率（預設 192k，僅在需要重壓音訊時使用）")
    p.add_argument("-r", "--recursive", action="store_true",
                   help="資料夾模式下遞迴掃描子目錄")
    p.add_argument("-f", "--force", action="store_true",
                   help="覆寫已存在的輸出檔（預設跳過）")
    return p


def main() -> int:
    args = build_parser().parse_args()

    if not 1 <= args.quality <= 100:
        die("--quality 必須介於 1 到 100")

    target = args.input or DEFAULT_INPUT
    if args.input is None:
        print(f"未指定來源，使用預設資料夾: {target}", flush=True)
        if not target.exists():
            die(f"預設資料夾不存在: {target}\n"
                f"       請先建立它並把影片放進去，或直接指定路徑: "
                f"{Path(sys.argv[0]).name} /path/to/videos")
    if not target.exists():
        die(f"找不到: {target}")

    ffmpeg, ffprobe = check_ffmpeg()
    encoders = list_encoders(ffmpeg)
    encoder = pick_encoder(args, encoders)
    if args.cpu:
        encoder_desc = f"{encoder} (CPU, preset={args.preset})"
    elif encoder.endswith("videotoolbox"):
        encoder_desc = f"{encoder} (硬體加速)"
    else:
        encoder_desc = f"{encoder} (CPU，此 ffmpeg 沒有對應的 VideoToolbox 編碼器)"

    files = collect(target, args.recursive)
    if not files:
        die(f"沒有找到 .wmv/.asf/.mov 檔案於: {target}")

    if args.output_dir:
        args.output_dir.mkdir(parents=True, exist_ok=True)

    print(f"重新編碼時使用: {encoder_desc}")
    print(f"待處理: {len(files)} 個檔案\n")

    ok = skipped = failed = remuxed = 0
    for i, src in enumerate(files, 1):
        out_dir = args.output_dir or src.parent
        dst = out_dir / f"{src.stem}.mp4"

        print(f"[{i}/{len(files)}] {src.name}")

        if dst.exists() and not args.force:
            print("  – 已存在，跳過（要覆寫請加 --force）")
            skipped += 1
            continue
        if dst.resolve() == src.resolve():
            print("  – 來源與輸出同路徑，跳過")
            skipped += 1
            continue

        info = probe(ffprobe, src)
        video, audio = first_streams(info)
        if not info or not video:
            print("  ✗ 無法讀取，檔案可能損毀或不含視訊")
            failed += 1
            continue

        duration, codecs = describe(info, video, audio)
        copy_video, copy_audio = plan(video, audio, args)

        if copy_video:
            mode = "無損重封裝"
            if audio and not copy_audio:
                mode += "（音訊轉 AAC）"
        else:
            mode = f"重新編碼 {encoder}"
            if audio and copy_audio:
                mode += "（音訊直接沿用）"
        print(f"  來源: {codecs}  長度 {human_time(duration)}")
        print(f"  模式: {mode}")

        if (not copy_video and not args.hevc
                and video.get("color_transfer") in HDR_TRANSFERS):
            print("  ! 來源是 HDR，壓成 8-bit H.264 顏色會偏灰，建議加 --hevc")

        cmd = build_command(ffmpeg, src, dst, args, video, audio,
                            copy_video, copy_audio, encoder)
        if convert(ffmpeg, cmd, dst, duration):
            ok += 1
            if copy_video:
                remuxed += 1
        else:
            failed += 1

    print(f"\n完成 {ok} 個" +
          (f"（其中 {remuxed} 個無損重封裝）" if remuxed else "") +
          (f"，跳過 {skipped} 個" if skipped else "") +
          (f"，失敗 {failed} 個" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n已中斷")
        sys.exit(130)
