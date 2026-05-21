# Frontiers Batch — 真实样本体检报告

这里是 PaperGuard 在 6 篇 Frontiers 公开 PDF 上的体检产物,作为开源透明化的回测证据。

## 样本组成

| 文件 | 类型 | 来源 |
|---|---|---|
| `rw_frontiers_70224_fnagi_2018_00207` | 退稿 | 10.3389/fnagi.2018.00207 |
| `rw_frontiers_70593_fgene_2021_724197` | 退稿 | 10.3389/fgene.2021.724197 |
| `rw_frontiers_70594_fonc_2021_616390`  | 退稿 | 10.3389/fonc.2021.616390 |
| `rw_frontiers_70601_fphys_2020_01092`  | 退稿 | 10.3389/fphys.2020.01092 |
| `control_frontiers_fphys_2024_1441076` | 对照 | Frontiers in Physiology 2024 #1441076 |
| `control_frontiers_fphys_2024_1464144` | 对照 | Frontiers in Physiology 2024 #1464144 |

## 当前体检分数

| 文件 | risk_score | 判定 |
|---|---|---|
| rw_70224 | 4.5 | 低风险(贴近阈值) |
| rw_70594 | 4.5 | 低风险(贴近阈值) |
| rw_70601 | 4.5 | 低风险(贴近阈值) |
| **rw_70593** | **0** | ❌ 漏报(图像被矢量图过滤跳过) |
| control_1441076 | 0 | 干净 ✅ |
| control_1464144 | 0 | 干净 ✅ |

**P = 100%(0 FP), R = 83%(1 FN), F1 = 91%**

> 当前默认配置偏保守 — wb_clone 引入了"白底矢量图/统计图"前置过滤,代价是
> rw_70593 这种图像被一并跳过(true positive 没抓到)。这是个**精确度优先**的取舍:
> 工具结果当作复核线索而非结论,实际使用建议同时人工浏览图像。
>
> 退稿样本中 3/4 拿到 risk=4.5(贴线),代表至少 1 个 WB 图被 detector 命中。
> 如果你的场景需要更高 recall,可以下调 `paperguard/detectors/wb_clone.py::_looks_like_vector_figure`
> 的过滤强度。

## 重新生成

```bash
for p in cases/pdfs/*.pdf; do
  name=$(basename "$p" .pdf)
  python -m paperguard check "$p" -f md > "cases/reports/frontiers_batch/${name}.paperguard.md"
done
```
