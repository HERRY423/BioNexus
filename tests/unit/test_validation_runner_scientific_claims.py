"""Runner regressions: real model requests and honest statistical denominators."""

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from scipy import sparse

ad = pytest.importorskip("anndata")

from evals import flagship_validation as flagship
from evals import pseudobulk_stress_test as stress
from scripts import run_flagship_validation as report_runner


@pytest.fixture
def paired_data():
    donors = np.tile(np.repeat(["d1", "d2", "d3", "d4"], 2), 10)
    obs = pd.DataFrame(
        {"donor": donors, "condition": ["ctrl", "stim"] * 40},
        index=[f"c{i}" for i in range(80)],
    )
    return ad.AnnData(
        X=sparse.csr_matrix(np.full((80, 100), 100, dtype=int)),
        obs=obs,
        var=pd.DataFrame(index=[f"g{i}" for i in range(100)]),
    )


@pytest.fixture
def fit_capture(monkeypatch):
    calls = []

    def fit(counts, design, **kwargs):
        calls.append((counts.copy(), design.copy(), kwargs))
        assert kwargs["donor"] == "donor"
        assert "donor" in design.columns
        return pd.DataFrame({"gene": counts.columns, "padj": 0.01}), {
            "paired": True,
            "design_formula": "~ donor + condition",
            "method": "pydeseq2.DeseqStats",
            "backend": "pydeseq2",
        }

    monkeypatch.setattr(stress, "run_pydeseq2", fit)
    return calls, fit


def test_all_stress_fit_dimensions_request_paired_model(paired_data, fit_capture):
    calls, _ = fit_capture
    truth = pd.DataFrame({"gene": paired_data.var_names, "support": 1})
    first = stress.test_dim1_public_reference(paired_data, truth)
    assert first["model_design"] == "~ donor + condition"
    assert first["independent_ground_truth"] is False
    stress.test_dim2_cell_downsampling(paired_data, truth, set(paired_data.var_names))
    stress.test_dim4_effect_size_sensitivity(paired_data)
    stress.test_dim5_permutation_null(paired_data)
    assert len(calls) == 10


def test_permutation_preserves_donor_pairs_and_does_not_claim_fdr(paired_data, fit_capture):
    calls, _ = fit_capture
    result = stress.test_dim5_permutation_null(paired_data)
    permuted = calls[0][1]
    assert all(set(group.condition) == {"ctrl", "stim"} for _, group in permuted.groupby("donor"))
    assert result["observed_global_null_rejection_fraction"] == 1.0
    assert result["passed"] is False
    assert result["fdr_controlled"] is None
    assert result["global_null_truth_established"] is False
    assert result["n_permutations"] == 1


@pytest.mark.parametrize(
    "pvalues, expected_fraction, expected_pass, expected_n",
    [([0.01, 0.9, np.nan], 0.5, False, 2), ([np.nan], None, False, 0), ([0.9], 0.0, True, 1)],
)
def test_permutation_uses_estimable_denominator(paired_data, monkeypatch, pvalues, expected_fraction, expected_pass, expected_n):
    monkeypatch.setattr(stress, "run_pydeseq2", lambda *a, **k: (pd.DataFrame({"padj": pvalues}), {}))
    result = stress.test_dim5_permutation_null(paired_data)
    assert result["observed_global_null_rejection_fraction"] == expected_fraction
    assert result["n_genes_tested"] == expected_n
    assert result["passed"] is expected_pass
    assert result["fdr_controlled"] is None


@pytest.mark.parametrize("bad", [-0.1, 1.1, np.inf, -np.inf])
def test_permutation_rejects_invalid_adjusted_pvalues(paired_data, monkeypatch, bad):
    monkeypatch.setattr(stress, "run_pydeseq2", lambda *a, **k: (pd.DataFrame({"padj": [bad]}), {}))
    with pytest.raises(ValueError, match="finite probabilities"):
        stress.test_dim5_permutation_null(paired_data)


def test_flagship_requests_paired_model_and_records_method(paired_data, fit_capture, monkeypatch):
    import scrna_deseq

    import bionexus.backend_conformance as conformance

    calls, fit = fit_capture
    monkeypatch.setattr(conformance, "verify_backend_identity", lambda cap: SimpleNamespace(conformant=True))
    monkeypatch.setattr(flagship, "flagship_dataset_present", lambda dataset: True)
    monkeypatch.setattr(ad, "read_h5ad", lambda path: paired_data)
    monkeypatch.setattr(pd, "read_csv", lambda path: pd.DataFrame({"gene": paired_data.var_names, "support": 1}))
    monkeypatch.setattr(scrna_deseq, "run_pydeseq2", fit)
    result = flagship._suite_pseudobulk_external_truth(None, {})
    assert len(calls) == 1
    observed = result["observed"]
    assert observed["paired"] is True
    assert observed["adjusted_pvalue_method"]["n_available_adjusted_pvalues"] == 100
    metrics = {item["name"]: item for item in report_runner._build_metrics_for_pseudobulk_run(observed)}
    assert "fdr_control" not in metrics
    assert metrics["multiple_testing_method_applied"]["result"] == "pass"
    assert metrics["multiple_testing_method_applied"]["observed"]["error_rate_control_established"] is False
    assert metrics["donor_aware_design"]["result"] == "pass"


def test_samples_alone_do_not_establish_paired_fit_or_adjustment():
    observed = {"published_support_fraction": 0.9, "n_pseudobulk_samples": 16}
    metrics = {item["name"]: item for item in report_runner._build_metrics_for_pseudobulk_run(observed)}
    assert metrics["donor_aware_design"]["result"] == "fail"
    assert metrics["multiple_testing_method_applied"]["result"] == "fail"


def test_failed_metric_makes_root_report_fail(monkeypatch):
    case = SimpleNamespace(data_metadata={"dataset_id": "citeseq_pbmc_sorted", "flagship_suite": "annotation_distrust"})
    monkeypatch.setattr(report_runner, "flagship_dataset_present", lambda dataset: True)
    monkeypatch.setattr(report_runner, "run_flagship_case", lambda case: {
        "actual_status": "PERMITTED", "observed": {"post_run_scientific_audit": {"claim_target_supported": False}},
    })
    monkeypatch.setattr(report_runner, "_resolve_backend_identity", lambda cap: {})
    monkeypatch.setattr(report_runner, "compute_file_checksum", lambda path: "fixture")
    monkeypatch.setattr(report_runner, "capture_execution_provenance", lambda **kw: {})
    monkeypatch.setattr(report_runner, "bind_validation_source_provenance", lambda *args: {})
    artifact = report_runner.run_single_capability("scrna.annotation_evidence", "citeseq_pbmc_sorted", [case])
    assert artifact.status == "fail"
