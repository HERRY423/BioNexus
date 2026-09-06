# Rosalind Workbench 真实单细胞演示包

## 展示命题

**一条被审计的 IFN-β 单细胞证据链**：从 GEO 原始 UMI 计数和作者元数据出发，在 8 位 SLE 供者的源注释 CD14+ 单核细胞中重建 `donor × condition` 伪 bulk 样本，用配对设计 `~ donor + condition` 分析刺激响应；再由 BioNexus 明确指出哪些结果可陈述、哪些身份和外推仍未得到验证。

数据是 Kang et al. 的 GSE96583。公开研究含 8 位供者的 PBMC 对照与 6 小时 IFN-β 刺激。本包直接读取 GEO `GSE96583_RAW.tar`、基因索引和作者的逐细胞元数据，只保留作者标记为 singlet 的细胞。主分析使用作者提供的 `CD14+ Monocytes` 标签，但 BioNexus 不把这个来源标签升级为独立确认的细胞身份。

## 为什么适合活动展示

它同时展示三个层面：Workbench 连接公开数据、统计执行和可视化；Rosalind 把生物学问题、方法决策和文献解释串起来；BioNexus 审计“细胞不是独立重复”“标签不是新验证”和“单一队列不是外部复现”。结果是可用的，同时保留负面结论和证据缺口。

## Workbench 中的实际执行

1. 从 [官方入口](https://openai.com/rosalind/) 打开 Rosalind Workbench，按引导设置，在研究任务或科学工具入口开始一个基因组学问题。将本仓库 `C:\Plugin\BioNexus` 作为本地项目打开；具体入口名称以当前界面为准。确认 **Life Sciences Literature** 与你自己的 **BioNexus Reliability** 可用。Explore 模式即可起步，不必等待特殊 GPT-Rosalind 模型权限。
2. 新建任务，粘贴 `WORKBENCH_PROMPT.md` 的提示词。要求 Workbench 先展示计划并停在人工批准点。
3. 核对计划必须写明：GSE96583；8 位配对供者；singlet；CD14+ 单核细胞是来源标签；分析单位为供者而非细胞；公式 `~ donor + condition`；对比为 stim vs ctrl。缺任何一项就不要批准。
4. 批准后让 Workbench 先执行 `python review/workbench-ifnb-demo/fetch_inputs.py`，再执行 `python review/workbench-ifnb-demo/run_analysis.py --out review/workbench-ifnb-demo/workbench-run-01`。输出目录若已存在完整结果，改用 `workbench-run-02`，保留旧结果。打开该目录下的 `showcase_figure.png`、`analysis_manifest.json` 和 `paired_pseudobulk_de.csv`。
5. 让 Life Sciences Literature 检索 Kang 论文并核对 IFN 相关基因解释。把检索返回的 DOI、PMID 或 URL 保留在对话截图中。不得把“与文献一致”表述成独立复现。
6. 让 BioNexus 审计最终陈述。保留它的真实返回；当前源代码预演的身份判断为 `TENTATIVE`，不是独立确认。最终只声称“在来源注释的 CD14+ 单核细胞中观察到队列内相关表达变化”。

本方案从公开计数矩阵开始。执行器是 Workbench 调用的 Python 与 BioNexus 审计代码，不能把这一步写成 NGS Analysis Workbench 已运行的注册工作流。NGS Analysis Workbench 可选用于数据理解或计划审查，只有实际执行了相应技能/工具并留下记录才列入插件清单。

如果当前任务不能读取本地目录，优先使用官方提供的 Codex 本地项目入口。若必须上传，需同时提供本目录、三个公开输入和可运行的 BioNexus 源码/安装包，并让 Workbench 明确修改实际路径；单独上传数据无法使脚本找到 BioNexus。不要上传仓库里预计算的 `bionexus_pseudobulk_full_de.csv` 作为本次执行结果。

## 截图清单

截 4 张图即可：

1. **输入与批准**：Workbench 显示 8 位供者、两种条件和人工批准的计划。
2. **真实插件调用**：对话中同时可见实际使用的插件名和成功返回；只列真正调用过的插件。
3. **科学结果**：打开 `showcase_figure.png`，左图是作者原有 t-SNE 坐标的条件着色，中图是 4 个预先指定 IFN 基因的新计算供者配对变化，右图是新计算的配对伪 bulk 火山图。不要把左图称为本次新算的 UMAP。
4. **可信边界**：打开 `analysis_manifest.json`，突出 `formula`、`bionexus_identity_audit` 和 limitations。

预演图可以用于说明方案，但必须注明“本地预演”。脚本本身不能识别或证明宿主，所以 manifest 始终保守保留 `LOCAL_REHEARSAL_NOT_WORKBENCH_EVIDENCE`；不要删掉或改写这个字段来伪造宿主证据。实际 Workbench 执行的依据是新目录中的结果、对应对话/工具调用和真实截图，把这些另存到 `host-execution.md`。Windows 可用 `Win + Shift + S` 截图。

## 本地预演

```powershell
cd C:\Plugin\BioNexus
python scripts\doctor.py
python review\workbench-ifnb-demo\fetch_inputs.py
python review\workbench-ifnb-demo\run_analysis.py --out review/workbench-ifnb-demo/my-local-run-01
```

预演会重建输入并生成新结果，通常不需要 GPU、scvi-tools、Harmony 或 Nextflow。它用于确认数据与脚本能运行；活动证据仍应来自 Workbench 内的真实执行记录。

当前机器已完成依赖检查。换机器时先准备可用 Python 环境，安装本目录 `requirements.txt`，并在完整 BioNexus 仓库中运行；该依赖表不是完整环境锁。如果安装失败，保留错误，不要降级成未经说明的统计替代方法。

## 已经完成的预演

`local-rehearsal-v2` 是最终预演；`local-rehearsal` 保留首次运行用于追踪。输入包含 **24,679 个作者标记 singlet 的细胞、5,385 个来源注释 CD14+ 单核细胞、8 位配对供者**。全部 16 个聚合样本均保留。这里没有生成新细胞类型标签，也没有使用预计算 DE 结果。

本次采用“保留作者 singlet、完整报告 QC”的策略，不追加根据结果挑选的细胞阈值。公开矩阵中线粒体计数为零，因此线粒体 QC 解释保持 `NOT_ASSESSED`，不能声称所有细胞线粒体质量合格。最低基因数很低，后续可增加预先写明的低质量细胞过滤敏感性分析，比较效应方向是否稳定；不能只保留更好看的版本。

## 人工验收

- 本地状态与 Workbench 宿主执行证据分开保存，不靠手填一个状态字段证明成功。
- 16 个伪 bulk 样本、8 位供者，每位供者都有 ctrl 和 stim。
- PyDESeq2 模型公式恰好为 `~ donor + condition`。
- 结果文件的输入散列与 manifest 一致。
- BioNexus 不确认来源标签是真实细胞身份，也不把单一队列升级为外部复现或普遍因果结论。

## 谁需要完成什么

我已完成：公开数据选择、计数矩阵重建、来源散列核对、配对统计入口、真实本地运行、图表与结果表、BioNexus 身份判断、提示词和提交草稿。

你需要完成：在 Workbench 打开本地项目并运行提示词，确认实际可用插件，批准具体计划，保存真实截图，决定是否发布到 Chris 的原帖。官方 Literature 若网络失败，本地分析仍可进行，但不要声称已使用该插件。

本次展示不依赖外部实验室或 GPU。若进一步声称普遍科学有效性，需要独立队列、独立文库/实验重复和非作者专家审阅；这些不是这次公开数据展示的前置条件。

预留约 30–60 分钟完成首次 Workbench 会话和截图整理；这只是操作预算，实际耗时取决于插件访问、依赖和网络。原始计数文件约 76 MB，当前已经存在；缺失时下载脚本会从 NCBI 取回并核对散列。
