# 投稿前 DE 影子审阅 · installed-demo

目标：定位可能影响声明的问题，供研究者复核；本报告不批准分析或投稿。
审计状态：`NEEDS_REVISION`。净收益：**尚未评估**。

**合成教学示例：不是真实研究，不能计入实验室收益。**

待审声明：These genes are significantly differentially expressed after FDR correction.

## 先处理这些问题

### F001 · 缺失 FDR 多重假设检验校正 (Missing FDR / Adjusted P-value)

影响：差异分析结果表中仅报告了原始 p 值，未进行 Benjamini-Hochberg (FDR) 校正。单细胞转录组同时检验数万个基因，若仅以 p < 0.05 筛选，存在成百上千个假阳性基因被当做真实生物学发现的风险。

定位：Differential Expression Post-processing

最小下一步：

```text
from statsmodels.stats.multitest import multipletests
_, padj, _, _ = multipletests(de_df['pvalue'], method='fdr_bh')
de_df['padj'] = padj
sig_degs = de_df[de_df['padj'] < 0.05]
```

## 还缺哪些证据

- 供体细胞贡献失衡：未提供细胞类型列，供体失衡未评估。
- 批次与组别混杂：未提供批次列，混杂未评估。
- 原始整数计数层：未提供表达矩阵，计数层未评估。
- 分析脚本/笔记本：未提供分析脚本，静态方法学调用未评估。
- 分析事实与执行记录绑定：未提供经核查的供体级执行记录（统计单位、设计矩阵、拟合状态未绑定）。

## 当前如何表述

只能确认已检查的输入（6 donors; condition counts control=3, treated=3）。缺少差异表达执行记录或结果时，不得陈述已完成的群体差异表达。

严禁把未提供的矩阵、模型或 DE 结果写成已经执行的 NB GLM、Wald 或 BH 校正。

## 负责人需要复核

没有额外生成方法权衡项；仍需由研究者确认发现与声明。

## 完成审阅

打开 [review.json](review.json)，记录人工判定、漏检、审阅时间与是否愿意复用。
未完成的评审保留 PENDING；独立参考审阅应在看本报告之前完成。
需要修改分析时，在原工作流修复，再生成新的审阅目录。旧报告与未解决问题继续保留。

[完整证据与全部发现](audit-full.md) · [机器结果](audit.json) · [输入指纹](manifest.json)
