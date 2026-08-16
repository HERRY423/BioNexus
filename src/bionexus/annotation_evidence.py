"""
BioNexus Cell Annotation Evidence Assessment (flagship capability B, BNS-013).

BioNexus is not another CellTypist. This module answers a different question:
**how much evidence backs a candidate cell-type label?**

Inputs are evidence classes, not raw matrices:
- marker consistency (positive-marker coherence within the labeled population)
- negative-marker violation rate (fraction of labels whose lineage-exclusive
  negatives are expressed)
- reference mapping score (atlas / model transfer confidence)
- doublet rate within the labeled population
- ontology compatibility (does the label exist and cohere in CL / HRA vocabularies)
- cross-method agreement (label concordance across independent annotators)
- open-set signal (population outside the reference universe)

Output is a per-label verdict on a deliberately small ladder:

    SUPPORTED   multiple independent evidence classes cohere
    TENTATIVE   partial evidence; at least one class missing or weak
    ABSTAIN     no evidence, contradictory evidence, or open-set population

Deterministic scoring; thresholds are published in this file and are part of
the capability contract (they MAY only change with a contract version bump).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# Published, deterministic thresholds (contract-visible; see module docstring).
THRESHOLDS: Dict[str, float] = {
    "marker_consistency_min": 0.60,
    "negative_marker_violation_max": 0.20,
    "reference_mapping_min": 0.70,
    "cross_method_agreement_min": 0.80,
    "doublet_rate_max": 0.15,
}

VERDICT_LADDER = ("SUPPORTED", "TENTATIVE", "ABSTAIN")


@dataclass
class AnnotationEvidence:
    """The evidence classes available for one candidate label."""

    marker_consistency: Optional[float] = None  # 0..1
    negative_marker_violation: Optional[float] = None  # 0..1 (lower is better)
    reference_mapping_score: Optional[float] = None  # 0..1
    doublet_rate: Optional[float] = None  # 0..1
    ontology_compatible: Optional[bool] = None
    cross_method_agreement: Optional[float] = None  # 0..1
    open_set_detected: bool = False


@dataclass
class AnnotationVerdict:
    """Per-label verdict with the reasons that produced it."""

    label: str
    verdict: str  # VERDICT_LADDER
    reasons: List[str] = field(default_factory=list)
    missing_evidence: List[str] = field(default_factory=list)
    evidence: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "label": self.label,
            "verdict": self.verdict,
            "reasons": list(self.reasons),
            "missing_evidence": list(self.missing_evidence),
            "evidence": dict(self.evidence),
        }


def assess_annotation_evidence(label: str, evidence: AnnotationEvidence) -> AnnotationVerdict:
    """
    Assess how much evidence backs one candidate label (deterministic).

    Ladder semantics:
    - ABSTAIN: open-set population, ontology-incompatible label, an evidence
      class actively contradicts the label, or no positive evidence at all.
    - SUPPORTED: reference (or cross-method) evidence AND marker coherence AND
      negative markers AND doublet control AND ontology compatibility all pass.
    - TENTATIVE: some positive evidence exists but SUPPORTED conditions are not
      all met; missing classes are listed as evidence requests.
    """
    ev = evidence.evidence = {
        k: getattr(evidence, k) for k in (
            "marker_consistency",
            "negative_marker_violation",
            "reference_mapping_score",
            "doublet_rate",
            "ontology_compatible",
            "cross_method_agreement",
            "open_set_detected",
        )
    }
    reasons: List[str] = []
    missing: List[str] = []
    failures: List[str] = []

    if evidence.open_set_detected:
        return AnnotationVerdict(
            label=label,
            verdict="ABSTAIN",
            reasons=[
                "Open-set population: the label lies outside the reference universe; "
                "report it as unknown/novel rather than the nearest known label (BN-F003)."
            ],
            missing_evidence=["orthogonal evidence for a novel population (sorted bulk profile, spatial markers)"],
            evidence=ev,
        )

    if evidence.ontology_compatible is False:
        failures.append("label is not compatible with the declared ontology vocabulary")

    # Positive evidence classes
    has_reference = evidence.reference_mapping_score is not None
    has_cross_method = evidence.cross_method_agreement is not None
    has_markers = evidence.marker_consistency is not None

    if not (has_reference or has_cross_method or has_markers):
        return AnnotationVerdict(
            label=label,
            verdict="ABSTAIN",
            reasons=["No annotation evidence source available: identity cannot be assessed or asserted (BN-F003)."],
            missing_evidence=["reference atlas mapping or curated marker panel (positive and negative markers)"],
            evidence=ev,
        )

    if has_reference:
        if evidence.reference_mapping_score >= THRESHOLDS["reference_mapping_min"]:
            reasons.append(
                f"reference mapping score {evidence.reference_mapping_score:.2f} >= {THRESHOLDS['reference_mapping_min']:.2f}"
            )
        else:
            failures.append(
                f"reference mapping score {evidence.reference_mapping_score:.2f} < {THRESHOLDS['reference_mapping_min']:.2f}"
            )
    else:
        missing.append("reference atlas mapping")

    if has_cross_method:
        if evidence.cross_method_agreement >= THRESHOLDS["cross_method_agreement_min"]:
            reasons.append(
                f"cross-method agreement {evidence.cross_method_agreement:.2f} >= {THRESHOLDS['cross_method_agreement_min']:.2f}"
            )
        else:
            failures.append(
                f"cross-method agreement {evidence.cross_method_agreement:.2f} < {THRESHOLDS['cross_method_agreement_min']:.2f}"
            )
    else:
        missing.append("cross-method annotation agreement")

    if has_markers:
        if evidence.marker_consistency >= THRESHOLDS["marker_consistency_min"]:
            reasons.append(
                f"positive-marker consistency {evidence.marker_consistency:.2f} >= {THRESHOLDS['marker_consistency_min']:.2f}"
            )
        else:
            failures.append(
                f"positive-marker consistency {evidence.marker_consistency:.2f} < {THRESHOLDS['marker_consistency_min']:.2f}"
            )
    else:
        missing.append("positive-marker consistency measurement")

    if evidence.negative_marker_violation is not None:
        if evidence.negative_marker_violation <= THRESHOLDS["negative_marker_violation_max"]:
            reasons.append(
                f"negative-marker violation rate {evidence.negative_marker_violation:.2f} "
                f"<= {THRESHOLDS['negative_marker_violation_max']:.2f}"
            )
        else:
            failures.append(
                f"negative-marker violation rate {evidence.negative_marker_violation:.2f} "
                f"> {THRESHOLDS['negative_marker_violation_max']:.2f} (lineage exclusivity violated)"
            )
    else:
        missing.append("negative-marker evaluation")

    if evidence.doublet_rate is not None:
        if evidence.doublet_rate <= THRESHOLDS["doublet_rate_max"]:
            reasons.append(f"doublet rate {evidence.doublet_rate:.2f} <= {THRESHOLDS['doublet_rate_max']:.2f}")
        else:
            failures.append(
                f"doublet rate {evidence.doublet_rate:.2f} > {THRESHOLDS['doublet_rate_max']:.2f} "
                "(population may be a doublet artifact)"
            )
    else:
        missing.append("doublet-rate estimate")

    if failures:
        return AnnotationVerdict(
            label=label,
            verdict="TENTATIVE",
            reasons=[f"contradicting evidence: {f}" for f in failures] or ["partial evidence only"],
            missing_evidence=missing,
            evidence=ev,
        )

    # SUPPORTED requires an independent identity source (reference or
    # cross-method) plus marker-level support; markers alone stay TENTATIVE.
    independent_identity = (
        (has_reference and evidence.reference_mapping_score >= THRESHOLDS["reference_mapping_min"])
        or (has_cross_method and evidence.cross_method_agreement >= THRESHOLDS["cross_method_agreement_min"])
    )
    marker_support = has_markers and evidence.marker_consistency >= THRESHOLDS["marker_consistency_min"]
    negatives_checked = (
        evidence.negative_marker_violation is not None
        and evidence.negative_marker_violation <= THRESHOLDS["negative_marker_violation_max"]
    )

    if independent_identity and marker_support and negatives_checked:
        return AnnotationVerdict(label=label, verdict="SUPPORTED", reasons=reasons, missing_evidence=[], evidence=ev)

    if not independent_identity:
        missing.append("independent identity source (reference mapping or cross-method agreement)")
    return AnnotationVerdict(
        label=label,
        verdict="TENTATIVE",
        reasons=reasons or ["positive evidence present but insufficient for SUPPORTED"],
        missing_evidence=missing,
        evidence=ev,
    )
