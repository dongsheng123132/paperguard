# 回测数据集

用于评估 PaperGuard 在已知有争议/已撤稿论文上的真实命中率。

## 设计原则

1. **不分发论文本身** — 每个案例只描述元数据 + 期望命中,不打包 PDF。
   PDF 由用户自行通过合法渠道下载并放到 `cases/pdfs/<case_id>.pdf`。
2. **来源透明** — 案例必须给出 PubPeer/Retraction Watch URL,允许人工复核。
3. **期望命中明确** — 每个案例标注期望触发哪类检测器(`expected_detectors`)及置信度下限,便于自动评测。
4. **二分类标签 + 多标签** — `verdict` 字段: `retracted` / `disputed` / `clean_control`。最后一类是干净论文,用来测 false positive。

## 案例 JSON Schema

```json
{
  "id": "case_2018_xxxx",
  "title": "Example Title",
  "doi": "10.xxxx/xxxxxx",
  "year": 2018,
  "journal": "Cell Reports",
  "verdict": "retracted",
  "sources": [
    {"type": "pubpeer", "url": "https://pubpeer.com/publications/..."},
    {"type": "retraction_watch", "url": "https://retractionwatch.com/..."}
  ],
  "known_issues": [
    {"category": "image_dup", "desc": "Fig 2C 与 Fig 4A 同图,水平翻转"},
    {"category": "statcheck", "desc": "Table 1 t 检验 p 值不自洽"}
  ],
  "expected_detectors": ["image_dup", "statcheck"],
  "pdf_path": "cases/pdfs/case_2018_xxxx.pdf",
  "notes": "用户自行获取 PDF 后放入指定路径"
}
```

## 评测指标

对每个案例:
- **detector hit**: 期望的检测器是否至少有一个 finding
- **false positive**: 干净对照组论文上 `risk_score >= 5` 算 FP

聚合指标:
- precision = 真阳 / (真阳 + 假阳)
- recall = 真阳 / (真阳 + 假阴)
- F1 = 2PR / (P+R)

## 如何添加案例

1. 在 PubPeer / Retraction Watch 上找一篇有具体可机器检测特征的论文
2. 在 `cases/seed/` 下新建 JSON
3. 把 PDF 放到 `cases/pdfs/<id>.pdf`(不进 git)
4. `python -m cases.benchmark` 跑回测
