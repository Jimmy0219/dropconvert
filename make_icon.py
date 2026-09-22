#!/usr/bin/env python3
"""把 icon.svg 轉成 AppIcon.icns（由 make_app.sh 呼叫）。

用 macOS 原生的 NSImage 繪製，保留透明背景；每個尺寸各自從向量繪製，
小圖也清晰。需要 pyobjc，已包含在 pywebview 的相依套件裡。
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from AppKit import (NSBitmapImageRep, NSCompositingOperationCopy, NSGraphicsContext,
                    NSImage, NSPNGFileType)

# iconutil 規定的檔名與像素尺寸
SIZES = {f"icon_{pt}x{pt}{suffix}.png": pt * scale
         for pt in (16, 32, 128, 256, 512)
         for suffix, scale in (("", 1), ("@2x", 2))}


def render(svg: NSImage, pixels: int, out: Path) -> None:
    rep = NSBitmapImageRep.alloc().initWithBitmapDataPlanes_pixelsWide_pixelsHigh_bitsPerSample_samplesPerPixel_hasAlpha_isPlanar_colorSpaceName_bytesPerRow_bitsPerPixel_(
        None, pixels, pixels, 8, 4, True, False, "NSDeviceRGBColorSpace", 0, 0)
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.setCurrentContext_(
        NSGraphicsContext.graphicsContextWithBitmapImageRep_(rep))
    svg.drawInRect_fromRect_operation_fraction_(
        ((0, 0), (pixels, pixels)), ((0, 0), (0, 0)), NSCompositingOperationCopy, 1.0)
    NSGraphicsContext.restoreGraphicsState()
    rep.representationUsingType_properties_(NSPNGFileType, {}).writeToFile_atomically_(
        str(out), True)


def main(svg_path: Path, icns_path: Path) -> None:
    svg = NSImage.alloc().initWithContentsOfFile_(str(svg_path))
    if svg is None:
        sys.exit(f"讀不到圖示: {svg_path}")
    with tempfile.TemporaryDirectory() as tmp:
        iconset = Path(tmp) / "AppIcon.iconset"
        iconset.mkdir()
        for name, pixels in SIZES.items():
            render(svg, pixels, iconset / name)
        subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(icns_path)],
                       check=True)
        if len(sys.argv) > 3:   # 除錯用：另外存一張 1024 的預覽圖
            shutil.copy(iconset / "icon_512x512@2x.png", sys.argv[3])


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
