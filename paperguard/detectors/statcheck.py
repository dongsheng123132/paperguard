"""StatCheck — 自动重算论文中报告的 p 值,标记不自洽。

抓取四类常见统计报告:
- t(df) = X, p = Y
- F(df1, df2) = X, p = Y
- χ²(df, N=?) = X, p = Y  (chi2 / X^2 / chi-square)
- r(df) = X, p = Y

策略: 用论文里的统计量 + 自由度 重新算一遍 p,与作者报告的 p 比较。
不自洽到一定阈值就报。
"""
from __future__ import annotations

import math
import re

from scipy import stats

from ..core.pdf import Document
from ..core.types import DetectorResult, Finding, Severity

DETECTOR = "statcheck"


# 允许 = ≈ < > ≤ ≥
_OP = r"(?:[=≈<>≤≥]|<=|>=)"
_NUM = r"-?\d+(?:\.\d+)?"

# t(df) = stat, p = pval
_T_RE = re.compile(
    rf"\bt\s*\(\s*(?P<df>{_NUM})\s*\)\s*{_OP}\s*(?P<stat>{_NUM})\s*[,;)]?\s*p\s*(?P<pop>{_OP})\s*(?P<p>{_NUM})",
    re.IGNORECASE,
)
# F(df1, df2) = stat, p = pval
_F_RE = re.compile(
    rf"\bF\s*\(\s*(?P<df1>{_NUM})\s*,\s*(?P<df2>{_NUM})\s*\)\s*{_OP}\s*(?P<stat>{_NUM})\s*[,;)]?\s*p\s*(?P<pop>{_OP})\s*(?P<p>{_NUM})",
    re.IGNORECASE,
)
# chi-square: χ²(df) / χ2(df) / chi2(df) / X2(df)
_CHI_RE = re.compile(
    rf"(?:χ\s*2|χ\s*²|chi[- ]?square|chi2|x\s*2|x\s*²)\s*\(\s*(?P<df>{_NUM})(?:\s*,\s*N\s*=\s*{_NUM})?\s*\)\s*{_OP}\s*(?P<stat>{_NUM})\s*[,;)]?\s*p\s*(?P<pop>{_OP})\s*(?P<p>{_NUM})",
    re.IGNORECASE,
)
# r(df) = stat, p = pval
_R_RE = re.compile(
    rf"\br\s*\(\s*(?P<df>{_NUM})\s*\)\s*{_OP}\s*(?P<stat>-?0?\.\d+)\s*[,;)]?\s*p\s*(?P<pop>{_OP})\s*(?P<p>{_NUM})",
    re.IGNORECASE,
)


def _two_sided_t(stat: float, df: float) -> float:
    return float(2 * stats.t.sf(abs(stat), df))


def _f_p(stat: float, df1: float, df2: float) -> float:
    if stat < 0:
        return 1.0
    return float(stats.f.sf(stat, df1, df2))


def _chi2_p(stat: float, df: float) -> float:
    if stat < 0:
        return 1.0
    return float(stats.chi2.sf(stat, df))


def _r_p(stat: float, df: float) -> float:
    if abs(stat) >= 1.0 or df <= 0:
        return 0.0
    t = stat * math.sqrt(df / (1 - stat * stat))
    return _two_sided_t(t, df)


def _compare(reported_op: str, reported_p: float, computed_p: float) -> tuple[bool, bool]:
    """返回 (不一致, 决策反转).

    决策反转 = 报告 p<0.05 但实际 ≥0.05,或反之 — 会改变结论。
    """
    op = reported_op.replace("<=", "≤").replace(">=", "≥")
    if op in {"<", "≤"}:
        ok = computed_p <= reported_p + 0.001
    elif op in {">", "≥"}:
        ok = computed_p >= reported_p - 0.001
    else:  # = ≈
        if reported_p == 0:
            ok = computed_p < 0.0005
        else:
            tol = max(0.01, reported_p * 0.5)
            ok = abs(computed_p - reported_p) <= tol
    decision_flip = (reported_p < 0.05) != (computed_p < 0.05)
    return (not ok, decision_flip)


def _snippet(text: str, start: int, end: int, span: int = 60) -> str:
    a = max(0, start - span)
    b = min(len(text), end + span)
    return text[a:b].replace("\n", " ").strip()


def _scan(doc: Document) -> list[Finding]:
    findings: list[Finding] = []
    for page in doc.pages:
        text = page.text
        for label, pattern, compute in [
            ("t", _T_RE, lambda m: _two_sided_t(float(m["stat"]), float(m["df"]))),
            ("F", _F_RE, lambda m: _f_p(float(m["stat"]), float(m["df1"]), float(m["df2"]))),
            ("χ²", _CHI_RE, lambda m: _chi2_p(float(m["stat"]), float(m["df"]))),
            ("r", _R_RE, lambda m: _r_p(float(m["stat"]), float(m["df"]))),
        ]:
            for m in pattern.finditer(text):
                try:
                    computed = compute(m)
                except Exception:  # noqa: BLE001
                    continue
                reported_p = float(m["p"])
                pop = m["pop"]
                inconsistent, flip = _compare(pop, reported_p, computed)
                if not inconsistent:
                    continue
                severity = Severity.HIGH if flip else Severity.MEDIUM
                findings.append(
                    Finding(
                        detector=DETECTOR,
                        severity=severity,
                        title=f"{label} 检验报告的 p 值与重算不符" + (" (决策反转)" if flip else ""),
                        detail=(
                            f"报告: p {pop} {reported_p}; 用 {label}={m['stat']} 重算 p ≈ {computed:.4g}。"
                            "可能是排版错误、舍入异常,或数值被人为调整。"
                        ),
                        snippet=_snippet(text, m.start(), m.end()),
                        page=page.page,
                        confidence=0.85 if flip else 0.7,
                        metadata={
                            "statistic": label,
                            "reported_p": reported_p,
                            "computed_p": round(computed, 6),
                            "decision_flip": flip,
                        },
                    )
                )
    return findings


def run(doc: Document) -> DetectorResult:
    try:
        findings = _scan(doc)
        return DetectorResult(detector=DETECTOR, findings=findings)
    except Exception as e:  # noqa: BLE001
        return DetectorResult(detector=DETECTOR, error=str(e))
