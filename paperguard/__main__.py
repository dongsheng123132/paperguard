"""命令行入口 — `python -m paperguard check x.pdf`."""
from __future__ import annotations

import argparse
import json
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="paperguard", description="开源论文造假体检")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_check = sub.add_parser("check", help="对论文执行体检")
    p_check.add_argument("path", help="PDF / TXT 文件路径")
    p_check.add_argument("-f", "--format", choices=["text", "json", "md", "html"], default="text")
    p_check.add_argument("-o", "--output", help="保存到文件(仅 html 需要)")
    args = parser.parse_args(argv)
    if args.cmd == "check":
        return _cmd_check(args)
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
