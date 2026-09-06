# AnalysisPlan — 待用户确认
状态：AWAITING_USER_APPROVAL。此文件是科学分析计划，不是 NGS 注册工作流的不可变执行计划。

## 研究问题与可支持范围
在 Kang 2018 / GSE96583 的 8 位供者中，来源注释为 CD14+ Monocytes 的细胞，其 6 小时 IFN-β 条件相对于 ctrl 有哪些供者配对的表达差异？
估计对象是本队列的条件相关差异；由于条件与测序文库完全混杂，差异可能同时包含文库影响。不能将其解释为可独立识别的 IFN-β 纯效应、普遍因果机制或外部复现。

## 固定设计
- 读取已核验的两个 batch-2 UMI 矩阵、作者逐细胞元数据及基因索引；不用既有 h5ad 子集或预计算 DE 表。
- 保留作者 multiplets == singlet；主分析限定 cell == CD14+ Monocytes。来源标签不升级为独立细胞身份验证。
- 以供者为生物学重复，按 donor × condition 对原始整数计数求和；预期 8 对、16 个伪 bulk 样本。细胞数不作为独立重复数。
- PyDESeq2 0.5.4；公式恰好为 ~ donor + condition；对比 condition: stim vs ctrl。
- 预先固定基因过滤：至少 4 个伪 bulk 样本 count >= 10。
- 保留 PyDESeq2 size-factor/dispersion 拟合、Cook's 处理与默认 independent_filter；BH 调整，alpha=0.05。保留所有结果与 NA，不把未检验或过滤后的基因算作有效显著性检验。
- 报告 log2FoldChange、lfcSE、pvalue、padj；火山图红点规则固定为 padj < 0.05 且 |log2FC| >= 1。
- 预先指定 ISG15、IFIT1、MX1、STAT1。配对展示使用 log2(CPM+1)，不把这个显示值送入 DESeq2 模型。

## QC 和失败条件
主分析不在作者 singlet 之外追加事后阈值。记录每个细胞的总计数、基因数、线粒体计数，每个 donor-condition 的细胞数与文库大小。
线粒体计数为零只说明本矩阵观察到零，质量解释固定为 NOT_ASSESSED。
额外低质量细胞过滤只能作为另行预先约定的敏感性分析，保留主分析全部结果。
哈希不匹配、条码关联不唯一/缺失、非整数/负数/非有限计数、零计数保留细胞、供者不成对、非 16 个样本、非满秩设计或模型失败时停止并保留错误，不自动换统计方法。
~ donor + condition 的满秩不解决 condition 与 library 混杂；不增加与 condition 共线的 library 项来声称已经校正。
身份验证、ambient RNA、独立 doublet 复核、独立队列复现仍未建立。

## 用户批准后的实施顺序
1. 运行准备好的 fetch_inputs.py。现有输入完整且哈希匹配时仅重新核验，不重新下载。发现变化则停止。
2. 确认 review/workbench-ifnb-demo/workbench-run-01 完全不存在，再运行现有 run_analysis.py。若目录存在，包括不完整结果，换下一个全新编号。
3. 执行命令：
   python review/workbench-ifnb-demo/fetch_inputs.py
   python review/workbench-ifnb-demo/run_analysis.py --out review/workbench-ifnb-demo/workbench-run-01
   工作目录固定 C:\Plugin\BioNexus，解释器为已检查的 Anaconda Python。
4. 核验新输出中的 16 个样本、8 位配对供者、设计满秩记录/检查、过滤范围、NA、效应和不确定性、输入及输出散列。保留原始日志和完整 DE 表，不只选好看的结果。
5. 展示 showcase_figure.png：左图为作者 t-SNE 的固定种子最多 12,000 细胞抽样，不是新 UMAP；中图为四个预指定基因的供者配对值；右图为本次 DE 火山图。
6. 保存 analysis_manifest.json、paired_pseudobulk_de.csv、pseudobulk_counts.csv.gz、pseudobulk_design.csv、donor_cell_counts.csv、cell_metadata_and_qc.csv.gz、prespecified_genes_by_donor.csv。
7. 按现有提示词使用 Life Sciences Literature 的 PubMed 技能检索 DOI 10.1038/nbt.4042，并核对设计和 IFN 相关解释。检索失败照实记录，不冒称插件成功或文献一致性等于复现。该插件本轮尚未调用。
8. 用已准备入口的 BioNexus assess_annotation_metadata 审计来源标签，并针对本次结果审查陈述：
   “在这个队列的来源注释 CD14+ 单核细胞中，IFN-β 条件与供者配对表达变化相关；该条件与测序文库混杂。”
   保存真实返回及不支持项。外部结果封装审计仅可使用已完成运行的真实返回；若需要人工判断，保持待人工决定，不制造审阅者或签名。

## 执行证据
准确称为“当前 Codex 本地任务调用 Python 分析，并使用 BioNexus 审计”。NGS Analysis Workbench 的作用为数据理解、设计和实时目录查询，不能称为已运行注册工作流。
保留脚本 manifest 原有 LOCAL_REHEARSAL_NOT_WORKBENCH_EVIDENCE 状态。
另存 host-execution.md：真实宿主名称、插件清单、源码路径/版本/散列、命令、时间、输出路径、实际工具返回、可取得的调用引用和截图路径；未知项留空。
当前源码目录有既存修改；运行时捕获实际源码状态与散列，不把版本号当作代码身份证明。
最终验收需用户确认；BioNexus PERMITTED 不替代本次明确的人类执行批准。

## 当前实施要求与未验证项
Python 和所需模块导入已通过，正式模型运行尚未发生。NGS 基础设施探测结果未取得；本计划不依赖 Nextflow、Snakemake、STARsolo、GPU、scVI 或 Harmony。
requirements.txt 是最小依赖清单，不是完整环境锁。
