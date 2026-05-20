"""回测 runner — 对 cases/seed/*.json 里所有案例跑 PaperGuard,聚合指标."""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

from paperguard.core.pipeline import analyze
from paperguard.core.types import Report
from .schema import Case, Verdict

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SEED_DIR = ROOT / "cases" / "seed"
REPORT_DIR = ROOT / "cases" / "reports"


@dataclass
class CaseResult:
    case: Case
    report: Report | None
    error: str | None = None
    expected_hit: list[str] = field(default_factory=list)  # 命中的期望检测器
    expected_miss: list[str] = field(default_factory=list)  # 漏掉的
    extra: list[str] = field(default_factory=list)  # 没期望但报了的 detector

    @property
    def is_tp(self) -> bool:
        if self.case.verdict == Verdict.CLEAN_CONTROL:
            return False
        return bool(self.expected_hit) or (self.report is not None and self.report.risk_score >= 5)

    @property
    def is_fp(self) -> bool:
        if self.case.verdict != Verdict.CLEAN_CONTROL:
            return False
        return self.report is not None and self.report.risk_score >= 5


def load_cases(seed_dir: Path = DEFAULT_SEED_DIR) -> list[Case]:
    cases: list[Case] = []
    for path in sorted(seed_dir.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        cases.append(Case(**data))
    return cases


def _evaluate_case(case: Case) -> CaseResult:
    if not case.input_path():
        return CaseResult(case=case, report=None, error="no input path")
    pdf = ROOT / case.input_path()
    if not pdf.exists():
        return CaseResult(case=case, report=None, error=f"file missing: {pdf}")
    try:
        report = analyze(str(pdf))
    except Exception as e:  # noqa: BLE001
        return CaseResult(case=case, report=None, error=str(e))

    hit_detectors = {f.detector for f in report.findings}
    expected = set(case.expected_detectors)
    return CaseResult(
        case=case,
        report=report,
        expected_hit=sorted(expected & hit_detectors),
        expected_miss=sorted(expected - hit_detectors),
        extra=sorted(hit_detectors - expected),
    )


def run(seed_dir: Path = DEFAULT_SEED_DIR) -> int:
    cases = load_cases(seed_dir)
    if not cases:
        print(f"⚠️  没有案例: {seed_dir}")
        print("请在 cases/seed/ 下新建 *.json (参考 cases/README.md)。")
        return 1
    results = [_evaluate_case(c) for c in cases]

    print(f"📊 共 {len(results)} 个案例\n")
    tp = sum(1 for r in results if r.is_tp)
    fp = sum(1 for r in results if r.is_fp)
    has_label_positive = sum(1 for r in results if r.case.verdict != Verdict.CLEAN_CONTROL and not r.error)
    has_label_neg = sum(1 for r in results if r.case.verdict == Verdict.CLEAN_CONTROL and not r.error)
    errors = sum(1 for r in results if r.error)

    fn = has_label_positive - tp
    tn = has_label_neg - fp

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

    print(f"  ✅ TP {tp}  ❌ FN {fn}  🟢 TN {tn}  🟠 FP {fp}  ⚠️ 错误 {errors}")
    print(f"  precision = {precision:.2%}   recall = {recall:.2%}   F1 = {f1:.2%}")
    print()

    for r in results:
        c = r.case
        if r.error:
            print(f"[ERR ] {c.id}: {r.error}")
            continue
        status = "TP" if r.is_tp else ("FP" if r.is_fp else ("TN" if c.verdict == Verdict.CLEAN_CONTROL else "FN"))
        score = r.report.risk_score
        print(
            f"[{status:3}] {c.id:30} verdict={c.verdict.value:14} risk={score:5.1f}"
            f"  hit={r.expected_hit or '—'}  miss={r.expected_miss or '—'}"
        )

    # 保存详细 JSON 报告
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORT_DIR / "benchmark.json"
    out.write_text(
        json.dumps(
            {
                "summary": {
                    "tp": tp, "fp": fp, "tn": tn, "fn": fn,
                    "precision": precision, "recall": recall, "f1": f1,
                    "errors": errors,
                },
                "cases": [
                    {
                        "id": r.case.id,
                        "verdict": r.case.verdict.value,
                        "risk_score": r.report.risk_score if r.report else None,
                        "expected": r.case.expected_detectors,
                        "hit": r.expected_hit,
                        "miss": r.expected_miss,
                        "extra": r.extra,
                        "error": r.error,
                    }
                    for r in results
                ],
            },
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\n📝 详细报告: {out.relative_to(ROOT)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="PaperGuard 回测")
    parser.add_argument("--seed", type=Path, default=DEFAULT_SEED_DIR, help="案例 JSON 目录")
    args = parser.parse_args()
    return run(args.seed)


if __name__ == "__main__":
    sys.exit(main())
