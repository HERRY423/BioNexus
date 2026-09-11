# 外部任务收益与可纠错治理：执行指南

本页对应当前开发源码，尚非已发布 rc.5 的能力证明。首个产品范围仍是：被动审阅已经完成的多供体单细胞 DE 结果，支持有姓名的研究者作出判断。外部任务增益、实验室采用、独立专家结论均需实际数据，目前新增的软件检查不证明其中任何一项。

## 1. 在未参与开发的任务上比较两类错误

使用原研究/数据集作为分组单位，先冻结完整任务清单，再产生参考标签和两组结果。禁止用同一研究的多个基因、措辞或重跑充当独立研究；本工具只给描述性计数和按任务家族的分层，不输出显著性或独立样本置信区间。

先明确每个任务的完整输入包：数据/结果、样本设计、拟发表的精确声明、已有执行证据，以及本次允许判定的使用范围。`packet_sha256` 指该冻结输入包的文件 SHA-256；`dataset_sha256` 指实际共享的数据集指纹。两组结果与参考标签都必须绑定同一个输入包，不能拿另一个分析的结果充数。

```powershell
python -m bionexus.de_external_study template --out external-plan.json
```

此命令只写空白计划，不创建实验或研究者。由研究负责人填写：

- `study_id`、`intended_use`、带时区的 `frozen_at`、冻结源码归档的 `source_sha256`。
- `developer_ids`：全部开发/调参人员；`development_dataset_sha256`：开发时接触的数据集，空列表须是真实声明。
- `cases`：完整预定清单，每例包含 `case_id`、`task_family`、`site_id`、两个输入指纹、`data_origin`（`REAL_TASK` 或 `SYNTHETIC_DEMO`）、`not_used_in_development`（布尔值）。选择任务的人员须核查研究、供体及派生数据是否与开发集重叠；软件只能识别登记的相同指纹与声明。

冻结后将计划与独立保留的摘要交给研究负责人保存；摘要是规范 JSON 的 SHA-256，由以下空白观察文件的 `plan_sha256` 给出。若做正式研究，应在收集结果前完成外部登记和统计方案；本地日期、摘要都不证明已预注册。

```powershell
python -m bionexus.de_external_study template --plan external-plan.json --out external-observations.json
```

观察文件不发给被评估产品。每例收集两个相互独立的参考审阅记录，再收集两组输出：

| 记录 | 必填字段与含义 |
|---|---|
| `reference_reviews[]` | `reviewer_id`、`label`（`VALID` / `INVALID` / `UNRESOLVED`）、`rationale`、`evidence_sha256`、`packet_sha256`、`reviewed_at`、`blinded_to_arms=true`、`independent_of_development=true` |
| `arms.baseline` / `arms.assisted` | `decision`（`ACCEPT` / `HOLD` / `FAILED`）、`operator_id`、`artifact_sha256`、`packet_sha256`、`finished_at`；assisted 还需匹配计划的 `source_sha256` |
| `costs` | 下节的双臂成本；未记录则保持 null |

`VALID` 指该精确声明在指定证据和使用范围内成立；不能仅根据 BioNexus 是否通过赋标签。参考审阅者不能是开发人员或两组操作者，参考时间应早于两组输出。当前严格参考集要求至少两人一致；分歧原样保留，进入未解决分母，不能投票抹掉异议。需要裁决或新增证据时，保留原记录与首轮结果，在关联的新版本中重新评估，不编辑原观察文件冒充预先共识。

两组最终决定必须是实际记录：原流程与 BioNexus 辅助流程接受/暂缓该精确结论，技术失败记 `FAILED`。缺少整例或其中一组，仍保留在登记清单中。`FAILED` 对有效结论计为未能保留，并另报失败次数；缺失输出另列最坏情况错误率。不能为了提高指标删去安装失败、用时过长或没有完成审阅的任务。

```powershell
python -m bionexus.de_external_study score external-plan.json external-observations.json --expected-plan-sha256 <负责人独立保存的摘要> --out external-summary.json
```

输出 `joint_error_reduction_observed` 仅在参考明确、两组输出完整、有效与无效任务均存在时计算；要求辅助组的两类错误都严格减少。全部放行、全部拦截均不能通过此条件。一个指标下降而另一个上升会被保留。开发重叠和合成任务列为排除项，并保留原因；参考缺失/争议不会伪装为有效或无效。

身份、独立性、计时、输入包及输出的真实性仍需外部复核；此离线汇总校验声明间的绑定，不读取或认证指纹所指向的实验。即使描述性指标为正，`external_validation` 和 `net_benefit` 仍为 `NOT_ESTABLISHED`。实际外部证明复用现有 `trust_evidence` / `validation_network`，不让本工具自发证书。

## 2. 完整人工成本和安装摊销

`review.json` 新增可选 `costs`，旧文件仍可读。`costs.baseline` 与 `costs.assisted` 均逐项填以下人分钟；两人各工作十分钟计二十人分钟。各类互斥，不能把误报复核同时算入 review 与 false_alarm_handling。

| 字段 | 计入范围 |
|---|---|
| `installation` | 安装、依赖排障、接入与输入整理；包含失败尝试 |
| `review` | 阅读证据、正常复核、科学负责人审阅 |
| `false_alarm_handling` | 排查、解释和关闭误报的人工时间 |
| `repair` | 修复分析、重新运行的人工操作、修改结论 |
| `communication` | 与开发者、共同作者、统计专家、实验室负责人沟通 |

设置 `unit=person_minutes`、`comparison=PAIRED_SAME_CASE`；`allocation_note` 说明记录来源、互斥分类、安装成本如何分摊。真实零成本明确填 0；未知填 null。任何缺失都不能用零补齐。比较两组各五类总和的差值，负数表示成本增加。

外部研究另填 `installation_totals[site_id].baseline/assisted`，记录该实验室为本次纳入的留出队列实际付出的总安装人分钟。逐任务分摊之和必须与总账一致，不能摊给尚不存在的未来任务。缺总账时只能展示已有记录的差值，`cohort_person_minutes_saved` 为 null。合成/开发任务不进入此留出队列，需明确将其安装投入与真实外部队列分开核算。

试点汇总升级为 `bionexus.de-pilot-summary.v2`：

- `fully_costed_cases` 现在仅指双臂五类完整的案例；`mean_full_person_minutes_saved` 使用新口径。
- 旧的接入/修复口径继续提供 `setup_and_repair_costed_cases` 与 `mean_minutes_saved_after_setup_and_repair`，是部分成本，不能称净收益。
- 原 `review.v1` 与 `bundle.v1` 不变，未填写新成本的历史记录不会自动成为完整成本。

这是人工时间核算，不是涵盖设备、算力、经费、机会成本和科学错误损失的总经济收益。两组操作者分配、顺序及学习效应需要在正式研究方案中控制，软件不会把同一人先后审阅的差值当作因果净效应。

## 3. 规则可以被纠正，旧结论必须可追溯

现有 `ChallengeNetwork` 已修复：未声明适用范围不能认定普适；受限平台需精确匹配；样本量、特征数、设计和组织条件都需满足。缺上下文返回不满足，不代表该科学结论获准。此处是注册表适用性检查，不是自动关闭 DE 引擎中的约束。

每次专家意见保留在 `review_history`，当前票只是最新状态。改票不能继承旧票的验证凭证，凭证不能用于第二人或第二次意见。已验证的专家出现分歧时保留 `UNDER_REVIEW`，多数票不会自动形成规则真理。可用新证据或拆分适用范围提交修订；既有争议历史继续保留。统一意见仍须通过现有外部凭证验证，且挑战状态不自动激活规则或改写科学审计。

规则修改需要保存修改前后的注册表文件，并对所有已知受影响报告建立复核队列：

```powershell
python -m bionexus.rule_impact registry-before.json registry-after.json lab-a-001 lab-b-001 --out rule-impact.json
```

输出保留规则前后摘要、增删改类型、适用范围、旧审计状态与文件摘要：

- 命中变更规则或其别名：`REASSESS_REQUIRED`。
- 没命中但缺少完整规则执行轨迹：`RULE_APPLICATION_UNRECORDED`，不能称无影响。
- 包损坏或不兼容：`INTEGRITY_BLOCKED`。
- 两个注册表内容相同：`NO_REGISTRY_CHANGE`，仅表示该比较未变化，不证明代码或结论未变化。

此清单只覆盖传入的报告与注册表。纯代码修订须同时使用既有 `evidence_index` 的源码依赖检查，并由维护者补齐受影响案例；不能把只查几个文件说成所有历史结论都已追踪。

由维护者在原 Issue/PR 记录规则版本、修改理由、反例、范围、回归结果、具名审阅人及分歧。按队列重跑后输出新目录，以 `human_adjudication` 将具名负责人的决定绑定到新评估摘要，同时保留旧评估与修订链接。不得把测试通过当作科学接受，也不得覆盖旧报告。当前 `review_history` 是保留历史的本地记录，并非带外部锚的不可篡改日志；正式外部审查可用现有验证日志绑定导出快照。

维护遵循 [MAINTENANCE.md](../MAINTENANCE.md) 的实际负责人和 best-effort 范围，不承诺不存在的独立委员会或固定响应 SLA。
