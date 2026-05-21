"""WB / 显微镜单图内的"局部克隆"检测.

经典造假手法: 把一块条带 copy-paste 到同一张图的另一处。
策略: 对图片做不重叠分块 (32×32),计算每块 dHash,统计完全相同的非邻块对。
- 排除背景纯色块(方差太低)
- 排除相邻块(自然纹理可能近似)
"""
from __future__ import annotations

import base64
import io

import imagehash
import numpy as np
from PIL import Image

from ..core.images import ExtractedImage, extract_from_pdf
from ..core.types import DetectorResult, Finding, Severity

DETECTOR = "wb_clone"

BLOCK = 32
MIN_VAR = 50  # 像素方差阈值,低于则视为均匀背景
NEIGHBOR = 2  # 块距小于该值的不算
SATURATION_PAIRS = 15000  # 超过此数视为图本身有规则重复纹理(柱状图坐标轴/表格),降级为提示


def _looks_like_vector_figure(rgb: Image.Image, gray_arr: np.ndarray) -> bool:
    """跳过统计图、流程图、Logo 这类矢量/排版图。

    wb_clone 的目标是凝胶、WB、显微图里的局部复制。普通图表里大量白底、
    坐标轴、文字和重复线框会制造很多相同小块,继续扫描只会抬高误报。
    """
    arr = np.asarray(rgb.convert("RGB"))
    maxc = arr.max(axis=2).astype(np.int16)
    minc = arr.min(axis=2).astype(np.int16)
    saturation = maxc - minc
    white_ratio = np.all(arr > 245, axis=2).mean()
    near_white_ratio = np.all(arr > 235, axis=2).mean()
    dark_ratio = (gray_arr < 80).mean()
    mid_ratio = ((gray_arr >= 80) & (gray_arr <= 235)).mean()
    colorful_ratio = (saturation > 50).mean()
    hist = np.bincount(gray_arr.ravel(), minlength=256)
    dominant_ratio = hist.max() / gray_arr.size

    # 白底彩色/黑色统计图、箱线图、折线图。
    if near_white_ratio > 0.80 and mid_ratio < 0.15:
        return True
    # 灰底流程图/信息图:大面积同色底 + 少量文字/边框。
    if dominant_ratio > 0.25 and dark_ratio < 0.10 and (white_ratio > 0.25 or mid_ratio > 0.50):
        return True
    # 白底彩色图表即使有少量填充块,也不是 WB copy-move 的适用对象。
    if white_ratio > 0.55 and colorful_ratio > 0.03 and dark_ratio < 0.15:
        return True
    # 深色渐变背景 + 大量彩色矢量元素通常是机制示意图,不是显微图。
    if dark_ratio > 0.60 and colorful_ratio > 0.35 and dominant_ratio < 0.10:
        return True
    return False


def _scan_single(img: ExtractedImage) -> list[Finding]:
    try:
        rgb = Image.open(io.BytesIO(img.bytes_png)).convert("RGB")
        pil = rgb.convert("L")
    except Exception:  # noqa: BLE001
        return []
    arr = np.asarray(pil)
    h, w = arr.shape
    if h < BLOCK * 4 or w < BLOCK * 4:
        return []
    if _looks_like_vector_figure(rgb, arr):
        return []
    rows = h // BLOCK
    cols = w // BLOCK
    hashes: dict = {}
    for r in range(rows):
        for c in range(cols):
            y0, x0 = r * BLOCK, c * BLOCK
            block = arr[y0 : y0 + BLOCK, x0 : x0 + BLOCK]
            if block.var() < MIN_VAR:
                continue
            ph = imagehash.dhash(Image.fromarray(block), hash_size=8)
            key = str(ph)
            hashes.setdefault(key, []).append((r, c, block))

    cloned_pairs: list[tuple[tuple[int, int], tuple[int, int]]] = []
    for positions in hashes.values():
        if len(positions) < 2:
            continue
        for i in range(len(positions)):
            for j in range(i + 1, len(positions)):
                r1, c1, _ = positions[i]
                r2, c2, _ = positions[j]
                if abs(r1 - r2) <= NEIGHBOR and abs(c1 - c2) <= NEIGHBOR:
                    continue  # 邻块
                cloned_pairs.append(((r1, c1), (r2, c2)))

    if len(cloned_pairs) < 2:
        # 少量孤立命中可能是巧合,要至少 2 对克隆才报
        return []

    n_pairs = len(cloned_pairs)
    if n_pairs >= SATURATION_PAIRS:
        return []
    overlay = _annotate(pil, cloned_pairs)
    severity = Severity.HIGH
    confidence = 0.75
    title = "图片内部疑似克隆 (copy-move)"
    detail = (
        f"P{img.page}#{img.index}: 检测到 {n_pairs} 对非相邻区块的指纹完全相同。"
        "在 Western blot / 凝胶图中,这是把同一条带 copy-paste 到不同泳道的典型造假特征。"
    )
    return [
        Finding(
            detector=DETECTOR,
            severity=severity,
            title=title,
            detail=detail,
            snippet="",
            page=img.page,
            confidence=confidence,
            metadata={
                "pairs": n_pairs,
                "image_size": [img.width, img.height],
                "annotated_b64": overlay,
                "page_image": img.page,
            },
        )
    ]


def _annotate(pil: Image.Image, pairs: list) -> str:
    """在原图上画框,标注克隆块对,返回 base64 png."""
    from PIL import ImageDraw

    rgb = pil.convert("RGB")
    draw = ImageDraw.Draw(rgb)
    palette = ["red", "yellow", "lime", "cyan", "magenta", "orange"]
    for k, (p1, p2) in enumerate(pairs[:20]):
        color = palette[k % len(palette)]
        for r, c in (p1, p2):
            x0, y0 = c * BLOCK, r * BLOCK
            draw.rectangle([x0, y0, x0 + BLOCK, y0 + BLOCK], outline=color, width=2)
    # 缩到 320 px 宽以节省体积
    if rgb.width > 320:
        ratio = 320 / rgb.width
        rgb = rgb.resize((320, int(rgb.height * ratio)))
    buf = io.BytesIO()
    rgb.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def run_from_pdf(path: str) -> DetectorResult:
    try:
        images = extract_from_pdf(path)
        if not images:
            return DetectorResult(detector=DETECTOR, skipped=True)
        findings: list[Finding] = []
        for img in images:
            findings.extend(_scan_single(img))
        return DetectorResult(detector=DETECTOR, findings=findings)
    except Exception as e:  # noqa: BLE001
        return DetectorResult(detector=DETECTOR, error=str(e))
