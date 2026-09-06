# SpatialWarrant：Workbench 完整执行手册

本手册保留原方案全部 S0–S7 内容。目标是让完整方案按正确顺序执行，并生成可核验的截图，而不是删掉复杂分析。

## 一、模型分工

| 环节 | 模型 | 推理强度 | 原因 |
| --- | --- | --- | --- |
| S0 预注册与统计设计 | gpt-6-astra | high | 需要识别循环论证、伪重复、批次混杂和不可支持的声明 |
| S1–S6 下载、编码、运行、恢复 | gpt-5.6-sol | high | 适合长时间文件操作、脚本执行、检查点和结果整理 |
| S6 文献批量核对 | gpt-5.6-sol | high | 批量调用插件并保存原始返回 |
| S7 对抗审查与最终叙事 | gpt-6-astra | xhigh | 需要同时审查科学、证据、截图和英文措辞 |
| Astra 发现问题后的定点修复 | gpt-5.6-sol | high | 按审查清单修改代码并重跑受影响步骤 |
| 最终四图和推文核准 | gpt-6-astra | high | 压缩故事并阻止未执行或越界文案进入提交 |

模型本身不构成科学验证。竞争力来自分工形成的真实证据链：Astra 负责提出难问题，Sol 负责留下可复核执行记录，BioNexus 负责不越过证据边界，用户负责最终科学裁决。

## 二、开始前的界面操作

1. 在 Rosalind Workbench 首页找到 **NGS Analysis Workbench**，点击 `View/查看`。
2. 在插件详情页点击右上角黑色的 **打开插件**，创建一个新分析任务。
3. 不要点击默认的 FASTQ、STARsolo 示例；本项目从处理后公开矩阵开始。
4. 在新任务右侧“来源/工具”确认至少出现：
   - `ngs-analysis-workbench`
   - `Life Sciences Literature`
   - 当前安装的 `BioNexus Reliability`/`bionexus-local-mcp`
5. 将任务关联到项目目录 `C:\Plugin\BioNexus`。
6. 在输入框底部点模型菜单，选择 **gpt-6-astra**，推理强度选择 **high**。
7. 本次对话全程使用同一个任务。切换模型时不要新建任务，以便保留计划、批准和运行记录。

## 三、Astra：只做 S0 预注册

将下面整段发给 Astra：

```text
请读取并遵守以下两个文件：
C:\Plugin\BioNexus\review\spatialwarrant-revised-design\ANALYSIS_PLAN_LOCK.md
C:\Plugin\BioNexus\review\spatialwarrant-revised-design\CLAIMS_PREREGISTERED.csv

项目：SpatialWarrant。请保留完整 S0-S7 设计，包括 GSE176078 scRNA 参考、Zenodo 4739739 六张 Visium、空间域、Tangram、marker/NNLS、scanpy ingest 标签迁移、niche、LIANA、10x 技术迁移、BioNexus ledger/debt 和过度解读测试。不要删除任何模块。

当前只执行只读检查与预注册，不下载、不安装、不运行分析：
1. 检查项目目录、插件实际可调用状态和执行环境。
2. 调用 NGS Analysis Workbench 的数据理解/分析设计能力，并查询实时 workflow catalog，判断是否存在 processed scRNA/Visium matrix 到本项目终点的兼容工作流。
3. 明确列出每个插件和本地 Python 的真实角色。若无兼容注册工作流，必须写明 local Python execution，不得称 NGS registered workflow run。
4. 核实主问题、统计单位、patient-sample-section 身份门槛、几何边界定义、主终点、完整 S0-S7 次级分析、停止条件和产物目录。
5. 边界必须仅由发布者病理区域和空间几何定义；免疫比例、基因表达、聚类、去卷积和文献不得参与主边界定义。
6. 所有结果、资源用量和 verdict 保持 PENDING。不要预测 CXCL9/10/11 上调、显著性、SUPPORTED/ROBUST、峰值内存或运行时间。
7. 将完成的计划写入新目录：
C:\Plugin\BioNexus\review\spatialwarrant-run-01\00_plan\analysis-plan.lock.md
并生成 plugin-capability-check.json 与 plan.sha256。

输出一张简洁的 readiness 表、完整计划摘要、硬停止条件、尚未解决事项，以及我应发送的唯一批准句。完成后停止，不启动分析。
```

检查 Astra 的返回中是否同时出现以下内容：

- `six sections`，而不是未经核实的 `six patients`；
- producer-provided pathology reference，而不是 independent ground truth；
- Tangram 与 marker/NNLS 比较组成，ingest 只作标签迁移；
- 主边界由 pathology geometry 预先冻结；
- NGS 注册工作流与本地 Python 的真实边界；
- 所有科学结果为 `PENDING`。

若全部满足，回复：

```text
我批准 analysis-plan.lock.md 当前 SHA-256 所绑定的完整 S0-S7 计划。请保留所有阶段和旧预演；只在新的 spatialwarrant-run-01 目录执行。批准探索性计算不代表我接受任何生物学结论。下一步切换到 Sol，先完成 S1 数据与身份审计；遇到下载、安装或执行原生批准点时按 Workbench 正常审批流程暂停。
```

## 四、Sol：执行 S1 数据与身份审计

在同一任务中把模型切换到 **gpt-5.6-sol / high**，发送：

```text
继续执行已批准且 SHA-256 锁定的 SpatialWarrant S0-S7 计划。当前只完成 S1，不推进 S2。

要求：
1. 使用新的 C:\Plugin\BioNexus\review\spatialwarrant-run-01 目录；不得覆盖任何 rehearsal 或既有结果。
2. 获取 Zenodo 4739739、GSE176078 和计划中的 10x 技术迁移输入。每个文件保存 URL、provider id、远端校验值、字节数、下载时间、本地 SHA-256、成功/失败日志。
3. 使用 Life Sciences Literature 实际核对 Wu et al. 2021；保存原始工具返回。失败后可重试一次，仍失败则如实记录，不用模型记忆补成成功。
4. 建立 sample-identity.csv，至少包含 patient_id、sample_id、section_id、subtype、processing_lab、modality、source_field、verification_status。
5. 在身份表核实前只写 six sections。不要假设 HER2+，不要假设每张切片对应独立患者。
6. 调用 BioNexus provenance-and-audit 生成输入 sidecar；哈希自洽只证明技术完整性，不证明生物学有效性。
7. 输出 S1-checkpoint.md，列出已完成、失败、未知、下载大小、实际耗时和下一步是否满足 S2 入口门槛。

完成 S1 后停止并给我检查点，不自动推进。
```

必须人工查看 `sample-identity.csv`。若无法证明六个独立患者，后续统计继续按 six sections，并把总体推断限制为该数据集的 section-level paired analysis。

## 五、Sol：执行 S2 和 S3

S1 门槛通过后发送：

```text
按锁定计划继续 S2 和 S3，保留全部原方案内容。

S2 scRNA：
- 先使用 NGS Analysis Workbench 查询并记录兼容执行入口。只有真实调用兼容注册工作流时才这样命名；否则使用本地 Python/scverse 并明确记录。
- 保留按患者×作者标签分层至不超过 40k 细胞、QC、HVG、PCA、数字 Leiden、作者标签证据和 EvidenceCard。
- 作者标签称 producer annotation，不称 ground truth；clusters 保持数字编号。

S3 Visium：
- 逐切片验证原始计数、barcode、坐标、组织内 spot 和病理标签覆盖。
- 在查看表达差异之前，仅用 invasive-cancer/stroma 病理区域与空间坐标生成 1/2/3 spot-distance 的 boundary/core masks，并冻结主阈值。
- 免疫比例、IFN 基因、Leiden、Tangram、ingest 和 niche 结果都不能修改主 mask。
- 保留空间 QC、Leiden resolution 扫描、ARI/NMI、Moran 与六张叠加图；ARI/NMI 只作描述，另报 boundary Dice/Jaccard。
- 输出每 section 的 boundary/core spot 数、总 UMI 和排除原因。任一区域少于计划门槛时停止该 section 的主统计。

保存脚本、命令、环境、日志、输入/输出 SHA-256 和实际峰值 RAM/耗时。完成后写 S2-S3-checkpoint.md 并停止。
```

此阶段最关键的截图是：同一张图里展示 H&E、发布者病理区域和纯几何 boundary/core mask。

## 六、Sol：执行 S4 和 S5

发送：

```text
继续完整计划的 S4 与 S5。不得改变已经冻结的 primary boundary mask。

S4：
- 保留 Tangram cluster-mode CPU 映射和原参数敏感性。
- 增加 marker/NNLS 组成基线；Tangram 与 marker/NNLS 比较可比的 spot composition 输出。
- 保留 scanpy ingest，但只称 label transfer；不得生成或宣称比例 Spearman。
- 三者共用 Wu scRNA 参考，因此所有一致性只叫 method sensitivity，不叫 independent validation。
- 记录训练基因集、随机种子、epochs、收敛、失败 section、每 section 指标及 500/1000/2000 基因敏感性。

S5：
- 保留跨切片 KMeans niche、k=6..10、silhouette、邻域富集、共现和 Moran。
- 用已经冻结的纯几何 boundary 判断 niche 是否边界富集；niche 或细胞比例不得反向改变 boundary。
- CAF、CD8 T、macrophage、endothelial 是预指定关注对象，不得写成必然发现。
- 在 10x held-out 上保留技术迁移；没有匹配病理真值时，不宣称生物学复现。

产出完整 S4/S5 表、六切片图、敏感性图、运行日志和哈希。输出 S4-S5-checkpoint.md 后停止。
```

## 七、Sol：执行 S6 主统计、LIANA 和文献核对

发送：

```text
执行 S6。先运行预注册主终点，再运行完整扩展分析；不得因探索结果修改主终点或 boundary。

1. 对每个合格 section 的 boundary/core 原始计数求和，建立目标 12 个 pseudobulk；保存 spot 数、总 UMI 和设计表。
2. 如果身份审计证明独立患者，使用验证后的 patient key；否则使用 ~ section + region，并把结论限制为 section-level paired association。
3. 先计算冻结 immune/IFN program 的逐 section 配对效应、总体效应、95% 区间、同方向 section 数和 leave-one-section-out。报告实际分母。
4. 再运行探索性全基因 DE 和 BH 校正；输出完整表，包括非显著结果。CXCL9/CXCL10/CXCL11/IDO1 只因预注册而标注，不因显著才选择。
5. 保留 LIANA、decoupler、Reactome/STRING/Open Targets/UniProt。LIANA 写 inferred communication，不写 mechanism。
6. 用 Life Sciences Literature 对 Top 结果及矛盾结果生成一致/矛盾/无报道表，保存原始返回；文献一致不能作为本队列独立复现。
7. 生成 S6-checkpoint.md、实际运行时间/峰值内存、所有命令、环境和 SHA-256 后停止。
```

## 八、Astra：S7 对抗性审查

把模型切换为 **gpt-6-astra / xhigh**，发送：

```text
不要重跑或重算。请读取 spatialwarrant-run-01 的锁定计划、全部 checkpoints、表格、图、原始工具返回、日志、环境与哈希，完成 S7 对抗性科学审查。

逐项检查：
- patient/sample/section 是否被混用；
- spots 是否被当作独立重复；
- boundary 是否被表达、比例、niche 或结果污染；
- 预指定主终点与探索性结果是否混淆；
- subtype、processing lab 和技术批次是否混杂；
- Tangram/NNLS/ingest 是否被错误称为独立验证；
- 发布者病理是否被错误称为 independent ground truth；
- 10x held-out 是否被错误称为生物学复现；
- 文献是否被双重计数；
- 小 p 值是否掩盖小样本、异质性或不稳定性；
- 任何 result、runtime、RAM、plugin use 或 verdict 是否没有真实证据。

然后调用 BioNexus 对 C1-C6、T1-T2 进行真实审计，保留 PERMITTED、ABSTAIN、TENTATIVE、NOT_ASSESSED、REFUSED 等原始状态及其对象。不要为了展示改成通过。

输出：
1. adversarial-review.md；
2. claim-ledger.json，所有条目绑定输入与结果哈希；
3. 四张主图的选择及逐图一句结论；
4. 需要 Sol 修复的阻断问题清单；
5. 一份待我签署的 Human Scientific Adjudication，允许接受、有限接受或不接受。

若存在阻断问题，停止在修复清单，不生成最终推文。
```

## 九、Sol 修复后由 Astra 最终核准

若 Astra 找到阻断问题，切回 **Sol / high**：

```text
只修复 adversarial-review.md 中列出的阻断问题。保持锁定问题、全部 S0-S7 范围和旧结果；不要顺带改方法。受影响分析写入新的版本化子目录，重新生成哈希和 checkpoint。完成后停止。
```

再切回 **Astra / high**：

```text
复核修复后的版本和哈希。只有全部阻断项关闭后，基于真实结果生成最终四图顺序、每图说明和一条主推文加最多两条回复。必须列出实际使用的 Rosalind plugins，并把 local Python/scverse 单独说明。不要承诺获奖，不要写未执行结果，不要把技术完整性升级为生物学验证。推文中的数字必须逐项指向结果文件。
```

## 十、最终提交检查

提交前逐项回答“是”：

- 四张主图在手机宽度仍能读清标题和结论。
- 第一张图能看出这是 Workbench 中的真实计划/插件调用。
- 第二张图能看出边界与表达分析分离。
- 第三张图显示每个独立样本，而不只显示合并 p 值。
- 第四张图同时显示可支持结论和不能支持的结论。
- 推文列出的插件名称与 Workbench 实际安装名称完全一致。
- `Astra challenged / Sol executed` 有会话与文件证据。
- 没有 `independent ground truth`、未经核实的 `6 patients/HER2+`、预写 `SUPPORTED/ROBUST`、估算 RAM 或估算耗时。
- 人工裁决已经签署；机器 verdict 没有通过 UI 下拉框修改。

无法保证评选结果。最能增加胜率的不是增加更多模块，而是让评委在四张图里同时看到：真实科学问题、真实插件调用、可信统计单位、漂亮结果和诚实的证据边界。

