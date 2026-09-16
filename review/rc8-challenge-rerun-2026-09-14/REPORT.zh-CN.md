# rc.8 回放 09-08 的 54 个审计案例

**预定义终点没有翻盘。** `bionexus_full` 仍是有效保留 **0/12**、错误放行 **0/42**。联合改善条件为：有效保留上升 **且** 错误放行不上升。后半满足，前半不满足，故 `joint_improvement = false`。

这不是“rc.8 什么都没改”。声明核对和产物绑定都更严、更准；有效案例仍被 **执行凭证词表/缺字段 + 未降级的 BFA-001c** 挡住，过不了 `ROBUST_PASS`。

## 1. 这次实际跑了什么

| 项 | 值 |
|---|---|
| 引擎 | `fffd792`（`v1.0.0-rc.8`），142 个源文件拷入 `rc8-source/` 后从该树导入 |
| 案例 | 只读回放 `review/methods-experiments-2026-09-08/run-01/challenge/cases/` 的 54 个文件夹 |
| 通过定义 | 与 09-08 相同：`accepted = (overall_status == "ROBUST_PASS")` |
| 09-08 freeze / run-01 | 未改写 |
| 耗时 | 20.89 s（`run-01/execution-end.json`） |
| 科学授权 | `NONE` |

主结果与探索臂：

| 臂 | 有效保留 | 错误放行 | 角色 |
|---|---:|---:|---|
| 09-08 `bionexus_full` | 0/12 | 0/42 | 冻结对照 |
| rc.8 `bionexus_full` | **0/12** | **0/42** | **预定义主终点** |
| rc.8 `COMPLETE→COMPLETED` 同义词 | 0/12 | 0/42 | 探索，不是确认 |
| 确定性清单 | 12/12 | 33/42 | 与 09-08 相同的非产品对照 |

原始 09-08 探索消融（把 BFA-001c 降为 ADVISORY）曾得到 9/12 有效保留、24/42 错误放行。那是用有效结论换假放行，不是联合改善。本次 rc.8 **没有**重复那种交换。

## 2. 主终点为什么仍是 0/12

以 `valid_positive-0`（“IL1RN is upregulated and significant after FDR…”）为例。

**09-08 挡住它的两条 HIGH_IMPACT：**

1. BFA-001c 极小 P 启发式  
2. BFA-008：把上调/显著误判成因果声明  

**rc.8 主臂：**

- 声明微观事实：`claim_fact_concordance = ASSESSED`（方向和显著性与表一致）
- 声明边界：`claim_targeted_warrant = ASSESSED`，`causal_claim` 不再被请求；BFA-008 **消失**
- 仍失败：`analysis_execution_binding = ISSUE_FOUND`（`fit_status=COMPLETE` 不在 rc.8 允许的 `SUCCESS|SUCCEEDED|CONVERGED|COMPLETED|PASS|PASSED|OK`）
- 供体级执行因此不算核验成功，BFA-001c **不能**降为 ADVISORY，保持 HIGH_IMPACT
- `_compute_overall_status` 遇 HIGH_IMPACT 或 required check `ISSUE_FOUND` → `NEEDS_REVISION`，不是 `ROBUST_PASS`

12 个有效案例（positive / negative / limited / table_presence × 3 种措辞）全部是这条路径。`valid_limited` 的免责声明已被正确当作 limitation，不再当生物学阴性结果，但同样过不了执行绑定。

同义词臂把 `COMPLETE` 改成 `COMPLETED` 后，绑定失败变成 **缺少 `donor_ids`**（09-08 收据只有 `n_donors=8`，没有 rc.8 要求的非空供体 ID 列表）。BFA-001c 仍不降级。所以 **不是单字母词表就能翻盘**。

## 3. 错误放行没有变差；若干无效家族更硬

错误放行保持 0/42。六个无效家族从 `NEEDS_REVISION` 升到 `BLOCKER_DETECTED`（每家族 3 例，共 18 例）：

`changed_result`，`failed_fit`，`invalid_probability`，`missing_fdr`，`wrong_design`，`wrong_result_hash`

这是产物绑定收紧，不是有效保留。

表事实类无效案例现在能点到具体声明，而不只靠 BFA-001c：

| 家族 | rc.8 `claim_fact_concordance` |
|---|---|
| `absent_gene`（3/3） | ISSUE_FOUND：基因不在表中 |
| `wrong_direction`（3/3） | ISSUE_FOUND：方向/显著性与表矛盾 |
| `false_significance`（3/3） | ISSUE_FOUND |
| `false_negative`（3/3） | ISSUE_FOUND |
| `false_global_null-0/2` | ISSUE_FOUND |
| `false_global_null-1` | MISSING_EVIDENCE：该条改写触发复合/否定无法唯一绑定 |
| `causal_overclaim`（3/3） | 表事实 ASSESSED；`claim_targeted_warrant = ISSUE_FOUND`（因果仍被拦住） |

09-08 报告写过：不存在的基因、方向错误等当时仍可能被标成 ASSESSED。rc.8 在这些家族上把定位补上了。这改变的是**拒绝原因是否正确**，不是 0/12 vs 0/42 的联合计数。

## 4. 这不能支持的句子

- “rc.8 已实现低错误率且保留有效结论”
- “净收益已由本回放证明”
- “只要用户把 COMPLETE 改成 COMPLETED 就能通过”
- 独立专家标签、实验室人分钟、外部复现

本回放是开发者家族标签上的软件对照，不是实验室试点。

## 5. 对净收益叙事的含义

rc.8 修对了 09-08 里那条**假因果误拦**（valid 上调句不再变 BFA-008），也修对了若干**表事实/哈希/拟合失败**的定位。  
它**没有**让冻结收据跨过新的执行绑定合同，因此 BFA-001c 仍在全部含 Kang 配对表的案例上保持 HIGH_IMPACT，有效保留锁死在 0。

联合计数与 09-08 主结果相同。净收益叙事**不能**用 rc.8 翻盘。

若下一步还要回答“绑定合同满足后有效案例会不会通过”，必须另开研究、预声明收据字段（至少 `fit_status` 词表 + `donor_ids`），**不得**回写本次冻结案例或 09-08 `run-01/`。那会是新实验，不是本回放的一部分。
