from paperguard.core.pdf import Document, PageText
from paperguard.detectors import statcheck


def _doc(text: str) -> Document:
    return Document(source="<inline>", pages=[PageText(page=1, text=text)])


def test_t_inconsistent_flagged():
    # t(20) = 2.00 双侧 p≈0.059; 报告 p=0.001 明显不符且决策反转
    doc = _doc("Anxiety predicted scores, t(20) = 2.00, p = 0.001.")
    res = statcheck.run(doc)
    assert any(f.metadata.get("decision_flip") for f in res.findings)


def test_t_consistent_not_flagged():
    # t(28) = 4.55 双侧 p≈0.0001 — 报告 p=0.0001 一致
    doc = _doc("Recall differed, t(28) = 4.55, p = 0.0001.")
    res = statcheck.run(doc)
    assert not res.findings


def test_F_decision_flip():
    # F(2,21)=1.20 -> p≈0.32; 报告 p < 0.01 强烈反转
    doc = _doc("ANOVA, F(2, 21) = 1.20, p < 0.01.")
    res = statcheck.run(doc)
    assert res.findings
    assert res.findings[0].metadata["decision_flip"] is True


def test_chi2_inconsistent():
    # chi2(3)=7.81, p≈0.05; 报告 p=0.001 显著偏低
    doc = _doc("chi2(3) = 7.81, p = 0.001.")
    res = statcheck.run(doc)
    assert res.findings


def test_r_inconsistent():
    # r(15)=0.92 -> p≈ extremely small; 报告 p=0.300 不一致且反转
    doc = _doc("Correlation in subgroup A was r(15) = 0.92, p = 0.300.")
    res = statcheck.run(doc)
    assert res.findings
    assert res.findings[0].metadata["decision_flip"] is True
