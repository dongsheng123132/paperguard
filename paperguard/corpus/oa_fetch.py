"""Phase B —— 开放获取(OA)论文自动下载 + 逐篇深扫.

只下载 **开放获取** 的 PDF(open_access.is_oa=True),下到缓存目录,
逐篇喂给已有的单篇流水线 analyze() 跑 statcheck/grim/image_dup/wb_clone。

合规边界:
- 只碰 OA 论文;非 OA 一律跳过(版权)。
- 下载内容校验是不是真 PDF(落地页/付费墙 HTML 直接丢弃)。
- 限速 + 大小上限;缓存目录默认在系统临时区,不入 git。
- 深扫疑点是单篇检测器的输出 —— "疑似"而非"定罪",仍需人工复核原文。
"""
from __future__ import annotations

import tempfile
import time
import urllib.request
from pathlib import Path

from ..core.pipeline import analyze
from ..core.types import Severity
from .openalex import _opener
from .retraction_watch import normalize_doi

_MAX_BYTES = 60_000_000  # 单篇 PDF 上限 ~60MB
_SEV_W = {Severity.INFO: 0, Severity.LOW: 1, Severity.MEDIUM: 3, Severity.HIGH: 6, Severity.CRITICAL: 10}


def oa_pdf_url(work: dict) -> str | None:
    """从 OpenAlex work 里取一个可下载的 OA PDF 链接;非 OA 返回 None。"""
    oa = work.get("open_access") or {}
    if not oa.get("is_oa"):
        return None
    loc = work.get("best_oa_location") or {}
    return loc.get("pdf_url") or oa.get("oa_url")


def _work_filename(work: dict) -> str:
    wid = (work.get("id") or "work").rsplit("/", 1)[-1]
    return f"{wid}.pdf"


def download_pdf(url: str, dest: Path, *, proxy: str | None = None,
                 timeout: float = 60.0, max_bytes: int = _MAX_BYTES) -> Path | None:
    """下一个 PDF 到 dest。校验确是 PDF;失败/超大/非 PDF 返回 None。"""
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; PaperGuard/0.4 OA-fetch)",
        "Accept": "application/pdf,*/*",
    })
    try:
        with _opener(proxy).open(req, timeout=timeout) as resp:  # noqa: S310
            ctype = (resp.headers.get("Content-Type") or "").lower()
            data = resp.read(max_bytes + 1)
    except Exception:  # noqa: BLE001
        return None
    if not data or len(data) > max_bytes:
        return None
    # 真 PDF 以 %PDF 开头;否则多半是落地页 HTML / 付费墙
    if not data[:5].startswith(b"%PDF") and "pdf" not in ctype:
        return None
    try:
        dest.write_bytes(data)
    except Exception:  # noqa: BLE001
        return None
    return dest


def deep_scan_works(works: list[dict], *, max_pdfs: int = 5, proxy: str | None = None,
                    cache_dir: str | Path | None = None, sleep: float = 1.0) -> list[dict]:
    """对前 max_pdfs 篇 OA 论文下载 + analyze。返回每篇结果 dict 列表。

    每项: {title, doi, year, url, risk_score(float|None), n_findings, top[str], error(str|None)}。
    risk_score=None 表示没取到 PDF 或解析失败。
    """
    cache = Path(cache_dir) if cache_dir else Path(tempfile.mkdtemp(prefix="pg_oa_"))
    cache.mkdir(parents=True, exist_ok=True)

    results: list[dict] = []
    picked = 0
    for w in works:
        if picked >= max_pdfs:
            break
        url = oa_pdf_url(w)
        if not url:
            continue
        picked += 1
        title = (w.get("title") or "(无标题)")[:160]
        doi = normalize_doi(w.get("doi"))
        year = w.get("publication_year")
        dest = cache / _work_filename(w)

        if dest.exists():
            got = dest                                  # 命中缓存,不下载、不限速
        else:
            got = download_pdf(url, dest, proxy=proxy)
            time.sleep(sleep)                           # 仅真正发起下载后限速
        if not got:
            results.append({"title": title, "doi": doi, "year": year, "url": url,
                            "risk_score": None, "n_findings": 0, "top": [],
                            "error": "未取到 PDF(可能是落地页/付费墙,非 PDF)"})
            continue
        try:
            rep = analyze(str(got))
            top = [f"[{f.severity.value}] {f.title}"
                   for f in sorted(rep.findings, key=lambda x: -_SEV_W[x.severity])[:3]]
            results.append({"title": title, "doi": doi, "year": year, "url": url,
                            "risk_score": rep.risk_score, "n_findings": len(rep.findings),
                            "top": top, "error": None})
        except Exception as e:  # noqa: BLE001
            results.append({"title": title, "doi": doi, "year": year, "url": url,
                            "risk_score": None, "n_findings": 0, "top": [],
                            "error": f"解析失败: {e}"})
    return results
