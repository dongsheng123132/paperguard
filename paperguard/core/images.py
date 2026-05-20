"""图片抽取 — PDF 内嵌图 + 整页渲染图。

策略:
- 内嵌图(get_images): 抓到的就是论文图,信息最直接
- 同时给整页渲染一份缩略图,用于复核报告里"图片在哪一页"
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class ExtractedImage:
    page: int
    index: int  # 该页第几张
    bytes_png: bytes
    width: int
    height: int

    def to_ndarray_gray(self) -> np.ndarray:
        import cv2

        arr = np.frombuffer(self.bytes_png, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
        return img


def extract_from_pdf(path: str | Path, min_pixels: int = 64 * 64) -> list[ExtractedImage]:
    import fitz  # PyMuPDF

    out: list[ExtractedImage] = []
    with fitz.open(path) as doc:
        for pno, page in enumerate(doc, start=1):
            for i, info in enumerate(page.get_images(full=True)):
                xref = info[0]
                try:
                    pix = fitz.Pixmap(doc, xref)
                except Exception:  # noqa: BLE001
                    continue
                # 转 RGB(避免 CMYK)
                if pix.n - pix.alpha >= 4:
                    pix = fitz.Pixmap(fitz.csRGB, pix)
                if pix.width * pix.height < min_pixels:
                    continue
                png = pix.tobytes("png")
                out.append(
                    ExtractedImage(
                        page=pno,
                        index=i,
                        bytes_png=png,
                        width=pix.width,
                        height=pix.height,
                    )
                )
    return out


def render_page_thumb(path: str | Path, page: int, scale: float = 0.5) -> bytes:
    import fitz

    with fitz.open(path) as doc:
        pg = doc.load_page(page - 1)
        mat = fitz.Matrix(scale, scale)
        pix = pg.get_pixmap(matrix=mat, alpha=False)
        return pix.tobytes("png")
