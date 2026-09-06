# 可直接粘贴到 Rosalind Workbench

请在 Rosalind Workbench 中使用我的 BioNexus Reliability 和 Life Sciences Literature，完成一次可审查的公开单细胞分析。项目根目录是 `C:\Plugin\BioNexus`。先读取 `review/workbench-ifnb-demo/README.zh-CN.md` 和 `SOURCES.md`。这是计数矩阵重分析；不要冒称 NGS Analysis Workbench 已执行注册工作流。若使用它做数据理解或设计审查，保存真实调用记录并准确说明作用。

研究问题：在 Kang et al. GSE96583 队列中，来源注释为 CD14+ Monocytes 的细胞在 6 小时 IFN-β 刺激后有哪些表达变化？

先只检查输入并提出计划，不要立即执行。必须核对 `data/flagship/kang2018_pbmc_ifnb/GSE96583_RAW.tar`、`GSE96583_batch2.total.tsne.df.tsv.gz` 和 `review/workbench-ifnb-demo/GSE96583_batch2.genes.tsv.gz`；报告文件散列、细胞数、8 位供者、ctrl/stim 是否成对、计数是否为非负整数、作者 singlet 和来源细胞类型字段。禁止把单细胞当作生物学重复。

计划的主分析必须限定为来源注释的 CD14+ 单核细胞，聚合为 8 donor × 2 condition 的 16 个伪 bulk 样本，用 PyDESeq2 公式 `~ donor + condition`，对比 stim vs ctrl；基因过滤预先固定为“至少 4 个伪 bulk 样本中 count >= 10”；BH 调整；预先指定查看 ISG15、IFIT1、MX1、STAT1。说明条件与测序文库混杂这一局限。把计划展示给我，等待我明确批准。

批准后先执行 `python review/workbench-ifnb-demo/fetch_inputs.py`，再执行 `python review/workbench-ifnb-demo/run_analysis.py --out review/workbench-ifnb-demo/workbench-run-01`。目录已完成时换新编号，不能覆盖。展示该目录的 `showcase_figure.png`，摘要 `analysis_manifest.json`，并保留完整 `paired_pseudobulk_de.csv`。左图重用作者 t-SNE，不是新算 UMAP。使用 Life Sciences Literature 的 PubMed 技能检索 DOI `10.1038/nbt.4042`，保存真实检索结果，核对数据设计及对 IFN 响应的解释并给出可点击来源。

最后调用 BioNexus 审计下列陈述：“在这个队列的来源注释 CD14+ 单核细胞中，IFN-β 刺激与供者配对的表达变化相关。”不要把来源标签说成新验证的细胞身份，不要声称外部复现、临床效用或普遍因果机制。列出实际调用成功的插件和工具；失败或未调用的插件不要列为已使用。

脚本已实际调用本地 BioNexus 注释证据接口，但这不证明安装的插件版本或 Workbench 集成已经通过验收。保存实际使用的 BioNexus 插件版本、源码路径、会话/工具调用引用、命令、输出目录和截图路径到 `host-execution.md`；不存在的记录留空，不要编造工具调用编号。保留 manifest 的保守宿主状态。当前公开矩阵的线粒体计数为零，不要把零解释为通过线粒体质量检测；如提出额外 QC 过滤，写成单独的敏感性分析并保留原结果。
