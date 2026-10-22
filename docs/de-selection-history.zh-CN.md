# 分析选择历史：结果是怎样被选出的

这是开发工作区中的有界、被动审阅接口，未激活 GA 支持。它接收宿主导出的最小事件记录，不接管研究工作流，也不采集完整聊天。

先前两层回答“给定分析的声明前提是否满足”以及“结论对合理替代分析有何依赖”。本层增加第三个问题：**最终表格与声明，是在怎样的结果暴露和选择过程中确定的？**

相同的 DE 数值可以有不同的用途。预先记录的分析与看到结果后选择的分析，均可保留符合原有证据边界的描述；后者不能仅凭原表的普通显著性声称完成确认性检验。该区分沿用 [Nosek 等关于预注册与探索/确认的论述](https://www.pnas.org/doi/10.1073/pnas.1708274114)。有限验证反馈在专门条件下可以支持自适应研究，但不能把任意验证集复用都当作普通独立验证，参见 [The Generic Holdout](https://arxiv.org/abs/1809.05596)。本实现不执行这些论文中的统计校正算法。

## 输入与输出

```powershell
bionexus audit-de --de-table results.csv --sample-sheet metadata.csv --claim-contract contract.json --selection-history history.json --bundle new-review
```

可附加 `--selection-expected-head <独立保留的摘要>`，以及前一层的 `--alternative-plan` / `--alternative-runs`。退出码仍遵循原审计合同，资料不全或需修订时返回 1。一致的历史不保证整体审计通过，更不构成科学授权。

Python 接口位于 `bionexus.de.selection`：

```python
from bionexus.de.selection import seal_selection_history, evaluate_selection_history

# manifest 和 events 来自宿主显式导出；封装过程不证明事件真实发生。
history = seal_selection_history(manifest, events)
# 保存 history JSON 后审阅；所有产物引用均相对历史文件目录。
review = evaluate_selection_history(
    "history.json", claim_contract="contract.json",
    alternative_plan="alternatives/plan.json",
)
```

无历史时 `evaluate_selection_history()` 返回 `NOT_ASSESSED`。普通 `audit-de` 输出同样明确保留这个状态，不把缺日志解释为“没有选择偏差”。

| 历史判断 | 意义 | 确认性用途 |
|---|---|---|
| `PRE_RESULT_PLAN_RECORDED` | 在声明的捕获范围内，存在早于所记录结果的匹配计划 | `NOT_ESTABLISHED`：无独立真实性、完整性认证 |
| `SELECTION_DEPENDENCE_RECORDED` | 记录显示结果暴露后选择、计划偏离或验证污染风险 | `EXPLORATORY_ONLY_FOR_RECORDED_SELECTION`：本合同不支持据此升级确认性用途 |
| `HISTORY_INCOMPLETE` | 分支、捕获范围、绑定或时间关系存在缺口 | `NOT_ESTABLISHED` |
| `NOT_ASSESSED` | 没有历史 | `NOT_ESTABLISHED` |
| `INVALID_HISTORY` | 审计适配器无法解析或验证输入 | 必需检查失败；不按通过处理 |

这些状态不是研究诚信裁决，也不证明效应错误。探索性报告仍受原声明条件约束；因果、总体外推等缺失前提不会被选择历史补齐。

## 最小事件合同

机器合同是 `src/bionexus/data/de-selection.v1.schema.json`。每个事件只含 `actor_id`、`session_id`、`kind` 和该种事件专属 `payload`。事件编号与前序哈希由封装器产生，拒绝未知字段、重复 JSON 键、非有限数值和非法状态转换。

| kind | 核心 payload | 检查 |
|---|---|---|
| `branch_planned` | `branch_id`, `role`, `plan` 文件引用 | 新分支；候选结果或补充敏感性分析 |
| `plan_revised` | 分支、新计划、`parent_sha256`, `reason` | 必须延续当前版本；已有结果后需新建分支 |
| `result_available` | 分支、`contract` 文件引用 | 产物绑定；计划与实际结构化声明、队列、模型字段一致 |
| `result_viewed` | 分支 | 必须先有结果；查看不同于仅已生成 |
| `branch_discarded` | 分支、`decision_basis`, `reason` | 保留放弃原因和结果知情状态 |
| `result_selected` | 分支、`decision_basis`, `reason` | 单一最终候选结果；必须与正在审计的结果合同一致 |
| `data_accessed` | 数据集、`access=metadata/outcomes` | 查看元数据不同于接触结局；结局指对研究者/Agent 可见的结果信息 |
| `holdout_evaluated` | 验证集、分支 | 对研究者/Agent 返回验证反馈的一次逻辑评估 |
| `alternative_plan_frozen` | 替代分析计划引用 | 将突破二的确切计划关联到已记录暴露顺序 |

`decision_basis` 为 `predeclared`、`operational` 或 `result_informed`。这是声明，不能覆盖序列中已有的相反证据。宿主应将一次逻辑评估的网络重试去重；重复回放事件不是新的统计实验。本接口没有根据传输 ID 自动证明或恢复宿主的去重。

候选分支之间的结果暴露按同一研究范围保守传播，不能通过更换 Agent 或 session 清零。`sensitivity` 分支须披露，但不能被选择为主要结果；事后的敏感性诊断不会自动将原预定主结果改判为事后挑选。更广的多声明依赖图、不同研究问题之间的精细因果归属尚未实现，应拆分并明确声明审阅范围。

计划文件先固定 `analysis`、完整结构化 `claims`、元数据摘要、`model.formula/statistical_unit/effect_measure`，以及 `selection_rule=report_all_planned_claims`。这允许在结果不存在时保存计划；不能用包含结果哈希的最终合同充当事前计划。未实现对全部软件参数、标准化、基因过滤和潜在搜索空间的完整冻结。不能将 `PRE_RESULT_PLAN_RECORDED` 解释为“全部自由度已经控制”。

## 捕获覆盖、完整性与验证集

`manifest` 明确 `scope_id`、actor/session 清单、分支总清单、`capture_mode`、`coverage`、`gaps`、数据集与 `synthetic`。`complete_declared` 只是完整性声明；空白历史、回顾性导出、缺少分支和未决分支都不会消失。结果报告保留计划数、已记录数、缺失 ID、选中/放弃/未决数量。

每个数据集通过摘要绑定 CSV `sample_id,donor_id`，并声明 `identity_namespace`。发现集成员必须与最终合同中的实际元数据对应；同一命名空间内按供体或样本重叠检查验证污染，同一文件改名或换数据集 ID 不能洗掉复用记录。不同命名空间无法确认真实身份一致性时，保持 `HOLDOUT_IDENTITY_NOT_COMPARABLE`。成员不重叠仍不证明统计独立、来源独立或生物学外推有效。

在验证反馈前暴露原始结局、重复返回验证反馈，以及发现集/验证集重叠会明确显示。最终验证后为报告而查看数据，保留暴露记录但不会单独否定此前固定的主分析。若随后再次基于它修改候选分析，新的选择仍会被标记。

事件顺序以导出的序列为准，不接受任意填写的时间戳作为事前证据。哈希链验证内部一致性；外部保留的最终 head 可以发现与该 head 不一致的截断或重写。**二者均不能证明事件真实发生、早于现实结果，或没有漏记其他工作区、人员、会话及线下交流。** `seal_selection_history` 可以封装回顾性材料，不能赋予预注册身份。真实宿主的实时捕获、可信时间来源、独立锚定和覆盖审阅仍是后续外部验证工作。

## 复现与接受标准

```powershell
python examples/de-selection/build_examples.py --out new-synthetic-selection-demo
```

生成五个标记为 `synthetic=true` 的反事实情景：事前计划、结果知情选择、部分捕获、验证集改名复用、事后补充敏感性分析。其最终结果和声明合同逐字节相同，选择用途判断不同。它们不含真实研究活动或独立预注册，也没有重新拟合模型；不能补进此前真实或合成分析中缺失的历史。

已实现的接受标准包括：

- 相同结果文件保持相同效应、P 值、条件判断，选择历史改变确认性用途边界。
- 已放弃及缺失分支留在清单中；不通过增加日志数量制造独立证据。
- 重排、修改、未绑定的产物及不可能的状态转换不能通过一致性检查；整体重写必须有独立 head 才可与历史承诺比较。
- 缺少日志不获“无选择偏差”结论；诚实披露探索不被自动转成数值事实错误。
- 不按尝试次数机械调整 P 值，不输出选择后推断有效性证明。

真实实验室中的漏记率、错误限制率、跨宿主覆盖和是否改善研究决策仍待实证评估。本实现和测试不能建立这些效果。
