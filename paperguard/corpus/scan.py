"""corpus scan 编排 —— 三重交叉验证 -> Report.

借鉴 Co-Scientist 的思路: 把力气花在跨独立来源的验证上,而不是单一信号下结论。
三个信号:
  1. OpenAlex `is_retracted` 标记
  2. Retraction Watch 的 DOI 命中(强)
  3. Retraction Watch 的机构/作者名命中(弱,需人工确认)

输出复用 paperguard 既有 Report 契约(kind='corpus'),一律"疑似/记录",不下"造假"定论。
"""
from __future__ import annotations

import re

from ..core.types import DetectorResult, Finding, Report, Severity
from . import oa_fetch, openalex, retraction_watch as rw

DETECTOR = "corpus_retraction"
DETECTOR_DEEP = "corpus_deepscan"
_MAX_NAME_HITS = 15


def _clean_name(name: str) -> str:
    """'Kingfa (China)' -> 'Kingfa';去括号后缀,便于和退稿库机构名做子串匹配。"""
    return re.sub(r"\s*[\(（].*?[\)）]\s*$", "", (name or "").strip()).strip()


def _doi_url(doi: str | None) -> str:
    return f"https://doi.org/{doi}" if doi else ""


def _rw_url(row: dict, norm_doi: str | None) -> str:
    urls = (row.get(rw.COL_URLS) or "").strip()
    if urls:
        return urls.split(";")[0].strip()
    return f"https://retractionwatch.com/?s={norm_doi}" if norm_doi else "https://retractionwatch.com/"


def _profile_finding(entity: dict, works: list[dict], total: int) -> Finding:
    years = [w.get("publication_year") for w in works if w.get("publication_year")]
    oa = sum(1 for w in works if (w.get("open_access") or {}).get("is_oa"))
    span = f"{min(years)}–{max(years)}" if years else "—"
    recent: dict[int, int] = {}
    for y in years:
        recent[y] = recent.get(y, 0) + 1
    recent_str = ", ".join(f"{y}:{recent[y]}" for y in sorted(recent, reverse=True)[:3]) or "—"
    capped = f"(本次仅取最近 {len(works)} 篇做体检)" if total > len(works) else ""
    detail = (
        f"{entity['kind']} · {entity['display_name']} · OpenAlex {entity['id']}\n"
        f"作品总数 {total} · 被引 {entity.get('cited_by_count', 0)} · 年份跨度 {span} · "
        f"开放获取(OA) {oa}/{len(works)} 篇 {capped}\n"
        f"近年发文: {recent_str}"
    )
    return Finding(detector=DETECTOR, severity=Severity.INFO, title="📊 发文画像",
                   detail=detail, confidence=1.0,
                   metadata={"entity_id": entity["id"], "works_total": total, "oa_count": oa})


def _retraction_findings(works: list[dict], rw_rows: list[dict]) -> list[Finding]:
    """合并 OpenAlex is_retracted 与 RW DOI 命中,按 DOI 去重。"""
    # 语料里按归一化 DOI 建索引
    work_by_doi: dict[str, dict] = {}
    for w in works:
        nd = rw.normalize_doi(w.get("doi"))
        if nd:
            work_by_doi[nd] = w

    rw_hits = rw.match_by_dois(rw_rows, [w.get("doi") for w in works])
    rw_by_doi = {h["_norm_doi"]: h for h in rw_hits}

    findings: list[Finding] = []
    seen: set[str] = set()

    # 1) 语料内被任一来源标记撤稿的论文
    for w in works:
        nd = rw.normalize_doi(w.get("doi"))
        is_oa_retracted = bool(w.get("is_retracted"))
        rw_row = rw_by_doi.get(nd) if nd else None
        if not is_oa_retracted and not rw_row:
            continue
        key = nd or w.get("id") or w.get("title", "")
        if key in seen:
            continue
        seen.add(key)
        title = (w.get("title") or "(无标题)")[:160]
        year = w.get("publication_year")
        if rw_row:  # 退稿库命中 = 强信号
            reason = (rw_row.get(rw.COL_REASON) or "").strip(" ;") or "未注明"
            nature = (rw_row.get(rw.COL_NATURE) or "").strip() or "Retraction"
            journal = (rw_row.get(rw.COL_JOURNAL) or "").strip()
            date = (rw_row.get(rw.COL_RETRACTION_DATE) or "").strip()
            src = "OpenAlex + Retraction Watch 双来源确认" if is_oa_retracted else "Retraction Watch 收录"
            findings.append(Finding(
                detector=DETECTOR, severity=Severity.CRITICAL,
                title=f"已撤稿: {title}",
                detail=(f"{src}。\n类型: {nature} · 期刊: {journal or '—'} · 撤稿日期: {date or '—'}\n"
                        f"原因: {reason}\nDOI: {_doi_url(nd)}"),
                confidence=0.95,
                metadata={"doi": nd, "url": _rw_url(rw_row, nd), "year": year,
                          "sources": ["openalex", "retraction_watch"] if is_oa_retracted else ["retraction_watch"]},
            ))
        else:  # 仅 OpenAlex 标记
            findings.append(Finding(
                detector=DETECTOR, severity=Severity.HIGH,
                title=f"OpenAlex 标记为已撤稿: {title}",
                detail=(f"OpenAlex `is_retracted=true`,但本地 Retraction Watch 库未命中该 DOI。"
                        f"建议人工到期刊页 / Retraction Watch 复核。\nDOI: {_doi_url(nd)}"),
                confidence=0.8,
                metadata={"doi": nd, "url": _doi_url(nd), "year": year, "sources": ["openalex"]},
            ))

    # 2) RW 命中但不在(可能被截断的)语料里 —— 仍按强信号报出
    for nd, h in rw_by_doi.items():
        if nd in seen or nd in work_by_doi:
            continue
        seen.add(nd)
        title = (h.get(rw.COL_TITLE) or nd)[:160]
        findings.append(Finding(
            detector=DETECTOR, severity=Severity.CRITICAL,
            title=f"已撤稿(退稿库命中): {title}",
            detail=(f"Retraction Watch 收录该 DOI(未出现在本次抓取的作品列表里,可能因抓取上限)。\n"
                    f"原因: {(h.get(rw.COL_REASON) or '').strip(' ;') or '未注明'}\nDOI: {_doi_url(nd)}"),
            confidence=0.9,
            metadata={"doi": nd, "url": _rw_url(h, nd), "sources": ["retraction_watch"]},
        ))
    return findings


def _name_findings(rw_rows: list[dict], names: list[str], covered_dois: set[str]) -> list[Finding]:
    """RW 机构/作者名命中(弱)。排除已被 DOI 命中的论文,避免重复;有上限。"""
    seen_ids: set[str] = set()
    out: list[Finding] = []
    for name in names:
        for field in (rw.COL_INSTITUTION, rw.COL_AUTHOR):
            for row in rw.match_by_name(rw_rows, name, field):
                nd = rw.normalize_doi(row.get(rw.COL_OG_DOI))
                rid = row.get("Record ID") or row.get(rw.COL_TITLE) or nd or ""
                if rid in seen_ids or (nd and nd in covered_dois):
                    continue
                seen_ids.add(rid)
                title = (row.get(rw.COL_TITLE) or nd or "(无标题)")[:160]
                out.append(Finding(
                    detector=DETECTOR, severity=Severity.MEDIUM,
                    title=f"退稿库存在同名「{name}」记录: {title}",
                    detail=(f"Retraction Watch 的 {('机构' if field == rw.COL_INSTITUTION else '作者')}字段含 "
                            f"「{name}」,但其 DOI 未与本次语料对上。**可能是同名/同机构他人,需人工确认是否同一实体。**\n"
                            f"原因: {(row.get(rw.COL_REASON) or '').strip(' ;') or '未注明'}\nDOI: {_doi_url(nd)}"),
                    confidence=0.5,
                    metadata={"doi": nd, "url": _rw_url(row, nd), "match_field": field, "match_name": name},
                ))
                if len(out) >= _MAX_NAME_HITS:
                    out.append(Finding(
                        detector=DETECTOR, severity=Severity.INFO,
                        title=f"同名记录较多,仅展示前 {_MAX_NAME_HITS} 条",
                        detail="退稿库里同名机构/作者记录较多,建议带上 DOI / 机构 ROR 做更精确的核对。",
                        confidence=1.0))
                    return out
    return out


def _deepscan_findings(results: list[dict]) -> list[Finding]:
    """把 OA 深扫的 per-paper 结果转成 corpus 报告里的 finding(独立 detector,不影响撤稿判定)。"""
    scanned = len(results)
    errs = sum(1 for r in results if r.get("error"))
    issues = [r for r in results if r.get("risk_score")]
    summary = (f"🔬 OA 深扫: 分析了 {scanned} 篇 OA 论文,{len(issues)} 篇有疑点"
               + (f",{errs} 篇未取到 PDF" if errs else ""))
    out = [Finding(detector=DETECTOR_DEEP, severity=Severity.INFO, title=summary,
                   detail="对开放获取(OA)论文下载 PDF 后跑了单篇检测器(statcheck/grim/图像)。"
                          "**深扫疑点 ≠ 撤稿,均为'疑似',需人工复核原文。** 非 OA 论文未涉及。",
                   confidence=1.0)]
    for r in issues:
        rs = r["risk_score"]
        sev = Severity.HIGH if rs >= 15 else Severity.MEDIUM if rs >= 5 else Severity.LOW
        out.append(Finding(
            detector=DETECTOR_DEEP, severity=sev,
            title=f"OA 深扫疑点(risk {rs}): {r['title']}",
            detail=("; ".join(r["top"]) or "见单篇报告") + f"\nDOI: {_doi_url(r['doi'])}",
            confidence=0.7,
            metadata={"doi": r["doi"], "url": r["url"], "paper_risk": rs, "n_findings": r["n_findings"]}))
    return out


def scan_corpus(query: str | None = None, kind: str = "auto", *,
                rw_path: str | None = None, max_works: int = 500,
                mailto: str | None = None, proxy: str | None = None,
                dois: list[str] | None = None,
                deep: bool = False, max_pdfs: int = 5,
                oa_cache: str | None = None) -> Report:
    """机构/作者级体检。

    两种模式:
      - 实体模式: 传 query(机构名/作者名/OpenAlex ID),走 OpenAlex 拉作品 + RW 交叉核。
      - 离线 DOI 模式: 传 dois=[...](query 留空),只用本地 RW 库核对这些 DOI(不联网)。
    """
    rw_rows = rw.load(rw_path)
    findings: list[Finding] = []
    error: str | None = None
    subject = query or "DOI 清单"

    # ---- 离线 DOI 模式 ----
    if not query and dois:
        subject = f"DOI 清单 ({len(dois)} 条)"
        findings.append(Finding(
            detector=DETECTOR, severity=Severity.INFO, title="📋 离线核对",
            detail=f"仅用本地 Retraction Watch 库核对 {len(dois)} 个 DOI,未联网。", confidence=1.0))
        rw_hits = rw.match_by_dois(rw_rows, dois)
        for h in rw_hits:
            nd = h["_norm_doi"]
            findings.append(Finding(
                detector=DETECTOR, severity=Severity.CRITICAL,
                title=f"已撤稿: {(h.get(rw.COL_TITLE) or nd)[:160]}",
                detail=(f"Retraction Watch 收录。类型: {(h.get(rw.COL_NATURE) or 'Retraction').strip()} · "
                        f"期刊: {(h.get(rw.COL_JOURNAL) or '—').strip()}\n"
                        f"原因: {(h.get(rw.COL_REASON) or '').strip(' ;') or '未注明'}\nDOI: {_doi_url(nd)}"),
                confidence=0.95, metadata={"doi": nd, "url": _rw_url(h, nd), "sources": ["retraction_watch"]}))
        if not rw_hits:
            findings.append(_clean_bill(rw_rows))
        return _wrap(subject, findings, error)

    if not query:
        findings.append(Finding(detector=DETECTOR, severity=Severity.MEDIUM,
                                title="未提供查询对象", detail="请给机构名 / 作者名 / OpenAlex ID,或一份 DOI 清单。",
                                confidence=1.0))
        return _wrap(subject, findings, "no query")

    # ---- 实体模式 ----
    entity = None
    try:
        entity = openalex.resolve_entity(query, kind, mailto=mailto, proxy=proxy)
    except openalex.OpenAlexError as e:
        error = str(e)

    if error:
        findings.append(Finding(
            detector=DETECTOR, severity=Severity.MEDIUM, title="体检未完成: OpenAlex 不可达",
            detail=f"{error}\n(可设代理: --proxy http://127.0.0.1:7897,或导出 HTTPS_PROXY)。已退化为仅离线 RW 名字核对。",
            confidence=1.0))
        for f in _name_findings(rw_rows, [query, _clean_name(query)], set()):
            findings.append(f)
        if len(findings) == 1:
            findings.append(_clean_bill(rw_rows, name_only=True))
        return _wrap(subject, findings, error)

    if entity is None:
        findings.append(Finding(detector=DETECTOR, severity=Severity.HIGH,
                                title="未在 OpenAlex 找到该实体",
                                detail=f"「{query}」在 OpenAlex 机构/作者库里没匹配。换全称或直接给 OpenAlex ID 试试。",
                                confidence=0.9))
        return _wrap(subject, findings, error)

    subject = entity["display_name"]
    try:
        works, total = openalex.fetch_works(entity["id"], entity["kind"],
                                            max_works=max_works, mailto=mailto, proxy=proxy)
    except openalex.OpenAlexError as e:
        error = str(e)
        findings.append(Finding(detector=DETECTOR, severity=Severity.MEDIUM,
                                title="体检未完成: 拉取作品失败", detail=str(e), confidence=1.0))
        return _wrap(subject, findings, error)

    findings.append(_profile_finding(entity, works, total))
    ret = _retraction_findings(works, rw_rows)
    findings.extend(ret)

    covered = {f.metadata.get("doi") for f in ret if f.metadata.get("doi")}
    names = [entity["display_name"], _clean_name(entity["display_name"]), query]
    findings.extend(_name_findings(rw_rows, list(dict.fromkeys(n for n in names if n)), covered))

    has_retraction = any(f.severity in (Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM)
                         for f in findings if f.detector == DETECTOR and f.title != "体检未完成")
    if not has_retraction:
        findings.append(_clean_bill(rw_rows))

    if deep and works:
        deep_results = oa_fetch.deep_scan_works(works, max_pdfs=max_pdfs, proxy=proxy, cache_dir=oa_cache)
        findings.extend(_deepscan_findings(deep_results))

    return _wrap(subject, findings, error)


def _clean_bill(rw_rows: list[dict], name_only: bool = False) -> Finding:
    src = "本地 Retraction Watch 库" if name_only else "OpenAlex + 本地 Retraction Watch 库"
    note = "" if rw_rows else "(注意: 本地 RW 缓存为空,仅依据 OpenAlex)"
    return Finding(
        detector=DETECTOR, severity=Severity.INFO,
        title="✅ 公开撤稿库未发现该实体的撤稿记录",
        detail=f"在{src}中均未命中。**这只代表公开撤稿记录层面合格,不等于每篇论文都无问题。** {note}",
        confidence=1.0)


def _wrap(subject: str, findings: list[Finding], error: str | None) -> Report:
    result = DetectorResult(detector=DETECTOR, findings=findings, error=error)
    report = Report(kind="corpus", subject=subject, source=subject,
                    page_count=0, word_count=0, results=[result])
    report.compute_risk()
    return report
