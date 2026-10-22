# 声明成立条件的可执行验证

此开发功能将精确的多供体 DE 声明编译成逐项必要前提，读取实际产物执行检查，并保留不同范围的具体表述。它通过 `audit-de --claim-contract` 和 Python API 使用，不增加项目版本号，也不扩张冻结的 Core 支持承诺。

## 输入与使用

先明确基因、细胞集合、分子/分母条件、效应尺度、方向、声明范围和阈值。v1 使用人工或上游工具明确提供的结构化字段，不自动把任意自然语言翻译为已验证的声明。`--claim` 的原有文字审查继续独立运行；合同验证结果只适用于生成的 `canonical_statement`。

```bash
bionexus audit-de --de-table examples/de-claim-conditions/valid/results.csv --sample-sheet examples/de-claim-conditions/valid/metadata.csv --claim-contract examples/de-claim-conditions/valid/contract.json --out conditions-review.md
```

示例是合成工程夹具，没有执行 DE 拟合。合同内已覆盖的必要条件通过，整个旧有审计仍因缺少其执行证据而返回非零。这两个结果会分别显示，合同不能覆盖其他审计缺口。

独立检查同一合同：

```python
from bionexus.de.conditions import verify_de_claim_conditions

report = verify_de_claim_conditions("examples/de-claim-conditions/valid/contract.json")
for claim in report["claims"]:
    print(claim["canonical_statement"], claim["status"])
    print(claim["supported_statements"])
```

已有审计 API 接受新增的可选参数 `claim_contract=...`。通过 `--bundle` 生成的 `audit.json`、`audit-full.md` 和 `REVIEW.md` 都包含相应结果。历史调用不传合同则维持旧接口行为，旧的证据等级不会被追认成这些条件已经验证。

## 合同与产物

[JSON Schema](../src/bionexus/data/de-claim-conditions.v1.schema.json) 定义全部字段；[完整示例](../examples/de-claim-conditions/valid/contract.json) 可直接参考。

合同引用四类文件，引用采用合同目录内的相对路径与 SHA-256。每个文件只读入一次并从该份字节解析，不运行包内脚本，不查询外部服务。

| 文件 | 必须提供的语义 |
| --- | --- |
| `results.csv` / `.tsv` | `gene, cell_type, numerator, denominator, log2_fold_change, padj, ci_lower, ci_upper, ci_level`。`ci_level` 是 0 到 1 的置信水平；区间与效应须在相同 log2 尺度上。 |
| `metadata.csv` / `.tsv` | 每个模型观测一行；合同显式映射 sample、donor、condition 列，另提供模型使用的协变量。样本标识按字符串保留。 |
| `design.csv` / `.tsv` | `sample_id` 及全部实际数值设计列；按 ID 对齐，不按文件行顺序猜测。 |
| `model.json` | 绑定前三个产物的摘要，记录精确公式、列编码、数值对比、细胞集合、比较方向、效应尺度、统计单位和拟合状态。 |

`model.json` 应由原分析工作流导出。手工补写的记录仍是未认证记录。哈希相等仅说明字节绑定，不证明生产者身份、真实运行或原始计数确实按记录参与拟合。另传给 `audit-de` 的 DE 表、样本表必须与合同文件逐字节一致；内存 DataFrame 或 AnnData 无法在这个文件绑定适配器中获得这种等价性，不能借另一份样本表绕过核对。

## 来源和判定是两个维度

| 来源 `source` | 含义 |
| --- | --- |
| `ARTIFACT_EXTRACTED` | 从提供的文件内容提取或重新计算。 |
| `EXTERNAL_RECORD_CHECKED` | 对提供的执行记录、文件摘要及相互一致性做检查；不表示已经访问或认证外部执行服务。 |
| `RESEARCHER_DECLARED` | 研究者声明，保留原文。当前的人群外推/因果适配器不会把声明升级为通过。 |
| `MISSING` | 所需产物或事实没有提供。 |

每项条件另有 `SATISFIED / UNSATISFIED / CONFLICT / NOT_ASSESSED` 判定、要求、方法、文件引用、观测值、检查范围和修复建议。缺文件、无法解释的编码与缺置信区间保留未评估；字节或方向记录不一致保留冲突。不能用一个总分相互抵消。聚合显示优先级为冲突、不满足、未评估、满足，原始条件不会被丢弃。

## 实际执行哪些检查

1. **目标绑定。** 结果行必须唯一匹配基因、细胞集合及有序比较；相同基因的其他细胞群或反向对比不能代替。
2. **统计单位。** 样本 ID 唯一且与模型行一一对应。独立供体模式要求每位供体一行；配对模式要求每位供体恰好有两种条件各一行，并在设计中具有供体固定效应。这里核对标识结构，不认证真实供体身份，也不证明独立抽样。
3. **真实设计。** 依据样本表和显式列编码重新构建设计矩阵，检查与所提供数值矩阵是否相同。仅支持 `~ 1 + ...` 的加性数值协变量及 treatment-coded 分类变量。
4. **对比身份与可估计性。** 从条件编码推导分子减分母的向量，要求干扰项权重为零。对实际矩阵做 SVD，检查对比是否位于行空间；同时单列满秩和剩余自由度检查。可估计性与满秩不是同一件事。
5. **文字需要的结果事实。** 有限 log2 效应的符号、调整后 P 值、区间与效应一致性、区间方向及置信水平分别检查。缺区间不会由小 P 值自动补齐；跨零不会被解释为没有效应。

SVD 先按列 L2 范数缩放，使用机器精度相关秩容差，并记录对比投影的相对残差和 `1e-8` 容差。病态、接近容差的设计仍需要数值与领域复核；通过不证明模型适用。

统计设计参考：DESeq2 作者的[模型矩阵、混淆与配对设计说明](https://github.com/thelovelab/DESeq2/blob/devel/vignettes/DESeq2.Rmd)；estimability 包作者对[行空间可估计性](https://stat.ethz.ch/CRAN/web/packages/estimability/vignettes/add-est-check.html)的说明。此实现的双条件、加性编码限制是本适配器的覆盖范围，不是声称其他有效研究设计不成立。

## 从一个等级到一组具体表述

每条输入声明都生成独立的范围评估与必要条件清单：

- `table_observation`：只陈述所提供表中的数值及方向。
- `cohort_association`：在所提供模型下、所分析队列中的关联。必须满足产物绑定、设计、统计单位、对比、方向、不确定性和显著性检查。
- `population_effect`：在上述检查之外，需要人群外推前提；v1 保留未评估。
- `causal_effect`：在队列检查之外，需要因果识别前提；v1 保留未评估。因果范围并不自动要求人群外推，也不能用供体数量替代因果识别。

`supported_within_checked_scope=true` 仅表示该表述的**已实现必要条件**通过。它不意味着整个科学命题已被证明或已获得发表授权。下游必须保留完整的 `conditions`、`unmet_conditions` 和顶层限制，不能只取这一布尔值生成“已科学验证”。

## 可重跑验收与证据上限

[示例目录](../examples/de-claim-conditions/README.md) 包含三份**结果表逐字节相同**的包：有效加性设计、批次完全混淆设计、缺设计文件。预期队列条件分别为满足、不满足、未评估；三者都可保留表内正向数值事实。

测试还覆盖配对供体、重复供体、样本重排、伪造列编码、反向对比、结果替换、重复键、路径越界、缺/错区间、多声明、CLI 与审阅包。它们属于本地工程验收，不是外部研究验证。

目前未完成原始计数聚合核验、DE 模型重拟合、P 值/区间重算、随机效应及交互模型、人群运输或因果识别验证，也没有认证运行生产者。输出始终保留 `scientific_authorization=NONE`、`producer_authentication=NOT_ESTABLISHED`、`analysis_execution_verification=NOT_PERFORMED`。真正的外部科研收益仍需冻结研究任务、独立审阅及完整人工成本评估。
