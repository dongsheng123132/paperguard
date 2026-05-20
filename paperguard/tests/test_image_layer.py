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
    assert res.findings[0].metadata["pairs"] >= 2


def test_full_pipeline_pdf_has_image_findings():
    _ensure_pdf()
    rpt = analyze(str(PDF))
    det = {f.detector for f in rpt.findings}
    assert "image_dup" in det
    assert "wb_clone" in det
    assert rpt.risk_score >= 5
