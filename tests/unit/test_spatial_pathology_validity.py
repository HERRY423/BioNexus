"""
Unit tests for BioNexus Spatial Inference Pathological Ground Truth & Biological Validity Engine.
Validates:
1. Dice similarity coefficient and Jaccard index calculations
2. Pathological domain morphological concordance against clinical histology annotations
3. 4-part artifact discrimination battery (true interface biology vs optical blur, density, and tile seams)
4. Comprehensive tissue cohort validation benchmark
"""

import numpy as np

from bionexus.spatial_pathology_benchmark import (
    SpatialPathologyValidationResult,
    compute_dice_and_jaccard,
    evaluate_pathology_domain_concordance,
    evaluate_spatial_biological_vs_artifact_discrimination,
    run_spatial_pathology_validation_suite,
)


def test_compute_dice_and_jaccard_exact():
    """Test Dice and Jaccard metrics under known overlapping masks."""
    # Complete match
    m1 = np.array([True, True, True, False, False])
    m2 = np.array([True, True, True, False, False])
    d, j = compute_dice_and_jaccard(m1, m2)
    assert d == 1.0
    assert j == 1.0

    # No overlap
    m3 = np.array([False, False, False, True, True])
    d_zero, j_zero = compute_dice_and_jaccard(m1, m3)
    assert d_zero == 0.0
    assert j_zero == 0.0

    # Partial overlap: intersection = 2, total_true = 3, total_pred = 3, union = 4
    m4 = np.array([True, True, False, True, False])
    d_part, j_part = compute_dice_and_jaccard(m1, m4)
    assert abs(d_part - (2 * 2 / 6)) < 1e-6
    assert abs(j_part - (2 / 4)) < 1e-6

    # Both empty masks
    empty = np.array([False, False])
    d_empty, j_empty = compute_dice_and_jaccard(empty, empty)
    assert d_empty is None
    assert j_empty is None


def test_evaluate_pathology_domain_concordance():
    """Test multi-domain histological concordance against pathologist ground truth."""
    gt = ["TUMOR"] * 50 + ["STROMA"] * 30 + ["IMMUNE"] * 20
    # Inferred has 90% concordance
    inferred = ["TUMOR"] * 48 + ["STROMA"] * 2 + ["STROMA"] * 28 + ["TUMOR"] * 2 + ["IMMUNE"] * 20

    metrics = evaluate_pathology_domain_concordance(
        inferred_domain_labels=inferred,
        pathologist_ground_truth=gt,
        min_dice_threshold=0.75,
    )

    assert len(metrics) == 3
    domains = {m.domain_name: m for m in metrics}

    assert "TUMOR" in domains
    assert "STROMA" in domains
    assert "IMMUNE" in domains

    assert domains["TUMOR"].domain_validated is False
    assert domains["TUMOR"].overlap_threshold_met is True
    assert domains["TUMOR"].dice_coefficient > 0.90
    assert domains["IMMUNE"].dice_coefficient == 1.0
    assert domains["IMMUNE"].domain_validated is False
    assert domains["IMMUNE"].overlap_threshold_met is True


def test_evaluate_spatial_biological_vs_artifact_discrimination():
    """Test discrimination battery between genuine biology and technical artifacts."""
    coords = np.random.uniform(0, 1000, size=(100, 2))
    expr = np.random.poisson(5, size=(100, 5))
    genes = ["CXCL12", "CXCR4", "EPCAM", "COL1A1", "CD3E"]
    domains = ["TUMOR"] * 50 + ["STROMA"] * 50

    battery = evaluate_spatial_biological_vs_artifact_discrimination(
        coords=coords,
        expression_matrix=expr,
        gene_names=genes,
        pathologist_domains=domains,
    )

    assert len(battery) == 4
    test_names = [t.test_name for t in battery]
    assert "tumor_stroma_interface_chemokine_interaction" in test_names
    assert "optical_diffusion_segmentation_leakage" in test_names
    assert "cell_density_crowding_confounding" in test_names
    assert "fov_tile_edge_stitching_artifact" in test_names

    # Raw or synthetic arrays contain no actual control experiments or truth.
    for test in battery:
        assert test.is_true_biology is None
        assert test.raw_spatial_statistic is None
        assert test.post_control_statistic is None
        assert test.system_verdict == "NOT_EVALUATED"
        assert test.correctly_discriminated is None


def test_evaluate_spatial_tissue_cohort_benchmark():
    """Test full tissue cohort benchmark execution."""
    coords = np.random.uniform(0, 500, size=(60, 2))
    expr = np.ones((60, 3), dtype=float)
    genes = ["GENE_A", "GENE_B", "GENE_C"]
    domains = ["CARCINOMA_CORE"] * 40 + ["STROMA"] * 20
    inferred = ["CARCINOMA_CORE"] * 38 + ["STROMA"] * 2 + ["STROMA"] * 20

    res = run_spatial_pathology_validation_suite(
        cohort_name="Xenium_Pathology_Cohort_01",
        tissue_type="human_carcinoma_tissue",
        coords=coords,
        expression_matrix=expr,
        gene_names=genes,
        pathologist_ground_truth=domains,
        inferred_domains=inferred,
    )

    assert isinstance(res, SpatialPathologyValidationResult)
    assert res.n_total_cells == 60
    assert res.mean_dice_coefficient >= 0.75
    assert res.pathology_concordance_pass is False
    assert res.reference_concordance_threshold_met is True
    assert res.artifact_discrimination_pass is False
    assert res.biological_validity_promoted is False
