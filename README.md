---
title: PaperGuard 论文体检
emoji: 🛡️
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
license: mit
short_description: 开源论文体检 — 统计自洽 / 数字一致 / 图片完整性的疑点扫描
---

# PaperGuard 论文体检 · 开源学术稳健性自检工具

> 给一份 PDF/TXT,自动扫描**统计自洽性、数字一致性、图片完整性**的潜在问题。
>
> 灵感来自 PubPeer、Elisabeth Bik、"耿同学讲故事"的工作方法。
>
> **定位**: 辅助人工复核的疑点清单,**不替代同行评审,不作为指控依据**。所有报告附置信度,仅供参考。

## ⚠️ 重要免责声明

1. 本工具输出 **"疑似"** 而非 **"定罪"**。命中即可疑,**不等于造假**;未命中也**不等于无问题**。
2. 任何争议必须以**原始数据复核**为准。作者可能在论文里做了正当的舍入/简化/数据加工。
3. **请勿将本工具的输出作为公开指控他人学术不端的依据**。如需举报,请走期刊、机构、PubPeer 等正规渠道。
4. 上传他人论文请确认**不侵犯版权**。本服务**不存储**用户上传的 PDF,跑完即弃。
5. 本工具按"现状"提供,不对检测结果的准确性、完整性作任何保证。使用者自行承担一切责任。

## 现阶段能做什么(v0.3)

**文本统计层**
- ✅ **StatCheck**: t/F/χ²/r 与 p 值自洽,标决策反转
- ✅ **GRIM Test**: 均值 vs 样本量整数自洽
- ✅ **dup_numbers**: 段内 + 跨段数字雷同(完全相同序列、Jaccard)

**图像层**
- ✅ **image_dup**: pHash + ORB 二级验证,含水平/垂直翻转/180° 旋转复用
- ✅ **wb_clone**: 32×32 分块自相关,捕获 WB 条带 copy-move

**通用**
- ✅ CLI / Markdown / HTML / JSON 多格式报告(带图片缩略图和克隆块标注)
- ✅ Streamlit Web UI

## 路线图

- v0.1 — 文本统计校验 ✅
- v0.2 — 图片同图复用 / WB copy-move ✅
- v0.3 — Retraction Watch 数据集 + 回测框架 ✅
- v0.4 — 图表数值反向提取(WebPlotDigitizer 思路) + 相关性异常
- v0.5 — 引文/作者关联(论文工厂识别)

## 回测(v0.3)

```bash
# 1. 从 Crossref Retraction Watch 拉退稿元数据(自动分类期望检测器)
python -m cases.fetch_retraction_watch --email you@example.com \
  --keyword "Manipulation of Images" "Falsification" --limit 50

# 2. 把对应 PDF 通过合法渠道下到 cases/pdfs/<id>.pdf

# 3. 运行回测,输出 precision/recall/F1
python -m cases.benchmark
```

当前指标:

| 子集 | 案例数 | precision | recall | F1 |
|---|---|---|---|---|
| 合成样本(假 vs 干净) | 5 | 100% | 100% | 100% |
| 真实 Frontiers(4 退稿 + 2 控制组) | 6 | 100% | 75% | 86% |
| **合计** | 11 (+5 PDF 待补) | **100%** | **83%** | **91%** |

> **真实数据 0 个 false positive**(对照组 risk 均压到 0),但代价是 1 个 false negative
> (rw_70593 真退稿但图像层被"白底矢量图"过滤跳过,risk=0)。
> 这反映了 wb_clone/dup_numbers 在保守与激进之间的取舍 —
> **当前默认偏保守(宁可漏报不要误报)**,真实使用建议同时人工浏览图像。

样本报告参见 [`cases/reports/frontiers_batch/`](cases/reports/frontiers_batch/)。

## 本地运行

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 命令行体检
python -m paperguard check samples/demo_fraud.pdf

# 3. Web 体检
streamlit run paperguard/web/app.py
```

## 项目结构

```
paperguard/
  core/         # PDF 文本抽取、数字清洗、共用类型
  detectors/    # 各类检测器 (statcheck / grim / dup_numbers / ...)
  report/       # JSON / Markdown / HTML 报告渲染
  web/          # Streamlit 上传界面
  tests/        # pytest 用例
cases/          # 真实退稿论文回测框架
samples/        # 论文样本(测试用)
```

## 在线体验

- 🤗 Hugging Face Spaces: <https://huggingface.co/spaces/hefs/paperguard>
- 📦 GitHub: <https://github.com/dongsheng123132/paperguard>

## Contributing

欢迎 PR 和 issue。开始之前请:

1. `pip install -r requirements.txt && pip install pytest`
2. `python -m pytest paperguard/tests/ -q` 必须全绿
3. 加新检测器请同时提供至少一个 positive + 一个 negative 测试,详见 `ARCHITECTURE.md`
4. 不要把任何真实他人论文 PDF 提交到仓库(版权 + 隐私)

## License

MIT — 见 `LICENSE`。
