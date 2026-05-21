"""图片层端到端 — 用 samples/demo_fraud.pdf."""
from pathlib import Path

import pytest

from paperguard.core.pipeline import analyze
from paperguard.detectors import image_dup, wb_clone

ROOT = Path(__file__).resolve().parents[2]
PDF = ROOT / "samples" / "demo_fraud.pdf"


def _ensure_pdf():
    if not PDF.exists():
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "make_fraud_pdf", ROOT / "samples" / "make_fraud_pdf.py"
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.build_pdf(PDF)


def test_image_dup_finds_flipped_reuse():
    _ensure_pdf()
    res = image_dup.run_from_pdf(str(PDF))
    assert res.findings, "应抓到翻转复用"
    assert any("翻转" in f.title for f in res.findings)


def test_wb_clone_finds_internal_copy():
    _ensure_pdf()
    res = wb_clone.run_from_pdf(str(PDF))
    assert res.findings, "应抓到内部 copy-move"
    f = res.findings[0]
    assert f.metadata["pairs"] >= 2
    # 合成样本 pair 数远低于饱和阈值,应保持 HIGH severity
    assert f.severity.value == "high"


def test_wb_clone_saturation_is_ignored():
    """图本身富含规则纹理时 (pairs >= SATURATION_PAIRS),不应报 copy-move 疑点。"""
    import io
    import numpy as np
    from PIL import Image
    from paperguard.core.images import ExtractedImage
    from paperguard.detectors.wb_clone import _scan_single, SATURATION_PAIRS

    # 构造高纹理但规则重复的灰度图:把 64x64 的随机块在 16x16 网格中重复
    rng = np.random.default_rng(42)
    tile = (rng.integers(0, 256, size=(64, 64), dtype=np.uint8))
    big = np.tile(tile, (16, 16))  # 1024x1024,16*16=256 块同样的内容
    buf = io.BytesIO()
    Image.fromarray(big).save(buf, format="PNG")
    img = ExtractedImage(
        page=1, index=0, bytes_png=buf.getvalue(),
        width=big.shape[1], height=big.shape[0],
    )
    assert SATURATION_PAIRS > 0
    findings = _scan_single(img)
    assert not findings


def test_full_pipeline_pdf_has_image_findings():
    _ensure_pdf()
    rpt = analyze(str(PDF))
    det = {f.detector for f in rpt.findings}
    assert "image_dup" in det
    assert "wb_clone" in det
    assert rpt.risk_score >= 5
