"""生成 demo_fraud.pdf — 用于端到端测试图片层.

构造 4 张图,模拟以下造假手法:
- fig1: 一张合成的 WB 条带原图
- fig2: 把 fig1 整张图水平翻转放入 — 触发 image_dup 翻转复用
- fig3: 完全独立的另一张图(背景纹理)
- fig4: 在自己内部把某条带 copy-paste 到另一处 — 触发 wb_clone
"""
from __future__ import annotations

import io
import random
from pathlib import Path

import fitz
import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent
random.seed(42)
np.random.seed(42)


def _synth_wb_blots(seed: int) -> Image.Image:
    """合成一张假 WB 凝胶图: 灰色底 + 几条深色条带."""
    rng = np.random.default_rng(seed)
    h, w = 240, 480
    bg = (200 + rng.normal(0, 8, (h, w))).clip(150, 240).astype(np.uint8)
    img = Image.fromarray(bg, mode="L").convert("RGB")
    draw = ImageDraw.Draw(img)
    for lane in range(6):
        cx = 40 + lane * 70
        # 条带的宽度和深度都加点噪声
        bandw = 40 + rng.integers(-5, 5)
        bandh = 30 + rng.integers(-8, 8)
        intensity = int(rng.integers(40, 110))
        # 模糊矩形
        for dy in range(-bandh // 2, bandh // 2):
            for dx in range(-bandw // 2, bandw // 2):
                edge = abs(dx) / (bandw / 2)
                v = int(intensity + edge * (210 - intensity))
                x, y = cx + dx, 120 + dy
                if 0 <= x < w and 0 <= y < h:
                    cur = img.getpixel((x, y))
                    img.putpixel((x, y), (min(cur[0], v), min(cur[1], v), min(cur[2], v)))
    return img


def _texture(seed: int) -> Image.Image:
    rng = np.random.default_rng(seed)
    h, w = 200, 320
    arr = (rng.normal(128, 50, (h, w))).clip(0, 255).astype(np.uint8)
    return Image.fromarray(arr, mode="L").convert("RGB")


def _clone_inside(img: Image.Image) -> Image.Image:
    """在图片内部把 96x96 区域复制到另一处 — 模拟 WB 条带 copy-move.

    用 32 px 网格对齐的坐标,确保 32x32 分块检测能完整命中."""
    out = img.copy()
    # 源区域: x=32..128, y=96..192 (在 480x240 内)
    src = out.crop((32, 96, 128, 192))
    # 粘贴到两处非邻区域
    out.paste(src, (256, 32))
    out.paste(src, (352, 128))
    return out


def _save_png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def build_pdf(out_path: Path) -> None:
    fig1 = _synth_wb_blots(seed=1)
    fig2 = fig1.transpose(Image.FLIP_LEFT_RIGHT)  # 翻转复用
    fig3 = _texture(seed=99)
    fig4 = _clone_inside(_synth_wb_blots(seed=7))

    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((50, 50), "Demo Fraud Paper - Figure 1 (original WB)")
    page.insert_image(fitz.Rect(50, 80, 500, 280), stream=_save_png(fig1))
    page.insert_text((50, 320), "Figure 2 (independent control)")
    page.insert_image(fitz.Rect(50, 340, 500, 540), stream=_save_png(fig2))

    page2 = doc.new_page(width=595, height=842)
    page2.insert_text((50, 50), "Figure 3 (unrelated texture)")
    page2.insert_image(fitz.Rect(50, 80, 400, 280), stream=_save_png(fig3))
    page2.insert_text((50, 320), "Figure 4 (knockdown WB)")
    page2.insert_image(fitz.Rect(50, 340, 500, 540), stream=_save_png(fig4))

    doc.save(out_path)
    doc.close()


if __name__ == "__main__":
    target = ROOT / "demo_fraud.pdf"
    build_pdf(target)
    print(f"✅ 生成: {target}")
