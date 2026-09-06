# 一条可审查的 IFN-β 单细胞重分析记录

本次已真实运行，结果来自 `workbench-run-01`。执行环境是 Codex 本地任务调用 Python；使用了 NGS Analysis Workbench 技能、Life Sciences Literature 技能和 BioNexus 审计。未运行 NGS 注册工作流，尚无人类生物学结论确认，未发布。

## 研究问题与数据

在 Kang 2018 / GSE96583 的 8 位配对供者中，来源注释 CD14+ Monocytes 的表达在 6 小时 IFN-β 条件与 ctrl 之间如何变化？

使用 GEO 公开 UMI 矩阵、基因索引和作者元数据。24,679 个作者 singlet 中，主分析保留 5,385 个来源注释 CD14+ 单核细胞，按 8 donor × 2 condition 汇总成 16 个伪 bulk 样本。作者标签不是本次重新验证的细胞身份。

原论文与方法已由 Life Sciences Literature 检索，并阅读公开 PMC 手稿核对。[原论文](https://pubmed.ncbi.nlm.nih.gov/29227470/) · [GEO](https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE96583)

## 实际完成的工作

输入 SHA-256 核对、矩阵/条码/元数据对应检查、作者 singlet 筛选、细胞 QC 汇总、供者伪 bulk 聚合、PyDESeq2 0.5.4 的 `~ donor + condition` 配对分析、BH 调整、预指定基因展示、完整结果导出、图表检查、文献核对、BioNexus 多层审计。

所有 16 个样本保留。设计矩阵 9 列、秩 9。基因过滤固定为至少 4 个样本 count ≥10：35,635 个输入基因中，4,914 个进入模型，30,721 个在模型前过滤。4,914 个结果均有非缺失 pvalue 和 padj。没有在看到结果后添加细胞过滤或更换模型。

## 主要结果

- 2,845 / 4,914 个基因 BH padj <0.05；其中正向 1,445 个、负向 1,400 个。
- 1,481 个同时满足 padj <0.05 且 |log2FC| ≥1。
- 四个预指定基因的 log2(CPM+1) 均在 8/8 位供者中由 ctrl 到 stim 升高。

|基因|PyDESeq2 log2FC|标准误 lfcSE|BH padj|展示值升高供者|
|---|---:|---:|---:|---:|
|ISG15|7.736|0.459|7.08e-62|8/8|
|IFIT1|8.634|0.599|1.54e-45|8/8|
|MX1|6.255|0.481|2.69e-37|8/8|
|STAT1|2.328|0.186|1.40e-34|8/8|

这些 log2FC 是条件系数的模型估计，与图中 log2(CPM+1) 的配对差值不是同一个量。它们来自本次数据，不是从原论文或既有预演表复制。

## 如何读图

![本次分析三联图](C:/Plugin/BioNexus/review/workbench-ifnb-demo/workbench-run-01/showcase_figure.png)

左图重用作者 t-SNE 坐标，固定种子从所有 singlet 抽样 12,000 个细胞并按条件着色；不是新算的 UMAP，也不是只画 CD14+ 子集。条件分离不单独证明处理因果性。

中图每条灰线连接同一供者的 ctrl/stim，蓝色 ctrl、红色 stim。四个基因各有 8 对观测；可见基线差异及升高幅度差异。纵轴是用于展示的 log2(CPM+1)，实际检验用原始伪 bulk 计数。

右图横轴为 stim/ctrl 的模型 log2FC，纵轴为 −log10(BH padj)。红点同时达到预定的显著性和效应量阈值；标注的是按 padj 排名前五的基因，不是另行预指定的五个终点。

## 限制与审计结论

1. 条件与测序文库完全混杂。供者项控制供者基线差异，但不能把纯 IFN-β 效应从文库影响中分离；很小的 p 值不修复该问题。
2. 单一 SLE 队列，8 位供者。结论不自动外推健康人群、其他细胞类型或疾病，不构成临床效用或独立复现。
3. 标签与 singlet 判断来自作者。本次 BioNexus 身份判定为 `TENTATIVE`。
4. 线粒体计数为零，质量解释为 `NOT_ASSESSED`。主分析未追加阈值；单核细胞中最少检测到 22 个基因，30 个细胞少于 200 个基因。低质量敏感性分析尚未进行。
5. 未做独立细胞身份校准、ambient RNA 校正、重新 doublet 判断或替代方法稳健性检验。
6. 原文采用 DESeq2 并提及 qvalue FDR；本次采用明确的 PyDESeq2 配对模型、固定过滤和 BH。不能声称精确重现原文基因清单。
7. 已发现 2020 年作者更正记录，但其正文具体影响尚未核实。见文献核对记录。

`PERMITTED` 是预执行可行性；预执行主张 `ABSTAIN` 保留；本次标签 `TENTATIVE` 保留；结果/文献封装 `VALID` 仅表示完整性；完成后关联规则检查 `WARRANTED / SUPPORTED` 仅针对明确限定的关联句，依赖本次运行事实，不是人工接受或独立认证。

建议陈述：“在这个队列的来源注释 CD14+ 单核细胞中，IFN-β 条件与供者配对表达差异相关；该条件与测序文库混杂。” 人工科学裁决仍待完成。

## 插件各自做了什么

|组件|实际贡献|未据此声称|
|---|---|---|
|NGS Analysis Workbench 0.2.16|数据理解、分析设计技能；实时查询注册目录与计算目标|注册工作流执行成功|
|本地 Python / PyDESeq2|计数重建、QC、聚合、配对统计与图表|这是 NGS 工作流运行|
|Life Sciences Literature 0.1.5|DOI → PMID 检索、原文摘要、PMC 版本与全文位置；保存首次失败和成功返回|第二个独立研究或逐基因机制验证|
|BioNexus 1.0.0-rc.4 技能与本地源码|预执行判断、来源身份评估、完成结果完整性和限定关联规则审查|人工科学认可、细胞身份确认、普遍因果结论|

执行记录：`host-execution.md`；完整结果：`../workbench-run-01/paired_pseudobulk_de.csv`；完整参数与来源：原 `analysis_manifest.json`。原 manifest 的宿主保守状态保持不变。
