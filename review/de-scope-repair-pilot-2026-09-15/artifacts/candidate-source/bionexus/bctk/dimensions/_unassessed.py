"""Shared fail-closed dimension result for the Scientific Trust Reset."""

from bionexus.bctk.spec import (
    BCTK_RULE_CATALOG,
    ConformanceDimension,
    DimensionResult,
    DimensionStatus,
    RuleEvaluation,
)
from bionexus.bctk.targets import TargetDescriptor


def unassessed_dimension(dimension: ConformanceDimension, target: TargetDescriptor) -> DimensionResult:
    rules = [rule for rule in BCTK_RULE_CATALOG.values() if rule.dimension == dimension]
    evaluations = [
        RuleEvaluation(
            rule_id=rule.rule_id,
            dimension=dimension,
            status=DimensionStatus.NOT_ASSESSED,
            severity=rule.severity,
            message="No target-bound evidence adapter is active during the Scientific Trust Reset.",
            details={"target": target.name, "certification_suspended": True},
        )
        for rule in rules
    ]
    return DimensionResult(
        dimension=dimension,
        status=DimensionStatus.NOT_ASSESSED,
        score_percentage=0.0,
        passed_rules=0,
        total_rules=len(evaluations),
        critical_failures=0,
        rule_evaluations=evaluations,
    )
