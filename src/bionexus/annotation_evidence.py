"""BioNexus Cell Annotation Evidence Assessment (BNS-013 / BNS-018).

BioNexus assesses how much evidence backs a candidate cell-type label. Score
values are not self-interpreting: every numeric comparison is resolved through
an empirical calibration profile conditioned on tissue, platform, reference,
task, and the metric's evidence source.

Positive warrants fail closed. A missing, pending, ambiguous, or out-of-domain
profile cannot be replaced by a global expert constant. Open-set and rare
populations abstain regardless of their top score, and continuous-state systems
cannot be promoted to a discrete SUPPORTED identity solely by threshold passes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from bionexus.empirical_warrant import (
    CalibrationContext,
    CalibrationRegistry,
    CalibrationResolutionStatus,
    MetricAssessment,
    default_calibration_registry,
)

# Retained only so old reports can identify what was migrated. Runtime warrant
# decisions never read this mapping; the packaged registry represents these as
# LEGACY_UNCALIBRATED profiles that are ineligible for resolution.
LEGACY_THRESHOLDS: Dict[str, float] = {
    "marker_consistency_min": 0.60,
    "negative_marker_violation_max": 0.20,
    "reference_mapping_min": 0.70,
    "cross_method_agreement_min": 0.80,
    "doublet_rate_max": 0.15,
    "orthogonal_protein_min": 0.75,
}
THRESHOLDS = LEGACY_THRESHOLDS  # compatibility alias; not used by the engine

VERDICT_LADDER = ("ROBUST", "SUPPORTED", "TENTATIVE", "CONFLICTED", "ABSTAIN")


@dataclass
class AnnotationEvidence:
    """The evidence classes available for one candidate label."""

    marker_consistency: Optional[float] = None
    negative_marker_violation: Optional[float] = None
    reference_mapping_score: Optional[float] = None
    doublet_rate: Optional[float] = None
    ontology_compatible: Optional[bool] = None
    cross_method_agreement: Optional[float] = None
    orthogonal_protein_evidence: Optional[float] = None
    protein_concordant: Optional[bool] = None
    open_set_detected: bool = False


@dataclass
class AnnotationVerdict:
    """Per-label verdict with evidence, calibration, and warrant ceiling."""

    label: str
    verdict: str
    reasons: List[str] = field(default_factory=list)
    missing_evidence: List[str] = field(default_factory=list)
    evidence: Dict[str, Any] = field(default_factory=dict)
    calibration: Dict[str, Any] = field(default_factory=dict)
    warrant_ceiling: str = "ABSTAIN"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "label": self.label,
            "verdict": self.verdict,
            "reasons": list(self.reasons),
            "missing_evidence": list(self.missing_evidence),
            "evidence": dict(self.evidence),
            "calibration": dict(self.calibration),
            "warrant_ceiling": self.warrant_ceiling,
        }


_METRIC_INPUTS = {
    "marker_consistency": "marker_consistency",
    "negative_marker_violation": "negative_marker_violation",
    "reference_mapping": "reference_mapping_score",
    "cross_method_agreement": "cross_method_agreement",
    "doublet_rate": "doublet_rate",
    "orthogonal_protein": "orthogonal_protein_evidence",
}


def _comparison_text(assessment: MetricAssessment) -> str:
    resolution = assessment.resolution
    assert assessment.score is not None and resolution.threshold is not None and resolution.direction is not None
    operator = ">=" if resolution.direction.value == "AT_LEAST" else "<="
    return (
        f"{assessment.metric} {assessment.score:.3f} {operator} {resolution.threshold:.3f} "
        f"under {resolution.profile_id}@{resolution.profile_version}"
    )

def _calibration_gap(assessment: MetricAssessment) -> str:
    return (
        f"approved empirical calibration for {assessment.metric} "
        f"({assessment.resolution.status.value}: {assessment.resolution.reason})"
    )


def assess_annotation_evidence(
    label: str,
    evidence: AnnotationEvidence,
    *,
    calibration_context: Optional[CalibrationContext] = None,
    calibration_registry: Optional[CalibrationRegistry] = None,
) -> AnnotationVerdict:
    """Assess one candidate label with profile-conditioned calibration.

    Compatibility is preserved at the Python-call level: callers may omit the
    new keyword arguments. Scientifically, however, an omitted context is not
    treated as permission to reuse a universal threshold; score-bearing cases
    remain TENTATIVE until a complete approved profile can be resolved.
    """

    context = calibration_context or CalibrationContext()
    registry = calibration_registry or default_calibration_registry()
    ev = {
        key: getattr(evidence, key)
        for key in (
            "marker_consistency",
            "negative_marker_violation",
            "reference_mapping_score",
            "doublet_rate",
            "ontology_compatible",
            "cross_method_agreement",
            "orthogonal_protein_evidence",
            "protein_concordant",
            "open_set_detected",
        )
    }
    ev["calibration_context"] = context.to_dict()

    if evidence.open_set_detected or context.population_scope in {"open_set", "rare"}:
        scope = "open-set" if evidence.open_set_detected or context.population_scope == "open_set" else "rare"
        return AnnotationVerdict(
            label=label,
            verdict="ABSTAIN",
            reasons=[
                f"{scope.capitalize()} population: no forced nearest-known label is warranted regardless of top score (BN-F003)."
            ],
            missing_evidence=["independent evidence establishing a population inside a calibrated reference universe"],
            evidence=ev,
            calibration={"registry": registry.inventory(), "metric_assessments": {}},
            warrant_ceiling="ABSTAIN",
        )

    if evidence.protein_concordant is False:
        return AnnotationVerdict(
            label=label,
            verdict="CONFLICTED",
            reasons=[
                "Orthogonal surface-protein evidence contradicts RNA marker expression; the disagreement must be resolved."
            ],
            missing_evidence=["resolution of RNA versus protein discordance"],
            evidence=ev,
            calibration={"registry": registry.inventory(), "metric_assessments": {}},
            warrant_ceiling="CONFLICTED",
        )

    assessments: Dict[str, MetricAssessment] = {}
    for metric, attr in _METRIC_INPUTS.items():
        value = getattr(evidence, attr)
        if value is not None:
            assessments[metric] = registry.assess(metric, value, context)

    calibration = {
        "registry": registry.inventory(),
        "metric_assessments": {metric: result.to_dict() for metric, result in assessments.items()},
        "fallback_used": False,
    }
    invalid_scores = [
        result
        for result in assessments.values()
        if result.resolution.status == CalibrationResolutionStatus.INVALID_SCORE
    ]
    if invalid_scores:
        return AnnotationVerdict(
            label=label,
            verdict="ABSTAIN",
            reasons=[result.resolution.reason for result in invalid_scores],
            missing_evidence=["valid score inputs within [0, 1]"],
            evidence=ev,
            calibration=calibration,
            warrant_ceiling="ABSTAIN",
        )

    has_raw_positive = any(
        value is not None
        for value in (
            evidence.reference_mapping_score,
            evidence.cross_method_agreement,
            evidence.marker_consistency,
        )
    )
    if not has_raw_positive:
        return AnnotationVerdict(
            label=label,
            verdict="ABSTAIN",
            reasons=["No annotation evidence source is available; identity cannot be assessed or asserted (BN-F003)."],
            missing_evidence=["reference mapping, independent annotator agreement, or a curated marker panel"],
            evidence=ev,
            calibration=calibration,
            warrant_ceiling="ABSTAIN",
        )

    reasons: List[str] = []
    missing: List[str] = []
    failures: List[str] = []
    for assessment in assessments.values():
        if assessment.passed is True:
            reasons.append(_comparison_text(assessment))
        elif assessment.passed is False:
            failures.append(_comparison_text(assessment))
        else:
            missing.append(_calibration_gap(assessment))

    if evidence.ontology_compatible is False:
        failures.append("label is incompatible with the declared ontology vocabulary")
    elif evidence.ontology_compatible is None:
        missing.append("ontology compatibility evaluation")

    for metric, description in (
        ("reference_mapping", "reference atlas mapping"),
        ("cross_method_agreement", "cross-method annotation agreement"),
        ("marker_consistency", "positive-marker consistency measurement"),
        ("negative_marker_violation", "negative-marker evaluation"),
        ("doublet_rate", "doublet-rate estimate"),
    ):
        if metric not in assessments:
            missing.append(description)

    if failures:
        return AnnotationVerdict(
            label=label,
            verdict="TENTATIVE",
            reasons=[f"contradicting or below-profile evidence: {item}" for item in failures],
            missing_evidence=missing,
            evidence=ev,
            calibration=calibration,
            warrant_ceiling="TENTATIVE",
        )

    passed = {metric: result.passed is True for metric, result in assessments.items()}
    independent_identity = passed.get("reference_mapping", False) or passed.get("cross_method_agreement", False)
    core_support = (
        independent_identity
        and passed.get("marker_consistency", False)
        and passed.get("negative_marker_violation", False)
        and passed.get("doublet_rate", False)
        and evidence.ontology_compatible is True
    )

    if core_support and context.state_geometry == "continuous":
        reasons.append(
            "Continuous-state penalty: threshold passes do not justify a discrete identity boundary in a developmental or transitional manifold."
        )
        return AnnotationVerdict(
            label=label,
            verdict="TENTATIVE",
            reasons=reasons,
            missing_evidence=missing + ["state-aware continuous or trajectory validation"],
            evidence=ev,
            calibration=calibration,
            warrant_ceiling="TENTATIVE",
        )

    if core_support:
        if passed.get("orthogonal_protein", False):
            return AnnotationVerdict(
                label=label,
                verdict="ROBUST",
                reasons=reasons,
                missing_evidence=[],
                evidence=ev,
                calibration=calibration,
                warrant_ceiling="ROBUST",
            )
        return AnnotationVerdict(
            label=label,
            verdict="SUPPORTED",
            reasons=reasons,
            missing_evidence=[],
            evidence=ev,
            calibration=calibration,
            warrant_ceiling="SUPPORTED",
        )

    if not independent_identity:
        missing.append("calibrated independent identity source (reference mapping or cross-method agreement)")
    return AnnotationVerdict(
        label=label,
        verdict="TENTATIVE",
        reasons=reasons or ["Evidence scores are present but unresolved or insufficient for a positive warrant."],
        missing_evidence=list(dict.fromkeys(missing)),
        evidence=ev,
        calibration=calibration,
        warrant_ceiling="TENTATIVE",
    )
