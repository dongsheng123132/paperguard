"""corpus scan 单元测试 —— 不打真实网络(OpenAlex 全部 monkeypatch)。"""
from __future__ import annotations

import csv
from pathlib import Path

from paperguard.corpus import scan as scanmod
from paperguard.corpus.scan import scan_corpus
from paperguard.corpus.retraction_watch import match_by_dois, match_by_name, normalize_doi

_RW_HEADER = ["Record ID", "Title", "Institution", "Author", "Journal",
              "OriginalPaperDOI", "RetractionDate", "Reason", "RetractionNature", "URLS"]


def _write_rw_csv(tmp_path: Path) -> Path:
    """造一个 2 行的退稿库 fixture(列名与真实 rw_cache.csv 一致)。"""
    rows = [
        ["1", "Fake Retracted Study", "Test University; Other Lab", "Smith, John",
         "Journal of Tests", "10.1234/retracted.1", "2023-01-01",
         "+Falsification of Data", "Retraction", "https://retractionwatch.com/x"],
        ["2", "Another Retraction", "Big Institute", "Doe, Jane", "Mat. Lett.",
         "10.5678/retracted.2", "2022-06-01", "+Image Manipulation", "Retraction", ""],
    ]
    p = tmp_path / "rw.csv"
    with p.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(_RW_HEADER)
        w.writerows(rows)
    return p


# ───────────── retraction_watch 工具函数 ─────────────

def test_normalize_doi():
    assert normalize_doi("https://doi.org/10.1/AbC") == "10.1/abc"
    assert normalize_doi("DOI:10.2/x") == "10.2/x"
    assert normalize_doi("  10.3/Y/ ") == "10.3/y"
    assert normalize_doi("unavailable") is None
    assert normalize_doi("") is None
    assert normalize_doi(None) is None


def test_match_by_dois_hit_and_miss():
    rows = [{"OriginalPaperDOI": "https://doi.org/10.1/a", "Title": "A"},
            {"OriginalPaperDOI": "10.2/b", "Title": "B"}]
    hits = match_by_dois(rows, ["10.1/A"])  # 大小写 + 前缀都要被归一
    assert len(hits) == 1 and hits[0]["_norm_doi"] == "10.1/a"
    assert match_by_dois(rows, ["10.9/none"]) == []     # 负样本
    assert match_by_dois(rows, []) == []


def test_match_by_name():
    rows = [{"Institution": "Test University; X", "OriginalPaperDOI": "10.1/a"}]
    assert match_by_name(rows, "test university")       # 忽略大小写、子串
    assert match_by_name(rows, "ab") == []              # 太短(<4)不匹配,防误命中


# ───────────── 离线 DOI 模式 ─────────────

def test_offline_doi_hit(tmp_path):
    csv_path = _write_rw_csv(tmp_path)
    rep = scan_corpus(dois=["10.1234/retracted.1", "https://doi.org/10.5678/retracted.2", "10.0/clean"],
                      rw_path=str(csv_path))
    crit = [f for f in rep.findings if f.severity.value == "critical"]
    assert len(crit) == 2, "两个在库 DOI 应各触发一条 CRITICAL"
    assert rep.kind == "corpus" and rep.risk_score > 0


def test_offline_doi_clean(tmp_path):
    csv_path = _write_rw_csv(tmp_path)
    rep = scan_corpus(dois=["10.999/definitely-not-in-db"], rw_path=str(csv_path))
    assert rep.risk_score == 0
    assert any("公开撤稿库未发现" in f.title for f in rep.findings)


# ───────────── 实体模式(monkeypatch OpenAlex)─────────────

def _patch_openalex(monkeypatch, entity, works, total=None):
    monkeypatch.setattr(scanmod.openalex, "resolve_entity",
                        lambda q, k, **kw: entity)
    monkeypatch.setattr(scanmod.openalex, "fetch_works",
                        lambda eid, k, **kw: (works, total if total is not None else len(works)))


def test_scan_entity_positive(monkeypatch, tmp_path):
    csv_path = _write_rw_csv(tmp_path)
    entity = {"id": "I999", "kind": "institution", "display_name": "Test University",
              "works_count": 3, "cited_by_count": 50}
    works = [
        # 命中退稿库 DOI -> CRITICAL
        {"id": "W1", "doi": "https://doi.org/10.1234/retracted.1", "title": "Fake Retracted Study",
         "publication_year": 2022, "is_retracted": False, "open_access": {"is_oa": True}},
        # OpenAlex 标记但不在退稿库 -> HIGH
        {"id": "W2", "doi": "https://doi.org/10.9999/oa.flag", "title": "OA-flagged only",
         "publication_year": 2021, "is_retracted": True, "open_access": {"is_oa": False}},
        # 干净
        {"id": "W3", "doi": "https://doi.org/10.0000/clean", "title": "Clean paper",
         "publication_year": 2020, "is_retracted": False, "open_access": {}},
    ]
    _patch_openalex(monkeypatch, entity, works)
    rep = scan_corpus("Test University", "institution", rw_path=str(csv_path))
    sevs = {f.severity.value for f in rep.findings}
    assert "critical" in sevs, "退稿库 DOI 命中应 CRITICAL"
    assert "high" in sevs, "OpenAlex is_retracted 但库里没有应 HIGH"
    assert rep.risk_score > 0 and rep.subject == "Test University"


def test_scan_entity_clean(monkeypatch, tmp_path):
    csv_path = _write_rw_csv(tmp_path)
    entity = {"id": "I777", "kind": "institution", "display_name": "Spotless Inc",
              "works_count": 1, "cited_by_count": 9}
    works = [{"id": "W", "doi": "https://doi.org/10.111/clean", "title": "Clean",
              "publication_year": 2020, "is_retracted": False, "open_access": {}}]
    _patch_openalex(monkeypatch, entity, works)
    rep = scan_corpus("Spotless Inc", "institution", rw_path=str(csv_path))
    assert rep.risk_score == 0, "干净机构 risk 必须为 0"
    assert all(f.severity.value == "info" for f in rep.findings), "应全是 INFO(画像 + 合格)"
    assert any("公开撤稿库未发现" in f.title for f in rep.findings)


def test_scan_entity_not_found(monkeypatch):
    monkeypatch.setattr(scanmod.openalex, "resolve_entity", lambda q, k, **kw: None)
    rep = scan_corpus("Nonexistent Xyz Org", "institution", rw_path="/nonexistent.csv")
    assert any("未在 OpenAlex 找到" in f.title for f in rep.findings)


# ───────────── Phase B: OA 深扫 ─────────────

def test_oa_pdf_url():
    from paperguard.corpus import oa_fetch
    assert oa_fetch.oa_pdf_url(
        {"open_access": {"is_oa": True}, "best_oa_location": {"pdf_url": "http://x/a.pdf"}}) == "http://x/a.pdf"
    assert oa_fetch.oa_pdf_url(
        {"open_access": {"is_oa": True, "oa_url": "http://y/b"}, "best_oa_location": None}) == "http://y/b"
    assert oa_fetch.oa_pdf_url(
        {"open_access": {"is_oa": False}, "best_oa_location": {"pdf_url": "http://z"}}) is None  # 非 OA


def test_deep_scan_summary(monkeypatch, tmp_path):
    """深扫接入: monkeypatch 掉真实下载/分析,只验证 per-paper 结果 -> finding 的汇总逻辑。"""
    csv_path = _write_rw_csv(tmp_path)
    entity = {"id": "I1", "kind": "institution", "display_name": "Clean Org",
              "works_count": 2, "cited_by_count": 5}
    works = [{"id": "W1", "doi": "https://doi.org/10.1/oa", "title": "An OA paper",
              "publication_year": 2023, "is_retracted": False,
              "open_access": {"is_oa": True}, "best_oa_location": {"pdf_url": "http://x/a.pdf"}}]
    _patch_openalex(monkeypatch, entity, works)
    # 假装深扫: 一篇高风险 + 一篇干净
    fake = [
        {"title": "An OA paper", "doi": "10.1/oa", "year": 2023, "url": "http://x/a.pdf",
         "risk_score": 20.0, "n_findings": 3, "top": ["[critical] x", "[high] y"], "error": None},
        {"title": "Clean OA", "doi": "10.2/oa", "year": 2022, "url": "http://x/b.pdf",
         "risk_score": 0.0, "n_findings": 0, "top": [], "error": None},
    ]
    monkeypatch.setattr(scanmod.oa_fetch, "deep_scan_works", lambda works, **kw: fake)

    rep = scan_corpus("Clean Org", "institution", rw_path=str(csv_path), deep=True, max_pdfs=5)
    deep = [f for f in rep.findings if f.detector == "corpus_deepscan"]
    assert any("OA 深扫" in f.title for f in deep), "应有深扫汇总 finding"
    assert any(f.severity.value == "high" for f in deep), "risk=20 的论文应 HIGH"
    # 撤稿层仍应判为"合格"(深扫疑点不影响撤稿 clean-bill)
    assert any("公开撤稿库未发现" in f.title for f in rep.findings if f.detector == "corpus_retraction")


def test_deep_scan_does_not_break_clean_verdict(monkeypatch, tmp_path):
    """深扫全干净时,不应新增任何 LOW+ 疑点,corpus 结论仍为合格。"""
    csv_path = _write_rw_csv(tmp_path)
    entity = {"id": "I2", "kind": "institution", "display_name": "Spotless",
              "works_count": 1, "cited_by_count": 1}
    works = [{"id": "W", "doi": "https://doi.org/10.9/oa", "title": "OK",
              "publication_year": 2021, "is_retracted": False,
              "open_access": {"is_oa": True}, "best_oa_location": {"pdf_url": "http://x/c.pdf"}}]
    _patch_openalex(monkeypatch, entity, works)
    monkeypatch.setattr(scanmod.oa_fetch, "deep_scan_works",
                        lambda works, **kw: [{"title": "OK", "doi": "10.9/oa", "year": 2021,
                                              "url": "http://x/c.pdf", "risk_score": 0.0,
                                              "n_findings": 0, "top": [], "error": None}])
    rep = scan_corpus("Spotless", "institution", rw_path=str(csv_path), deep=True)
    deep_issue = [f for f in rep.findings
                  if f.detector == "corpus_deepscan" and f.severity.value != "info"]
    assert not deep_issue, "全干净深扫不应产生疑点 finding"
    assert rep.risk_score == 0.0
