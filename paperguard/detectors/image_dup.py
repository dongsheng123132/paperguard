"""图片同图复用 — pHash + ORB 两级检查.

第一级: pHash 距离 ≤8 → 视觉高度相似 (含轻度压缩/缩放)
第二级: 对 pHash 命中对再做 ORB 几何验证,排除"两张都很白"之类的假阳

也覆盖几何变换: 检测器会试 4 种翻转 (原图 / 水平翻 / 垂直翻 / 180°)。
"""
from __future__ import annotations

import base64
import io
from dataclasses import dataclass

from PIL import Image

from ..core.images import ExtractedImage, extract_from_pdf
from ..core.types import DetectorResult, Finding, Severity

DETECTOR = "image_dup"


@dataclass
class _ImgFeat:
    image: ExtractedImage
    phashes: list  # imagehash 对象列表(4 种变换)
    pil: Image.Image


def _load_feat(img: ExtractedImage) -> _ImgFeat | None:
    import imagehash

    try:
        pil = Image.open(io.BytesIO(img.bytes_png)).convert("L")
    except Exception:  # noqa: BLE001
        return None
    # 跳过纯白/纯黑(大量论文里全白填充图)
    extrema = pil.getextrema()
    if extrema[1] - extrema[0] < 20:
        return None
    variants = [
        pil,
        pil.transpose(Image.FLIP_LEFT_RIGHT),
        pil.transpose(Image.FLIP_TOP_BOTTOM),
        pil.rotate(180),
    ]
    return _ImgFeat(image=img, phashes=[imagehash.phash(v) for v in variants], pil=pil)


def _phash_distance(a: _ImgFeat, b: _ImgFeat) -> tuple[int, int]:
    """返回 (最小汉明距离, 命中的变换索引)."""
    best = 64
    best_idx = 0
    for i, ph in enumerate(b.phashes):
        d = a.phashes[0] - ph
        if d < best:
            best = d
            best_idx = i
    return best, best_idx


def _orb_inliers(a: Image.Image, b: Image.Image) -> int:
    """ORB 匹配后的几何内点数 — 越多说明真的是同一张图,而非偶然 hash 撞了。"""
    import cv2
    import numpy as np

    arr_a = np.array(a)
    arr_b = np.array(b)
    orb = cv2.ORB_create(nfeatures=500)
    kp1, des1 = orb.detectAndCompute(arr_a, None)
    kp2, des2 = orb.detectAndCompute(arr_b, None)
    if des1 is None or des2 is None or len(kp1) < 10 or len(kp2) < 10:
        return 0
    bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
    matches = bf.match(des1, des2)
    if len(matches) < 10:
        return len(matches)
    src = np.float32([kp1[m.queryIdx].pt for m in matches]).reshape(-1, 1, 2)
    dst = np.float32([kp2[m.trainIdx].pt for m in matches]).reshape(-1, 1, 2)
    try:
        _, mask = cv2.findHomography(src, dst, cv2.RANSAC, 5.0)
    except cv2.error:
        return 0
    return int(mask.sum()) if mask is not None else 0


def _thumb_b64(pil: Image.Image, size: int = 128) -> str:
    cp = pil.copy()
    cp.thumbnail((size, size))
    buf = io.BytesIO()
    cp.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


_VARIANT_NAME = ["原图", "水平翻转", "垂直翻转", "180° 旋转"]


def _scan(images: list[ExtractedImage], hash_thr: int = 10, orb_thr: int = 15) -> list[Finding]:
    feats: list[_ImgFeat] = []
    for img in images:
        f = _load_feat(img)
        if f is not None:
            feats.append(f)

    out: list[Finding] = []
    for i in range(len(feats)):
        for j in range(i + 1, len(feats)):
            a, b = feats[i], feats[j]
            dist, variant = _phash_distance(a, b)
            if dist > hash_thr:
                continue
            # 第二级验证
            b_pil = b.pil
            if variant == 1:
                b_pil = b_pil.transpose(Image.FLIP_LEFT_RIGHT)
            elif variant == 2:
                b_pil = b_pil.transpose(Image.FLIP_TOP_BOTTOM)
            elif variant == 3:
                b_pil = b_pil.rotate(180)
            inliers = _orb_inliers(a.pil, b_pil)
            if dist > 4 and inliers < orb_thr:
                # hash 像但 ORB 不像 — 可能是构图相似的两张不同图,放弃
                continue
            if variant == 0:
                title = "图片复用 — 两张图视觉高度一致"
                sev = Severity.HIGH if dist <= 4 else Severity.MEDIUM
            else:
                title = f"图片复用 — 一张是另一张的{_VARIANT_NAME[variant]}"
                sev = Severity.HIGH  # 翻转复用基本只能是人为
            out.append(
                Finding(
                    detector=DETECTOR,
                    severity=sev,
                    title=title,
                    detail=(
                        f"P{a.image.page}#{a.image.index} 与 P{b.image.page}#{b.image.index} "
                        f"pHash 距离 {dist} (≤8 视觉相同),ORB 几何内点 {inliers}。"
                        + (f" 命中变换: {_VARIANT_NAME[variant]}。" if variant else "")
                        + "WB / 显微镜图的同图复用是常见的图像完整性问题,建议人工复核原图。"
                    ),
                    snippet="",
                    page=a.image.page,
                    confidence=0.9 if dist <= 4 else 0.75,
                    metadata={
                        "page_a": a.image.page,
                        "page_b": b.image.page,
                        "phash_distance": dist,
                        "orb_inliers": inliers,
                        "variant": _VARIANT_NAME[variant],
                        "thumb_a_b64": _thumb_b64(a.pil),
                        "thumb_b_b64": _thumb_b64(b.pil),
                    },
                )
            )
    return out


def run_from_pdf(path: str) -> DetectorResult:
    try:
        images = extract_from_pdf(path)
        if len(images) < 2:
            return DetectorResult(detector=DETECTOR, skipped=True)
        return DetectorResult(detector=DETECTOR, findings=_scan(images))
    except Exception as e:  # noqa: BLE001
        return DetectorResult(detector=DETECTOR, error=str(e))
