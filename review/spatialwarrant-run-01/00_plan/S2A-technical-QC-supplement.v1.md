# SpatialWarrant S2A 技术 QC 补充 v1

状态：PROPOSED_AWAITING_HASH_BOUND_HUMAN_APPROVAL。此文件只细分 S2 的入口与技术 QC 范围，不是本次计算授权。
父方案：00_plan/analysis-plan.lock.md；SHA-256：854e2d06eb25903a870606934964fd8b7f0a40a16a9658ef565cf5ab14a03c82。
身份裁决：02_identity/scRNA-identity-resolution.v1.json；SHA-256：9aa98d57bd4317e9e185ce094bdd67d737c467b13410448535ec0d7665d12a44。
创建时间：2026-09-05T10:34:48.068785+00:00。全部数据、临时文件、输出、日志和审计记录均位于 C:\Plugin\BioNexus\review\spatialwarrant-run-01。

## 不变的科学合同

原 S0–S7 锁定方案及 claim 原文保留；拒绝的 D 盘 storage-only v2 和失败写入检查保留为 NOT_APPROVED 历史。此次补充不改变主问题、主终点、独立单位要求、几何定义、停止条件或证据边界。
完整保留 GSE176078 参考、六张 Zenodo Visium、空间域、Tangram、marker/NNLS、scanpy ingest、niche、LIANA、10x 技术迁移、BioNexus ledger/debt、过度解读测试与 S7 产物。未执行模块保持 PENDING，不能因身份未明而删除。
主边界只由发布者病理区域、组织掩膜和空间几何定义；免疫比例、表达、聚类、去卷积及文献都不能决定主边界。

## 输入与身份

未来 S2A 只使用已索引的 GSE176078 count_matrix_sparse.mtx、count_matrix_genes.tsv、count_matrix_barcodes.tsv 和 metadata.csv。这里的“原始计数”指发布者处理后、已做发布者 QC 的整数 UMI count 层，不是未经细胞筛选的液滴全集或 FASTQ。不能恢复被发布者排除的细胞。
当前发布矩阵声明 29733 genes × 100064 cells；26 个 orig.ident 与 GEO 的 26 个 Sample_title 精确匹配。该对应只支持 source_sample_id。禁止创建 patient_id，也不能声称 orig.ident 已证明为单个文库或捕获批次。
保留 CID4290 与 CID4290A 原样、分开命名空间，别名 PENDING；分开标识也不证明它们来自不同患者。保留 producer celltype_minor 原字符串，不重注释、不合并。旧 patient_id/section_id 审计列中的占位或来源字符串不能被当作已核实患者/切片主键。

## S2A：仅指标计算，完成后停止

仅在人工批准本补充的 SHA-256 后才可执行，路线为 **local Python execution**，不是 NGS registered workflow run。只使用已可用的本地依赖；缺失或不兼容时停止，不安装。

1. 重核父方案、补充及输入精确字节哈希；重核 C 盘空间并执行仅临时新文件的非破坏性写入/读回检查。现有文件一律只读。矩阵以稀疏或流式形式读取，禁止稠密化或复制大型输入。对所有计数做整数、有限、非负、索引范围及维度一致性检查；检查重复坐标，不得无声折叠或改变特征。S1 只检过 MatrixMarket 声明，没有声称已扫描所有数值。
2. 用 barcode 一对一连接元数据，保留全部输入细胞；不因指标、零 UMI、缺失字段或作者标签选择细胞。关键条码歧义、重复或不一致为硬停止。缺失的非关键字段只能标记缺失，不能推断身份。
3. 对每个细胞计算 total_UMI = 全部输入基因原始计数之和；detected_genes = 原始计数 > 0 的输入基因数；mitochondrial_percent = 100 × 线粒体基因 UMI / total_UMI。total_UMI = 0 时该比例为缺失，并保存 zero_UMI 标志，不能填成 0%。
4. 线粒体集合仅以当前人类基因符号表中大小写精确的 MT- 前缀确定，先保存完整成员、索引及哈希；不用表达挑选基因，不扩展别名。若符号模式/物种不兼容、集合为空或特征映射存在歧义，停止相应指标并报告，不能伪造比例。有效集合下真实 0 计数与缺失必须分开。
5. 每个 source_sample_id 输出每细胞指标及样本内 n、有效/缺失/零值数、最小值、最大值、中位数与固定分位数（1%、5%、25%、75%、95%、99%），保持分母与有效值计数明确。使用未改变的原始指标，不把作者已有 nCount_RNA/nFeature_RNA/percent.mito 当作本次重算结果。只做技术分布汇总，不计算组间检验、患者效应或细胞类型生物学比较。
6. 只报告检测基因数、UMI、线粒体比例及缺失情况，以及保证其可解释性所需的输入/身份一致性记录。数值 QC 阈值保持 PENDING，待这些分布产生后另建版本化阈值提案，逐样本给出理由和预计保留数，提交人工批准。S2A 不应用阈值，不生成已过滤细胞集。

S2A 明确禁止过滤/删细胞、抽样、HVG、归一化/log1p、PCA、Leiden、整合、doublet/ambient caller、marker 解释、细胞标签评估、参考矩阵构建、空间数据加载分析、S3、任何主终点计算或生物学解释。无需安装 S2–S6 依赖。
未来产物目录提案：03_reference/S2A_metrics.v1/（本次不创建）；其中包含 per-cell-QC.v1.csv、per-source-sample-QC.v1.csv、missingness.v1.json、mitochondrial-feature-mask.v1.json、input-validation.v1.json、checkpoint.v1.md，以及指向源文件的 manifest 和哈希。qc-threshold-proposal.v1.json 在指标产生后才能另建，状态必须 AWAITING_HUMAN_APPROVAL。所有输出只新建，冲突即停。

## S2B：过滤及技术参考构建的单独门槛

当前为 PENDING，不包含在 S2A 批准中。必须先由人工批准 S2A 的数据依赖 QC 阈值，冻结具体过滤规则、缺失处置及输入/阈值哈希，再明确批准 S2B 的分层键与可行分配。
患者映射若已由明确来源核实，保留原 verified patient × producer celltype_minor 分层；若仍未核实，可另行批准 source_sample_id（精确 orig.ident）× producer celltype_minor 的**来源样本平衡技术参考**分支。这只是样本/文库平衡意图下的来源样本代理，不能声称已完成文库平衡、患者平衡或患者级推断。此候选分支不覆盖原患者分层模块；后者等待证据。
S2B 经单独批准后保留 ≤40000 细胞上限、seed 20260904、原稀有标签保留规则、不重复采样、2000 HVG、PCA、数值 Leiden 和标签证据评估；保留可选 Harmony/BBKNN 的条件分支。患者证据未核实时，跨患者评估模块继续 PENDING，不以跨来源样本结果冒充。标签不能合并；分配冲突/身份歧义必须先复核。此次不选择数据依赖阈值、抽样细胞或调整任何科学参数。

## 阶段性阻断与存储

病理标签映射未冻结、10 个组织外条码的分析排除名单尚未冻结、物理 section/组织区域关系及坐标注册未完成，均不影响单独的 scRNA S2A 指标计算，也不自行否定候选 scRNA 技术参考；但必须继续阻断 S3。组织外条码分别来自 CID4290（6）、CID44971（2）、CID4535（2）；只能依据发布者 in_tissue 排除，保留原始文件，不能因表达把它们纳入。S3 的标签/掩膜生成仍需来源支持的病理映射与人工检查点。
未知 donor/sample/section 独立性阻断患者推断和独立重复声明；即使以后允许 section 描述，也不能从六个文件束推成六个独立患者。原少于四个已核实独立配对单位时仅描述的门槛不变。
本次空间快照：41481740288 字节（38.632881 GiB），2026-09-05T10:34:48.068785+00:00。S2A 启动时必须重新确认 ≥32212254720 字节（30 GiB）；每次写入前及分块写入期间检查，若 <21474836480 字节（20 GiB）立即停止继续写入，不为保存尾部日志绕过门槛。为有余量时写入预先限制块大小并保留检查点；低于门槛后只在会话报告中说明，恢复须复核。
逐阶段存储预算：旧 S1 预算和实际记录保留；S2A 新增文件总预算上限 1 GiB（技术指标表、轻量日志/检查点/哈希），不复制矩阵、不缓存大型中间对象。它是操作上限而非用量预测；写入会越预算时停止并提交版本化预算修订。S2B–S7 各阶段预算 PENDING，必须在各自获准执行前建立，不借 S2A 许可启动后续阶段。

硬停止：父方案/补充/输入哈希不符；无本补充人工批准；空间不足/越预算；目标文件冲突；计数非有限/负数/非整数或坐标重复；barcode/特征映射不一致；所需依赖不可用；请求越过指标范围；试图以未知患者、合并别名或表达定义边界。遇到停止保留既有文件，记录真实错误，不能宣称完成。
科学结果、效应、显著性、BioNexus machine verdict、分析 RAM/运行时间与 Human Scientific Adjudication 均为 PENDING。计算许可不代表生物学结论被接受。
