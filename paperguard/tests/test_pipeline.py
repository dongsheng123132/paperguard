from pathlib import Path

from paperguard.core.pipeline import analyze

ROOT = Path(__file__).resolve().parents[2]


def test_demo_fraud_flags():
    rpt = analyze(str(ROOT / "samples" / "demo_fraud.txt"))
    assert rpt.risk_score > 5
    titles = " ".join(f.title for f in rpt.findings)
    assert "p" in titles or "GRIM" in titles or "雷同" in titles


def test_demo_clean_minimal():
    rpt = analyze(str(ROOT / "samples" / "demo_clean.txt"))
    # 干净样本应低分(<5)
    assert rpt.risk_score < 5
