"""
BCTK Conformance Test Engine.

Orchestrates multi-dimensional development diagnostics against arbitrary targets:
1. Target discovery and introspection
2. Dispatch across 8 scientific conformance dimensions
3. Non-certifying diagnostic scoring
4. Target-content digest binding
"""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from bionexus.abi import ABI_VERSION
from bionexus.bctk.profiles import evaluate_protocol_profiles
from bionexus.bctk.spec import (
    BCTK_RULE_CATALOG,
    ConformanceDimension,
    ConformanceReport,
    ConformanceTier,
    DimensionResult,
    DimensionStatus,
    RuleEvaluation,
    calculate_conformance_tier,
)
from bionexus.bctk.targets import TargetDescriptor, detect_target, snapshot_target

BCTK_VERSION = "0.2.0-development"


def _not_assessed_dimension(dimension: ConformanceDimension, target_name: str) -> DimensionResult:
    rules = [rule for rule in BCTK_RULE_CATALOG.values() if rule.dimension == dimension]
    evaluations = [
        RuleEvaluation(
            rule_id=rule.rule_id,
            dimension=dimension,
            status=DimensionStatus.NOT_ASSESSED,
            severity=rule.severity,
            message="No target-bound evidence adapter is active during the Scientific Trust Reset.",
            details={"target": target_name, "certification_suspended": True},
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


def run_conformance_test(
    target_path_or_spec: Union[str, Path, TargetDescriptor],
    *,
    strict: bool = False,
    custom_name: Optional[str] = None,
) -> ConformanceReport:
    """
    Run full BioNexus Conformance Test Kit evaluation against a target.

    Parameters:
        target_path_or_spec: Path to plugin/skill/script/artifact, or python module spec.
        strict: If True, warnings are escalated to failures.
        custom_name: Optional custom display name for target.

    Returns:
        Structured target-bound development diagnostic. Certification is suspended.
    """
    iso_timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()

    if isinstance(target_path_or_spec, TargetDescriptor):
        target = target_path_or_spec
    else:
        target = detect_target(target_path_or_spec)

    target_name = custom_name or target.name
    target_snapshot = snapshot_target(target)

    dimension_results: Dict[str, DimensionResult] = {}
    critical_violations: List[Dict[str, Any]] = []

    # The old evaluators tested BioNexus internals and projected those results onto
    # arbitrary targets. During the trust reset, every dimension is fail-closed
    # until a target-bound adapter provides evidence for that exact target digest.
    for dimension in ConformanceDimension:
        result = _not_assessed_dimension(dimension, target_name)
        dimension_results[dimension.value] = result

    # Aggregate scores & critical failures
    total_score = sum(res.score_percentage for res in dimension_results.values())
    overall_score = total_score / len(dimension_results) if dimension_results else 0.0

    total_critical_failures = sum(res.critical_failures for res in dimension_results.values())

    for dim_name, res in dimension_results.items():
        for ev in res.rule_evaluations:
            if ev.status == DimensionStatus.FAIL and ev.severity.value in ("CRITICAL", "HIGH"):
                critical_violations.append({
                    "dimension": dim_name,
                    "rule_id": ev.rule_id,
                    "severity": ev.severity.value,
                    "message": ev.message,
                    "details": ev.details,
                })

    # Preserve the old score mapping only as an explicitly non-certifying diagnostic.
    diagnostic_tier = calculate_conformance_tier(overall_score, dimension_results, total_critical_failures)
    profile_results = {
        profile_id: result.to_dict()
        for profile_id, result in evaluate_protocol_profiles(dimension_results).items()
    }

    # BioFailureBench score from failure handling dimension
    bfb_score = None

    summary_text = (
        "BioNexus development diagnostic only; certification and badging are suspended | "
        f"Scientific ABI v{ABI_VERSION} | "
        f"Score: {overall_score:.1f}% | "
        f"Unverified diagnostic tier: {diagnostic_tier.value} | "
        f"Target snapshot: {target_snapshot.sha256 or 'UNAVAILABLE'}"
    )

    report = ConformanceReport(
        target_name=target_name,
        target_type=target.target_type.value,
        target_path=str(target.root_path),
        abi_version=ABI_VERSION,
        bctk_version=BCTK_VERSION,
        timestamp=iso_timestamp,
        overall_score=overall_score,
        conformance_tier=ConformanceTier.NOT_ASSESSED,
        biofailurebench_score=bfb_score,
        dimension_results=dimension_results,
        profile_results=profile_results,
        critical_violations=critical_violations,
        assessment_status="DEVELOPMENT_NOT_CERTIFIABLE",
        diagnostic_tier=diagnostic_tier,
        target_content_sha256=target_snapshot.sha256,
        target_file_count=target_snapshot.file_count,
        badge_eligible=False,
        evidence_attestation_ids=[],
        trust_decision="NOT_ASSESSED",
        badge_markdown="",
        summary_text=summary_text,
    )
    report.cryptographic_fingerprint = report.compute_fingerprint()

    return report
