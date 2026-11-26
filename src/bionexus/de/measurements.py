"""Translate inspected DE artifacts into conditional design and evidence assessments."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

from bionexus.contracts import ConclusionMaturity
from bionexus.de.models import CheckRecord, CheckStatus, DEFinding, ExecutionRecord, FindingCategory, FindingSeverity
from bionexus.evidence_model import EvidenceFactor, assess_evidence
from bionexus.pseudobulk_warrant import evaluate_pseudobulk_inferential_warrant
from bionexus.statistical_rules import assess_statistical_power


def _lodo_direction_stable(report: dict[str, Any] | None, scope: dict[str, Any]) -> bool | None:
    if not report:
        return None
    branches = [b for b in report["branches"] if b["specification"]["kind"] == "leave_one_donor_out"]
    target = report["baseline_condition_review"]["analysis"]
    if any(scope.get(key) is not None and scope[key] != target[field] for key, field in
           (("case", "numerator"), ("reference", "denominator"), ("cell_type", "cell_type"))):
        return None
    results = [item for branch in branches for item in branch["claims"]]
    if any(item["changes"]["direction_reversed"] or item["changes"]["direction_at_zero"]
           for item in results if item["status"] == "COMPARED"):
        return False
    if (not branches or any(b["status"] != "COMPARABLE" or not b["claims"] for b in branches)
            or any(item["status"] != "COMPARED" for item in results)):
        return None
    return True


def _claimed_effect(table: Any, report: dict[str, Any] | None) -> dict[str, float]:
    """Use the weakest explicitly shrunken, uniquely identified effect among the claims."""
    if table is None or not report:
        return {}
    effect_col = next((c for c in ("shrunk_log2fc", "shrunk_log2_fold_change") if c in table), None)
    if effect_col is None or "baseMean" not in table:
        return {}
    scope = report["analysis"]
    claims = [item["claim"] for item in report["claims"]]
    if any(check["status"] != "SATISFIED" for item in report["claims"] for check in item["conditions"]
           if check["condition_id"] in {"artifact_results", "result_identity", "effect_direction"}):
        return {}
    genes = {claim["gene"] for claim in claims}
    if not {"gene", *scope} <= set(table.columns):
        return {}
    rows = table[table["gene"].isin(genes)]
    for column, value in scope.items():
        rows = rows[rows[column] == value]
    if not genes or len(rows) != len(genes) or set(rows["gene"]) != genes:
        return {}
    try:
        by_gene = rows.set_index("gene")[effect_col]
        effects = [(1 if claim["direction"] == "up" else -1) * float(by_gene[claim["gene"]]) for claim in claims]
        means = [float(v) for v in rows["baseMean"]]
    except (ValueError, TypeError):
        return {}
    if not all(map(math.isfinite, [*effects, *means])) or min(effects) <= 0:
        return {}
    return {"shrunk_log2fc": min(effects), "base_mean": min(means)}


def assess_de_measurements(
    *,
    cohort: dict[str, Any],
    execution: ExecutionRecord,
    bound: bool,
    declared: Sequence[str],
    findings: list[DEFinding],
    checks: list[CheckRecord],
    min_donors: int,
    fdr: float,
    alternatives: dict[str, Any] | None,
    selection_dependent: bool,
    claim_report: dict[str, Any] | None,
    table: Any,
    power_parameters: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    strata = cohort.get("replicate_strata", [])
    statuses = {c.check_id: c.status for c in checks}
    design_ok = [
        s["design"]["estimable"] and (s["design"]["residual_df"] or 0) >= 2 for s in strata
    ]
    measured: dict[EvidenceFactor, bool | None] = {
        EvidenceFactor.PROVENANCE: True if bound else False if statuses.get("analysis_execution_binding") == CheckStatus.ISSUE_FOUND else None,
        EvidenceFactor.SENSITIVITY_ANALYSIS: _lodo_direction_stable(alternatives, cohort.get("replicate_scope", {})),
    }
    if strata:
        # An unmeasured stratum leaves the overall assessment unknown unless another stratum fails.
        measured[EvidenceFactor.SAMPLE_DESIGN] = False if False in design_ok else None if None in design_ok else True
        if all(len(s["donors_by_condition"]) >= 2 for s in strata):
            if any(s["min_donors"] < min_donors for s in strata):
                measured[EvidenceFactor.REPLICATION] = False
            elif all(s["cell_type"] is not None and s["row_unit"] == "cell" for s in strata):
                measured[EvidenceFactor.REPLICATION] = True
        if bound and cohort.get("batch_key") and all(s["design"]["estimable"] is not None for s in strata):
            measured[EvidenceFactor.CONFOUND_CONTROLS] = (
                cohort["batch_key"] in execution.design_factors
                and all(s["design"]["batch_in_design"] and s["design"]["estimable"] for s in strata)
            )

    observed = [f for f, present in measured.items() if present is True]
    conflicts = sorted(f.value for f, present in measured.items() if present is False and f in declared)
    if conflicts:
        findings.append(DEFinding(
            rule_id="BFA-017", category=FindingCategory.CLAIM_BOUNDARY, severity=FindingSeverity.ADVISORY,
            title="声明的证据因子与实测结果冲突",
            impact_on_conclusion="以下因子未通过本次产物核查：" + "、".join(conflicts) + "。",
            evidence_data={"conflicting_factors": conflicts},
            minimal_fix="核对供体分层、设计和执行记录，按本次实际测得的因子修订声明。",
        ))

    raw = statuses.get("input_count_type")
    claimed_effect = _claimed_effect(table, claim_report)
    warrants = []
    for stratum in strata:
        counts = stratum["donors_by_condition"]
        design = stratum["design"]
        n = stratum["min_donors"]
        cells = stratum["min_cells_per_eligible_sample"]
        power = None
        if n >= 2 and len(counts) == 2:
            power = assess_statistical_power(
                n_donors_per_group=n, cells_per_sample=cells or 100, nominal_fdr=fdr,
                shrunk_log2fc=claimed_effect.get("shrunk_log2fc"), base_mean=claimed_effect.get("base_mean"),
                **power_parameters,
            )
        item: dict[str, Any] = {
            "cell_type": stratum["cell_type"], "donors_by_condition": counts,
            "power": power.to_dict() if power else None,
            "cell_depth_basis": "minimum_eligible_sample" if cells is not None else "planning_default",
        }
        # This verdict concerns the measured input and contrast only. Missing matrix
        # evidence is distinct from a matrix that demonstrably violates count assumptions.
        if raw not in (CheckStatus.ASSESSED, CheckStatus.ISSUE_FOUND) or len(counts) != 2:
            item.update(status="NOT_ASSESSED", reason="需要可检查的计数矩阵和明确的两组对比。")
        elif design["estimable"] is None and n >= 2:
            item.update(status="NOT_ASSESSED", reason="目标对比的可估计性未知。")
        else:
            verdict = evaluate_pseudobulk_inferential_warrant(
                n_donors_per_group=counts, min_cells_per_sample=cells or 100,
                is_raw_counts=raw == CheckStatus.ASSESSED, has_donor_metadata=True,
                is_confounded=design["estimable"] is False and n >= 2,
                power=power, nominal_fdr=fdr,
            )
            item.update(status="CONDITIONAL_DESIGN_CEILING", verdict=verdict.to_dict())
        warrants.append(item)

    # Positive design ceilings are conditional. They cannot remove an existing audit
    # violation or turn byte-level provenance into scientific/causal authorization.
    triggers = sorted({f.rule_id for f in findings if f.severity in (FindingSeverity.BLOCKER, FindingSeverity.HIGH_IMPACT)})
    if selection_dependent:
        triggers.append("SELECTION_DEPENDENCE_RECORDED")
    ceilings = [w["verdict"]["maturity_ceiling"] for w in warrants if "verdict" in w]
    provisional = not bound or len(ceilings) != len(strata) or "PRELIMINARY" in ceilings
    cap = ConclusionMaturity.PRELIMINARY if provisional else ConclusionMaturity.UNASSESSED
    assessment = assess_evidence(
        base_maturity=cap, satisfied_factors=declared, measured_factors=observed, warrant_triggers=triggers,
    )
    if not triggers and all(present is None for present in measured.values()):
        assessment.evidence_maturity = ConclusionMaturity.UNASSESSED.value
        assessment.rationale = "No DE evidence factor could be measured from the supplied artifacts."
    result = assessment.to_dict()
    result["measurement_results"] = {f.value: v for f, v in measured.items()}
    return result, warrants
