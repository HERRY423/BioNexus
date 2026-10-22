"""
Metadata audit rules for multi-donor single-cell differential expression.

Audits biological replicates, donor dominance/imbalance, and batch confounding.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional

from bionexus.de.models import (
    CheckRecord,
    CheckStatus,
    DEFinding,
    FindingCategory,
    FindingSeverity,
    PIDecisionItem,
)

if TYPE_CHECKING:
    import pandas as pd
else:
    try:
        import pandas as pd
    except ImportError:
        pd = None


def _record_metadata_checks(
    checks: List[CheckRecord],
    findings: List[DEFinding],
    d_col: Optional[str],
    c_col: Optional[str],
    ct_col: Optional[str],
    b_col: Optional[str],
    cond_donor_counts: Dict[str, int],
) -> None:
    """Record metadata checks for replicates, imbalance, and batch confounding."""
    replicate_ids = {"BFA-001", "BFA-001b", "BFA-005"}
    if any(f.rule_id in replicate_ids for f in findings):
        min_n = min(cond_donor_counts.values()) if cond_donor_counts else 0
        checks.append(
            CheckRecord(
                check_id="donor_replicates",
                title="供体/生物学重复设计",
                status=CheckStatus.ISSUE_FOUND,
                summary=f"已检查样本设计：每组最少 {min_n} 个供体。",
                required_for_pass=True,
            )
        )
    else:
        summary = ", ".join(f"{k} N={v}" for k, v in cond_donor_counts.items()) or "condition counts unavailable"
        checks.append(
            CheckRecord(
                check_id="donor_replicates",
                title="供体/生物学重复设计",
                status=CheckStatus.ASSESSED,
                summary=f"已检查样本设计：{summary}。",
                required_for_pass=True,
            )
        )

    if not ct_col:
        checks.append(
            CheckRecord(
                check_id="donor_imbalance",
                title="供体细胞贡献失衡",
                status=CheckStatus.MISSING_EVIDENCE,
                summary="未提供细胞类型列，供体失衡未评估。",
                required_for_pass=False,
            )
        )
    elif any(f.rule_id == "BFA-007" for f in findings):
        checks.append(
            CheckRecord(
                check_id="donor_imbalance",
                title="供体细胞贡献失衡",
                status=CheckStatus.ISSUE_FOUND,
                summary="已检查细胞类型内供体分布：存在单一供体主导。",
                required_for_pass=False,
            )
        )
    else:
        checks.append(
            CheckRecord(
                check_id="donor_imbalance",
                title="供体细胞贡献失衡",
                status=CheckStatus.ASSESSED,
                summary="已检查细胞类型内供体分布，未见超过阈值的单一供体主导。",
                required_for_pass=False,
            )
        )

    if not b_col:
        checks.append(
            CheckRecord(
                check_id="batch_confounding",
                title="批次与组别混杂",
                status=CheckStatus.MISSING_EVIDENCE,
                summary="未提供批次列，混杂未评估。",
                required_for_pass=False,
            )
        )
    elif any(f.rule_id == "BFA-004" for f in findings):
        checks.append(
            CheckRecord(
                check_id="batch_confounding",
                title="批次与组别混杂",
                status=CheckStatus.ISSUE_FOUND,
                summary="已检查：组别与批次完全混杂。",
                required_for_pass=False,
            )
        )
    else:
        checks.append(
            CheckRecord(
                check_id="batch_confounding",
                title="批次与组别混杂",
                status=CheckStatus.ASSESSED,
                summary="已检查批次与组别交叉表，未见完全混杂。",
                required_for_pass=False,
            )
        )


def _audit_metadata(
    obs_df: pd.DataFrame,
    d_col: Optional[str],
    c_col: Optional[str],
    ct_col: Optional[str],
    b_col: Optional[str],
    findings: List[DEFinding],
    pi_decisions: List[PIDecisionItem],
    cohort_summary: Dict[str, Any],
    checks: List[CheckRecord],
    dominance_threshold: float = 0.70,
    min_donors_required: int = 3,
    min_cells_per_donor: int = 20,
) -> None:
    """Audit biological replicates, donor imbalance, and batch confounding."""
    cohort_summary["n_cells"] = len(obs_df)

    if not d_col:
        findings.append(
            DEFinding(
                rule_id="BFA-005",
                severity=FindingSeverity.BLOCKER,
                category=FindingCategory.DONOR_REPLICATES,
                title="缺失供体/生物学重复标识 (Missing Biological Replicate Identifiers)",
                impact_on_conclusion="元数据中未发现供体/样本列，无法区分细胞间变异与供体间真实生物学变异。直接进行组间差异分析构成纯粹伪重复，产出大量假阳性基因。",
                step_or_location="sample_metadata / adata.obs",
                minimal_fix="在 adata.obs 中补充供体标识列（例如 adata.obs['donor_id'] = ...），确保每个细胞可归属至具体生物学个体。",
            )
        )
        checks.append(
            CheckRecord(
                check_id="donor_replicates",
                title="供体/生物学重复设计",
                status=CheckStatus.ISSUE_FOUND,
                summary="元数据中未发现供体/样本列。",
                required_for_pass=True,
            )
        )
        checks.append(
            CheckRecord(
                check_id="batch_confounding",
                title="批次与组别混杂",
                status=CheckStatus.MISSING_EVIDENCE,
                summary="无供体列，批次混杂未评估。",
                required_for_pass=False,
            )
        )
        checks.append(
            CheckRecord(
                check_id="donor_imbalance",
                title="供体细胞贡献失衡",
                status=CheckStatus.MISSING_EVIDENCE,
                summary="无供体列，供体失衡未评估。",
                required_for_pass=False,
            )
        )
        return

    donors = obs_df[d_col].unique()
    cohort_summary["n_donors"] = len(donors)
    cohort_summary["donors"] = list(donors)

    if not c_col:
        findings.append(
            DEFinding(
                rule_id="BFA-012",
                severity=FindingSeverity.ADVISORY,
                category=FindingCategory.CLAIM_BOUNDARY,
                title="未指定实验对比组别 (Condition Column Undetermined)",
                impact_on_conclusion="未指定或未能自动推断 condition/disease 列，仅能审计聚类内部各供体的细胞分布特征。",
                minimal_fix="使用参数 --condition-col <列名> 指定实验对照分组（如 Disease vs Healthy）。",
            )
        )
        checks.append(
            CheckRecord(
                check_id="donor_replicates",
                title="供体/生物学重复设计",
                status=CheckStatus.MISSING_EVIDENCE,
                summary=f"已识别 {len(donors)} 个供体，但未指定 condition 列，组别重复未评估。",
                required_for_pass=True,
            )
        )
        checks.append(
            CheckRecord(
                check_id="batch_confounding",
                title="批次与组别混杂",
                status=CheckStatus.MISSING_EVIDENCE,
                summary="无组别列，批次混杂未评估。",
                required_for_pass=False,
            )
        )
        checks.append(
            CheckRecord(
                check_id="donor_imbalance",
                title="供体细胞贡献失衡",
                status=CheckStatus.MISSING_EVIDENCE if not ct_col else CheckStatus.ASSESSED,
                summary="无组别列，仅能描述供体细胞分布。" if not ct_col else "已检查细胞类型内供体分布。",
                required_for_pass=False,
            )
        )
        return

    # 1. Biological replicates per condition
    cond_donor_counts: Dict[str, int] = {}
    for cond, sub in obs_df.groupby(c_col, observed=False):
        cond_donor_counts[str(cond)] = sub[d_col].nunique()
    cohort_summary["conditions"] = cond_donor_counts

    min_donors = min(cond_donor_counts.values()) if cond_donor_counts else 0

    if min_donors < 2:
        findings.append(
            DEFinding(
                rule_id="BFA-001",
                severity=FindingSeverity.BLOCKER,
                category=FindingCategory.DONOR_REPLICATES,
                title=f"生物学重复严重不足 (N={min_donors} < 2 Replicates per Condition)",
                impact_on_conclusion=f"至少有一个实验组别仅有 {min_donors} 个供体/动物。统计学自由度为 0，无法估算组内真实生物学离散度（Biological Dispersion）。任何观察到的差异基因均可能来自个体的私有特征。",
                sample_or_donor=", ".join([f"{k} (N={v})" for k, v in cond_donor_counts.items() if v < 2]),
                step_or_location="Experimental Design / Sample Intake",
                minimal_fix=(
                    "# 无法仅靠算法修正零生物学重复缺陷：\n"
                    "# 1. 必须补测至少 2~3 例独立生物学重复；\n"
                    "# 2. 若无法补测，必须在文稿中明确降级为「单个病人的探索性观察 (Exploratory Case Study)」，严禁声称任何群体结论。"
                ),
                evidence_data={"donors_by_condition": cond_donor_counts},
            )
        )
    elif min_donors == 2:
        findings.append(
            DEFinding(
                rule_id="BFA-001b",
                severity=FindingSeverity.HIGH_IMPACT,
                category=FindingCategory.DONOR_REPLICATES,
                title="生物学重复临界不足 (N=2 Replicates per Condition)",
                impact_on_conclusion="每组仅有 2 个生物学重复。虽然可运行 DESeq2/EdgeR，但方差估计完全依赖基因间的经验贝叶斯收缩（Empirical Bayes Shrinkage），检出力较低且易受离群值干扰。只能作为初步探索，不足以支持稳健人群外推。",
                sample_or_donor=", ".join([f"{k} (N={v})" for k, v in cond_donor_counts.items() if v == 2]),
                step_or_location="Experimental Design",
                minimal_fix=(
                    "# 最小修复与风险声明：\n"
                    "# 1. 推荐将队列扩充至 N >= 3 供体/组；\n"
                    "# 2. 在论文中声明结果为探索性（Exploratory），并在关键基因上补充 qPCR 或流式正交验证。"
                ),
                evidence_data={"donors_by_condition": cond_donor_counts},
            )
        )
        pi_decisions.append(
            PIDecisionItem(
                decision_id="PI-DEC-01",
                title="N=2 供体实验设计结论定性裁决",
                context=f"当前每组仅有 2 例供体 ({cond_donor_counts})，低于 Nature/Cell 子刊对群体单细胞差异表达默认推荐的 N>=3 门槛。",
                option_a="[推荐] 保持现有数据，但在文稿 Results 中将结论严格界定为「队列内部探索性候选基因 (Exploratory Candidate Set)」，严禁使用因果或普适标志物措辞；",
                option_b="暂停投稿，补测同批次 1~2 例同质供体后再行合并分析。",
                tradeoff_explanation="选项 A 可快速推进组会交流或预印本发布，但正式审稿大概率被要求补样；选项 B 可一劳永逸达到审稿标准。",
                recommended_option="A",
            )
        )

    # 2. Donor cell dominance / Imbalance per cell type
    if ct_col:
        imbalanced_clusters: list[dict[str, Any]] = []
        low_count_donors: list[dict[str, Any]] = []
        for ct_val, ct_sub in obs_df.groupby(ct_col, observed=False):
            if ct_sub.empty:
                continue
            total_cluster_cells = len(ct_sub)
            donor_counts = ct_sub[d_col].value_counts()
            max_donor = donor_counts.index[0]
            max_frac = donor_counts.iloc[0] / total_cluster_cells if total_cluster_cells > 0 else 0

            if max_frac >= dominance_threshold and total_cluster_cells >= 50:
                imbalanced_clusters.append({
                    "cell_type": str(ct_val),
                    "dominant_donor": str(max_donor),
                    "fraction": round(float(max_frac), 3),
                    "donor_cells": int(donor_counts.iloc[0]),
                    "total_cells": int(total_cluster_cells),
                })

            # Check for low count donors (< 10 cells)
            for d_id, c_count in donor_counts.items():
                if c_count < 10:
                    low_count_donors.append({
                        "cell_type": str(ct_val),
                        "donor": str(d_id),
                        "count": int(c_count),
                    })

        if imbalanced_clusters:
            top_imb = imbalanced_clusters[0]
            findings.append(
                DEFinding(
                    rule_id="BFA-007",
                    severity=FindingSeverity.HIGH_IMPACT,
                    category=FindingCategory.DONOR_IMBALANCE,
                    title=f"单一供体细胞占比极端倾斜 (Extreme Donor Imbalance: {top_imb['cell_type']})",
                    impact_on_conclusion=f"在「{top_imb['cell_type']}」细胞类型中，供体 {top_imb['dominant_donor']} 贡献了 {top_imb['fraction']*100:.1f}% 的细胞。差异表达分析得到的所谓「组间标志物」，极大可能只是该特定供体的私有基因表达特征（Donor Private Transcriptome）。",
                    sample_or_donor=f"供体 {top_imb['dominant_donor']} 在细胞群「{top_imb['cell_type']}」中",
                    step_or_location="Cell type subsetting / Pseudobulk input",
                    minimal_fix=(
                        f"# 最小修复（按供体聚合为 Pseudobulk，使各供体平权）：\n"
                        f"# 1. 严禁直接在该亚群运行单细胞 Wilcoxon 检验；\n"
                        f"# 2. 执行 Leave-One-Donor-Out 敏感性分析，验证剔除供体 {top_imb['dominant_donor']} 后 DEG 列表重合度是否 > 75%。"
                    ),
                    evidence_data={"imbalanced_clusters": imbalanced_clusters},
                )
            )
            pi_decisions.append(
                PIDecisionItem(
                    decision_id="PI-DEC-02",
                    title=f"{top_imb['cell_type']} 亚群单一供体主导处理裁决",
                    context=f"供体 {top_imb['dominant_donor']} 在该亚群占 {top_imb['fraction']*100:.1f}% 细胞，其他供体细胞数偏低。",
                    option_a=f"[推荐] 采用 Pseudobulk 求和平权，并附上剔除 {top_imb['dominant_donor']} 前后的 DEG 灵敏度对比图；",
                    option_b="若该细胞群在其他供体中极少发生，考虑在正文中明确将其归为「供体特异性扩张亚群 (Donor-Specific Expansion)」，而非通用疾病相关亚群。",
                    tradeoff_explanation="选项 A 能保全该亚群的统计检验；选项 B 能诚实规避被审稿人质疑挑选特例的风险。",
                    recommended_option="A",
                )
            )

    # 3. Batch vs Condition Confounding (100% Confounded design)
    if b_col:
        contingency = pd.crosstab(obs_df[c_col], obs_df[b_col])
        cohort_summary["batches"] = len(obs_df[b_col].unique())
        # Check if condition is completely collinear with batch
        is_perfectly_confounded = bool((contingency.gt(0).sum(axis=0) <= 1).all())

        if is_perfectly_confounded and len(contingency) > 1:
            findings.append(
                DEFinding(
                    rule_id="BFA-004",
                    severity=FindingSeverity.BLOCKER,
                    category=FindingCategory.BATCH_CONFOUNDING,
                    title="实验组别与技术批次 100% 完全混杂 (Complete Batch Confounding)",
                    impact_on_conclusion="疾病组与对照组完全在不同的技术批次/测序泳道中进行（如全部 Control 在 Batch 1，全部 Disease 在 Batch 2）。在数理上完全无法区分差异表达是由生物学疾病引起，还是由测序仪/反应批次噪声导致。",
                    sample_or_donor=", ".join([f"批次 {b}" for b in obs_df[b_col].unique()]),
                    step_or_location="Experimental Design / Batch Allocation",
                    minimal_fix=(
                        "# 完全混杂无法通过数学模型完全脱敏：\n"
                        "# 1. 严禁声称任何因果或生物学特异性差异表达；\n"
                        "# 2. 最优解：在同一批次中重新对部分样本进行平行测序；\n"
                        "# 3. 次优解：在文稿讨论中明确列为主要局限，并仅将表达方向与已有公共数据集（如 GSE 权威队列）一致的基因列为潜在候选。"
                    ),
                    evidence_data={"contingency_matrix": contingency.to_dict()},
                )
            )

    _record_metadata_checks(
        checks=checks,
        findings=findings,
        d_col=d_col,
        c_col=c_col,
        ct_col=ct_col,
        b_col=b_col,
        cond_donor_counts=cond_donor_counts,
    )
