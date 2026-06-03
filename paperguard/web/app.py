"""Streamlit 论文体检 Web UI.

启动: streamlit run paperguard/web/app.py

两种模式:
- 📄 单篇 PDF / TXT 体检 —— 统计自洽 / 数字一致 / 图片完整性
- 🏛️ 机构 / 作者级体检 —— OpenAlex + Retraction Watch 撤稿核对
"""
from __future__ import annotations

import base64
import tempfile
from pathlib import Path

import streamlit as st

from paperguard.core.pipeline import analyze
from paperguard.core.types import Report, Severity
from paperguard.corpus import scan_corpus
from paperguard.report.render import to_html, to_markdown, _report_verdict

st.set_page_config(page_title="PaperGuard 论文体检", page_icon="🛡️", layout="wide")

st.title("🛡️ PaperGuard · 论文体检")
st.caption(
    "单篇论文扫**统计自洽 / 数字一致 / 图片完整性**;机构/作者查**公开撤稿记录**。"
    "灵感来自 PubPeer、Elisabeth Bik、耿同学讲故事。"
    "**定位**:辅助人工复核的疑点清单,不替代同行评审,不作为指控依据。"
)

with st.expander("⚠️ 使用前必读 · 免责声明", expanded=False):
    st.markdown(
        """
        1. 本工具输出 **"疑似 / 记录"** 而非 **"定罪"**。命中即可疑,**不等于造假**;未命中也**不等于无问题**。
        2. 任何争议必须以**原始数据复核**为准。作者可能做了正当的舍入/简化/数据加工。
        3. **请勿将本工具的输出作为公开指控他人学术不端的依据**。如需举报,请走期刊、机构、PubPeer 等正规渠道。
        4. 上传他人论文请确认**不侵犯版权**。本服务**不存储**用户上传的 PDF,跑完即弃。
        5. 机构/作者体检仅核对**公开撤稿数据库**(OpenAlex + Retraction Watch),"合格"只代表公开记录层面无撤稿。
        6. 本工具按"现状"提供,不对检测结果的准确性、完整性作任何保证。**使用者自行承担一切责任**。
        """
    )

_SEV_COLOR = {
    Severity.INFO: "#6c757d",
    Severity.LOW: "#198754",
    Severity.MEDIUM: "#ffc107",
    Severity.HIGH: "#fd7e14",
    Severity.CRITICAL: "#dc3545",
}


def _render_findings(findings) -> None:
    if not findings:
        st.markdown("### ✅ 没有命中,本工具未发现明显异常。")
        return
    for f in findings:
        color = _SEV_COLOR[f.severity]
        page = f"P{f.page}" if f.page else "—"
        with st.container(border=True):
            st.markdown(
                f"<span style='background:{color};color:white;padding:2px 8px;border-radius:4px;font-size:12px;font-weight:600'>"
                f"{f.severity.value.upper()}</span> &nbsp; "
                f"<span style='color:#57606a;font-size:12px'>{f.detector} · {page} · 置信度 {f.confidence:.0%}</span>",
                unsafe_allow_html=True,
            )
            st.markdown(f"#### {f.title}")
            # 保留 detail 里的换行
            st.markdown(f.detail.replace("\n", "  \n"))
            if f.snippet:
                st.code(f.snippet, language=None)
            meta = f.metadata or {}
            if meta.get("url"):
                st.markdown(f"🔗 [{meta['url']}]({meta['url']})")
            imgs = [(k, meta[k]) for k in ("thumb_a_b64", "thumb_b_b64", "annotated_b64") if meta.get(k)]
            if imgs:
                cols = st.columns(len(imgs))
                labels = {"thumb_a_b64": "图片 A", "thumb_b_b64": "图片 B", "annotated_b64": "克隆块标注"}
                for col, (k, b64) in zip(cols, imgs):
                    col.image(base64.b64decode(b64), caption=labels[k])


def _render_report(report: Report) -> None:
    c1, c2, c3, c4 = st.columns(4)
    if report.kind == "corpus":
        profile = next((f for f in report.findings if f.title.startswith("📊")), None)
        total = profile.metadata.get("works_total", "—") if profile else "—"
        retr = sum(1 for f in report.findings
                   if f.detector == "corpus_retraction" and f.severity in (Severity.CRITICAL, Severity.HIGH))
        c1.metric("📚 作品数", total)
        c2.metric("🚩 撤稿/标记", retr)
    else:
        c1.metric("📑 页数", report.page_count)
        c2.metric("📝 词数", report.word_count)
    c3.metric("⚠️ 风险分", report.risk_score)
    c4.metric("🔎 命中数", len(report.findings))

    verdict, advice = _report_verdict(report)
    sevs = {f.severity for f in report.findings}
    if Severity.CRITICAL in sevs or report.risk_score >= 15:
        st.error(f"{verdict} — {advice}")
    elif Severity.HIGH in sevs or Severity.MEDIUM in sevs or report.risk_score >= 5:
        st.warning(f"{verdict} — {advice}")
    elif report.risk_score > 0:
        st.info(f"{verdict} — {advice}")
    else:
        st.success(f"{verdict} — {advice}")

    st.divider()
    tab1, tab2, tab3 = st.tabs(["📋 命中明细", "📥 下载报告", "🧪 原始 JSON"])
    with tab1:
        _render_findings(report.findings)
    with tab2:
        st.download_button("⬇️ 下载 Markdown 报告", to_markdown(report), file_name="paperguard.md")
        st.download_button("⬇️ 下载 HTML 报告", to_html(report), file_name="paperguard.html")
        st.download_button(
            "⬇️ 下载 JSON 原始结果",
            report.model_dump_json(indent=2),
            file_name="paperguard.json",
            mime="application/json",
        )
    with tab3:
        st.json(report.model_dump())


with st.sidebar:
    st.header("使用方式")
    st.markdown(
        """
        - **单篇体检**: 投稿前自检笔误,或复核他人论文
        - **机构/作者体检**: 一键查某机构/作者名下有没有撤稿论文
        - 报告列出可疑点 + 置信度,**仅供参考,不作定论**
        """
    )
    st.divider()
    st.subheader("单篇检测项")
    st.markdown(
        """
        - **statcheck** — t/F/χ²/r 与 p 值自洽
        - **grim** — 均值与样本量的整数自洽
        - **dup_numbers** — 段落间数字雷同
        - **image_dup** — 图片复用 (pHash + ORB,含翻转)
        - **wb_clone** — 单图内 copy-move(WB 条带完整性)
        """
    )
    st.subheader("机构/作者检测项")
    st.markdown(
        """
        - **corpus_retraction** — OpenAlex `is_retracted` + Retraction Watch 撤稿库交叉核对
        """
    )
    st.divider()
    st.caption("v0.4 · 文本统计 + 图片层 + 机构/作者撤稿核对 🛡️")

mode = st.radio("体检对象", ["📄 单篇 PDF / TXT", "🏛️ 机构 / 作者"], horizontal=True)

# ───────────────────────── 单篇 PDF / TXT ─────────────────────────
if mode.startswith("📄"):
    uploaded = st.file_uploader("📄 上传论文(PDF / TXT)", type=["pdf", "txt", "md"])
    if uploaded is None:
        st.info("请先上传一份论文文件。也可以先放点 .txt 看看效果。")
        st.stop()

    with tempfile.NamedTemporaryFile(delete=False, suffix=Path(uploaded.name).suffix) as tmp:
        tmp.write(uploaded.getbuffer())
        tmp_path = tmp.name

    with st.spinner("🔍 正在体检..."):
        report = analyze(tmp_path)
    _render_report(report)

# ───────────────────────── 机构 / 作者 ─────────────────────────
else:
    col_a, col_b = st.columns([3, 1])
    query = col_a.text_input("机构名 / 作者名 / OpenAlex ID", placeholder="如 Kingfa(金发科技)")
    kind_label = col_b.selectbox("类型", ["自动", "机构", "作者"])
    with st.expander("⚙️ 高级选项"):
        mailto = st.text_input("OpenAlex 邮箱(礼貌池,可选)", value="")
        proxy = st.text_input("HTTP(S) 代理(可选)", placeholder="http://127.0.0.1:7897")
        max_works = st.slider("最多拉取作品数", 50, 1000, 300, 50)
        deep = st.checkbox("🔬 深扫 OA 论文(下载 PDF 逐篇查统计/图像,慢)")
        max_pdfs = st.slider("深扫篇数上限", 1, 20, 5) if deep else 5

    go = st.button("🔍 开始机构 / 作者体检", type="primary", disabled=not query.strip())
    if not go:
        st.info("输入机构名 / 作者名 / OpenAlex ID,点上方按钮开始。示例:Kingfa。")
        st.stop()

    kind = {"自动": "auto", "机构": "institution", "作者": "author"}[kind_label]
    spin = "🔬 正在查 OpenAlex + 撤稿库,并下载 OA 论文深扫(较慢)..." if deep else "🌐 正在查 OpenAlex + 撤稿库..."
    with st.spinner(spin):
        try:
            report = scan_corpus(query.strip(), kind, mailto=mailto or None,
                                 proxy=proxy or None, max_works=int(max_works),
                                 deep=deep, max_pdfs=int(max_pdfs))
        except Exception as e:  # noqa: BLE001
            st.error(f"体检失败: {e}")
            st.stop()
    _render_report(report)
