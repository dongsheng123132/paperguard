"""GRIM Test — Granularity-Related Inconsistency of Means.

整数计数项(如李克特量表、人数、次数)的均值 = 总和 / N。
所以 mean * N 必须接近某个整数。如果不接近,该均值在物理上不可能。

例: N=10 时,均值小数位只能是 .0/.1/.2/.../.9,出现 4.27 就有问题。
"""
from __future__ import annotations

import re

from ..core.pdf import Document
from ..core.types import DetectorResult, Finding, Severity

DETECTOR = "grim"

# M = 3.27, SD = 0.81, N = 24
# Mean = 3.27 (SD = 0.81, N = 24)
_NUM = r"\d+\.\d+"
_PATTERNS = [
    # M = 4.27, SD = 1.10, N = 24  /  Mean = 4.27 (N = 24)  /  均值 = ...
    re.compile(
        rf"\b(?:M(?:ean)?|均值|平均值?)\s*[=:＝]\s*(?P<mean>{_NUM})"
        rf"(?:\s*[,，;；(（]\s*(?:SD|σ|std|标准差)\s*[=:＝]\s*{_NUM})?"
        rf"\s*[,，;；(（]\s*(?:N|n|样本量|人数)\s*[=:＝]\s*(?P<n>\d{{1,5}})",
        re.IGNORECASE,
    ),
    # 自由文本: "...was 4.27 (SD = 1.10, N = 24)"  /  "...is 3.83 (N = 17)"
    re.compile(
        rf"(?:was|is|were|of|=)\s*(?P<mean>{_NUM})\s*\(\s*"
        rf"(?:SD|σ|std|标准差)\s*[=:＝]\s*{_NUM}\s*[,，;；]\s*"
        rf"(?:N|n|样本量|人数)\s*[=:＝]\s*(?P<n>\d{{1,5}})\s*\)",
        re.IGNORECASE,
    ),
    re.compile(
        rf"(?:was|is|were|of|=)\s*(?P<mean>{_NUM})\s*\(\s*"
        rf"(?:N|n|样本量|人数)\s*[=:＝]\s*(?P<n>\d{{1,5}})\s*\)",
        re.IGNORECASE,
    ),
    # 4.27 ± 1.10, N = 24
    re.compile(
        rf"(?P<mean>{_NUM})\s*±\s*{_NUM}\s*[,，;；(（]\s*(?:N|n|样本量|人数)\s*[=:＝]\s*(?P<n>\d{{1,5}})",
        re.IGNORECASE,
    ),
]


def _is_grim_inconsistent(mean: float, n: int, decimals: int) -> bool:
    if n <= 0 or n > 5000:
        return False
    total = mean * n
    nearest = round(total)
    # 若四舍五入后再除以 N、再四舍五入到同样小数位 — 是否能还原 mean?
    rounded_back = round(nearest / n, decimals)
    return abs(rounded_back - mean) > 0.5 * 10 ** (-decimals)


def _decimal_places(s: str) -> int:
    if "." not in s:
        return 0
    return len(s.split(".", 1)[1])


def _snippet(text: str, start: int, end: int, span: int = 60) -> str:
    a = max(0, start - span)
    b = min(len(text), end + span)
    return text[a:b].replace("\n", " ").strip()


def _scan(doc: Document) -> list[Finding]:
    out: list[Finding] = []
    seen: set[tuple[int, int, int]] = set()  # (page, start, end) 去重
    for page in doc.pages:
        text = page.text
        for pattern in _PATTERNS:
            for m in pattern.finditer(text):
                key = (page.page, m.start(), m.end())
                if key in seen:
                    continue
                seen.add(key)
                mean_s = m["mean"]
                try:
                    mean = float(mean_s)
                    n = int(m["n"])
                except ValueError:
                    continue
                decimals = _decimal_places(mean_s)
                if decimals == 0:
                    continue
                if not _is_grim_inconsistent(mean, n, decimals):
                    continue
                out.append(
                    Finding(
                        detector=DETECTOR,
                        severity=Severity.MEDIUM,
                        title="GRIM 检验失败 — 均值与样本量不自洽",
                        detail=(
                            f"均值 {mean} 在 N={n} 条件下不可由整数计数得到。"
                            "若所测变量是整数(人数/计数/李克特量表),该均值物理上不可能。"
                            "可能是 N 报错、均值笔误,或数据被人为编造。"
                        ),
                        snippet=_snippet(text, m.start(), m.end()),
                        page=page.page,
                        confidence=0.55,  # 仅当变量确为整数才适用 → 中等置信度
                        metadata={"mean": mean, "n": n, "decimals": decimals},
                    )
                )
    return out


def run(doc: Document) -> DetectorResult:
    try:
        return DetectorResult(detector=DETECTOR, findings=_scan(doc))
    except Exception as e:  # noqa: BLE001
        return DetectorResult(detector=DETECTOR, error=str(e))
