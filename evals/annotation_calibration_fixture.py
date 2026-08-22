"""Synthetic calibration fixtures for annotation engine contract acceptance.

These profiles exercise positive and negative resolver paths. They are not
packaged with the runtime registry and are not biological calibration evidence.
"""

from __future__ import annotations

from typing import Dict

from bionexus.empirical_warrant import (
    CalibrationContext,
    CalibrationProfile,
    CalibrationRegistry,
    CalibrationReviewStatus,
    ComparisonDirection,
    EmpiricalEvidence,
    ReviewerApproval,
)

SYNTHETIC_REFERENCE = "synthetic_pbmc_citeseq_reference_v1"
SYNTHETIC_TASK = "synthetic_closed_set_cell_identity"
SYNTHETIC_SOURCES: Dict[str, str] = {
    "marker_consistency": "synthetic_marker_panel_v1",
    "negative_marker_violation": "synthetic_negative_panel_v1",
    "reference_mapping": "synthetic_mapper_v1",
    "cross_method_agreement": "synthetic_ensemble_v1",
    "doublet_rate": "synthetic_doublet_detector_v1",
    "orthogonal_protein": "synthetic_adt_panel_v1",
}


def synthetic_annotation_context(**changes: object) -> CalibrationContext:
    values = {
        "tissue": "synthetic_pbmc",
        "platform": "synthetic_citeseq",
        "reference": SYNTHETIC_REFERENCE,
        "task": SYNTHETIC_TASK,
        "evidence_sources": SYNTHETIC_SOURCES,
        "reference_domain_match": True,
        "state_geometry": "discrete",
        "population_scope": "closed_set",
    }
    values.update(changes)
    return CalibrationContext(**values)


def _profile(metric: str, threshold: float, direction: ComparisonDirection) -> CalibrationProfile:
    evidence = EmpiricalEvidence(
        evidence_id=f"synthetic-technical-acceptance:{metric}",
        dataset_id="citeseq_synthetic_technical_acceptance",
        source_uri="evals/annotation_calibration_fixture.py",
        source_sha256="1" * 64,
        sample_size=1200,
        positive_outcomes=900,
        negative_outcomes=300,
        outcome_definition="planted synthetic class label; contract test only",
        estimator="synthetic fixture operating point",
        validation_partition="synthetic holdout",
        independent_validation=True,
        observed_precision=0.75,
        precision_interval=(0.70, 0.80),
    )
    approval = ReviewerApproval(
        reviewer_id="synthetic-fixture-not-a-scientific-reviewer",
        reviewed_at="2026-08-21",
        decision="APPROVE",
        scope="resolver contract acceptance only; no biological or external validation claim",
        attestation_sha256="2" * 64,
    )
    return CalibrationProfile(
        profile_id=f"synthetic.contract.{metric}.v1",
        version="1.0.0",
        metric=metric,
        direction=direction,
        threshold=threshold,
        tissues=("synthetic_pbmc",),
        platforms=("synthetic_citeseq",),
        references=(SYNTHETIC_REFERENCE,),
        tasks=(SYNTHETIC_TASK,),
        evidence_sources=(SYNTHETIC_SOURCES[metric],),
        review_status=CalibrationReviewStatus.APPROVED,
        evidence=(evidence,),
        approvals=(approval,),
        metadata={
            "dataset_track": "synthetic_technical_acceptance",
            "scientific_claim": "none",
            "runtime_registry_eligible": False,
        },
    )


def synthetic_annotation_registry() -> CalibrationRegistry:
    return CalibrationRegistry(
        (
            _profile("marker_consistency", 0.60, ComparisonDirection.AT_LEAST),
            _profile("negative_marker_violation", 0.20, ComparisonDirection.AT_MOST),
            _profile("reference_mapping", 0.70, ComparisonDirection.AT_LEAST),
            _profile("cross_method_agreement", 0.80, ComparisonDirection.AT_LEAST),
            _profile("doublet_rate", 0.15, ComparisonDirection.AT_MOST),
            _profile("orthogonal_protein", 0.75, ComparisonDirection.AT_LEAST),
        ),
        registry_version="synthetic-technical-acceptance-v1",
        registry_metadata={
            "dataset_track": "synthetic_technical_acceptance",
            "scientific_claim": "none",
            "packaged_runtime_registry": False,
        },
    )

