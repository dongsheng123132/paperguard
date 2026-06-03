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

## 现阶段能做什么(v0.4)

**文本统计层**
- ✅ **StatCheck**: t/F/χ²/r 与 p 值自洽,标决策反转
- ✅ **GRIM Test**: 均值 vs 样本量整数自洽
- ✅ **dup_numbers**: 段内 + 跨段数字雷同(完全相同序列、Jaccard)

**图像层**
- ✅ **image_dup**: pHash + ORB 二级验证,含水平/垂直翻转/180° 旋转复用
- ✅ **wb_clone**: 32×32 分块自相关,捕获 WB 条带 copy-move

**机构 / 作者层(v0.4 新增)**
- ✅ **corpus_retraction**: 给机构名/作者名/OpenAlex ID,自动拉全部作品,用 OpenAlex `is_retracted` + 本地 Retraction Watch 库**三重交叉验证**撤稿记录,并给发文画像
- ✅ 离线 DOI 模式: 只用本地退稿库核对一份 DOI 清单(不联网)
- ✅ **OA 深扫(`--deep`)**: 对开放获取论文自动下 PDF,逐篇跑上面 5 个单篇检测器(`corpus_deepscan`)。只碰 OA、限速、跑完即弃
- ✅ 作为 Agent Skill 暴露(`skills/paperguard_corpus_scan/SKILL.md`,仿 google-deepmind/science-skills),Claude Code / Antigravity 可直接驱动

**通用**
- ✅ CLI / Markdown / HTML / JSON 多格式报告(带图片缩略图和克隆块标注)
- ✅ Streamlit Web UI(单篇 / 机构两种模式)

## 路线图

- v0.1 — 文本统计校验 ✅
- v0.2 — 图片同图复用 / WB copy-move ✅
- v0.3 — Retraction Watch 数据集 + 回测框架 ✅
- v0.4 — 图表数值反向提取(WebPlotDigitizer 思路) + 相关性异常
- v0.5 — 引文/作者关联(论文工厂识别)
  - ✅ 机构/作者级撤稿核对(OpenAlex + Retraction Watch)已交付 — `paperguard scan`
  - ✅ OA 论文自动深扫已交付 — `paperguard scan --deep`
  - ⏳ PubPeer 接入 / 论文工厂指纹 / 图像检测器降误报(WB copy-move 在材料·化学图上易误报)

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
| 真实 Frontiers(4 退稿 + 2 控制组) | 6 | 100% | 50% | 67% |
| **合计** | 11 (+5 PDF 待补) | **100%** | **67%** | **80%** |

> **真实数据 0 个 false positive**(对照组 risk 都是 0)— 当前 wb_clone 的"非显微图前置过滤"
> 把统计图 / 流程图 / 通路示意图都跳过,代价是 4 篇退稿里有 2 篇被一并跳过(risk=0)。
> 这是个**精确度优先**的取舍:宁可漏报也不要在普通图表上误报。
>
> 下一步:引入更专门的图像类型识别(先定位 WB / 凝胶 / 显微图区域,再做 copy-move),
> 目标是在不损失 P 的前提下把 R 提回 90%+。详见 v0.4 roadmap。

样本报告参见 [`cases/reports/frontiers_batch/`](cases/reports/frontiers_batch/)。

## 本地运行

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 命令行体检
python -m paperguard check samples/demo_fraud.pdf

# 3. Web 体检
streamlit run paperguard/web/app.py

# 4. 机构 / 作者体检(查公开撤稿记录)
python -m paperguard scan --institution "Kingfa" --mailto you@example.com
python -m paperguard scan --author "某作者" -f md -o report.md
python -m paperguard scan --doi-file dois.txt          # 离线: 只核对本地退稿库
# CN 网络访问 OpenAlex 可加 --proxy http://127.0.0.1:7897

# 4b. 深扫: 对开放获取(OA)论文下 PDF 逐篇查(慢;疑点 ≠ 撤稿,均需人工复核)
python -m paperguard scan --institution "Kingfa" --deep --max-pdfs 5
```

> 机构/作者体检样例: [`cases/reports/kingfa_corpus/`](cases/reports/kingfa_corpus/)
> —— 对金发科技(305 篇)的真实体检,公开撤稿库 0 命中,结论"合格"。
>
> ⚠️ `--deep` 的图像检测器(尤其 `wb_clone` copy-move)在**材料 / 化学类**图(大面积均匀背景、
> 发光照片、CIE 色度图)上**容易误报**。深扫疑点一律按"疑似"对待,**必须人工核对原图**,
> 不可作为指控依据。降低这类误报是下一步重点。

## 项目结构

```
paperguard/
  core/         # PDF 文本抽取、数字清洗、共用类型
  detectors/    # 单篇检测器 (statcheck / grim / dup_numbers / image_dup / wb_clone)
  corpus/       # 机构/作者级体检 (openalex + retraction_watch + scan)
  report/       # JSON / Markdown / HTML 报告渲染
  web/          # Streamlit 界面(单篇 + 机构两种模式)
  tests/        # pytest 用例
cases/          # 真实退稿论文回测框架
samples/        # 论文样本(测试用)
skills/         # Agent Skill(SKILL.md,仿 google-deepmind/science-skills)
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
