from paperguard.core.pdf import Document, PageText
from paperguard.detectors import grim


def _doc(text: str) -> Document:
    return Document(source="<inline>", pages=[PageText(page=1, text=text)])


def test_grim_violation_flagged():
    # 10 项 1-7 量表 N=24 -> 总和 = 4.27 * 24 = 102.48 -> round 102 / 24 = 4.25, 不等于 4.27
    doc = _doc("Mean anxiety score was 4.27 (SD = 1.10, N = 24).")
    res = grim.run(doc)
    assert res.findings, "应该报 GRIM 不一致"
    assert res.findings[0].metadata["mean"] == 4.27


def test_grim_consistent_ok():
    # 3.83 * 17 = 65.11 -> round 65 / 17 = 3.823529… -> round to 2 dp = 3.82
    # 实际 3.83 → 检查 64 / 17 = 3.7647 nope, 65/17 = 3.8235 -> 3.82,与 3.83 差 0.01,在 0.005 阈外
    # 但 66 / 17 = 3.8823 -> 3.88,也不行。所以 3.83 实际上是 GRIM-fail!
    # 取一个明确合法的: mean 3.82 N=17 -> 64.94 -> 65/17=3.8235 -> 3.82,合法
    doc = _doc("Treatment mean was 3.82 (SD = 0.91, N = 17).")
    res = grim.run(doc)
    assert not res.findings, f"应当通过 GRIM 但报了: {res.findings}"


def test_grim_skips_no_decimals():
    doc = _doc("Mean = 5 (N = 24).")
    res = grim.run(doc)
    assert not res.findings
