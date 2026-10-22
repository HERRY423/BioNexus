"""
Policy evaluation, claim boundary determination, and check state mutation for DE audits.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from bionexus.de.models import (
    CheckRecord,
    CheckStatus,
    ClaimScopeBoundary,
    DEFinding,
    ExecutionRecord,
    FindingSeverity,
)


def _set_check_status(
    checks: List[CheckRecord],
    check_id: str,
    status: CheckStatus,
    summary: str,
) -> None:
    """Explicitly update or set the check status in the list."""
    for chk in checks:
        if chk.check_id == check_id:
            chk.status = status
            chk.summary = summary
            return


def _compute_overall_status(
    findings: List[DEFinding],
    checks: List[CheckRecord],
    execution: ExecutionRecord,
    supplied: bool,
) -> str:
    """Compute top-level audit status."""
    if any(f.severity == FindingSeverity.BLOCKER for f in findings):
        return "BLOCKER_DETECTED"
    if not supplied:
        return "NOT_ASSESSED"
    if any(c.status == CheckStatus.PARSE_FAILED and c.required_for_pass for c in checks):
        return "NEEDS_DATA"
    if any(f.severity == FindingSeverity.HIGH_IMPACT for f in findings):
        return "NEEDS_REVISION"
    required = [c for c in checks if c.required_for_pass]
    if any(c.status == CheckStatus.ISSUE_FOUND for c in required):
        return "NEEDS_REVISION"
    if any(c.status != CheckStatus.ASSESSED for c in required):
        return "NEEDS_DATA"
    donor_level = (
        execution.aggregation in ("donor_pseudobulk", "pseudobulk")
        and not execution.cell_level_condition_test
    )
    replicate = next((c for c in checks if c.check_id == "donor_replicates"), None)
    if replicate is None or replicate.status != CheckStatus.ASSESSED:
        return "NEEDS_DATA"
    if not donor_level:
        return "NEEDS_DATA"
    return "ROBUST_PASS"


def _determine_claim_boundary(
    findings: List[DEFinding],
    cohort_summary: Dict[str, Any],
    claim_text: Optional[str],
    checks: List[CheckRecord],
    execution: ExecutionRecord,
    fdr_threshold: float = 0.05,
) -> ClaimScopeBoundary:
    """Claim scope and Methods text. Past-tense facts come only from execution records."""
    has_blocker = any(f.severity == FindingSeverity.BLOCKER for f in findings)
    has_high = any(f.severity == FindingSeverity.HIGH_IMPACT for f in findings)
    has_claim_exceeded = any(f.rule_id == "BFA-008" for f in findings)
    n_donors = cohort_summary.get("n_donors")
    conditions = cohort_summary.get("conditions") or {}
    required_missing = any(
        c.required_for_pass and c.status != CheckStatus.ASSESSED
        for c in checks
    )
    donor_level = (
        execution.aggregation in ("donor_pseudobulk", "pseudobulk")
        and not execution.cell_level_condition_test
    )

    recommended_methods = (
        "Recommended analysis, not recorded as performed: aggregate raw integer counts to donor-level "
        "pseudobulks per cell type (Squair et al., 2021), then test condition effects with a negative "
        "binomial GLM, Wald tests, and Benjamini-Hochberg FDR. Do not treat cell-level "
        "rank_genes_groups p-values as population inference."
    )
    executed_methods = " ".join(execution.facts)

    if has_blocker:
        allowed = "仅限作为该批次样本的初步技术描述 (Technical descriptive observation only)，不得外推至生物学总体。"
        prohibited = "严禁声称任何疾病关联、生物标志物 (Biomarkers)、群体差异或因果治疗靶点。"
        results = (
            "Inspected artifacts do not support population-level differential-expression claims; "
            "formal inference is withheld."
        )
        maturity = "UNWARRANTED"
    elif required_missing:
        design_bits = []
        if n_donors:
            design_bits.append(f"{n_donors} donors")
        if conditions:
            design_bits.append("condition counts " + ", ".join(f"{k}={v}" for k, v in conditions.items()))
        design_txt = "; ".join(design_bits) if design_bits else "no sample design"
        allowed = (
            f"只能确认已检查的输入（{design_txt}）。缺少差异表达执行记录或结果时，"
            "不得陈述已完成的群体差异表达。"
        )
        prohibited = "严禁把未提供的矩阵、模型或 DE 结果写成已经执行的 NB GLM、Wald 或 BH 校正。"
        results = (
            "Only inspected design or partial artifacts are described; differential-expression "
            "execution was not confirmed."
        )
        maturity = "NOT_ASSESSED"
    elif has_claim_exceeded:
        allowed = (
            f"在已核查的供体级结果与设计下（N={n_donors or 'cohort'} 独立生物学重复），仅支持群体级别的观察性统计关联措辞（Observational Association）。"
        )
        prohibited = "严禁对未提供因果扰动、实验验证或临床金标准支持的基因做出因果疗效、治疗驱动或临床诊断靶点声明。"
        results = "Observed differential expression supports associative findings only; causal or biomarker claims are unwarranted."
        maturity = "EXPLORATORY_COHORT"
    elif any(c.check_id == "fdr_multiple_testing" and "Honest Negative" in c.summary for c in checks) and donor_level and not has_blocker and not has_high:
        allowed = (
            f"在已核查的供体级结果与设计下（N={n_donors or 'cohort'} 独立生物学重复），"
            f"支持诚实阴性结论：在全转录组 FDR < {fdr_threshold} 阈值下未检出显著差异表达基因。"
        )
        prohibited = "严禁依据未校正的原始 p 值挑选基因进行选择性报告 (Selective Reporting / P-hacking)。"
        results = "Honest negative finding: no genes achieved FDR significance under verified donor-level testing."
        maturity = "NEGATIVE_RESULT_FREEZE"
    elif has_high or (isinstance(n_donors, int) and n_donors < 3):
        allowed = (
            f"可陈述为已检查队列内部的探索性候选（供体记录: {n_donors}），"
            "不能升级为稳健群体推断。"
        )
        prohibited = "严禁声称全人群诊断标志物或无扰动实验的因果机制。"
        results = "Inspected artifacts support exploratory candidate language only."
        maturity = "EXPLORATORY_COHORT"
    elif donor_level:
        allowed = (
            f"可陈述所提供结果表中的队列内观察性关联；执行记录的一致性不证明真实拟合或总体代表性。"
            f"{f' N={n_donors} 独立生物学重复。' if n_donors else ''}"
        )
        prohibited = "不得由记录一致性升级为总体外推、真实执行认证或因果驱动机制。"
        results = (
            "The supplied table and donor-level execution metadata were inspected for consistency. "
            "Describe within-cohort associations; actual fitting and population transport were not verified."
        )
        maturity = "EXPLORATORY_COHORT"
    else:
        allowed = "已检查提供的结果表与设计，但没有供体级执行记录，不能授权群体推断。"
        prohibited = "严禁把细胞级 rank_genes_groups 或来源不明的 p 值写成 NB GLM / Wald / BH 已执行。"
        results = "Results were inspected; the statistical unit of the test was not confirmed as donor-level."
        maturity = "NOT_ASSESSED"

    return ClaimScopeBoundary(
        allowed_scope=allowed,
        prohibited_scope=prohibited,
        recommended_methods_text=recommended_methods,
        recommended_results_text=results,
        overall_maturity=maturity,
        executed_methods_text=executed_methods,
    )
