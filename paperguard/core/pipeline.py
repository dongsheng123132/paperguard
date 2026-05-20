"""检测流水线 — 串起所有 detector."""
from __future__ import annotations

from pathlib import Path

from .pdf import Document, load
from .types import DetectorResult, Report
from ..detectors import statcheck, grim, dup_numbers, image_dup, wb_clone


_TEXT_DETECTORS = [statcheck.run, grim.run, dup_numbers.run]
_PDF_IMAGE_DETECTORS = [image_dup.run_from_pdf, wb_clone.run_from_pdf]


def analyze(path: str) -> Report:
    doc: Document = load(path)
    results: list[DetectorResult] = [fn(doc) for fn in _TEXT_DETECTORS]
    if Path(path).suffix.lower() == ".pdf":
        for fn in _PDF_IMAGE_DETECTORS:
            results.append(fn(path))
    report = Report(
        source=doc.source,
        page_count=doc.page_count,
        word_count=doc.word_count,
        results=results,
    )
    report.compute_risk()
    return report
