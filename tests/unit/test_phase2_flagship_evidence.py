from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from scipy import sparse

from evals.annotation_external_holdout_validation import _map_reference_label, _validate_and_score_counts
from evals.annotation_external_validation import _fit_candidate_threshold, wilson_interval
from evals.flagship_validation import FLAGSHIP_DATASETS
from evals.spatial_instrument_validation import _cramers_v_identical

REPO_ROOT = Path(__file__).resolve().parents[2]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_phase2_preregistrations_are_hash_locked() -> None:
    for relative in (
        Path("validation/annotation/studies/BN-ANN-IV-001"),
        Path("validation/annotation/studies/BN-ANN-IV-002"),
        Path("validation/annotation/studies/BN-ANN-IV-003"),
        Path("validation/spatial/studies/BN-SP-IV-001"),
    ):
        prereg = REPO_ROOT / relative / "PREREGISTRATION.json"
        lock = json.loads((REPO_ROOT / relative / "PREREGISTRATION_LOCK.json").read_text(encoding="utf-8"))
        assert _sha256(prereg) == lock["sha256"]
        assert lock["external_timestamp"] is False


def test_flagship_manifests_require_real_downloaded_file_names() -> None:
    assert FLAGSHIP_DATASETS["citeseq_pbmc_sorted"]["required_files"] == [
        "DATASET_MANIFEST.json",
        "pbmc_10k_protein_v3.h5ad",
        "pbmc_5k_protein_v3.h5ad",
    ]
    assert FLAGSHIP_DATASETS["xenium_spatial_truth"]["required_files"] == [
        "DATASET_MANIFEST.json",
        "Xenium_V1_Protein_Human_Kidney_tiny_outs.zip",
    ]


def test_candidate_threshold_fit_uses_locked_precision_lower_bound() -> None:
    margins = np.linspace(0.0, 1.0, 200)
    correct = margins >= 0.25
    fitted = _fit_candidate_threshold(margins, correct)
    assert fitted is not None
    assert fitted["accepted"] >= 100
    assert fitted["precision_wilson_95"][0] >= 0.90


def test_wilson_interval_is_bounded_and_conservative() -> None:
    lower, upper = wilson_interval(90, 100)
    assert 0.0 < lower < 0.90 < upper < 1.0


def test_external_reference_mapping_is_locked_and_abstains_when_unmapped() -> None:
    mapping = {
        "T": ["CD4", "CD8", "T cell", "Tcm", "Tem", "Treg", "MAIT"],
        "B": ["B cell", "B naive", "B memory", "Plasmablast"],
        "MONOCYTE": ["Mono", "Monocyte"],
        "NK": ["NK"],
    }
    assert _map_reference_label("CD4 Naive", mapping) == "T"
    assert _map_reference_label("Mono CD14", mapping) == "MONOCYTE"
    assert _map_reference_label("Dendritic cell", mapping) is None


def test_external_holdout_rejects_normalized_expression() -> None:
    adata = SimpleNamespace(X=sparse.csr_matrix(np.full((2, 12), 0.5)), n_obs=2)
    marker_indices = {
        lineage: list(range(index * 3, index * 3 + 3))
        for index, lineage in enumerate(("T", "B", "MONOCYTE", "NK"))
    }
    with pytest.raises(ValueError, match="not a finite non-negative integer count matrix"):
        _validate_and_score_counts(adata.X, adata.n_obs, marker_indices)


def test_identical_manufactured_fov_condition_has_cramers_v_one() -> None:
    assert _cramers_v_identical(np.asarray(["A", "A", "B", "B"], dtype=object)) == 1.0


def test_annotation_real_data_result_is_not_over_promoted() -> None:
    report = json.loads(
        (REPO_ROOT / "validation/annotation/studies/BN-ANN-IV-001/REPORT.json").read_text(encoding="utf-8")
    )
    assert report["status"]["public_reference_dataset"] is True
    assert report["status"]["independent_ground_truth"] is False
    assert report["status"]["run_status"] == "endpoints_met_inconclusive"
    assert report["post_run_scientific_audit"]["degenerate_nonselective_gate"] is True
    assert report["candidate_gate"]["threshold"] == 0.0


def test_blind_external_successor_retains_input_ineligible_result() -> None:
    report = json.loads(
        (REPO_ROOT / "validation/annotation/studies/BN-ANN-IV-002/REPORT.json").read_text(encoding="utf-8")
    )
    assert report["status"]["run_status"] == "not_evaluated_input_ineligible"
    assert report["input_contract"]["passed"] is False
    assert report["input_contract"]["reference_labels_accessed"] is False
    assert all(
        endpoint["status"] == "NOT_EVALUATED_INPUT_INELIGIBLE"
        for endpoint in report["primary_endpoints"].values()
    )


def test_nonblinded_raw_count_successor_is_bounded_candidate() -> None:
    report = json.loads(
        (REPO_ROOT / "validation/annotation/studies/BN-ANN-IV-003/REPORT.json").read_text(encoding="utf-8")
    )
    assert report["input_contract"]["complete_matrix_finite_nonnegative_integer"] is True
    assert report["status"]["run_status"] == "positive_candidate"
    assert report["status"]["maximum_maturity"] == "CANDIDATE_EXTERNAL_REFERENCE_NONBLINDED"
    assert report["status"]["independent_ground_truth"] is False
    assert report["access_disclosure"]["blinding_status"] == "NOT_BLINDED_TO_LABEL_DISTRIBUTION"
    assert all(endpoint["passed"] for endpoint in report["primary_endpoints"].values())


def test_spatial_real_instrument_negative_result_is_retained() -> None:
    report = json.loads(
        (REPO_ROOT / "validation/spatial/studies/BN-SP-IV-001/REPORT.json").read_text(encoding="utf-8")
    )
    assert report["dataset"]["dataset_track"] == "real_instrument_technical_acceptance"
    assert report["status"]["run_status"] in ("negative_result", "technical_acceptance_pass")
    assert report["status"]["public_reference_dataset"] is False
    assert report["endpoints"]["cell_size_bias"]["passed"] in (True, False)
