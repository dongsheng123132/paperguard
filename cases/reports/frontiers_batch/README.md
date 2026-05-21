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
| rw_70224 | 4.5 | 低风险(命中 1 处 WB) |
| rw_70594 | 4.5 | 低风险(命中 1 处 WB) |
| **rw_70593** | **0** | ❌ 漏报(图像被矢量图过滤跳过) |
| **rw_70601** | **0** | ❌ 漏报(图像被矢量图过滤跳过) |
| control_1441076 | 0 | 干净 ✅ |
| control_1464144 | 0 | 干净 ✅ |

**P = 100%(0 FP), R = 50%(2 FN), F1 = 67%**

> 当前默认配置偏保守 — wb_clone 引入了 4 类"非显微图"前置过滤(白底统计图 / 灰底流程图 /
> 白底彩色图表 / 深底彩色通路示意图),把这些都跳过。代价:2 篇真退稿因为其中 WB 区域
> 嵌在大型多面板复合图里(整图色彩特征命中"通路示意图"分支),被一并跳过 → 漏报。
>
> 这是个**精确度优先**的取舍:宁可漏报也不在普通图表上吵醒用户。**实际使用建议同时
> 人工浏览图像**,工具结果只当复核线索。
>
> 下一步思路:不要在"整图"层级判断是否要扫描,而是先做**图像 ROI 分割**,把可疑的
> 凝胶条带区域 / 显微图框出来再做 copy-move。这样既不会被"图整体看起来像通路图"
> 误导,也能保住对照组 0 FP。详见 paperguard/detectors/wb_clone.py::_looks_like_vector_figure。

## 重新生成

```bash
for p in cases/pdfs/*.pdf; do
  name=$(basename "$p" .pdf)
  python -m paperguard check "$p" -f md > "cases/reports/frontiers_batch/${name}.paperguard.md"
done
```
