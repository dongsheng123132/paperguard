"""本地 Retraction Watch 库交叉核对.

数据源: Crossref 公开维护的 Retraction Watch Database(免费,引用 "Retraction Watch Database, Crossref")。
仓库里已缓存在 `cases/rw_cache.csv`(由 `cases/fetch_retraction_watch.py` 下载)。

两类信号:
- **DOI 命中(强)**: 论文 DOI 出现在退稿库 OriginalPaperDOI 列 -> 基本可确认已撤稿。
- **名字命中(弱)**: 机构/作者名出现在 Institution/Author 列 -> 仅提示,需人工确认是否同名同机构。
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable

# 仓库根: paperguard/corpus/retraction_watch.py -> parents[2]
ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RW_PATH = ROOT / "cases" / "rw_cache.csv"

# rw_cache.csv 实际列名(已核对表头)
COL_TITLE = "Title"
COL_INSTITUTION = "Institution"
COL_AUTHOR = "Author"
COL_JOURNAL = "Journal"
COL_OG_DOI = "OriginalPaperDOI"
COL_RETRACTION_DATE = "RetractionDate"
COL_REASON = "Reason"
COL_NATURE = "RetractionNature"
COL_URLS = "URLS"


def normalize_doi(doi: str | None) -> str | None:
    """统一 DOI: 去前缀、小写、去空白。无效返回 None。"""
    if not doi:
        return None
    s = doi.strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/",
                   "http://dx.doi.org/", "doi:"):
        if s.startswith(prefix):
            s = s[len(prefix):]
            break
    s = s.strip().strip("/")
    if not s or s in ("unavailable", "na", "n/a", "none"):
        return None
    return s


def load(csv_path: str | Path | None = None) -> list[dict]:
    """读退稿库 CSV -> 行 dict 列表。文件不存在返回 [](上层据此提示 RW 不可用)。"""
    path = Path(csv_path) if csv_path else DEFAULT_RW_PATH
    if not path.exists():
        return []
    with path.open(encoding="utf-8", errors="replace", newline="") as f:
        return list(csv.DictReader(f))


def match_by_dois(rows: list[dict], dois: Iterable[str]) -> list[dict]:
    """DOI 命中(强信号)。返回命中的退稿行,并附 `_norm_doi`。"""
    wanted = {d for d in (normalize_doi(x) for x in dois) if d}
    if not wanted:
        return []
    hits: list[dict] = []
    for row in rows:
        nd = normalize_doi(row.get(COL_OG_DOI))
        if nd and nd in wanted:
            hit = dict(row)
            hit["_norm_doi"] = nd
            hits.append(hit)
    return hits


def match_by_name(rows: list[dict], name: str, field: str = COL_INSTITUTION) -> list[dict]:
    """名字命中(弱信号)。机构/作者名子串匹配(忽略大小写)。name 太短(<4)直接不匹配避免误命中。"""
    needle = (name or "").strip().lower()
    if len(needle) < 4:
        return []
    out: list[dict] = []
    for row in rows:
        hay = (row.get(field) or "").lower()
        if needle in hay:
            out.append(row)
    return out
