"""Streamlit 论文体检 Web UI.

启动: streamlit run paperguard/web/app.py
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import streamlit as st

from paperguard.core.pipeline import analyze
from paperguard.core.types import Severity
from paperguard.report.render import to_html, to_markdown

st.set_page_config(page_title="PaperGuard 论文体检", page_icon="🛡️", layout="wide")

st.title("🛡️ PaperGuard · 论文体检")
st.caption(
    "给一份 PDF/TXT,自动扫描**统计自洽性、数字一致性、图片完整性**的潜在问题。"
    "灵感来自 PubPeer、Elisabeth Bik、耿同学讲故事。"
    "**定位**:辅助人工复核的疑点清单,不替代同行评审,不作为指控依据。"
)

with st.expander("⚠️ 使用前必读 · 免责声明", expanded=False):
    st.markdown(
        """
        1. 本工具输出 **"疑似"** 而非 **"定罪"**。命中即可疑,**不等于造假**;未命中也**不等于无问题**。
        2. 任何争议必须以**原始数据复核**为准。作者可能做了正当的舍入/简化/数据加工。
        3. **请勿将本工具的输出作为公开指控他人学术不端的依据**。如需举报,请走期刊、机构、PubPeer 等正规渠道。
        4. 上传他人论文请确认**不侵犯版权**。本服务**不存储**用户上传的 PDF,跑完即弃。
        5. 本工具按"现状"提供,不对检测结果的准确性、完整性作任何保证。**使用者自行承担一切责任**。
        """
    )

_SEV_COLOR = {
    Severity.INFO: "#6c757d",
    Severity.LOW: "#198754",
    Severity.MEDIUM: "#ffc107",
    Severity.HIGH: "#fd7e14",
    Severity.CRITICAL: "#dc3545",
}

with st.sidebar:
    st.header("使用方式")
    st.markdown(
        """
        1. **上传你自己的论文**: 投稿前体检,避免笔误
        2. **上传他人论文**: 学习 / 复核 / 同行评审辅助
        3. 报告会列出可疑点 + 置信度,**仅供参考,不作定论**
        """
    )
    st.divider()
    st.subheader("当前检测项")
    st.markdown(
        """
        - **statcheck** — t/F/χ²/r 与 p 值自洽
        - **grim** — 均值与样本量的整数自洽
        - **dup_numbers** — 段落间数字雷同
        - **image_dup** — 图片复用 (pHash + ORB,含翻转)
        - **wb_clone** — 单图内 copy-move(WB 条带完整性)
        """
    )
    st.divider()
    st.caption("v0.2 · 文本统计 + 图片层。 PubPeer 案例回测在路上 🚧")

uploaded = st.file_uploader("📄 上传论文(PDF / TXT)", type=["pdf", "txt", "md"])

if uploaded is None:
    st.info("请先上传一份论文文件。也可以先放点 .txt 看看效果。")
    st.stop()

with tempfile.NamedTemporaryFile(delete=False, suffix=Path(uploaded.name).suffix) as tmp:
    tmp.write(uploaded.getbuffer())
    tmp_path = tmp.name

with st.spinner("🔍 正在体检..."):
    report = analyze(tmp_path)

c1, c2, c3, c4 = st.columns(4)
c1.metric("📑 页数", report.page_count)
c2.metric("📝 词数", report.word_count)
c3.metric("⚠️ 风险分", report.risk_score)
c4.metric("🔎 命中数", len(report.findings))

if report.risk_score >= 15:
    st.error("⚠️ 重大风险 — 多处不一致,建议作者核对原始数据。")
elif report.risk_score >= 5:
    st.warning("🟠 中等风险 — 存在多处可疑点。")
elif report.risk_score > 0:
    st.info("🟡 轻度异常 — 多为可能的排版/舍入问题。")
else:
    st.success("✅ 未命中已知模式 — 不等于论文无问题。")

st.divider()

tab1, tab2, tab3 = st.tabs(["📋 命中明细", "📥 下载报告", "🧪 原始 JSON"])

with tab1:
    if not report.findings:
        st.markdown("### ✅ 没有命中,本工具未发现明显异常。")
    else:
        for f in report.findings:
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
                st.write(f.detail)
                if f.snippet:
                    st.code(f.snippet, language=None)
                # 图片证据
                meta = f.metadata or {}
                imgs = [(k, meta[k]) for k in ("thumb_a_b64", "thumb_b_b64", "annotated_b64") if meta.get(k)]
                if imgs:
                    cols = st.columns(len(imgs))
                    labels = {"thumb_a_b64": "图片 A", "thumb_b_b64": "图片 B", "annotated_b64": "克隆块标注"}
                    for col, (k, b64) in zip(cols, imgs):
                        import base64 as _b64
                        col.image(_b64.b64decode(b64), caption=labels[k])

with tab2:
    md_text = to_markdown(report)
    html_text = to_html(report)
    st.download_button("⬇️ 下载 Markdown 报告", md_text, file_name="paperguard.md")
    st.download_button("⬇️ 下载 HTML 报告", html_text, file_name="paperguard.html")
    st.download_button(
        "⬇️ 下载 JSON 原始结果",
        report.model_dump_json(indent=2),
        file_name="paperguard.json",
        mime="application/json",
    )

with tab3:
    st.json(report.model_dump())
