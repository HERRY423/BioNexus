"""
Unit tests for BioNexus Tangram Spatial Deconvolution & Cell-to-Space Mapping (bionexus.tangram).
"""

from unittest.mock import MagicMock, patch

import anndata as ad
import numpy as np
import pandas as pd
import pytest
from scipy import sparse

from bionexus.abi import capability_abis, get_capability_abi
from bionexus.capabilities import CANONICAL_CAPABILITIES
from bionexus.intent_router import route_scientific_intent
from bionexus.tangram import (
    TangramConfig,
    TangramMappingResult,
    check_tangram_backend,
    run_tangram_spatial_mapping,
    select_training_marker_genes,
)


@pytest.fixture
def dummy_sc_and_spatial():
    """Create matched synthetic single-cell reference and spatial AnnData fixtures."""
    np.random.seed(42)
    n_sc = 60
    n_sp = 20
    genes = [f"Gene_{i}" for i in range(1, 31)]

    # Single-cell reference with 3 cell types
    X_sc = np.random.poisson(lam=2.0, size=(n_sc, len(genes))).astype(np.float32)
    # Plant marker signals
    X_sc[:20, 0:5] += 15.0  # CellType_A markers
    X_sc[20:40, 5:10] += 15.0  # CellType_B markers
    X_sc[40:60, 10:15] += 15.0  # CellType_C markers

    cell_types = ["CellType_A"] * 20 + ["CellType_B"] * 20 + ["CellType_C"] * 20
    adata_sc = ad.AnnData(
        X=sparse.csr_matrix(X_sc),
        obs=pd.DataFrame({"cell_type": cell_types}, index=[f"sc_{i}" for i in range(n_sc)]),
        var=pd.DataFrame(index=genes),
    )

    # Spatial target with 2D coordinates
    X_sp = np.random.poisson(lam=3.0, size=(n_sp, len(genes))).astype(np.float32)
    coords = np.random.uniform(0, 100, size=(n_sp, 2))
    adata_sp = ad.AnnData(
        X=sparse.csr_matrix(X_sp),
        obs=pd.DataFrame(index=[f"spot_{i}" for i in range(n_sp)]),
        var=pd.DataFrame(index=genes),
        obsm={"spatial": coords},
    )

    return adata_sc, adata_sp


def test_select_training_marker_genes(dummy_sc_and_spatial):
    """Verify marker gene extraction selects high-contrast markers shared with spatial data."""
    adata_sc, adata_sp = dummy_sc_and_spatial
    markers, sig_df = select_training_marker_genes(adata_sc, adata_sp, cell_type_col="cell_type", n_top_markers=5)

    assert len(markers) >= 10
    assert "Gene_1" in markers
    assert "Gene_6" in markers
    assert sig_df.shape[1] == 3  # 3 cell types


def test_run_tangram_mapping_fallback(dummy_sc_and_spatial):
    """Verify execution in fallback NNLS mode ONLY when caller explicitly opts in (allow_fallback=True)."""
    adata_sc, adata_sp = dummy_sc_and_spatial
    cfg = TangramConfig(num_epochs=10, min_shared_genes=5)

    res = run_tangram_spatial_mapping(
        adata_sc=adata_sc,
        adata_sp=adata_sp,
        cell_type_col="cell_type",
        config=cfg,
        allow_fallback=True,
    )

    assert res.success is True
    assert res.n_spots == 20
    assert res.n_cells_or_clusters == 3
    assert len(res.cell_type_names) == 3
    assert "tangram_ct_pred" in adata_sp.obsm
    assert "dominant_cell_type" in adata_sp.obs
    assert len(adata_sp.obs["dominant_cell_type"]) == 20
    assert res.status == "COMPLETED_WITH_HEURISTIC_FALLBACK"


def test_run_tangram_fail_closed_default_without_fallback(dummy_sc_and_spatial):
    """
    CRITICAL INVARIANT (Fail-closed by default, degrade only by explicit opt-in):
    When tangram is not installed and allow_fallback=False (the default),
    BioNexus MUST refuse with REFUSAL_BACKEND_UNAVAILABLE.
    """
    adata_sc, adata_sp = dummy_sc_and_spatial
    cfg = TangramConfig(min_shared_genes=5)

    # By default allow_fallback is False
    with patch("bionexus.tangram.check_tangram_backend", return_value=(False, "tangram not installed")):
        res = run_tangram_spatial_mapping(
            adata_sc=adata_sc,
            adata_sp=adata_sp,
            cell_type_col="cell_type",
            config=cfg,
            # allow_fallback=False by default!
        )

        assert res.success is False
        assert res.status == "REFUSAL_BACKEND_UNAVAILABLE"
        assert "allow_fallback=True" in res.remedy_if_failed


def test_run_tangram_refusal_missing_coordinates(dummy_sc_and_spatial):
    """Verify fail-closed refusal when target is missing obsm['spatial']."""
    adata_sc, adata_sp = dummy_sc_and_spatial
    del adata_sp.obsm["spatial"]

    res = run_tangram_spatial_mapping(adata_sc, adata_sp)
    assert res.success is False
    assert res.status == "REFUSAL_MISSING_COORDINATES"
    assert "obsm['spatial']" in res.remedy_if_failed


def test_run_tangram_refusal_invalid_coordinates_shape(dummy_sc_and_spatial):
    """Verify fail-closed refusal when obsm['spatial'] is 1D or invalid shape."""
    adata_sc, adata_sp = dummy_sc_and_spatial
    adata_sp.obsm["spatial"] = np.random.uniform(0, 10, size=(20, 5))  # 5D invalid

    res = run_tangram_spatial_mapping(adata_sc, adata_sp)
    assert res.success is False
    assert res.status == "REFUSAL_INVALID_COORDINATES"


def test_run_tangram_refusal_missing_cell_type_col(dummy_sc_and_spatial):
    """Verify fail-closed refusal when reference lacks specified cell_type column."""
    adata_sc, adata_sp = dummy_sc_and_spatial
    res = run_tangram_spatial_mapping(adata_sc, adata_sp, cell_type_col="non_existent_col")
    assert res.success is False
    assert res.status == "REFUSAL_MISSING_CELL_TYPE_ANNOTATION"


def test_run_tangram_refusal_insufficient_shared_genes(dummy_sc_and_spatial):
    """Verify fail-closed refusal when shared marker gene count is under threshold."""
    adata_sc, adata_sp = dummy_sc_and_spatial
    # Rename spatial genes so zero genes overlap
    adata_sp.var_names = [f"DifferentGene_{i}" for i in range(len(adata_sp.var_names))]

    res = run_tangram_spatial_mapping(adata_sc, adata_sp)
    assert res.success is False
    assert res.status == "REFUSAL_INSUFFICIENT_SHARED_GENES"


def test_tangram_capability_contract_registered():
    """Verify spatial.tangram_deconvolution is registered in CANONICAL_CAPABILITIES."""
    assert "spatial.tangram_deconvolution" in CANONICAL_CAPABILITIES
    cap = CANONICAL_CAPABILITIES["spatial.tangram_deconvolution"]
    assert cap.skill_name == "spatial-transcriptomics"
    assert cap.backend.import_name == "tangram"
    assert len(cap.preconditions) >= 3


def test_tangram_abi_projection_and_zero_drift():
    """Verify spatial.tangram_deconvolution projects cleanly to ABI with zero drift."""
    abis = capability_abis()
    assert "spatial.tangram_deconvolution" in abis

    abi = get_capability_abi("spatial.tangram_deconvolution")
    assert abi.capability_id == "spatial.tangram_deconvolution"
    assert abi.input_contract.coordinates_required is True
    assert abi.evidence_ceiling.without_external_validation in ("SUPPORTED", "PRELIMINARY")
    assert "clinical_diagnosis" in abi.forbidden_claims


def test_tangram_intent_routing():
    """Verify user queries about Tangram or spatial spot deconvolution route to spatial.tangram_deconvolution."""
    res = route_scientific_intent("Please run Tangram cell-to-space deconvolution on this 10x Visium sample")
    assert res.matched_capability is not None
    assert res.matched_capability.id == "spatial.tangram_deconvolution"

    res2 = route_scientific_intent("deconvolve spot cell type proportions using single-cell reference")
    assert res2.matched_capability is not None
    assert res2.matched_capability.id == "spatial.tangram_deconvolution"
