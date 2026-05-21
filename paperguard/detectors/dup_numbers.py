"""数字雷同扫描 — 跨段落寻找不合常理的数字序列重复。

思路:
- 将全文按段落切分
- 每段提取所有数值(非年份/页码/章节号)
- 对每对段落,取交集大小 ≥ 阈值 且 Jaccard ≥ 阈值 → 报警
- 同时检测"连续 ≥3 个数字序列完全相同"的硬重复
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from ..core.pdf import Document
from ..core.types import DetectorResult, Finding, Severity

DETECTOR = "dup_numbers"

# 抓"有意义的数值": 至少有一位小数,或者 4-6 位且非年份
_NUM_RE = re.compile(r"-?\d+\.\d+")

# 段落切分: 空行 + 编号
_PARA_SPLIT = re.compile(r"\n\s*\n+")

# DOI 前缀(出版社代码),例: 10.3389/fphys.2020.01092 → 整段都不该参与
_DOI_RE = re.compile(r"\b10\.\d{4,9}/[\w\-./;()]+", re.IGNORECASE)
# 期刊页眉页脚标志词
_JOURNAL_CRUFT = re.compile(
    r"\b(?:Article\s+(?:ID|No\.?)|Volume\s+\d+|Issue\s+\d+|Frontiers\s+in|"
    r"www\.[a-z]+\.(?:com|org)|doi:|https?://|©\s*\d{4}|"
    r"Journal\s+of\s+|Manuscript\s+received)\b",
    re.IGNORECASE,
)


@dataclass
class _Para:
    page: int
    idx: int
    text: str
    numbers: list[float]
    table_like: bool = False


def _clean_for_numbers(text: str) -> str:
    """剔除 DOI / URL / 期刊页眉页脚行,避免它们里的数字被当成数据。"""
    # 1) 先去 DOI 整串
    text = _DOI_RE.sub(" ", text)
    # 2) 再按行过滤明显的期刊 cruft(整行都丢弃)
    kept = []
    for line in text.splitlines():
        if _JOURNAL_CRUFT.search(line):
            continue
        kept.append(line)
    return "\n".join(kept)


def _strip_repeated_lines(doc: Document, min_pages: int = 3) -> dict[int, str]:
    """跨页重复出现的短行视为页眉页脚,逐页剔除后返回 {page: cleaned_text}."""
    # 统计每行(<=120 字)出现在多少不同页
    page_lines: dict[int, list[str]] = {}
    occur: Counter = Counter()
    for page in doc.pages:
        lines = [l.strip() for l in page.text.splitlines()]
        page_lines[page.page] = lines
        for l in set(l for l in lines if 4 <= len(l) <= 120):
            occur[l] += 1
    repeated = {l for l, n in occur.items() if n >= min_pages}
    out: dict[int, str] = {}
    for pg, lines in page_lines.items():
        kept = [l for l in lines if l.strip() not in repeated]
        out[pg] = "\n".join(kept)
    return out


def _is_table_like(text: str) -> bool:
    """识别 PDF 表格抽取后的伪段落,这类文本需要更强证据才报警。"""
    lower = text.lower()
    if lower.lstrip().startswith(("table ", "figure ", "fig. ", "fig ")):
        return True
    table_markers = (
        "p-value",
        "p value",
        "mean ±",
        "sd ",
        "standard deviation",
        "confidence interval",
        "bias square",
        "baseline characteristics",
    )
    marker_hits = sum(1 for marker in table_markers if marker in lower)
    numeric_hits = len(_NUM_RE.findall(text))
    if marker_hits >= 1 and numeric_hits >= 8:
        return True
    tokens = re.findall(r"[A-Za-z]+|-?\d+\.\d+|±|—", text)
    if numeric_hits >= 12 and tokens:
        numeric_density = numeric_hits / len(tokens)
        if numeric_density >= 0.35 or text.count("±") >= 4:
            return True
    return False


def _to_paragraphs(doc: Document) -> list[_Para]:
    cleaned_pages = _strip_repeated_lines(doc)
    paras: list[_Para] = []
    for page in doc.pages:
        page_text = _clean_for_numbers(cleaned_pages.get(page.page, page.text))
        for i, raw in enumerate(_PARA_SPLIT.split(page_text)):
            t = raw.strip()
            if len(t) < 40:
                continue
            nums = [float(x) for x in _NUM_RE.findall(t)]
            # 仅保留含 ≥4 个数字的段落,否则没意义
            if len(nums) < 4:
                continue
            paras.append(_Para(page=page.page, idx=i, text=t, numbers=nums, table_like=_is_table_like(t)))
    return paras


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _consecutive_match(a: list[float], b: list[float], k: int = 3) -> tuple[int, list[float]] | None:
    """寻找两个序列里长度≥k的最长公共连续子串。"""
    if len(a) < k or len(b) < k:
        return None
    best: list[float] = []
    for i in range(len(a) - k + 1):
        for j in range(len(b) - k + 1):
            m = 0
            while i + m < len(a) and j + m < len(b) and a[i + m] == b[j + m]:
                m += 1
            if m >= k and m > len(best):
                best = a[i : i + m]
    if best:
        return len(best), best
    return None


def _internal_repeat(numbers: list[float], k: int = 4) -> tuple[int, list[float], int] | None:
    """段落内自重复: 找 a[i:i+m] == a[j:j+m], m≥k, j > i+m-1。

    返回 (匹配长度, 序列, 起始 j)。
    """
    n = len(numbers)
    if n < 2 * k:
        return None
    best: tuple[int, list[float], int] | None = None
    for i in range(n - k + 1):
        for j in range(i + k, n - k + 1):
            m = 0
            while j + m < n and i + m < j and numbers[i + m] == numbers[j + m]:
                m += 1
            if m >= k and (best is None or m > best[0]):
                best = (m, numbers[i : i + m], j)
    return best


def _low_information_sequence(seq: list[float]) -> bool:
    """跳过 p 值阈值、显著性星号说明等低信息重复。"""
    rounded = [round(x, 6) for x in seq]
    uniq = set(rounded)
    if len(uniq) <= 2 and all(abs(x) <= 0.1 for x in uniq):
        return True
    common_thresholds = {0.001, 0.01, 0.05}
    if uniq and uniq.issubset(common_thresholds):
        return True
    return False


def _scan(doc: Document, jaccard_threshold: float = 0.6, min_overlap: int = 5) -> list[Finding]:
    paras = _to_paragraphs(doc)
    out: list[Finding] = []
    # 段落内自重复 — k=5 是经验值:k=4 会被 "p<0.05" 多次提及触发假阳性
    for p in paras:
        rep = _internal_repeat(p.numbers, k=5)
        if rep:
            m, seq, _start = rep
            if _low_information_sequence(seq):
                continue
            if p.table_like and m < 8:
                continue
            out.append(
                Finding(
                    detector=DETECTOR,
                    severity=Severity.HIGH if m >= 5 else Severity.MEDIUM,
                    title="数字雷同 — 同段内连续重复",
                    detail=(
                        f"段落 P{p.page}#{p.idx} 内部出现 {m} 个数值连续完全相同: {seq[:8]}。"
                        "常见于把对照组数据原样复制到实验组,或表格构造时复制粘贴未修改。"
                    ),
                    snippet=p.text[:240],
                    page=p.page,
                    confidence=0.85,
                    metadata={"consecutive": m, "sequence": seq, "para": p.idx},
                )
            )
    # 段落间相似
    for i in range(len(paras)):
        for j in range(i + 1, len(paras)):
            a, b = paras[i], paras[j]
            set_a = set(a.numbers)
            set_b = set(b.numbers)
            overlap = set_a & set_b
            if len(overlap) < min_overlap:
                continue
            jac = _jaccard(set_a, set_b)
            consec = _consecutive_match(a.numbers, b.numbers, k=3)
            if jac < jaccard_threshold and consec is None:
                continue
            if consec and _low_information_sequence(consec[1]):
                continue
            if a.table_like or b.table_like:
                if consec is None or consec[0] < 8 or jac < 0.2:
                    continue
            severity = Severity.HIGH if consec and consec[0] >= 5 else Severity.MEDIUM
            sample = sorted(overlap, key=lambda x: -abs(x))[:6]
            detail = (
                f"段落 P{a.page}#{a.idx} 与 P{b.page}#{b.idx} 共享 {len(overlap)} 个数值 "
                f"(Jaccard={jac:.2f})。"
            )
            if consec:
                detail += f" 其中 {consec[0]} 个数字连续完全一致: {consec[1][:8]}"
            detail += "。可能是同一份数据被改写复用,或对照组数据存在异常,建议人工核对原始记录。"
            out.append(
                Finding(
                    detector=DETECTOR,
                    severity=severity,
                    title="数字雷同 — 两段共享大量相同数值",
                    detail=detail,
                    snippet=f"[P{a.page}] {a.text[:120]}…  ↔  [P{b.page}] {b.text[:120]}…",
                    page=a.page,
                    confidence=0.7 if consec else 0.55,
                    metadata={
                        "overlap_count": len(overlap),
                        "jaccard": round(jac, 3),
                        "consecutive": consec[0] if consec else 0,
                        "sample_shared": sample,
                        "page_a": a.page,
                        "page_b": b.page,
                    },
                )
            )
    return out


def run(doc: Document) -> DetectorResult:
    try:
        return DetectorResult(detector=DETECTOR, findings=_scan(doc))
    except Exception as e:  # noqa: BLE001
        return DetectorResult(detector=DETECTOR, error=str(e))


__all__ = ["run", "DETECTOR"]
