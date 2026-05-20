# PaperGuard 论文体检 · 开源学术造假检测工具

> 给一篇论文,自动找出**可疑的统计错误、数据雷同、图片复用**等问题。
>
> 灵感来源: PubPeer、Elisabeth Bik、"耿同学讲故事"。
>
> **定位**: 提出质疑、不下定论。所有报告附置信度,辅助人工复核,不替代同行评审。

## 现阶段能做什么(v0.2)

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

合成样本上当前指标: **precision 100% · recall 100% · F1 100%**
(5 个合成假/干净样本 · 真实退稿案例待 PDF 就绪)

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 命令行体检
python -m paperguard check samples/demo.pdf

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
samples/        # 论文样本(测试用)
```

## 免责声明

本工具输出 **"疑似"** 而非 **"定罪"**。任何争议必须以原始数据复核为准,作者也可能在论文里报告了正当的舍入/简化。请理性使用。
