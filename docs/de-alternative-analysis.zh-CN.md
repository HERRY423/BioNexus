# 突破二：检验结论是否经得起合理替代分析

BioNexus 现在可以从一次 DE 声明的必要条件检查，进一步检查冻结方案内的替代结果：哪些分支确实比较同一个声明，哪些改变了问题，哪些发现供体依赖，哪些仍未完成。入口为 `de-alternatives-plan` 和 `audit-de --alternative-plan ... --alternative-runs ...`。

这是开发功能，没有增加项目版本号，也没有激活 GA 或外部科研有效性承诺。它复用[突破一的声明条件验证器](executable-claim-conditions.zh-CN.md)，实际计算仍由研究者原来的工作流执行。

## 工作流

1. 从原分析导出声明合同、数值设计、模型记录、样本级计数与细胞归属清单。
2. 冻结逐供体剔除和具有明确理由的方法/过滤替代。保留计划文件的 SHA-256。
3. 在原有分析工具中运行每个分支，按相同格式导出产物；失败和未完成任务也填入返回清单。
4. BioNexus 核对计划、输入变化及声明条件，生成逐分支数值比较和依赖说明。

```bash
bionexus de-alternatives-plan study/baseline/run.json --out study/plan.json --specifications study/specifications.json
bionexus audit-de --alternative-plan study/plan.json --alternative-runs study/runs.json --bundle study/review
```

`--specifications` 可省略；逐供体剔除自动覆盖每一个基线供体。`--out` 必须是新文件，基线包必须位于其目录内。没有 `runs.json` 时，可直接审阅计划，所有任务保持 `MISSING`，不会生成假结果。

完整的旧有审计仍有自己的执行证据要求。只交替代分析材料时，即使所有比较完成，整个 `audit-de` 也可能返回 `NEEDS_DATA` / 退出码 1。JSON 中的 `alternative_analysis` 分别记录比较覆盖和结论变化；不会用“比较完成”覆盖原分析证据缺口。

Python 接口：

```python
from bionexus.de.alternatives import create_alternative_plan, evaluate_alternative_plan

create_alternative_plan("study/baseline/run.json", "study/plan.json")
review = evaluate_alternative_plan("study/plan.json", "study/runs.json")
for claim in review["claims"]:
    print(claim["status"], claim["compared"], claim["planned"])
    print(claim["dependencies"], claim["unresolved"])
```

## 产物合同

[Schema](../src/bionexus/data/de-alternatives.v1.schema.json) 包含 `run`、`plan`、`results` 三个定义；未知字段、重复 JSON 键、未知分支类型及路径越界不能被静默接受。

每个 `run.json` 必须包含：

| 字段 | 内容与核验 |
| --- | --- |
| `contract` | 突破一的声明合同相对路径及 SHA-256；继续绑定结果、样本表、设计矩阵与模型记录。 |
| `counts` | CSV/TSV，相对路径及摘要；每个样本一行，`sample_id` 加基因列，非负整数计数。核对样本标识和值，而非文件名。 |
| `cells` | CSV/TSV，`cell_id,sample_id`；细胞 ID 唯一，样本集合与模型完全一致。用于发现细胞集合改变，不认证真实细胞身份。 |
| `analysis_spec` | `method, version, normalization, test, p_adjustment` 字符串，完整记录该适配器要求保持的设置。关键选项必须包含在相应描述中。 |
| `synthetic` | 合成材料必须为 `true`，并沿计划、返回分支和审阅包传播；合成包排除在真实试点收益统计之外。 |

文件引用使用包内相对路径；每个被消费的文件必须匹配声明摘要。输入按标识排序后比较，行顺序和等价数字格式不构成新的分析。

记录的作用是绑定**提供的产物**。它不能单独证明这些输入实际参与了拟合，不能认证工具生产者，也不能认证样本身份。`analysis_execution_verification` 仍为 `NOT_PERFORMED`。同一字段名称不保证两个算法具有相同科学目标，因此方法替代始终保留 `scientific_admissibility=REQUIRES_REVIEW`。

## 允许哪些替代，如何避免换了问题

### 逐供体剔除 `leave_one_donor_out`

必须删除指定供体的全部样本、计数行和细胞归属，其他样本的元数据、细胞及计数不变。配对样本一起删除；允许删除变为空的供体指示列或调整供体参考编码，条件对比及其他协变量保持不变。每个分支重新检查秩、剩余自由度和对比可估计性。

剔除改变了所分析的经验队列，所以标记为 `DONOR_INFLUENCE_DIAGNOSTIC`，不谎称每个分支是完全相同的经验估计对象。它检验供体影响，不构成独立复制、代表性证明或逐供体一致效应检验。

### 方法替代 `method`

预先提供完整 `analysis_spec` 和理由。保留同一细胞集合、供体、计数、基因集合、模型目标、log2 效应尺度及有序对比，检查返回设置与计划完全对应。更换调整协变量或条件编码会标为 `QUESTION_CHANGED`，不能因为写了“合理替代”就强行合并。

示例 `specifications.json` 条目：

```json
[
  {
    "spec_id": "method-ql",
    "kind": "method",
    "rationale": "比较事先选择的计数模型；相同条件对比与调整集，科学适用性由研究者复核。",
    "analysis_spec": {
      "method": "edgeR",
      "version": "填写实际版本",
      "normalization": "TMM；填写所有关键参数",
      "test": "QLF；填写所有关键参数",
      "p_adjustment": "BH"
    }
  },
  {
    "spec_id": "filter-10-3",
    "kind": "gene_filter",
    "rationale": "限定在原分析基因集合内，检查低表达过滤选择的影响。",
    "min_count": 10,
    "min_samples": 3
  }
]
```

### 基因过滤替代 `gene_filter`

在原有基因集合中，保留至少 `min_samples` 个样本具有 `min_count` 个计数的基因。验证器从基线计数实际重算应保留集合，核对返回的基因及保留计数；不能通过重贴“过滤”标签改掉表达值。目标基因被过滤掉时为 `TARGET_FILTERED_OUT`，不填零、不当作不显著。

过滤改变被检验的基因集合，调整 P 值变化不能直接解释为效应变化。报告同时保留基线与替代基因数、效应及调整 P 值。没有删除任何基因的过滤标为冗余，不视作额外证据。

更换细胞定义、目标基因、对比、效应尺度、调整集、声明范围或显著性阈值，均不能合并为同一声明的稳健性结果。标签置换暂不支持；缺少交换性/分层置换验证器时，系统不生成貌似有效的经验零分布。

## 返回清单与完整分母

`runs.json` 绑定计划字节摘要，每个条目显式声明已完成、待运行或失败：

```json
{
  "schema_version": "bionexus.de-alternative-results.v1",
  "plan_sha256": "填写原计划的64位SHA256",
  "runs": [
    {"spec_id": "lodo-001", "status": "completed", "record": {"path": "lodo-001/run.json", "sha256": "填写64位SHA256"}},
    {"spec_id": "lodo-002", "status": "failed", "reason": "记录真实失败原因"},
    {"spec_id": "lodo-003", "status": "pending", "reason": "尚未执行"}
  ]
}
```

未提交的任务自动保持 `MISSING`，失败、产物错误、改变问题及不可估计的分支也保留。重复 ID、额外未计划任务、删掉应有供体剔除任务或更换计划摘要会被拒绝。没有任何分支因结果“不好看”从分母消失。

冻结摘要说明内容没有改变，不证明计划在首次查看结果之前产生。系统保持 `selection_timing=NOT_VERIFIED`；探索与确认的历史核验属于另一个问题。

## 如何读结果

- **方向翻转**：定位到具体供体或方法。`DIRECTION_SENSITIVE` 不等于原结论已被证伪，更不等于证明某供体存在生物学异质性。
- **失去显著性**：单列 `significance_lost`，不解释为没有效应。减少样本可能影响功效，但本工具没有估计功效变化。
- **区间变宽/跨零**：分别报告；置信水平不同时，不比较宽度，保留水平改变。
- **不可估计、无效设计、缺少产物**：分别保留 `NOT_ESTIMABLE`、`INVALID_DESIGN`、缺失/未评估状态，不转换成效应方向或成功率。
- **全部可比且没有这些变化**：只报告 `DIRECTION_AND_THRESHOLDS_RETAINED_WITHIN_PLAN`。这不是普遍稳健性证书，也不说明效应量完全相同。

`complete` 表示计划分支都完成可比检查，不表示生物学结论正确。已经观察到方向变化但仍有缺失分支时，会同时报告 `DIRECTION_SENSITIVE` 和 `complete=false`。区间、效应范围和 P 值都是各次相关分析的描述，不进行多数投票、P 值合并、真值概率计算或联合推断。

方法学背景是 Simonsohn、Simmons 与 Nelson 的 [Specification curve analysis](https://www.nature.com/articles/s41562-020-0912-z)：合理分析设定需要理论依据、统计有效性及避免冗余。本实现借鉴这一约束原则，**未实现该论文的联合推断方法**，也不主张重新发明 specification curve。

## 已完成的本地验收与开放边界

[可重跑实例](../examples/de-alternatives/README.md) 包含真实执行的合成 PyDESeq2 示例：8 个合成供体、120 个基因，一次基线加八次剔除拟合。原始目标基因的调整 P 值很大，不支持显著差异；剔除预设的有影响供体后方向翻转。该例验证了计算—导出—计划绑定—逐项诊断链路，没有提供生物学效益证据。

单元/集成测试还覆盖方法替代、过滤、配对参考编码、混淆后不可估计、缺失区间、输入替换、多声明与合成包排除。下一层科学验收仍需要留出真实研究、独立专家判断哪些敏感性改变合理论文表述，并同时统计误报、漏报和人工成本。当前不宣称已经完成这些外部验收。
