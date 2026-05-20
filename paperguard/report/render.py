"""报告渲染 — Markdown / HTML."""
from __future__ import annotations

from html import escape

from ..core.types import Finding, Report, Severity

_SEV_EMOJI = {
    Severity.INFO: "ℹ️",
    Severity.LOW: "🟢",
    Severity.MEDIUM: "🟡",
    Severity.HIGH: "🟠",
    Severity.CRITICAL: "🔴",
}

_SEV_COLOR = {
    Severity.INFO: "#6c757d",
    Severity.LOW: "#198754",
    Severity.MEDIUM: "#ffc107",
    Severity.HIGH: "#fd7e14",
    Severity.CRITICAL: "#dc3545",
}


def _verdict(score: float) -> tuple[str, str]:
    if score >= 15:
        return ("⚠️ 重大风险", "建议人工细致复核,并比对原始数据。")
    if score >= 5:
        return ("🟠 中等风险", "存在多处可疑,建议作者核对并提供原始数据。")
    if score > 0:
        return ("🟡 轻度异常", "发现少量值得复核的点,多数可能为排版/舍入。")
    return ("✅ 未发现明显异常", "本工具未发现可识别的不一致 — 不等于论文无问题。")


def to_markdown(report: Report) -> str:
    verdict, advice = _verdict(report.risk_score)
    lines = [
        "# PaperGuard 论文体检报告",
        "",
        f"- **来源**: `{report.source}`",
        f"- **规模**: {report.page_count} 页 / {report.word_count} 词",
        f"- **风险评分**: **{report.risk_score}**",
        f"- **结论**: {verdict} — {advice}",
        "",
        '> 本报告输出 "疑似",而非 "定论"。任何争议须以原始数据复核为准。',
        "",
        "---",
        "",
    ]

    if not report.findings:
        lines.append("✅ 没有命中已知造假模式。")
        return "\n".join(lines)

    # 按检测器分组
    by_det: dict[str, list[Finding]] = {}
    for f in report.findings:
        by_det.setdefault(f.detector, []).append(f)

    for det, items in by_det.items():
        lines.append(f"## 🔍 {det} — {len(items)} 处")
        lines.append("")
        for f in items:
            page = f"P{f.page}" if f.page else "—"
            lines.append(
                f"### {_SEV_EMOJI[f.severity]} [{f.severity.value.upper()}] {f.title}  *({page}, 置信度 {f.confidence:.0%})*"
            )
            lines.append("")
            lines.append(f.detail)
            if f.snippet:
                lines.append("")
                lines.append("```")
                lines.append(f.snippet)
                lines.append("```")
            lines.append("")
    return "\n".join(lines)


def to_html(report: Report) -> str:
    verdict, advice = _verdict(report.risk_score)
    cards: list[str] = []
    for f in report.findings:
        color = _SEV_COLOR[f.severity]
        page = f"P{f.page}" if f.page else "—"
        snippet_html = ""
        if f.snippet:
            snippet_html = (
                f'<pre class="snippet">{escape(f.snippet)}</pre>'
            )
        # 图片证据
        img_html = ""
        meta = f.metadata or {}
        thumbs: list[str] = []
        for key, label in [("thumb_a_b64", "图片 A"), ("thumb_b_b64", "图片 B"), ("annotated_b64", "标注克隆块")]:
            b64 = meta.get(key)
            if b64:
                thumbs.append(
                    f'<figure class="thumb"><img src="data:image/png;base64,{b64}" alt="{label}"/><figcaption>{label}</figcaption></figure>'
                )
        if thumbs:
            img_html = f'<div class="thumbs">{"".join(thumbs)}</div>'
        cards.append(
            f"""
            <div class="card" style="border-left:6px solid {color}">
              <div class="card-head">
                <span class="sev" style="background:{color}">{f.severity.value.upper()}</span>
                <span class="det">{escape(f.detector)}</span>
                <span class="page">{page}</span>
                <span class="conf">置信度 {f.confidence:.0%}</span>
              </div>
              <h3>{escape(f.title)}</h3>
              <p>{escape(f.detail)}</p>
              {snippet_html}
              {img_html}
            </div>
            """
        )

    body = "\n".join(cards) if cards else '<p class="empty">✅ 未发现明显异常。</p>'

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>PaperGuard 体检报告 — {escape(report.source)}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif; max-width: 960px; margin: 32px auto; padding: 0 16px; color: #1f2328; }}
  h1 {{ margin-bottom: 4px; }}
  .meta {{ color: #57606a; margin-bottom: 24px; }}
  .summary {{ background: #f6f8fa; border-radius: 8px; padding: 16px 20px; margin-bottom: 24px; }}
  .score {{ font-size: 32px; font-weight: 700; }}
  .card {{ background: white; border: 1px solid #d0d7de; border-radius: 8px; padding: 16px 20px; margin: 16px 0; box-shadow: 0 1px 2px rgba(0,0,0,0.04); }}
  .card-head {{ display: flex; gap: 8px; align-items: center; font-size: 12px; margin-bottom: 4px; }}
  .sev {{ color: white; padding: 2px 8px; border-radius: 4px; font-weight: 600; }}
  .det, .page, .conf {{ color: #57606a; }}
  .card h3 {{ margin: 8px 0; }}
  .snippet {{ background: #f6f8fa; padding: 10px 12px; border-radius: 6px; font-size: 13px; white-space: pre-wrap; word-break: break-word; }}
  .disclaimer {{ font-size: 12px; color: #57606a; margin-top: 32px; padding-top: 16px; border-top: 1px solid #d0d7de; }}
  .empty {{ text-align: center; padding: 32px; color: #198754; font-size: 18px; }}
  .thumbs {{ display: flex; gap: 12px; margin-top: 12px; flex-wrap: wrap; }}
  .thumb {{ margin: 0; text-align: center; }}
  .thumb img {{ max-width: 220px; max-height: 180px; border: 1px solid #d0d7de; border-radius: 6px; }}
  .thumb figcaption {{ font-size: 12px; color: #57606a; margin-top: 4px; }}
</style>
</head>
<body>
  <h1>🛡️ PaperGuard 论文体检报告</h1>
  <div class="meta">{escape(report.source)} — {report.page_count} 页 / {report.word_count} 词</div>
  <div class="summary">
    <div class="score">风险评分: {report.risk_score}</div>
    <div>{escape(verdict)} — {escape(advice)}</div>
  </div>
  {body}
  <div class="disclaimer">
    本报告输出"疑似",非"定论"。所有命中点都附置信度,代表算法判断而非事实定性。
    人工复核与原始数据为最终依据。 PaperGuard 是开源工具,欢迎贡献 PR。
  </div>
</body>
</html>"""
