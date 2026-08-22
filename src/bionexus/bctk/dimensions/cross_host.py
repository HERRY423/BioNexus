"""BCTK Cross-Host Consistency development evaluator."""

from __future__ import annotations

from bionexus.bctk.spec import (
    BCTK_RULE_CATALOG,
    ConformanceDimension,
    DimensionResult,
    DimensionStatus,
    RuleEvaluation,
)
from bionexus.bctk.targets import TargetDescriptor


def evaluate_cross_host(target: TargetDescriptor) -> DimensionResult:
    """Return NOT_ASSESSED without executions from each declared host."""
    evaluations = []
    requirements = {
        "BCTK-HST-001": "host-native traces from every declared host",
        "BCTK-HST-002": "target executions repeated under a fixed seed",
        "BCTK-HST-003": "a completed target-specific headless CI run",
    }
    for rule_id, required in requirements.items():
        rule = BCTK_RULE_CATALOG[rule_id]
        evaluations.append(
            RuleEvaluation(
                rule_id=rule.rule_id,
                dimension=ConformanceDimension.CROSS_HOST_CONSISTENCY,
                status=DimensionStatus.NOT_ASSESSED,
                severity=rule.severity,
                message=f"Not assessed: requires {required}.",
                details={"target": target.name, "required_evidence": required},
            )
        )
    return DimensionResult(
        dimension=ConformanceDimension.CROSS_HOST_CONSISTENCY,
        status=DimensionStatus.NOT_ASSESSED,
        score_percentage=0.0,
        passed_rules=0,
        total_rules=len(evaluations),
        critical_failures=0,
        rule_evaluations=evaluations,
    )
