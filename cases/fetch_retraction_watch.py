"""从 Crossref Retraction Watch 数据集拉退稿元数据,生成案例骨架.

合规说明:
- Retraction Watch 数据由 Crossref 公开免费维护(2023-09 起)
- API: https://api.labs.crossref.org/data/retractionwatch?<your_email>
- 引用要求: "Retraction Watch Database, Crossref"
- 我们只下载元数据(DOI、Reason、Date),不下载论文 PDF

用法:
    python -m cases.fetch_retraction_watch --email you@example.com \
        --reason "Falsification" "Manipulation" --limit 50

会生成 cases/seed/rw_<doi-safe>.json,需要使用者自行通过合法渠道下载 PDF
放到 cases/pdfs/<id>.pdf 才能跑回测。
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
SEED_DIR = ROOT / "cases" / "seed"

CROSSREF_RW_URL = "https://api.labs.crossref.org/data/retractionwatch"

# CSV 大概的列名(以 Crossref 实际为准,我们做容错)
COL_OG_DOI = "OriginalPaperDOI"
COL_TITLE = "Title"
COL_JOURNAL = "Journal"
COL_DATE = "OriginalPaperDate"
COL_REASON = "Reason"


def _slugify(doi: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "_", doi).strip("_")
    return f"rw_{s[:80]}"


def _classify_reasons(reasons: str) -> list[str]:
    """根据 Retraction Watch 的 Reason 字段推断期望的 detector."""
    expected: list[str] = []
    low = reasons.lower()
    if any(k in low for k in ("image", "figure", "western blot", "wb", "blot", "manipulation of images")):
        expected.append("image_dup")
        expected.append("wb_clone")
    if any(k in low for k in ("statistics", "statistical", "p-value", "p value", "p-hacking")):
        expected.append("statcheck")
    if any(k in low for k in ("data fabrication", "duplicate", "duplication of data", "fabricated data")):
        expected.append("dup_numbers")
        expected.append("grim")
    if not expected:
        # 没法机器推断,标 unknown,跑回测时不当 ground truth
        expected = []
    return expected


def fetch_csv(email: str) -> str:
    import urllib.request

    url = f"{CROSSREF_RW_URL}?{email}"
    req = urllib.request.Request(url, headers={"User-Agent": f"PaperGuard/0.3 (mailto:{email})"})
    with urllib.request.urlopen(req, timeout=120) as resp:  # noqa: S310
        return resp.read().decode("utf-8", errors="replace")


def iter_rows(csv_text: str) -> Iterable[dict]:
    reader = csv.DictReader(io.StringIO(csv_text))
    for row in reader:
        yield row


def build_case(row: dict) -> dict | None:
    doi = (row.get(COL_OG_DOI) or "").strip()
    if not doi:
        return None
    reasons_raw = row.get(COL_REASON, "") or ""
    expected = _classify_reasons(reasons_raw)
    if not expected:
        return None  # 我们只要能机器评测的退稿原因
    case_id = _slugify(doi)
    title = (row.get(COL_TITLE) or "").strip() or doi
    journal = (row.get(COL_JOURNAL) or "").strip() or None
    year = None
    date = (row.get(COL_DATE) or "").strip()
    m = re.search(r"\b(19|20)\d{2}\b", date)
    if m:
        year = int(m.group())
    return {
        "id": case_id,
        "title": title[:200],
        "doi": doi,
        "year": year,
        "journal": journal,
        "verdict": "retracted",
        "sources": [
            {"type": "retraction_watch", "url": f"https://retractionwatch.com/?s={doi}"},
            {"type": "doi", "url": f"https://doi.org/{doi}"},
        ],
        "known_issues": [
            {"category": "rw_reason", "desc": reasons_raw[:500]}
        ],
        "expected_detectors": sorted(set(expected)),
        "pdf_path": f"cases/pdfs/{case_id}.pdf",
        "notes": "PDF 由使用者通过合法渠道(机构订阅 / 开放获取版本)获取后放到 pdf_path",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="从 Crossref Retraction Watch 生成案例骨架")
    parser.add_argument("--email", required=True, help="邮箱(Crossref polite pool)")
    parser.add_argument("--limit", type=int, default=20, help="最多生成多少案例")
    parser.add_argument("--keyword", nargs="*", default=[], help="只保留 Reason 包含该关键词的(可多个,任意一个匹配)")
    parser.add_argument("--out", type=Path, default=SEED_DIR, help="输出目录")
    parser.add_argument("--cache", type=Path, default=ROOT / "cases" / "rw_cache.csv", help="本地 CSV 缓存路径")
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    args.cache.parent.mkdir(parents=True, exist_ok=True)

    if args.cache.exists():
        print(f"📂 使用缓存: {args.cache}")
        csv_text = args.cache.read_text(encoding="utf-8")
    else:
        print(f"🌐 下载 Retraction Watch CSV (~80MB) ...")
        try:
            csv_text = fetch_csv(args.email)
        except Exception as e:  # noqa: BLE001
            print(f"❌ 下载失败: {e}", file=sys.stderr)
            return 1
        args.cache.write_text(csv_text, encoding="utf-8")
        print(f"✅ 已缓存到: {args.cache}")

    keywords = [k.lower() for k in args.keyword]
    written = 0
    for row in iter_rows(csv_text):
        if written >= args.limit:
            break
        if keywords:
            reason = (row.get(COL_REASON) or "").lower()
            if not any(k in reason for k in keywords):
                continue
        case = build_case(row)
        if case is None:
            continue
        out = args.out / f"{case['id']}.json"
        if out.exists():
            continue
        out.write_text(json.dumps(case, ensure_ascii=False, indent=2), encoding="utf-8")
        written += 1
    print(f"✅ 生成 {written} 个案例 → {args.out}")
    print("⚠️  下一步: 自行下载对应 PDF 放到 cases/pdfs/<id>.pdf,然后 python -m cases.benchmark")
    return 0


if __name__ == "__main__":
    sys.exit(main())
