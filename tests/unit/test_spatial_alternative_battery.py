"""Executable Spatial Alternative Explanation Battery contract tests.

The approved profiles and spatial layout below are synthetic software fixtures.
They demonstrate fail-closed resolution and perturbation behavior only; they
are not biological calibration evidence and cannot support a platform claim.
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest
from scipy import sparse

from bionexus.empirical_warrant import (
    CalibrationContext,
    CalibrationProfile,
    CalibrationRegistry,
    CalibrationReviewStatus,
    ComparisonDirection,
    EmpiricalEvidence,
    ReviewerApproval,
)
from bionexus.spatial_alternative_battery import (
    DiagnosticState,
    SpatialBatteryData,
    SpatialBatteryError,
    SpatialBatteryPlan,
    SpatialClaimKind,
    SpatialObservation,
    run_spatial_alternative_battery,
)

METRICS = {
    "spatial.segmentation_effect_retention": ComparisonDirection.AT_LEAST,
    "spatial.leakage_effect_retention": ComparisonDirection.AT_LEAST,
    "spatial.cell_size_adjusted_retention": ComparisonDirection.AT_LEAST,
    "spatial.nuclear_eccentricity_adjusted_retention": ComparisonDirection.AT_LEAST,
    "spatial.transcript_density_adjusted_retention": ComparisonDirection.AT_LEAST,
    "spatial.local_density_adjusted_retention": ComparisonDirection.AT_LEAST,
    "spatial.contact_geometry_retention": ComparisonDirection.AT_LEAST,
    "spatial.batch_fov_stability": ComparisonDirection.AT_LEAST,
    "spatial.radius_stability": ComparisonDirection.AT_LEAST,
    "spatial.permutation_p_value": ComparisonDirection.AT_MOST,
    "spatial.cell_label_stability": ComparisonDirection.AT_LEAST,
    "spatial.spatial_autocorrelation_null_p_value": ComparisonDirection.AT_MOST,
}


def test_top_level_spatial_battery_export_remains_available_lazily():
    import bionexus

    assert bionexus.SpatialBatteryPlan is SpatialBatteryPlan
    assert bionexus.run_spatial_alternative_battery is run_spatial_alternative_battery


def _context() -> CalibrationContext:
    return CalibrationContext(
        tissue="synthetic_tissue_fixture",
        platform="xenium",
        reference="synthetic_segmentation_fixture",
        task="contact_expression_enrichment_fixture",
        evidence_sources={metric: "synthetic_battery_fixture_v1" for metric in METRICS},
    )


def _profile(metric: str, direction: ComparisonDirection) -> CalibrationProfile:
    evidence = EmpiricalEvidence(
        evidence_id=f"fixture:{metric}",
        dataset_id="synthetic_spatial_contract_fixture",
        source_uri="tests/unit/test_spatial_alternative_battery.py",
        source_sha256="a" * 64,
        sample_size=100,
        positive_outcomes=80,
        negative_outcomes=20,
        outcome_definition="synthetic software-contract outcome only",
        estimator="fixture decision boundary",
        validation_partition="held_out_fixture",
        independent_validation=True,
        observed_precision=0.8,
        precision_interval=(0.75, 0.85),
    )
    approval = ReviewerApproval(
        reviewer_id="fixture-reviewer",
        reviewed_at="2026-08-21",
        decision="APPROVE",
        scope="synthetic software contract only; no biological use",
        attestation_sha256="b" * 64,
    )
    threshold = 0.25
    return CalibrationProfile(
        profile_id=f"test.{metric}",
        version="1.0.0",
        metric=metric,
        direction=direction,
        threshold=threshold,
        tissues=("synthetic_tissue_fixture",),
        platforms=("xenium",),
        references=("synthetic_segmentation_fixture",),
        tasks=("contact_expression_enrichment_fixture",),
        evidence_sources=("synthetic_battery_fixture_v1",),
        review_status=CalibrationReviewStatus.APPROVED,
        evidence=(evidence,),
        approvals=(approval,),
        metadata={"scientific_claim": "none", "fixture_only": True},
    )


def _registry() -> CalibrationRegistry:
    return CalibrationRegistry(
        tuple(_profile(metric, direction) for metric, direction in METRICS.items()),
        registry_version="synthetic-spatial-fixture",
        registry_metadata={"scientific_claim": "none"},
    )


def _fixture() -> tuple[SpatialObservation, SpatialBatteryData, SpatialBatteryPlan]:
    coordinates: list[tuple[float, float]] = []
    labels: list[str] = []
    exposed: list[bool] = []
    contact_pairs: list[tuple[int, int]] = []
    fovs: list[str] = []

    for fov_index, x_offset in enumerate((0.0, 100.0)):
        fov = f"fov_{fov_index + 1}"
        for y in (0.0, 20.0, 40.0, 60.0, 80.0):
            macrophage = len(labels)
            coordinates.append((x_offset, y))
            labels.append("Macrophage")
            exposed.append(False)
            fovs.append(fov)
            for delta in ((1.0, 0.0), (0.0, 1.0)):
                t_cell = len(labels)
                coordinates.append((x_offset + delta[0], y + delta[1]))
                labels.append("T_cell")
                exposed.append(True)
                fovs.append(fov)
                contact_pairs.append((macrophage, t_cell))
            for delta in ((10.0, 0.0), (10.0, 2.0)):
                coordinates.append((x_offset + delta[0], y + delta[1]))
                labels.append("T_cell")
                exposed.append(False)
                fovs.append(fov)

    n_cells = len(labels)
    expression = np.zeros((n_cells, 2), dtype=float)
    expression[:, 0] = np.where(np.asarray(exposed), 2.0, 0.5)
    expression[:, 1] = np.linspace(0.1, 1.0, n_cells)
    rows = [row for pair in contact_pairs for row in pair]
    cols = [col for pair in contact_pairs for col in reversed(pair)]
    contact = sparse.csr_matrix((np.ones(len(rows)), (rows, cols)), shape=(n_cells, n_cells))

    observation = SpatialObservation(
        observation_id="synthetic-contact-observation",
        statement="CXCL13 expression is enriched in T cells at macrophage contacts",
        target_gene="CXCL13",
        focal_cell_label="T_cell",
        neighbor_cell_label="Macrophage",
        claim_kind=SpatialClaimKind.CONTACT_EXPRESSION_ENRICHMENT,
    )
    data = SpatialBatteryData(
        expression=expression,
        gene_names=("CXCL13", "CONTROL"),
        coordinates=np.asarray(coordinates),
        cell_labels=labels,
        dataset_id="synthetic-spatial-contract-fixture",
        state_revision_id="state-r1",
        segmentation_revision_id="seg-r1",
        label_revision_id="labels-r1",
        coordinate_system_id="fixture-physical-space",
        coordinate_unit="micrometer",
        expression_scale="log1p",
        contact_graph=contact,
        cell_size=np.linspace(80.0, 120.0, n_cells),
        nuclear_eccentricity=np.tile(np.linspace(0.1, 0.8, 5), n_cells // 5),
        total_transcript_counts=np.linspace(100.0, 200.0, n_cells),
        fov_or_batch=fovs,
        segmentation_expression_variants={"seg-r2": expression * np.asarray([0.95, 1.0])},
        leakage_expression_variants={"deleakage-r1": expression * np.asarray([0.90, 1.0])},
    )
    plan = SpatialBatteryPlan(
        primary_radius=3.0,
        radius_grid=(2.0, 3.0, 4.0),
        assumed_leakage_fractions=(),
        label_flip_fraction=0.04,
        label_perturbations=10,
        coordinate_permutations=19,
        random_seed=17,
        minimum_group_cells=4,
        max_graph_edges=2_000,
    )
    return observation, data, plan


def test_missing_empirical_profiles_keeps_computed_battery_fragile() -> None:
    observation, data, plan = _fixture()
    result = run_spatial_alternative_battery(observation, data, plan)

    assert result.verdict.verdict == "FRAGILE"
    assert result.diagnostics["segmentation_uncertainty"].score is not None
    assert result.diagnostics["segmentation_uncertainty"].state == DiagnosticState.UNTESTED
    assert result.provenance["fallback_used"] is False
    assert result.semantic_envelope is not None
    semantics = result.semantic_envelope["attributes"]
    assert semantics["biological.unit"] == "cell"
    assert semantics["matrix.state"] == "log_normalized"
    assert semantics["claim.type"] == "associative"
    assert semantics["warrant.level"] == "fragile"
    assert semantics["warrant.status"] == "assessed"
    assert "segmentation" in semantics["confound.type"]
    assert len(result.semantic_envelope["semantic_fingerprint_sha256"]) == 64


def test_generic_approved_fixture_profiles_cannot_make_battery_robust() -> None:
    observation, data, plan = _fixture()
    result = run_spatial_alternative_battery(
        observation,
        data,
        plan,
        calibration_context=_context(),
        calibration_registry=_registry(),
    )

    assert result.verdict.verdict == "FRAGILE"
    assert all(
        item.state != DiagnosticState.CONTROLLED for item in result.diagnostics.values() if item.metric in METRICS
    )
    segmentation = result.diagnostics["segmentation_uncertainty"]
    assert segmentation.state == DiagnosticState.UNTESTED
    assert segmentation.calibration["passed"] is None
    assert segmentation.calibration["profile_comparison_ignored"] is True
    assert segmentation.calibration["effective_resolution_status"] == "GOLD_PROGRAM_AUTHORIZATION_REQUIRED"
    assert segmentation.calibration["spatial_empirical_gold_scope"]["profile_authorized"] is False
    assert result.provenance["state_revision_id"] == "state-r1"
    assert len(result.provenance["battery_run_sha256"]) == 64
    assert result.provenance["spatial_empirical_gold"]["declared_platform"] == "xenium"
    assert result.provenance["spatial_empirical_gold"]["platform_in_scope"] is True


def test_approved_profile_outside_three_platform_program_cannot_control_a_diagnostic() -> None:
    observation, data, plan = _fixture()
    context = replace(_context(), platform="generic_spatial_platform")
    profiles = tuple(replace(profile, platforms=("generic_spatial_platform",)) for profile in _registry().profiles)

    result = run_spatial_alternative_battery(
        observation,
        data,
        plan,
        calibration_context=context,
        calibration_registry=CalibrationRegistry(profiles, registry_version="out-of-scope-fixture"),
    )

    assert result.verdict.verdict == "FRAGILE"
    assert result.diagnostics["segmentation_uncertainty"].state == DiagnosticState.UNTESTED
    scope = result.diagnostics["segmentation_uncertainty"].calibration["spatial_empirical_gold_scope"]
    assert scope["platform_in_scope"] is False
    assert result.diagnostics["segmentation_uncertainty"].calibration["passed"] is None
    assert result.diagnostics["segmentation_uncertainty"].calibration["effective_resolution_status"] == (
        "OUT_OF_GOLD_PROGRAM_SCOPE"
    )


def test_segmentation_variant_that_removes_effect_is_conflicted() -> None:
    observation, data, plan = _fixture()
    failed_variant = np.asarray(data.expression).copy()
    failed_variant[:, 0] = 1.0
    data.segmentation_expression_variants = {"seg-destroys-effect": failed_variant}

    result = run_spatial_alternative_battery(
        observation,
        data,
        plan,
        calibration_context=_context(),
        calibration_registry=_registry(),
    )

    assert result.diagnostics["segmentation_uncertainty"].state == DiagnosticState.UNTESTED
    assert result.verdict.verdict == "FRAGILE"
    assert result.diagnostics["segmentation_uncertainty"].calibration["profile_comparison_ignored"] is False


def test_contact_claim_without_exact_contact_graph_is_not_promoted() -> None:
    observation, data, plan = _fixture()
    data.contact_graph = None

    result = run_spatial_alternative_battery(
        observation,
        data,
        plan,
        calibration_context=_context(),
        calibration_registry=_registry(),
    )

    assert result.diagnostics["contact_geometry"].state == DiagnosticState.UNTESTED
    assert result.verdict.verdict == "FRAGILE"
    assert "contact_geometry" in result.verdict.untested


def test_nonphysical_coordinates_and_unbounded_graph_fail_closed() -> None:
    observation, data, plan = _fixture()
    with pytest.raises(SpatialBatteryError, match="micrometers"):
        run_spatial_alternative_battery(observation, replace(data, coordinate_unit="UMAP"), plan)

    with pytest.raises(SpatialBatteryError, match="max_graph_edges"):
        run_spatial_alternative_battery(
            observation,
            data,
            replace(plan, primary_radius=1_000.0, max_graph_edges=1),
        )


def test_unestimable_baseline_abstains_instead_of_reporting_fragile_support() -> None:
    observation, data, plan = _fixture()
    labels = np.asarray(data.cell_labels, dtype=str)
    contact = sparse.lil_matrix(data.contact_graph)
    macrophages = np.flatnonzero(labels == "Macrophage")
    for index in np.flatnonzero(labels == "T_cell"):
        contact[index, macrophages[0]] = 1.0
        contact[macrophages[0], index] = 1.0
    data.contact_graph = contact.tocsr()

    result = run_spatial_alternative_battery(observation, data, plan)

    assert result.baseline_effect is None
    assert result.verdict.verdict == "ABSTAIN"
    assert "baseline_effect" in result.verdict.untested
