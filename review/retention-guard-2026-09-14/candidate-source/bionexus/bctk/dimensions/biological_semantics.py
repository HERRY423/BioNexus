"""BCTK Biological Semantics development evaluator.

Phase-1 Trust Reset: no rule may PASS by testing BioNexus itself or by assuming
properties of an arbitrary target. Target-specific fixtures are required.
"""

from __future__ import annotations

from bionexus.bctk.spec import (
    BCTK_RULE_CATALOG,
    ConformanceDimension,
    DimensionResult,
    DimensionStatus,
    RuleEvaluation,
)
from bionexus.bctk.targets import TargetDescriptor


def evaluate_biological_semantics(target: TargetDescriptor) -> DimensionResult:
    """Return NOT_ASSESSED until target-bound semantic fixtures are supplied."""
    evaluations = []
    for rule_id in ("BCTK-SEM-001", "BCTK-SEM-002", "BCTK-SEM-003", "BCTK-SEM-004"):
        rule = BCTK_RULE_CATALOG[rule_id]
        evaluations.append(
            RuleEvaluation(
                rule_id=rule.rule_id,
                dimension=ConformanceDimension.BIOLOGICAL_SEMANTICS,
                status=DimensionStatus.NOT_ASSESSED,
                severity=rule.severity,
                message="Target-specific semantic evidence was not supplied; no PASS is inferred.",
                details={"target": target.name, "required_evidence": "target-bound input/output fixture"},
            )
        )
    return DimensionResult(
        dimension=ConformanceDimension.BIOLOGICAL_SEMANTICS,
        status=DimensionStatus.NOT_ASSESSED,
        score_percentage=0.0,
        passed_rules=0,
        total_rules=len(evaluations),
        critical_failures=0,
        rule_evaluations=evaluations,
    )
