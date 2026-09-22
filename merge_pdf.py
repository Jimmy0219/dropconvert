#!/usr/bin/env python3
"""把多張圖片與 PDF 依序合併成一份 PDF（由 engines.merge_to_pdf 呼叫）。

    merge_pdf.py 輸出.pdf 輸入1 輸入2 …

用 macOS 內建的 CoreGraphics／PDFKit（pyobjc，已包含在 pywebview 的相依套件裡）：
- 圖片原樣嵌入、不重新壓縮；只有需要轉正方向的照片才會重新繪製
- 圖片頁面寬度統一為 A4 寬、高度依圖片比例，列印時不會出現超大頁面；
  像素完整保留，放大看一樣清楚
- PDF 整頁搬過來，保留文字、向量圖與連結
"""

from __future__ import annotations

import sys
from pathlib import Path

from Foundation import NSURL, NSMutableData
from Quartz import (CGContextDrawImage, CGDataConsumerCreateWithCFData, CGImageGetHeight,
                    CGImageGetWidth, CGImageSourceCopyPropertiesAtIndex,
                    CGImageSourceCreateImageAtIndex, CGImageSourceCreateThumbnailAtIndex,
                    CGImageSourceCreateWithURL, CGPDFContextBeginPage, CGPDFContextClose,
                    CGPDFContextCreate, CGPDFContextEndPage, CGRectMake, PDFDocument,
                    kCGImagePropertyOrientation, kCGImagePropertyPixelHeight,
                    kCGImagePropertyPixelWidth, kCGImageSourceCreateThumbnailFromImageAlways,
                    kCGImageSourceCreateThumbnailWithTransform,
                    kCGImageSourceThumbnailMaxPixelSize)

A4_WIDTH = 595.28   # 點（1/72 英寸）


def load_image(path: Path):
    source = CGImageSourceCreateWithURL(NSURL.fileURLWithPath_(str(path)), None)
    if source is None:
        raise ValueError(f"讀不到圖片：{path.name}")
    props = CGImageSourceCopyPropertiesAtIndex(source, 0, None) or {}
    if props.get(kCGImagePropertyOrientation, 1) == 1:
        # 方向本來就正確：直接用原始資料，CoreGraphics 會原樣嵌入，不重新壓縮
        image = CGImageSourceCreateImageAtIndex(source, 0, None)
    else:
        # 手機照片常把「要轉 90 度」記在 EXIF 裡，直接讀像素會是躺著的。
        # 讓 ImageIO 依 EXIF 轉正，尺寸維持原圖最長邊，不縮小。
        longest = max(props.get(kCGImagePropertyPixelWidth, 0),
                      props.get(kCGImagePropertyPixelHeight, 0))
        image = CGImageSourceCreateThumbnailAtIndex(source, 0, {
            kCGImageSourceCreateThumbnailFromImageAlways: True,
            kCGImageSourceCreateThumbnailWithTransform: True,
            kCGImageSourceThumbnailMaxPixelSize: longest,
        })
    if image is None:
        raise ValueError(f"讀不到圖片：{path.name}")
    return image


def image_page(path: Path):
    image = load_image(path)
    width, height = CGImageGetWidth(image), CGImageGetHeight(image)
    rect = CGRectMake(0, 0, A4_WIDTH, A4_WIDTH * height / width)
    data = NSMutableData.data()
    context = CGPDFContextCreate(CGDataConsumerCreateWithCFData(data), rect, None)
    CGPDFContextBeginPage(context, None)
    CGContextDrawImage(context, rect, image)
    CGPDFContextEndPage(context)
    CGPDFContextClose(context)
    return PDFDocument.alloc().initWithData_(data)


def pdf_document(path: Path):
    doc = PDFDocument.alloc().initWithURL_(NSURL.fileURLWithPath_(str(path)))
    if doc is None:
        raise ValueError(f"讀不到 PDF：{path.name}")
    if doc.isLocked():
        raise ValueError(f"「{path.name}」有密碼保護，無法合併")
    return doc


def merge(output: Path, inputs: list[Path]) -> None:
    merged = PDFDocument.alloc().init()
    sources = []   # 頁面屬於來源文件，寫檔前都要留著
    for path in inputs:
        doc = pdf_document(path) if path.suffix.lower() == ".pdf" else image_page(path)
        sources.append(doc)
        for i in range(doc.pageCount()):
            merged.insertPage_atIndex_(doc.pageAtIndex_(i), merged.pageCount())
    if merged.pageCount() == 0:
        raise ValueError("沒有任何頁面可以合併")
    if not merged.writeToFile_(str(output)):
        raise ValueError("寫入 PDF 失敗")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    try:
        merge(Path(sys.argv[1]), [Path(a) for a in sys.argv[2:]])
    except ValueError as e:
        sys.exit(str(e))
