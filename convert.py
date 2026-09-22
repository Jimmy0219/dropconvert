#!/usr/bin/env python3
"""資料夾式轉檔：檔案丟進「待轉檔/<目標格式>/」，執行後到「已轉檔/<目標格式>/」收檔。

    ~/Downloads/待轉檔/pdf/報告.docx
        → 轉好的檔案  ~/Downloads/已轉檔/pdf/報告.pdf
        → 原始檔移到  ~/Downloads/已處理/pdf/報告.docx

子資料夾名稱就是目標格式：pdf、md、docx、jpg、png、mp4。
直接放在「待轉檔」根目錄的影片會當成 mp4 處理（沿用 wmv2mp4 的習慣）。

用法:
    ./convert.py              # 轉換全部
    ./convert.py --dry-run    # 只列出會怎麼處理，不實際轉檔
"""

from __future__ import annotations

import argparse
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from engines import ROUTES, ConvertError, Engine, office_cleanup, unique_path

# 三個資料夾的位置。想換地方改這裡就好。
BASE = Path.home() / "Downloads"
INBOX = BASE / "待轉檔"
OUTBOX = BASE / "已轉檔"
DONE = BASE / "已處理"

ROOT_TARGET = "mp4"


@dataclass
class Job:
    src: Path
    target: str               # 目標格式，也就是子資料夾名稱
    engine: Engine | None     # None 表示無法處理，原因寫在 note
    note: str = ""


def ensure_folders() -> None:
    """建好每個目標格式的子資料夾，讓使用者打開「待轉檔」就知道能丟哪裡。"""
    for target in ROUTES:
        (INBOX / target).mkdir(parents=True, exist_ok=True)


def is_ignorable(path: Path) -> bool:
    # .DS_Store 等隱藏檔，以及 Office 開檔時產生的 ~$ 鎖定檔
    return path.name.startswith((".", "~$"))


def make_job(src: Path, target: str) -> Job:
    engine = ROUTES[target].get(src.suffix.lower())
    if engine:
        return Job(src, target, engine)
    accepted = " ".join(sorted(ROUTES[target]))
    return Job(src, target, None,
               f"{src.suffix or '沒有副檔名的檔案'} 不能轉成 {target}，可接受: {accepted}")


def scan() -> tuple[list[Job], list[str]]:
    """列出待轉檔裡所有檔案，並決定每個要怎麼處理。不會動到任何檔案。

    回傳 (工作清單, 警告訊息)。警告交給呼叫端顯示，這裡不直接 print：
    網頁介面每秒都會呼叫一次。
    """
    jobs: list[Job] = []
    warnings: list[str] = []
    if not INBOX.exists():
        return jobs, warnings
    for entry in sorted(INBOX.iterdir()):
        if is_ignorable(entry):
            continue
        if entry.is_dir():
            target = entry.name.lower()
            if target not in ROUTES:
                warnings.append(f"不認得的資料夾「{entry.name}」，已略過"
                                f"（可用的有: {' '.join(ROUTES)}）")
                continue
            jobs += [make_job(f, target) for f in sorted(entry.iterdir())
                     if f.is_file() and not is_ignorable(f)]
        elif entry.suffix.lower() in ROUTES[ROOT_TARGET]:
            jobs.append(make_job(entry, ROOT_TARGET))
        else:
            jobs.append(Job(entry, "", None,
                            "請放進目標格式的子資料夾，例如 待轉檔/pdf/"))
    return jobs, warnings


def run_job(job: Job) -> list[Path]:
    """轉換一個檔案；成功後把原始檔移到「已處理」。回傳產生的檔案。"""
    assert job.engine is not None
    out_dir = OUTBOX / job.target
    out_dir.mkdir(parents=True, exist_ok=True)
    dst = unique_path(out_dir / f"{job.src.stem}.{job.target}")

    try:
        outputs = job.engine(job.src, dst)
    except BaseException:
        dst.unlink(missing_ok=True)   # 不留半成品（含 Ctrl+C 中斷時）
        raise

    done_dir = DONE / job.target
    done_dir.mkdir(parents=True, exist_ok=True)
    shutil.move(job.src, unique_path(done_dir / job.src.name))
    return outputs


def show(path: Path) -> str:
    """顯示相對於 ~/Downloads 的路徑，比完整路徑好讀。"""
    try:
        return str(path.relative_to(BASE))
    except ValueError:
        return str(path)


def main() -> int:
    p = argparse.ArgumentParser(
        description="資料夾式轉檔：Word/Excel/PPT/圖片/Markdown/影片。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("-n", "--dry-run", action="store_true",
                   help="只列出會怎麼處理，不實際轉檔也不搬檔")
    args = p.parse_args()

    if not args.dry_run:
        ensure_folders()
    jobs, warnings = scan()
    for w in warnings:
        print(f"注意: {w}")
    if not jobs:
        print(f"{show(INBOX)} 裡沒有檔案。把要轉的檔案放進對應的子資料夾:")
        for target, routes in ROUTES.items():
            print(f"  {target + '/':6} ← {' '.join(sorted(routes))}")
        return 0

    todo = sum(1 for j in jobs if j.engine)
    print(f"找到 {len(jobs)} 個檔案，可轉換 {todo} 個"
          + ("（試跑模式，不會動到檔案）" if args.dry_run else "") + "\n")

    ok = failed = skipped = 0
    warned_markitdown = False
    try:
        for i, job in enumerate(jobs, 1):
            print(f"[{i}/{len(jobs)}] {show(job.src)}")
            if job.engine is None:
                print(f"  – 略過: {job.note}")
                skipped += 1
                continue
            if args.dry_run:
                print(f"  → 會轉成 {job.target}，輸出到 {show(OUTBOX / job.target)}/")
                continue
            if job.target == "md" and not warned_markitdown:
                print("  （第一次轉 Markdown 會先下載 markitdown 套件，可能要幾分鐘）")
                warned_markitdown = True

            try:
                outputs = run_job(job)
            except ConvertError as e:
                print(f"  ✗ 失敗: {e}")
                failed += 1
                continue

            for out in outputs:
                print(f"  ✓ {show(out)}")
            ok += 1
    finally:
        office_cleanup()

    if args.dry_run:
        return 0
    print(f"\n完成 {ok} 個" +
          (f"，略過 {skipped} 個（留在原處）" if skipped else "") +
          (f"，失敗 {failed} 個（留在原處）" if failed else ""))
    if ok:
        print(f"轉好的檔案在: {OUTBOX}")
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n已中斷")
        sys.exit(130)
