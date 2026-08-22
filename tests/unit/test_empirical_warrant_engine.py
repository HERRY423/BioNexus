"""Profile-conditioned empirical warrant tests.

Approved profiles in this file are synthetic contract fixtures. They test the
resolver and must not be interpreted as biological calibration evidence.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from bionexus.annotation_evidence import AnnotationEvidence, assess_annotation_evidence
from bionexus.empirical_warrant import (
    CalibrationContext,
    CalibrationError,
    CalibrationObservation,
    CalibrationProfile,
    CalibrationRegistry,
    CalibrationResolutionStatus,
    CalibrationReviewStatus,
    ComparisonDirection,
    EmpiricalEvidence,
    ReviewerApproval,
    default_calibration_registry,
    fit_candidate_profile,
)

REFERENCE = "azimuth_pbmc_citeseq_2021"
TASK = "closed_set_cell_identity"
SOURCES = {
    "marker_consistency": "curated_pbmc_marker_panel_v2",
    "negative_marker_violation": "curated_pbmc_negative_panel_v2",
    "reference_mapping": "azimuth_mapper_v2",
    "cross_method_agreement": "independent_ensemble_v1",
    "doublet_rate": "scrublet_calibrated_v1",
    "orthogonal_protein": "citeseq_antibody_panel_v1",
}


def _approved_profile(
    metric: str,
    threshold: float,
    direction: ComparisonDirection,
    *,
    tissue: str = "pbmc",
    profile_suffix: str = "fixture",
) -> CalibrationProfile:
    evidence = EmpiricalEvidence(
        evidence_id=f"fixture:{metric}:held_out",
        dataset_id="synthetic_contract_fixture",
        source_uri="tests/unit/test_empirical_warrant_engine.py",
        source_sha256="a" * 64,
        sample_size=100,
        positive_outcomes=80,
        negative_outcomes=20,
        outcome_definition="synthetic binary outcome for resolver contract testing only",
        estimator="fixture precision",
        validation_partition="held_out_fixture",
        independent_validation=True,
        observed_precision=0.8,
        precision_interval=(0.75, 0.85),
    )
    approval = ReviewerApproval(
        reviewer_id="fixture-reviewer",
        reviewed_at="2026-08-21",
        decision="APPROVE",
        scope="synthetic contract behavior only",
        attestation_sha256="b" * 64,
    )
    return CalibrationProfile(
        profile_id=f"test.{metric}.{profile_suffix}",
        version="1.0.0",
        metric=metric,
        direction=direction,
        threshold=threshold,
        tissues=(tissue,),
        platforms=("10x_3prime_v3",),
        references=(REFERENCE,),
        tasks=(TASK,),
        evidence_sources=(SOURCES[metric],),
        review_status=CalibrationReviewStatus.APPROVED,
        evidence=(evidence,),
        approvals=(approval,),
        metadata={"evidence_scope": "synthetic_contract_fixture"},
    )


def _registry(*, tissue: str = "pbmc") -> CalibrationRegistry:
    return CalibrationRegistry(
        (
            _approved_profile("marker_consistency", 0.60, ComparisonDirection.AT_LEAST, tissue=tissue),
            _approved_profile("negative_marker_violation", 0.20, ComparisonDirection.AT_MOST, tissue=tissue),
            _approved_profile("reference_mapping", 0.78, ComparisonDirection.AT_LEAST, tissue=tissue),
            _approved_profile("doublet_rate", 0.15, ComparisonDirection.AT_MOST, tissue=tissue),
        ),
        registry_version="synthetic-test-registry",
        registry_metadata={"scientific_claim": "none"},
    )


def _context(**changes: object) -> CalibrationContext:
    values = {
        "tissue": "pbmc",
        "platform": "10x_3prime_v3",
        "reference": REFERENCE,
        "task": TASK,
        "evidence_sources": SOURCES,
        "reference_domain_match": True,
        "state_geometry": "discrete",
        "population_scope": "closed_set",
    }
    values.update(changes)
    return CalibrationContext(**values)


def _strong_evidence() -> AnnotationEvidence:
    return AnnotationEvidence(
        marker_consistency=0.85,
        negative_marker_violation=0.05,
        reference_mapping_score=0.79,
        doublet_rate=0.03,
        ontology_compatible=True,
    )


def test_packaged_registry_exposes_legacy_numbers_but_approves_none() -> None:
    inventory = default_calibration_registry().inventory()
    assert inventory["status_counts"]["LEGACY_UNCALIBRATED"] == 6
    assert inventory["status_counts"]["APPROVED"] == 0
    assert inventory["metadata"]["fallback_policy"].startswith("No global threshold fallback")


def test_missing_context_never_falls_back_to_legacy_thresholds() -> None:
    verdict = assess_annotation_evidence("CD8 T cell", _strong_evidence())
    assert verdict.verdict == "TENTATIVE"
    assert verdict.calibration["fallback_used"] is False
    statuses = {
        item["resolution"]["status"]
        for item in verdict.calibration["metric_assessments"].values()
    }
    assert statuses == {"INSUFFICIENT_CONTEXT"}


def test_pbmc_citeseq_regime_resolves_profile_and_supports() -> None:
    verdict = assess_annotation_evidence(
        "CD8 T cell",
        _strong_evidence(),
        calibration_context=_context(),
        calibration_registry=_registry(),
    )
    assert verdict.verdict == "SUPPORTED"
    ref = verdict.calibration["metric_assessments"]["reference_mapping"]
    assert ref["resolution"]["threshold"] == 0.78
    assert ref["resolution"]["profile_sha256"]
    assert ref["passed"] is True


def test_resolved_below_profile_scores_are_explicit_contradictions() -> None:
    verdict = assess_annotation_evidence(
        "B cell",
        AnnotationEvidence(
            marker_consistency=0.2,
            negative_marker_violation=0.5,
            reference_mapping_score=0.9,
            doublet_rate=0.03,
            ontology_compatible=True,
        ),
        calibration_context=_context(),
        calibration_registry=_registry(),
    )
    assert verdict.verdict == "TENTATIVE"
    assert any("below-profile" in reason for reason in verdict.reasons)
    assert verdict.calibration["metric_assessments"]["marker_consistency"]["passed"] is False


def test_healthy_pbmc_reference_score_does_not_support_tumor_tme() -> None:
    verdict = assess_annotation_evidence(
        "nearest PBMC label",
        _strong_evidence(),
        calibration_context=_context(tissue="tumor_tme", reference_domain_match=False),
        calibration_registry=_registry(),
    )
    assert verdict.verdict == "TENTATIVE"
    ref = verdict.calibration["metric_assessments"]["reference_mapping"]
    assert ref["resolution"]["status"] == "DOMAIN_MISMATCH"
    assert ref["passed"] is None
    assert any("calibrated independent identity source" in item for item in verdict.missing_evidence)


def test_continuous_developmental_state_caps_discrete_identity() -> None:
    verdict = assess_annotation_evidence(
        "developmental intermediate",
        _strong_evidence(),
        calibration_context=_context(tissue="developmental", state_geometry="continuous"),
        calibration_registry=_registry(tissue="developmental"),
    )
    assert verdict.verdict == "TENTATIVE"
    assert verdict.warrant_ceiling == "TENTATIVE"
    assert any("Continuous-state penalty" in reason for reason in verdict.reasons)


@pytest.mark.parametrize("scope", ["rare", "open_set"])
def test_rare_or_open_set_population_abstains_regardless_of_score(scope: str) -> None:
    verdict = assess_annotation_evidence(
        "forced label",
        _strong_evidence(),
        calibration_context=_context(population_scope=scope),
        calibration_registry=_registry(),
    )
    assert verdict.verdict == "ABSTAIN"
    assert verdict.warrant_ceiling == "ABSTAIN"


def test_evidence_source_is_part_of_profile_identity() -> None:
    context = _context(evidence_sources={**SOURCES, "reference_mapping": "different_mapper"})
    resolution = _registry().resolve("reference_mapping", context)
    assert resolution.status == CalibrationResolutionStatus.NO_MATCH
    assert resolution.threshold is None


def test_pending_profile_is_not_resolvable() -> None:
    pending = replace(
        _approved_profile("reference_mapping", 0.78, ComparisonDirection.AT_LEAST),
        review_status=CalibrationReviewStatus.CANDIDATE,
        approvals=(),
    )
    resolution = CalibrationRegistry((pending,)).resolve("reference_mapping", _context())
    assert resolution.status == CalibrationResolutionStatus.PROFILE_NOT_APPROVED
    assert resolution.threshold is None


def test_conflicting_equally_specific_profiles_fail_closed() -> None:
    first = _approved_profile("reference_mapping", 0.78, ComparisonDirection.AT_LEAST, profile_suffix="a")
    second = _approved_profile("reference_mapping", 0.84, ComparisonDirection.AT_LEAST, profile_suffix="b")
    resolution = CalibrationRegistry((first, second)).resolve("reference_mapping", _context())
    assert resolution.status == CalibrationResolutionStatus.AMBIGUOUS
    assert set(resolution.candidate_profile_ids) == {first.profile_id, second.profile_id}


def test_fit_creates_candidate_with_held_out_receipt_never_auto_approves() -> None:
    template = replace(
        _approved_profile("reference_mapping", 0.5, ComparisonDirection.AT_LEAST),
        profile_id="candidate.reference_mapping.pbmc",
        review_status=CalibrationReviewStatus.CANDIDATE,
        evidence=(),
        approvals=(),
    )
    observations = [
        CalibrationObservation(0.80 + i * 0.005, True, "calibration", "cal-a") for i in range(20)
    ]
    observations += [
        CalibrationObservation(0.10 + i * 0.02, False, "calibration", "cal-a") for i in range(10)
    ]
    observations += [
        CalibrationObservation(0.82 + i * 0.01, True, "validation", "val-independent") for i in range(10)
    ]
    observations += [
        CalibrationObservation(0.10 + i * 0.02, False, "validation", "val-independent") for i in range(5)
    ]

    candidate, receipt = fit_candidate_profile(
        profile_template=template,
        observations=observations,
        target_precision_lower_bound=0.75,
        confidence_level=0.95,
        minimum_selected=10,
        source_uri="fixture://labelled-observations",
    )
    assert candidate.review_status == CalibrationReviewStatus.CANDIDATE
    assert candidate.approvals == ()
    assert candidate.evidence[0].independent_validation is True
    assert len(receipt.observations_sha256) == 64
    assert CalibrationRegistry((candidate,)).resolve("reference_mapping", _context()).status == (
        CalibrationResolutionStatus.PROFILE_NOT_APPROVED
    )


def test_fit_requires_held_out_validation_partition() -> None:
    template = replace(
        _approved_profile("reference_mapping", 0.5, ComparisonDirection.AT_LEAST),
        review_status=CalibrationReviewStatus.CANDIDATE,
        evidence=(),
        approvals=(),
    )
    with pytest.raises(CalibrationError, match="held-out validation"):
        fit_candidate_profile(
            profile_template=template,
            observations=[CalibrationObservation(0.9, True, "calibration", "only")],
            target_precision_lower_bound=0.5,
            confidence_level=0.95,
            minimum_selected=1,
            source_uri="fixture://missing-validation",
        )
