# SpatialWarrant S1→S2 入口裁决 v1

时间：2026-09-05T10:34:48.079441+00:00。范围：只读核验 S1，并新建评审/补充；本次未启动 S2A、S2B 或 S3。
父方案 SHA-256：854e2d06eb25903a870606934964fd8b7f0a40a16a9658ef565cf5ab14a03c82（一致，未改动）。

| 入口 | 裁决 | 具体依据与边界 |
| --- | --- | --- |
| S1 technical gate | PASS | 209 个历史文件字节哈希全部匹配；123 个输入索引全部一致；指定 11 文件已完整读取核对。仅通过 S1 输入准备/元数据技术检查，不代表全计数扫描或身份/病理通过。 |
| S2A metrics-only entry | PERMITTED | 稳定的 source_sample_id 足够支持每来源样本 QC 指标；须先人工批准下列补充哈希及启动前复查。此裁决不是启动指令。 |
| S2B filtering/reference construction | PENDING | S2A 尚未运行，数值 QC 阈值尚未产生/批准；来源样本技术参考分支与具体分配亦须另行批准。 |
| S3 entry | BLOCKED | 病理映射未冻结、组织外条码排除未冻结、物理 section 关系及注册未核实。仅靠完成 S2A 不解除这些门槛。 |
| patient-level inference | BLOCKED | orig.ident 不是已核实患者字段；CID4290/CID4290A 别名未证实；sample/section/donor 层级及独立性不明。 |

## 身份证据与决策

GEO 原始 SOFT、metadata.csv 和新建 GEO-metadata-identity-evidence.v1.json 一致显示：26 个 orig.ident 精确对应 26 个 GEO Sample_title；100064 条元数据与条码顺序一致，29 个 producer celltype_minor 标签原样保留。没有来源样本键或 minor label 缺失。固定用 source_sample_id，不制造 patient_id；通用测序建库说明不能证明每个 orig.ident 唯一对应一个文库或捕获批次。
GSM5354523 的标题为 CID4290A、BioSample 为 SAMN19546327。PMC 论文用 CID4290 描述 scRNA/Visium 同队列来源，但正文没有提供与 CID4290A 的明确别名声明。保留分离，状态 PENDING；不能因为相似或差一个后缀合并，也不能因此视为不同患者。
Life Sciences Literature 的 PMC 脚本本次实际成功；其返回的版本化 XML 已获取（HTTP 200），文件 MD5 与返回 URL 提供值一致。原 S1 PubMed 请求/原始 XML、GEO SOFT、PMC BioC 仍保留。补充表入口实际返回 HTTP 404，原始错误响应及请求均已保存。该失败限制身份核实，不能转写成“已阅读补充表”或“别名不存在”。

## S2 的分段与候选技术参考

S2A 只计算每个来源样本内的每细胞 detected genes、UMI、线粒体比例及缺失情况，保留全部细胞；不筛选、不抽样、不归一化、不做 HVG/PCA/Leiden/整合/标签生物学评估。输入是发布者已处理且已做 QC 的整数计数层，不是原始液滴全集。完整数值有效性扫描属于未来 S2A，本次只做文件哈希与元数据核查。
S2B 必须等待人工批准 S2A 数据依赖 QC 阈值。患者若核实，原 verified patient × producer celltype_minor 分层继续有效；患者未核实时，可以另行批准 source_sample_id × producer celltype_minor 的来源样本平衡技术分支，但不能称患者/已核实文库平衡，也不能进行患者级推断。上限 40000、seed 20260904、稀有组约束、HVG/PCA/数值 Leiden、标签证据评估与其他 S0–S7 模块全部保留。原跨患者模块继续等待来源证据，不能以技术样本比较替换。

## 阶段阻断及证据文件

病理映射：02_identity/pathology-label-map.json 为 PENDING_REVIEW_NOT_FROZEN；pathology-label-inventory.csv 保留复合类别。它不阻止 scRNA S2A 或未来独立批准的技术参考，但阻止 S3 的标签/边界锁。不得以免疫比例、表达、聚类、去卷积或文献决定主边界。
组织外条码：02_identity/visium-integrity-exceptions.json 记录 CID4290 6 个、CID44971 2 个、CID4535 2 个。它们不影响 scRNA 指标；进入空间分析前必须根据发布者 in_tissue 冻结排除清单，不能修改原文件或通过表达重新纳入。它们不是永久废弃整个样本的理由。
section 身份：02_identity/visium-sample-identity.csv 与 identity-gate.json 仍只支持来源文件束/标签。当前 XML Figure 6 明确提到 CID44971 三个 tissue regions，不能直接变成三个独立 section/patient。该缺口不阻止独立 scRNA 技术准备，但阻止当前 S3 的物理 section/注册/防跨片几何门槛及患者独立重复推断。
患者推断：02_identity/sample-identity.csv 和本次 scRNA-identity-resolution.v1.json 共同保留未知患者状态。原至少四个已核实独立配对单位的推断门槛保留；少于四个或独立性未核实，只能在未来获准且几何有效时做描述。10x 仍仅技术迁移，不算独立生物学复现。
S1 技术核验详情见 S1-checkpoint.md、S1-starting-point-assessment.json、manifest/S1-source-manifest.json、manifest/S1-input-file-index.json 及新证据目录的两个 verification/crosscheck JSON。primary-program.lock.json 的 196/200（98%）来源标识覆盖门槛保留通过；未计算表达程序或终点。

## 存储、停止与审计

C 盘快照：41481740288 字节（38.632881 GiB），记录时间 2026-09-05T10:34:48.068785+00:00。启动时必须重新满足 30 GiB，并在真正 S2A 启动前做非破坏性写入检查；本次只读评审不另做临时写入试验。运行中低于 20 GiB 立即停止继续写入。S2A 新增产物预算上限 1 GiB，是操作上限而非资源预测；其余各阶段预算执行前另建。
硬停止条件：无补充哈希批准、哈希变化、空间/预算不足、输出冲突、条码/特征歧义、非整数/负数/非有限计数、依赖不可用或请求越过 metrics-only 范围。原全计划停止条件继续有效；S3 还须先解决病理映射、组织外条码及空间注册/section 门槛。不会借用 S2A 许可继续 S2B/S3。
只新建文件，原方案、plan.sha256、D 盘 v2/失败检查、NOT_APPROVED 记录和全部旧预演均保留。Life Sciences Literature 是真实来源检索；NGS 是设计/可行性上下文；本地 Python 承担当前字节核验与未来技术计算；BioNexus 保留被动审计角色。当前没有 NGS registered workflow run，也没有 BioNexus 科学 Warrant 裁决。
所有科学结果、分析资源预测、机器 verdict 与生物学结论接受状态保持 PENDING/NOT_GIVEN；本表是阶段入口政策判断。

## 可供人工批准的唯一执行范围

补充文件：00_plan/S2A-technical-QC-supplement.v1.md；SHA-256：e6084a97821bc10eecc1060afde4bd049092446a1c1ad02427bd78c6e35086af。
身份裁决文件：02_identity/scRNA-identity-resolution.v1.json；SHA-256：9aa98d57bd4317e9e185ce094bdd67d737c467b13410448535ec0d7665d12a44。
当前审批状态 PENDING；若人工批准，只执行此补充的 S2A 技术指标计算，完成指标/检查点后停止。S2B、S3 及患者级推断均未获准。完整机器可读证据、条件与逐项文件列表见同名 v1.json；四份交付的 SHA-256 见 S1-to-S2-entry-review.v1.sha256。
