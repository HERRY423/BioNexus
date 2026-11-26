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
    *,
    case: Optional[str] = None,
    reference: Optional[str] = None,
    cell_type: Optional[str] = None,
    rows_are_cells: Optional[bool] = None,
) -> None:
    """Audit biological replicates, donor imbalance, and batch confounding."""
    cohort_summary["n_metadata_rows"] = len(obs_df)
    if rows_are_cells is True:
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

    cohort_summary["donor_key"] = d_col
    donors = obs_df[d_col].dropna().astype(str).unique()
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
                status=CheckStatus.MISSING_EVIDENCE,
                summary="无组别列，无法检查各条件内的供体贡献。",
                required_for_pass=False,
            )
        )
        return

    from bionexus.de.rules.sample_design import measure_replicate_strata, resolve_replicate_scope
    from bionexus.statistical_rules import STATISTICAL_THRESHOLDS

    scope = cohort_summary.get("replicate_scope")
    if scope is None:
        scope, _ = resolve_replicate_scope(table=None, obs=obs_df, ct_col=ct_col, c_col=c_col,
                                        cell_type=cell_type, case=case, reference=reference, contract=False, rgg=None)
        cohort_summary["replicate_scope"] = scope
    targets = scope["cell_types"]
    # When the result scope is unknown, the whole cohort can still establish a
    # design defect shared by every subset, e.g. a single donor or perfect batch confounding.
    pooled = scope["basis"] == "unspecified" and bool(scope["outside_cell_types"])
    strata, imbalance = measure_replicate_strata(
        obs_df, d_col, c_col, None if pooled else ct_col, b_col, min_cells_per_donor=min_cells_per_donor,
        case=case, reference=reference, cell_type=None, rows_are_cells=rows_are_cells,
        dominance_threshold=dominance_threshold, included_cell_types=targets,
    )
    if (targets and not ct_col) or scope["ambiguous_contrast"]:
        strata, imbalance = [], []
    cohort_summary["replicate_strata"] = [] if pooled else strata
    if pooled and strata:
        cohort_summary["unstratified_design"] = strata[0]
    if strata and scope["complete"]:
        cohort_summary["n_donors_in_scope"] = len({donor for s in strata for donor in s["eligible_donors"]})
    levels = strata[0]["donors_by_condition"] if strata else {}
    counts = {level: min(s["donors_by_condition"][level] for s in strata) for level in levels}
    cohort_summary["conditions"] = counts
    two_donor_strata = []
    for stratum in strata:
        n = stratum["min_donors"]
        if n >= max(3, min_donors_required):
            continue
        name = stratum["cell_type"] or "未分层"
        donors_by_condition = stratum["donors_by_condition"]
        if n < 2:
            rule, severity = "BFA-001", FindingSeverity.BLOCKER
            title = f"生物学重复严重不足 (N={n} < 2)"
            impact = "至少一个组别不足两个合格供体，无法在该组估计供体间差异。"
            fix = "必须增加独立生物学重复，或将结论收窄到所观察样本的描述。"
        else:
            rule, severity = "BFA-001b", FindingSeverity.HIGH_IMPACT
            title = f"生物学重复受限（最少 N={n}）"
            impact = "组内重复数有限，方差估计不稳定，个别供体可能改变结果。"
            fix = f"按预设设计增加独立供体（当前配置 {min_donors_required} 个/组），并评估功效。"
            if n == 2:
                two_donor_strata.append(name)
        findings.append(DEFinding(
            rule_id=rule, severity=severity, category=FindingCategory.DONOR_REPLICATES,
            title=f"{name}：{title}", impact_on_conclusion=impact,
            sample_or_donor=", ".join(f"{key} (N={v})" for key, v in donors_by_condition.items() if v == n),
            step_or_location="Experimental Design / Sample Intake", minimal_fix=fix,
            evidence_data={k: v for k, v in stratum.items() if k != "design"},
        ))
    if two_donor_strata:
        pi_decisions.append(PIDecisionItem(
            decision_id="PI-DEC-01", title="N=2 供体实验设计结论定性裁决",
            context=f"以下细胞类型至少有一组仅有两个合格供体：{', '.join(two_donor_strata)}。组内方差估计不稳定。",
            option_a="[推荐] 在 Results 中将结论界定为队列内部探索性候选基因，并报告不确定性。",
            option_b="按预先规定的效应大小和目标功效增加独立供体，重新评估。",
            tradeoff_explanation="现有样本支持描述性分析，增加供体有助于估计组间差异。",
            recommended_option="A",
        ))
    if imbalance:
        first = max(imbalance, key=lambda item: item["fraction"])
        name, cond, donor = first["cell_type"], first["condition"], first["dominant_donor"]
        fraction = f"{first['fraction']:.1%}"
        findings.append(DEFinding(
            rule_id="BFA-007", severity=FindingSeverity.HIGH_IMPACT, category=FindingCategory.DONOR_IMBALANCE,
            title=f"单一供体细胞占比倾斜（{name}，{cond}）", sample_or_donor=f"供体 {donor}",
            impact_on_conclusion=f"在 {cond} 条件内，{donor} 贡献了 {name} 细胞的 {fraction}，个体特征可能主导比较。",
            step_or_location="Cell type subsetting / Pseudobulk input",
            minimal_fix="运行 audit-de --alternative-plan 的逐供体剔除（LODO）分支，检查是否出现 DIRECTION_SENSITIVE。",
            evidence_data={"imbalanced_clusters": imbalance},
        ))
        pi_decisions.append(PIDecisionItem(
            decision_id="PI-DEC-02", title=f"{name} 亚群单一供体主导处理裁决",
            context=f"{cond} 条件内，供体 {donor} 贡献 {fraction} 的 {name} 细胞。",
            option_a="[推荐] 报告逐供体剔除的方向与不确定性变化。",
            option_b="将该亚群描述为供体特异性观察。", tradeoff_explanation="结论范围取决于其他供体提供的独立证据。",
            recommended_option="A",
        ))
    if b_col:
        cohort_summary["batches"] = int(obs_df[b_col].nunique())
    batch_findings = []
    threshold = STATISTICAL_THRESHOLDS["batch_cramers_v_advisory"]
    for stratum in strata:
        design = stratum["design"]
        if design["estimable"] is None:
            continue
        rule = "BFA-004"
        if b_col and not design["estimable"]:
            severity = FindingSeverity.BLOCKER
            title = "组别和批次/供体设计完全混杂"
            impact = "样本设计矩阵的行空间不包含所需条件对比，无法分离条件效应。"
            fix = "在相同批次增加跨条件的独立供体或重新设计比较。"
        elif design["residual_df"] < 2:
            severity = FindingSeverity.HIGH_IMPACT
            rule = "BFA-004" if b_col else "BFA-001e"
            title = "样本设计剩余自由度不足"
            impact = "所需条件对比可估计，但剩余生物学自由度不足 2，方差估计不稳定。"
            fix = "增加独立重复，检查批次分配与配对结构。"
        elif b_col and design["cramer_v"] >= threshold:
            severity = FindingSeverity.ADVISORY
            title = "样本层面组别与批次部分相关"
            impact = "条件与批次分布不均；可估计的条件对比仍可能对批次调整敏感。"
            fix = "报告条件与批次的样本交叉表，比较预先指定的批次调整模型。"
        else:
            continue
        batch_findings.append(DEFinding(
            rule_id=rule, severity=severity,
            category=FindingCategory.BATCH_CONFOUNDING if b_col else FindingCategory.DONOR_REPLICATES,
            title=title, impact_on_conclusion=impact, sample_or_donor=stratum["cell_type"],
            step_or_location="Experimental Design / Batch Allocation", minimal_fix=fix,
            evidence_data={"cell_type": stratum["cell_type"], "cramers_v_advisory_threshold": threshold, **design},
        ))
    findings.extend(batch_findings)
    for name in scope["outside_cell_types"]:
        findings.append(DEFinding(
            rule_id="BFA-001s", severity=FindingSeverity.ADVISORY, category=FindingCategory.DONOR_REPLICATES,
            title=f"{name}：未纳入结果范围", impact_on_conclusion="此细胞类型的供体、设计与功效未计入本次对比。",
            minimal_fix="如要审计该类型，请提供标注细胞类型的结果表或明确指定 --cell-type。",
            evidence_data={"cell_type": name, "scope_basis": scope["basis"]},
        ))
    _record_metadata_checks(checks, findings, d_col, c_col, None if pooled else ct_col, b_col, counts, strata=strata)
    if not scope["complete"]:
        checks.append(CheckRecord(
            check_id="replicate_scope", title="差异表达结果的细胞类型范围",
            status=CheckStatus.MISSING_EVIDENCE, required_for_pass=True,
            summary="结果范围未能完整对应。请明确目标细胞类型、有序条件对比，并提供匹配的元数据。",
        ))


def _record_metadata_checks(checks: List[CheckRecord], findings: List[DEFinding], d_col: Optional[str],
                            c_col: Optional[str], ct_col: Optional[str], b_col: Optional[str],
                            cond_donor_counts: Dict[str, int], *, strata: Optional[list] = None) -> None:
    """Summarize the checks without treating missing design measurements as passes."""
    summary = ", ".join(f"{k} N={v}" for k, v in cond_donor_counts.items())
    scope = "各细胞类型中的最少合格供体数" if ct_col else "未按细胞类型分层，供体数可能高估"
    low = any(f.rule_id in {"BFA-001", "BFA-001b", "BFA-001e", "BFA-005"} for f in findings)
    status = CheckStatus.ASSESSED if len(cond_donor_counts) >= 2 else CheckStatus.MISSING_EVIDENCE
    checks.append(CheckRecord(check_id="donor_replicates", title="供体/生物学重复设计",
                              status=CheckStatus.ISSUE_FOUND if low else status,
                              summary=f"{scope}。{summary}", required_for_pass=True))
    imbalance_checked = bool(ct_col and c_col and d_col)
    batch_checked = bool(b_col and d_col and c_col)
    if strata is not None:
        imbalance_checked = imbalance_checked and any(s["min_cells_per_donor"] is not None for s in strata)
        batch_checked = batch_checked and bool(strata) and all(s["design"]["estimable"] is not None for s in strata)
    for check_id, title, rule, measured, description in (
        ("donor_imbalance", "供体细胞贡献失衡", "BFA-007", imbalance_checked, "各细胞类型在各条件内的供体细胞贡献"),
        ("batch_confounding", "批次与组别混杂", "BFA-004", batch_checked, "供体/样本层面的组别与批次设计"),
    ):
        status = CheckStatus.ASSESSED if measured else CheckStatus.MISSING_EVIDENCE
        if any(f.rule_id == rule for f in findings):
            status = CheckStatus.ISSUE_FOUND
        checks.append(CheckRecord(check_id=check_id, title=title, status=status,
                                  summary=f"已检查{description}。" if measured else f"资料不足，未能完整评估{description}。",
                                  required_for_pass=False))
