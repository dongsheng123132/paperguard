# PaperGuard 架构说明 (给接手者)

> 写给下一个接手代码的人(Codex / Claude / 你自己)。
> 看完这份就能上手改任何模块。

## 顶层数据流

```
PDF/TXT
   │
   ▼
core/pdf.py        Document(pages=[PageText(page, text)])
   │
   ▼
core/pipeline.py   analyze(path)  -> 串起所有 detector
   │
   ├─ detectors/statcheck.py     # 文本: t/F/χ²/r vs p
   ├─ detectors/grim.py          # 文本: 均值 vs N 整数自洽
   ├─ detectors/dup_numbers.py   # 文本: 数字雷同(段内+跨段)
   ├─ detectors/image_dup.py     # 图像: pHash + ORB 同图复用(含翻转)
   └─ detectors/wb_clone.py      # 图像: 32x32 分块自相关 copy-move
   │
   ▼
core/types.py      Report(findings=[Finding(...)], risk_score)
   │
   ▼
report/render.py   Markdown / HTML(含图片缩略图 base64)
web/app.py         Streamlit UI
__main__.py        CLI
```

## 每个 Detector 的契约

所有检测器都是这个签名:

- 文本类: `def run(doc: Document) -> DetectorResult`
- 图像类: `def run_from_pdf(path: str) -> DetectorResult`

返回 `DetectorResult(detector=str, findings=[Finding], error=str|None, skipped=bool)`。

Pipeline 不关心检测器内部,只看 `findings`。要加新检测器:
1. 在 `paperguard/detectors/` 新建一个 `.py`
2. 实现 `run(doc)` 或 `run_from_pdf(path)`
3. 在 `core/pipeline.py` 的 `_TEXT_DETECTORS` / `_PDF_IMAGE_DETECTORS` 注册
4. 在 `paperguard/tests/` 写至少一个 positive + 一个 negative 测试

## 风险评分

`core/types.py::Report.compute_risk` —— 权重表:

```
INFO=0  LOW=1  MEDIUM=3  HIGH=6  CRITICAL=10
risk = Σ (weight × confidence)
```

> 5 显示中等风险; ≥15 重大风险。CLI 退出码: ≥5 退出 1(CI 友好)。

## 测试

- `paperguard/tests/` — 单元测试 15 个,`python -m pytest paperguard/tests/ -q`
- `samples/demo_fraud.txt` — 含已知错误的合成文本(5 处统计反转 + 2 GRIM + 1 数字雷同)
- `samples/demo_fraud.pdf` — `samples/make_fraud_pdf.py` 现场生成的合成 PDF(翻转复用 + copy-move)
- `samples/demo_clean.txt` / `demo_dense_clean.txt` / `demo_edge_cases.txt` — 应该 0 命中,验证不误报

## 回测系统

`cases/` 目录是回测专用:

- `cases/schema.py` — `Case` JSON 模型
- `cases/seed/*.json` — 案例库,版本受控
- `cases/pdfs/<id>.pdf` — 真实论文 PDF,**不进 git**(版权)
- `cases/fetch_retraction_watch.py` — 从 Crossref 拉退稿元数据,自动生成案例骨架
- `cases/benchmark.py` — 跑全部案例,输出 P/R/F1 → `cases/reports/benchmark.json`

Retraction Watch CSV 由 Crossref 公开免费提供(无 ToS 限制),所以 `fetch_retraction_watch.py`
只要邮箱就能跑。但是**对应的论文 PDF 必须使用者自行通过合法渠道获取**。

## 关键设计取舍

1. **不上传/不存储用户论文** — Streamlit 用 tempfile,跑完即弃
2. **所有 finding 必带 confidence** — 不下定论,只标"疑似"
3. **图像检测分两级** — pHash 快筛 + ORB 几何复核,降低 false positive
4. **wb_clone 阈值偏严** — 必须 ≥2 对克隆块才报(单独一对可能是巧合)
5. **GRIM 默认 confidence=0.55** — 因为变量是否为整数计数无法自动判断

## 已知短板 / 下一步

- v0.4: 图表数值反向提取(柱状图/曲线图反算数据点,做相关性异常)
- v0.5: 引文/作者关联分析(检测论文工厂)
- 真实退稿论文 PDF 没下到 → 真实场景下的 recall 数据待补
- 没有发布到 PyPI,目前只能源码运行
- Streamlit 的 base64 图片在长报告里会撑大页面,可以考虑切到 `st.image(file)`

## 给接手者的快速验证

```bash
pip install -r requirements.txt
python -m pytest paperguard/tests/ -q                # 必须 15/15 过
python -m paperguard check samples/demo_fraud.pdf    # 必须报 image_dup + wb_clone
python -m cases.benchmark                            # 合成样本应 P=R=100%
streamlit run paperguard/web/app.py                  # 浏览器 demo
```
