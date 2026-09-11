# BioNexus 证据审计报告：多供体单细胞差异表达

> **审计状态**：`NEEDS_REVISION` | **通过**：`False` | **阻断性问题**：0 | **高风险问题**：1 | **方法学建议**：0

## 实验设计与队列概况
- **供体总数 (Donors)**: 6
- **细胞总数 (Cells)**: 6
- **组别分布 (Conditions)**: control: 3 供体, treated: 3 供体

## 检查覆盖 (Assessed / Issue Found / Missing Evidence)
| 检查项 | 状态 | 说明 | 通过所必需 |
| :--- | :--- | :--- | :--- |
| 供体/生物学重复设计 | 已检查 (`ASSESSED`) | 已检查样本设计：control N=3, treated N=3。 | yes |
| 供体细胞贡献失衡 | 缺少证据 (`MISSING_EVIDENCE`) | 未提供细胞类型列，供体失衡未评估。 | no |
| 批次与组别混杂 | 缺少证据 (`MISSING_EVIDENCE`) | 未提供批次列，混杂未评估。 | no |
| 原始整数计数层 | 缺少证据 (`MISSING_EVIDENCE`) | 未提供表达矩阵，计数层未评估。 | no |
| 差异表达结果表 | 已检查 (`ASSESSED`) | 已读取 2 行差异表达结果（来源: de_table）。 | yes |
| FDR / 多重检验 | 发现问题 (`ISSUE_FOUND`) | 已检查 DE 表：缺失、非法或未使用 FDR 校正。 | yes |
| 分析脚本/笔记本 | 缺少证据 (`MISSING_EVIDENCE`) | 未提供分析脚本，静态方法学调用未评估。 | no |
| 分析事实与执行记录绑定 | 缺少证据 (`MISSING_EVIDENCE`) | 未提供经核查的供体级执行记录（统计单位、设计矩阵、拟合状态未绑定）。 | yes |
| 科学声明定向审计 | 已检查 (`ASSESSED`) | 声明符合当前证据支持边界：Claim 'CLAIM-USER-DE' Epistemic Evaluation: Warranted tiers: [association_claim]; Unwarranted tiers: [none]. Not requested: [population_claim, mechanistic_claim, causal_claim, cell_identity_claim, clinical_claim, structural_conformation_claim, bioactive_binding_claim]. Max warranted class: 'descriptive', ceiling: 'SUPPORTED'. | no |

## 1. 哪个问题会影响当前结论 (Issues Affecting Conclusions)
### [HIGH_IMPACT] 缺失 FDR 多重假设检验校正 (Missing FDR / Adjusted P-value) (`BFA-003`)
> [!WARNING]
> **对结论的影响**：差异分析结果表中仅报告了原始 p 值，未进行 Benjamini-Hochberg (FDR) 校正。单细胞转录组同时检验数万个基因，若仅以 p < 0.05 筛选，存在成百上千个假阳性基因被当做真实生物学发现的风险。

## 2. 问题对应哪个样本、步骤或声明 (Sample, Step & Claim Mapping)
| 编号 | 审计问题 | 对应样本/供体 | 对应分析步骤/代码 | 对应声明受损 |
| :--- | :--- | :--- | :--- | :--- |
| 1 | 缺失 FDR 多重假设检验校正 (Missing FDR / Adjusted P-value) | - | `Differential Expression Post-processing` | - |

## 3. 最小修复是什么 (Minimal Actionable Fixes)
#### 针对问题 1（缺失 FDR 多重假设检验校正 (Missing FDR / Adjusted P-value)）：
```python
from statsmodels.stats.multitest import multipletests
_, padj, _, _ = multipletests(de_df['pvalue'], method='fdr_bh')
de_df['padj'] = padj
sig_degs = de_df[de_df['padj'] < 0.05]
```

## 4. 当前可以陈述到什么范围 (Permissible Scientific Claim Scope)
> [!TIP]
> **允许陈述的科学范围**：
> 只能确认已检查的输入（6 donors; condition counts control=3, treated=3）。缺少差异表达执行记录或结果时，不得陈述已完成的群体差异表达。

> [!WARNING]
> **严禁越界声称的范围**：
> 严禁把未提供的矩阵、模型或 DE 结果写成已经执行的 NB GLM、Wald 或 BH 校正。

### 已执行方法 vs 建议分析
**Executed methods (past tense only from execution records)**:
> "A DE table with 2 rows was supplied and inspected."

**Recommended analysis (not claimed as completed)**:
> "Recommended analysis, not recorded as performed: aggregate raw integer counts to donor-level pseudobulks per cell type (Squair et al., 2021), then test condition effects with a negative binomial GLM, Wald tests, and Benjamini-Hochberg FDR. Do not treat cell-level rank_genes_groups p-values as population inference."

**Results phrasing**:
> "Only inspected design or partial artifacts are described; differential-expression execution was not confirmed."

---
*BioNexus Scientific Assertion Firewall (BNS-013 / BNS-015)*
