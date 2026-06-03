"""命令行入口.

- `python -m paperguard check x.pdf`              单篇论文体检
- `python -m paperguard scan --institution Kingfa` 机构/作者级体检(OpenAlex + Retraction Watch)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .core.pipeline import analyze
from .report.render import to_markdown, to_html


def _cmd_check(args: argparse.Namespace) -> int:
    path = Path(args.path)
    if not path.exists():
        print(f"❌ 文件不存在: {path}", file=sys.stderr)
        return 2

    report = analyze(str(path))
    fmt = args.format

    if fmt == "json":
        print(report.model_dump_json(indent=2))
    elif fmt == "md":
        print(to_markdown(report))
    elif fmt == "html":
        out = Path(args.output) if args.output else path.with_suffix(".paperguard.html")
        out.write_text(to_html(report), encoding="utf-8")
        print(f"✅ 报告已保存: {out}")
    else:  # text 概览
        _print_summary(report)
    return 0 if report.risk_score < 5 else 1


def _print_summary(report) -> None:
    print(f"📄 来源: {report.source}")
    if getattr(report, "kind", "paper") == "corpus":
        print(f"🏛️  机构/作者体检: {report.subject or report.source}")
    else:
        print(f"📑 {report.page_count} 页 / {report.word_count} 词")
    print(f"⚠️  风险分: {report.risk_score}")
    print(f"🔎 命中: {len(report.findings)} 处")
    print()
    by_det: dict[str, int] = {}
    for f in report.findings:
        by_det[f.detector] = by_det.get(f.detector, 0) + 1
    for det, n in by_det.items():
        print(f"  · {det}: {n}")
    print()
    for f in report.findings[:20]:
        page = f"P{f.page}" if f.page else "—"
        print(f"[{f.severity.value.upper():8}] [{page}] {f.title}")
        print(f"           {f.detail}")
        if f.snippet:
            print(f"           «{f.snippet[:140]}»")
        print()


def _cmd_scan(args: argparse.Namespace) -> int:
    from .corpus import scan_corpus

    dois = None
    if args.doi_file:
        p = Path(args.doi_file)
        if not p.exists():
            print(f"❌ DOI 清单不存在: {p}", file=sys.stderr)
            return 2
        dois = [ln.strip() for ln in p.read_text(encoding="utf-8").splitlines()
                if ln.strip() and not ln.strip().startswith("#")]

    query = args.institution or args.author or args.openalex
    kind = "institution" if args.institution else "author" if args.author else "auto"
    if not query and not dois:
        print("❌ 需指定 --institution / --author / --openalex 之一,或 --doi-file", file=sys.stderr)
        return 2

    report = scan_corpus(query, kind, rw_path=args.rw_cache, max_works=args.max_works,
                         mailto=args.mailto, proxy=args.proxy, dois=dois,
                         deep=args.deep, max_pdfs=args.max_pdfs, oa_cache=args.oa_cache)
    fmt = args.format
    if fmt == "json":
        print(report.model_dump_json(indent=2))
    elif fmt == "md":
        if args.output:
            Path(args.output).write_text(to_markdown(report), encoding="utf-8")
            print(f"✅ 报告已保存: {args.output}")
        else:
            print(to_markdown(report))
    elif fmt == "html":
        out = Path(args.output) if args.output else Path("paperguard_corpus.html")
        out.write_text(to_html(report), encoding="utf-8")
        print(f"✅ 报告已保存: {out}")
    else:
        _print_summary(report)
    return 0 if report.risk_score < 5 else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="paperguard", description="开源论文稳健性体检 — 统计 / 数字 / 图片一致性扫描")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_check = sub.add_parser("check", help="对单篇论文执行体检")
    p_check.add_argument("path", help="PDF / TXT 文件路径")
    p_check.add_argument("-f", "--format", choices=["text", "json", "md", "html"], default="text")
    p_check.add_argument("-o", "--output", help="保存到文件(仅 html 需要)")

    p_scan = sub.add_parser("scan", help="机构/作者级体检(OpenAlex + Retraction Watch 撤稿核对)")
    g = p_scan.add_mutually_exclusive_group()
    g.add_argument("--institution", help="机构名,如 Kingfa")
    g.add_argument("--author", help="作者名")
    g.add_argument("--openalex", help="OpenAlex 实体 ID(I… 机构 / A… 作者)")
    p_scan.add_argument("--doi-file", help="离线模式: 一行一个 DOI 的文件,只用本地 RW 库核对(不联网)")
    p_scan.add_argument("--max-works", type=int, default=500, help="最多拉取多少篇作品(默认 500)")
    p_scan.add_argument("--mailto", help="OpenAlex 礼貌池邮箱(或设环境变量 OPENALEX_MAILTO)")
    p_scan.add_argument("--proxy", help="HTTP(S) 代理,如 http://127.0.0.1:7897")
    p_scan.add_argument("--rw-cache", help="Retraction Watch CSV 路径(默认 cases/rw_cache.csv)")
    p_scan.add_argument("--deep", action="store_true", help="深扫: 下载开放获取(OA)论文 PDF 逐篇跑检测器(慢)")
    p_scan.add_argument("--max-pdfs", type=int, default=5, help="深扫最多下载多少篇 OA 论文(默认 5)")
    p_scan.add_argument("--oa-cache", help="OA PDF 缓存目录(默认系统临时目录,跑完即弃)")
    p_scan.add_argument("-f", "--format", choices=["text", "json", "md", "html"], default="text")
    p_scan.add_argument("-o", "--output", help="保存到文件(md / html)")

    args = parser.parse_args(argv)
    if args.cmd == "check":
        return _cmd_check(args)
    if args.cmd == "scan":
        return _cmd_scan(args)
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
