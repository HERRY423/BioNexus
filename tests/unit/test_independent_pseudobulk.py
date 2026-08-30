from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy import sparse

ad = pytest.importorskip("anndata", reason="scientific-backend test requires anndata")

from bionexus.independent_pseudobulk import (
    aggregate_pseudobulk,
    direction_concordance,
    exact_sign_flip_empirical_p_value,
    independent_claim_status,
    sign_flip_empirical_p_value,
    validate_independent_biostatistician_attestation,
    validate_preaggregated_pseudobulk,
    validate_preregistration,
    verify_negative_result_freeze,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _paired_adata(*, floats: bool = False) -> ad.AnnData:
    matrix = np.array(
        [
            [10, 1, 0],
            [8, 2, 0],
            [20, 1, 0],
            [18, 2, 0],
            [9, 1, 1],
            [7, 2, 0],
            [19, 2, 0],
            [17, 3, 0],
            [11, 0, 1],
            [9, 1, 0],
            [22, 1, 0],
            [20, 2, 0],
        ],
        dtype=float if floats else int,
    )
    if floats:
        matrix[0, 0] = 10.5
    obs = pd.DataFrame(
        {
            "donor": ["d1"] * 4 + ["d2"] * 4 + ["d3"] * 4,
            "condition": ["ctrl", "ctrl", "stim", "stim"] * 3,
        },
        index=[f"c{i}" for i in range(matrix.shape[0])],
    )
    return ad.AnnData(X=sparse.csr_matrix(matrix), obs=obs, var=pd.DataFrame(index=["g1", "g2", "g3"]))


def test_aggregate_pseudobulk_uses_paired_donors_and_raw_counts():
    counts, design, audit = aggregate_pseudobulk(
        _paired_adata(),
        donor_column="donor",
        condition_column="condition",
        cohort_id="C01",
        reference_level="ctrl",
        contrast_level="stim",
        minimum_paired_donors=3,
        minimum_cells_per_sample=2,
    )
    assert audit.passed is True
    assert audit.n_paired_donors == 3
    assert counts.shape == (6, 3)
    assert design["n_cells"].min() == 2
    assert counts.loc["C01__d1__ctrl", "G1"] == 18


def test_noninteger_counts_fail_closed():
    _counts, _design, audit = aggregate_pseudobulk(
        _paired_adata(floats=True),
        donor_column="donor",
        condition_column="condition",
        cohort_id="C01",
        reference_level="ctrl",
        contrast_level="stim",
        minimum_paired_donors=3,
        minimum_cells_per_sample=2,
    )
    assert audit.passed is False
    assert audit.raw_nonnegative_integer_counts is False
    assert any("raw non-negative integer" in issue for issue in audit.issues)


def test_preaggregated_pseudobulk_is_not_aggregated_twice():
    obs = pd.DataFrame(
        {
            "donor": ["d1", "d1", "d2", "d2", "d3", "d3"],
            "condition": ["ctrl", "stim"] * 3,
            "n_cells": [20, 10, 30, 15, 25, 12],
        },
        index=[f"s{i}" for i in range(6)],
    )
    matrix = sparse.csr_matrix(np.arange(18, dtype=np.uint32).reshape(6, 3))
    adata = ad.AnnData(X=matrix, obs=obs, var=pd.DataFrame(index=["g1", "g2", "g3"]))
    adata.layers["counts"] = matrix.copy()
    counts, design, audit = validate_preaggregated_pseudobulk(
        adata,
        donor_column="donor",
        condition_column="condition",
        cohort_id="C02",
        reference_level="ctrl",
        contrast_level="stim",
        minimum_paired_donors=3,
        minimum_cells_per_sample=10,
    )
    assert audit.passed is True
    assert audit.n_cells == 112
    assert counts.shape == (6, 3)
    assert counts.loc["C02__d1__ctrl", "G1"] == 0
    assert design["n_cells"].min() == 10


def test_direction_concordance_and_sign_flip_null_are_deterministic():
    donor_effects = pd.DataFrame(
        [[2.0, -1.0, 3.0], [1.5, -2.0, 2.0], [1.0, -1.5, 4.0]],
        index=["d1", "d2", "d3"],
        columns=["G1", "G2", "G3"],
    )
    expected = pd.Series({"G1": 1.0, "G2": -1.0, "G3": 1.0})
    concordance, n = direction_concordance(donor_effects.median(axis=0), expected, expected.index)
    assert concordance == 1.0
    assert n == 3
    observed, p_value, null_scores = sign_flip_empirical_p_value(
        donor_effects, expected, list(expected.index), permutations=7, seed=11
    )
    assert observed == 1.0
    assert p_value is not None
    assert len(null_scores) == 7


def test_exact_sign_flip_enumerates_every_nonidentity_assignment():
    donor_effects = pd.DataFrame(
        [[2.0, -1.0], [1.5, -2.0], [1.0, -1.5]],
        index=["d1", "d2", "d3"],
        columns=["G1", "G2"],
    )
    expected = pd.Series({"G1": 1.0, "G2": -1.0})
    observed, p_value, null_scores = exact_sign_flip_empirical_p_value(
        donor_effects, expected, list(expected.index)
    )
    assert observed == 1.0
    assert p_value == (1 + sum(value >= observed for value in null_scores)) / 8
    assert len(null_scores) == (2**3) - 1


def test_exact_sign_flip_has_4095_assignments_for_twelve_donors():
    donor_effects = pd.DataFrame(
        np.tile([[2.0, -1.0]], (12, 1)),
        index=[f"d{i}" for i in range(12)],
        columns=["G1", "G2"],
    )
    expected = pd.Series({"G1": 1.0, "G2": -1.0})
    _observed, _p_value, null_scores = exact_sign_flip_empirical_p_value(
        donor_effects, expected, list(expected.index)
    )
    assert len(null_scores) == 4095


def test_preregistration_hash_mismatch_is_rejected(tmp_path):
    prereg = {
        "schema_version": "bionexus.pseudobulk-independent-preregistration.v1",
        "study_id": "S1",
        "locked": True,
        "cohorts": [{}, {}],
        "primary_endpoints": {
            "discovery_top_n": 10,
            "donor_leave_one_out": {},
            "platform_holdout": {},
            "multi_cohort": {},
            "negative_control": {},
        },
    }
    path = tmp_path / "PREREGISTRATION.json"
    encoded = json.dumps(prereg).encode()
    path.write_bytes(encoded)
    lock = {
        "study_id": "S1",
        "preregistration_sha256": hashlib.sha256(encoded).hexdigest(),
    }
    assert validate_preregistration(prereg, lock, path) == []
    lock["preregistration_sha256"] = "0" * 64
    assert any("hash mismatch" in issue for issue in validate_preregistration(prereg, lock, path))


def test_exact_sign_flip_preregistration_rejects_post_hoc_style_sampling(tmp_path):
    prereg = {
        "schema_version": "bionexus.pseudobulk-independent-preregistration.v1",
        "study_id": "S2",
        "locked": True,
        "cohorts": [{}, {}],
        "primary_endpoints": {
            "discovery_top_n": 10,
            "donor_leave_one_out": {},
            "platform_holdout": {},
            "multi_cohort": {},
            "negative_control": {
                "method": "paired_donor_condition_label_exact_sign_flip",
                "donors": 12,
                "permutations": 255,
                "seed": 11,
            },
        },
    }
    path = tmp_path / "PREREGISTRATION.json"
    path.write_text(json.dumps(prereg), encoding="utf-8")
    lock = {"study_id": "S2", "preregistration_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    issues = validate_preregistration(prereg, lock, path)
    assert any("4095" in issue for issue in issues)
    assert any("must not specify a random seed" in issue for issue in issues)


def test_subsample_or_missing_blinding_caps_independent_claim():
    status = independent_claim_status(
        input_gates_passed=True,
        endpoints_passed=True,
        full_cohorts_used=False,
        independent_blinding_attested=False,
    )
    assert status == {
        "run_status": "incomplete_not_claim_ready",
        "conclusion_maturity": "PRELIMINARY",
        "independent_biological_validation": "ABSTAIN",
    }


def test_failed_endpoint_is_retained_as_negative_result():
    status = independent_claim_status(
        input_gates_passed=True,
        endpoints_passed=False,
        full_cohorts_used=True,
        independent_blinding_attested=True,
    )
    assert status["run_status"] == "negative_result"
    assert status["independent_biological_validation"] == "not_supported"


def test_committed_independent_report_retains_failed_endpoints_and_hashes():
    root = REPO_ROOT / "validation" / "pseudobulk" / "independent"
    prereg = json.loads((root / "PREREGISTRATION.json").read_text(encoding="utf-8"))
    lock = json.loads((root / "PREREGISTRATION_LOCK.json").read_text(encoding="utf-8"))
    report = json.loads((root / "REPORT.json").read_text(encoding="utf-8"))
    provenance = json.loads((root / "PROVENANCE.json").read_text(encoding="utf-8"))

    assert validate_preregistration(prereg, lock, root / "PREREGISTRATION.json") == []
    failed = sorted(name for name, endpoint in report["endpoints"].items() if not endpoint["passed"])
    assert sorted(report["negative_results"]) == failed
    assert report["status"]["run_status"] == "negative_result"
    assert report["status"]["independent_biological_validation"] == "not_supported"

    for artifact in provenance["output_files"]:
        p_str = artifact["path"]
        fname = Path(p_str.replace("\\", "/")).name
        path = Path(p_str)
        if not path.is_file():
            path = root / fname
            if not path.is_file():
                path = root / "evidence" / fname
        assert path.is_file()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == artifact["sha256"]


def test_committed_negative_result_freeze_is_intact():
    freeze = REPO_ROOT / "validation" / "pseudobulk" / "independent" / "NEGATIVE_RESULT_FREEZE.json"
    assert verify_negative_result_freeze(freeze) == []
    manifest = json.loads(freeze.read_text(encoding="utf-8"))
    assert manifest["result"]["empirical_p_value"] == 0.05859375
    assert manifest["policy"]["post_hoc_permutation_increase_prohibited"] is True


def test_pending_biostatistician_template_fails_closed():
    path = (
        REPO_ROOT
        / "validation"
        / "pseudobulk"
        / "studies"
        / "BN-PB-IV-003"
        / "reviewer"
        / "INDEPENDENT_BIOSTATISTICIAN_ATTESTATION.template.json"
    )
    issues = validate_independent_biostatistician_attestation(
        path,
        preregistration_sha256="a" * 64,
        blinded_packet_sha256="b" * 64,
        analysis_code_sha256="c" * 64,
    )
    assert any("not SIGNED_COMPLETE" in issue for issue in issues)
    assert any("reviewer independence" in issue for issue in issues)
