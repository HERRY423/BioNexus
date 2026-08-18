"""
Unit tests for BioNexus Closed-Loop Perturbation-to-Spatial-Niche Engine (GEARS + NicheFormer).

Verifies strict compliance with BioNexus Epistemic Honesty (BNS-EF-002 / BNS-CC-012):
- Fail-closed refusal by default when GEARS or NicheFormer backends are absent.
- Explicit opt-in required for heuristic fallbacks (allow_fallback=True).
- Transparent Grade C attribution (never masquerading as neural network).
"""

from unittest.mock import patch

import anndata as ad
import numpy as np
import pandas as pd
import pytest
from scipy import sparse

from bionexus.abi import capability_abis, get_capability_abi
from bionexus.capabilities import ALL_CAPABILITIES, CANONICAL_CAPABILITIES, FRONTIER_CAPABILITIES
from bionexus.closed_loop import (
    ClosedLoopEvaluationResult,
    GEARSPerturbationConfig,
    GEARSPredictionResult,
    NicheFormerConfig,
    NicheFormerForecastResult,
    check_gears_backend,
    check_nicheformer_backend,
    forecast_spatial_niche,
    predict_gears_perturbation,
    run_perturbation_to_niche_closed_loop,
)
from bionexus.intent_router import route_scientific_intent


@pytest.fixture
def synthetic_sc_adata():
    """Create synthetic single-cell baseline dataset."""
    np.random.seed(42)
    n_cells = 50
    genes = ["TP53", "CDKN1A", "MDM2", "MYC", "BAX", "BCL2", "CASP3", "EGFR", "CD8A", "FOXP3"]

    X = np.random.poisson(lam=2.0, size=(n_cells, len(genes))).astype(np.float32)
    # Plant distinct co-expression correlation
    X[:, 0] = 30.0  # TP53
    X[:, 1] = X[:, 0] * 0.8 + np.random.normal(0, 1, n_cells)  # CDKN1A correlated with TP53
    X[:, 2] = X[:, 0] * 0.6 + np.random.normal(0, 1, n_cells)  # MDM2 correlated with TP53

    adata = ad.AnnData(
        X=sparse.csr_matrix(np.clip(X, 0, None)),
        obs=pd.DataFrame({"cell_type": ["Tumor"] * 30 + ["Immune"] * 20}, index=[f"cell_{i}" for i in range(n_cells)]),
        var=pd.DataFrame(index=genes),
    )
    return adata


@pytest.fixture
def synthetic_spatial_adata():
    """Create synthetic spatial transcriptomics dataset with 2D coordinates."""
    np.random.seed(42)
    n_spots = 60
    genes = ["TP53", "CDKN1A", "MDM2", "MYC", "BAX", "BCL2", "CASP3", "EGFR", "CD8A", "FOXP3"]

    X = np.random.poisson(lam=1.5, size=(n_spots, len(genes))).astype(np.float32)
    coords = np.random.uniform(0, 100, size=(n_spots, 2)).astype(np.float32)

    adata = ad.AnnData(
        X=sparse.csr_matrix(X),
        obs=pd.DataFrame(index=[f"spot_{i}" for i in range(n_spots)]),
        var=pd.DataFrame(index=genes),
        obsm={"spatial": coords},
    )
    return adata


def test_gears_fail_closed_refusal_when_backend_missing(synthetic_sc_adata):
    """
    CRITICAL INVARIANT (BNS-EF-002):
    When GEARS model/checkpoint is not provided and allow_fallback=False (default),
    BioNexus MUST refuse with REFUSAL_CANONICAL_MODEL_REQUIRED.
    """
    _, res = predict_gears_perturbation(
        adata_base=synthetic_sc_adata,
        target_genes=["TP53"],
        mode="knockout",
        allow_fallback=False,
    )

    assert res.success is False
    assert res.status == "REFUSAL_CANONICAL_MODEL_REQUIRED"
    assert res.backend_used == "none"
    assert "allow_fallback=True" in res.remedy_if_failed


def test_gears_canonical_backend_execution_identity_mock(synthetic_sc_adata):
    """
    BACKEND EXECUTION IDENTITY TEST:
    Verify that when a canonical GEARS model is provided, BioNexus actually executes
    the canonical model's predict/forward method and attributes provenance accurately.
    """
    from unittest.mock import MagicMock

    # Create mock canonical GEARS model object
    mock_gears_model = MagicMock()
    # Mock predict method return format
    X_pert_mock = np.zeros((50, 10), dtype=np.float32)
    X_pert_mock[:, 0] = 0.0  # target zeroed
    mock_gears_model.predict.return_value = {"_pert": X_pert_mock}

    cfg = GEARSPerturbationConfig(
        target_genes=["TP53"],
        mode="knockout",
        gears_model=mock_gears_model,
    )

    adata_pert, res = predict_gears_perturbation(
        adata_base=synthetic_sc_adata,
        target_genes=["TP53"],
        mode="knockout",
        config=cfg,
        allow_fallback=False,
    )

    # Assert official backend predict method WAS called with perturbation targets
    mock_gears_model.predict.assert_called_once_with([["TP53"]])
    assert res.success is True
    assert res.status == "COMPLETED"
    assert res.backend_used == "gears-graph-neural-network (canonical)"


def test_predict_gears_perturbation_fallback_honesty(synthetic_sc_adata):
    """Verify GEARS fallback accurately attributes Grade C heuristic without masquerading."""
    adata_pert, res = predict_gears_perturbation(
        adata_base=synthetic_sc_adata,
        target_genes=["TP53"],
        mode="knockout",
        allow_fallback=True,
    )

    assert res.success is True
    assert res.status == "COMPLETED_WITH_HEURISTIC_FALLBACK"
    assert res.backend_used == "heuristic-coexpression-network (Grade C Experimental)"
    assert res.target_genes == ["TP53"]
    assert res.n_cells_predicted == 50
    assert len(res.top_downregulated_genes) > 0
    assert res.mean_fold_change > 0.0

    # Verify target gene is zeroed out in perturbed matrix
    t_idx = list(synthetic_sc_adata.var_names).index("TP53")
    X_pert = adata_pert.X.toarray() if sparse.issparse(adata_pert.X) else adata_pert.X
    assert np.all(X_pert[:, t_idx] == 0.0)


def test_predict_gears_perturbation_combinatorial_knockout(synthetic_sc_adata):
    """Verify GEARS combinatorial double knockout."""
    adata_pert, res = predict_gears_perturbation(
        adata_base=synthetic_sc_adata,
        target_genes=["TP53", "MYC"],
        mode="knockout",
        allow_fallback=True,
    )

    assert res.success is True
    assert res.target_genes == ["TP53", "MYC"]
    assert res.n_cells_predicted == 50


def test_gears_refusal_missing_genes(synthetic_sc_adata):
    """Verify fail-closed refusal when target genes are not in dataset."""
    _, res = predict_gears_perturbation(
        adata_base=synthetic_sc_adata,
        target_genes=["NON_EXISTENT_GENE_XYZ"],
        mode="knockout",
    )
    assert res.success is False
    assert res.status == "REFUSAL_TARGET_GENES_NOT_FOUND"


def test_nicheformer_fail_closed_refusal_when_backend_missing(synthetic_sc_adata, synthetic_spatial_adata):
    """
    CRITICAL INVARIANT (BNS-EF-002):
    When NicheFormer model/checkpoint is missing and allow_fallback=False (default),
    BioNexus MUST refuse with REFUSAL_CANONICAL_MODEL_REQUIRED.
    """
    _, res = forecast_spatial_niche(
        adata_cells=synthetic_sc_adata,
        adata_spatial=synthetic_spatial_adata,
        allow_fallback=False,
    )

    assert res.success is False
    assert res.status == "REFUSAL_CANONICAL_MODEL_REQUIRED"
    assert res.backend_used == "none"
    assert "allow_fallback=True" in res.remedy_if_failed


def test_nicheformer_canonical_backend_execution_identity_mock(synthetic_sc_adata, synthetic_spatial_adata):
    """
    BACKEND EXECUTION IDENTITY TEST:
    Verify that when a canonical NicheFormer model is provided, BioNexus actually executes
    the canonical model forward method and attributes provenance accurately.
    """
    from unittest.mock import MagicMock

    mock_nf_model = MagicMock()
    # Mock prediction return shape (N_spots, N_niches)
    mock_nf_model.predict.return_value = np.ones((60, 5), dtype=np.float32) / 5.0

    cfg = NicheFormerConfig(
        n_niche_classes=5,
        nicheformer_model=mock_nf_model,
    )

    ad_sp, res = forecast_spatial_niche(
        adata_cells=synthetic_sc_adata,
        adata_spatial=synthetic_spatial_adata,
        config=cfg,
        allow_fallback=False,
    )

    # Assert official model predict method WAS called
    mock_nf_model.predict.assert_called_once_with(synthetic_sc_adata, synthetic_spatial_adata)
    assert res.success is True
    assert res.status == "COMPLETED"
    assert res.backend_used == "nicheformer-multimodal-transformer (canonical)"


def test_forecast_spatial_niche_fallback_honesty(synthetic_sc_adata, synthetic_spatial_adata):
    """Verify NicheFormer fallback accurately attributes Grade C spatial clustering."""
    ad_sp, res = forecast_spatial_niche(
        adata_cells=synthetic_sc_adata,
        adata_spatial=synthetic_spatial_adata,
        config=NicheFormerConfig(n_niche_classes=4),
        allow_fallback=True,
    )

    assert res.success is True
    assert res.status == "COMPLETED_WITH_HEURISTIC_FALLBACK"
    assert res.backend_used == "heuristic-spatial-niche-clustering (Grade C Experimental)"
    assert res.n_spots == 60
    assert res.n_niche_types == 4
    assert len(res.niche_names) == 4
    assert "nicheformer_niche_pred" in ad_sp.obsm
    assert ad_sp.obsm["nicheformer_niche_pred"].shape == (60, 4)
    assert "dominant_niche" in ad_sp.obs


def test_nicheformer_refusal_missing_coordinates(synthetic_sc_adata, synthetic_spatial_adata):
    """Verify fail-closed refusal when spatial dataset lacks obsm['spatial']."""
    ad_no_coords = synthetic_spatial_adata.copy()
    del ad_no_coords.obsm["spatial"]

    _, res = forecast_spatial_niche(
        adata_cells=synthetic_sc_adata,
        adata_spatial=ad_no_coords,
    )
    assert res.success is False
    assert res.status == "REFUSAL_MISSING_COORDINATES"


def test_closed_loop_pipeline_end_to_end(synthetic_sc_adata, synthetic_spatial_adata):
    """Verify end-to-end dry-wet closed loop evaluation and hypothesis card generation."""
    res = run_perturbation_to_niche_closed_loop(
        adata_cells=synthetic_sc_adata,
        adata_spatial=synthetic_spatial_adata,
        target_genes=["TP53", "CDKN1A"],
        mode="knockout",
        allow_fallback=True,
    )

    assert res.success is True
    assert res.status == "COMPLETED"
    assert res.target_perturbation == ["TP53", "CDKN1A"]
    assert res.gears_result is not None
    assert res.niche_result_baseline is not None
    assert res.niche_result_perturbed is not None
    assert len(res.niche_remodeling_scores) > 0
    assert len(res.top_remodeled_niches) > 0

    card = res.wet_lab_hypothesis_card
    assert card["evidence_ceiling"] == "PRELIMINARY (BNS-CC-013)"
    assert len(card["primary_hypotheses"]) > 0
    assert len(card["recommended_wet_lab_assays"]) > 0


def test_closed_loop_capabilities_and_abi():
    """Verify capabilities are registered in Frontier track and project cleanly to ABI without drift."""
    assert "perturbation.gears_prediction" in FRONTIER_CAPABILITIES
    assert "spatial.nicheformer_forecasting" in FRONTIER_CAPABILITIES
    assert "closed_loop.perturbation_to_niche" in FRONTIER_CAPABILITIES
    assert "perturbation.gears_prediction" in ALL_CAPABILITIES

    abis = capability_abis(include_frontier=True)
    assert "perturbation.gears_prediction" in abis
    assert "spatial.nicheformer_forecasting" in abis
    assert "closed_loop.perturbation_to_niche" in abis

    abi_cl = get_capability_abi("closed_loop.perturbation_to_niche")
    assert abi_cl.evidence_ceiling.without_external_validation == "PRELIMINARY"
    assert "clinical_diagnosis" in abi_cl.forbidden_claims


def test_closed_loop_intent_routing():
    """Verify natural language queries match appropriate capabilities."""
    res1 = route_scientific_intent("predict combinatorial knockout of TP53 and CDKN1A with GEARS")
    assert res1.matched_capability is not None
    assert res1.matched_capability.id == "perturbation.gears_prediction"

    res2 = route_scientific_intent("forecast spatial niche composition and microenvironment with NicheFormer")
    assert res2.matched_capability is not None
    assert res2.matched_capability.id == "spatial.nicheformer_forecasting"

    res3 = route_scientific_intent("evaluate closed-loop perturbation to spatial niche remodeling using GEARS and NicheFormer")
    assert res3.matched_capability is not None
    assert res3.matched_capability.id == "closed_loop.perturbation_to_niche"

