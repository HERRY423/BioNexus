"""Adversarial checks for benchmark inputs and declared scientific endpoints."""

import hashlib
from dataclasses import replace
from types import SimpleNamespace

import pandas as pd
import pytest
import yaml

from evals.datasets.download_reference_benchmarks import download_benchmark
from evals.outcome_checks import check_de_recovery, check_spatial_effects
from evals.runner import load_eval_cases, run_single_case

DE = {"expected_de_genes": ["g0"], "fdr_q_max": 0.05, "min_log2fc": 1.0}


@pytest.mark.parametrize(
    "column,value",
    [
        ("padj", 0.6),
        ("padj", 0.05),
        ("padj", float("nan")),
        ("padj", -1),
        ("log2FoldChange", 0.2),
        ("log2FoldChange", -2),
        ("log2FoldChange", float("inf")),
        ("pvalue", float("nan")),
    ],
)
def test_top_rank_alone_cannot_pass_de(column, value):
    row = {"gene": "g0", "pvalue": 0.001, "padj": 0.01, "log2FoldChange": 2.0}
    row[column] = value
    assert check_de_recovery(pd.DataFrame([row]), DE)


def test_declared_de_endpoints_pass():
    assert not check_de_recovery(
        pd.DataFrame([{"gene": "g0", "pvalue": 0.001, "padj": 0.01, "log2FoldChange": 1.0}]), DE
    )


@pytest.mark.parametrize("value", [0.1, float("nan"), float("inf")])
def test_spatial_threshold_applies_to_every_declared_gene(value):
    table = pd.DataFrame({"gene": ["OTHER_GENE"], "morans_i": [value]})
    assert check_spatial_effects(table, {"expected_genes": ["OTHER_GENE"], "moran_i_min": 0.3})


def test_runner_uses_declared_fdr(monkeypatch):
    import sys

    table = pd.DataFrame([{"gene": "g0", "pvalue": 0.001, "padj": 0.9, "log2FoldChange": 2.0}])
    monkeypatch.setitem(sys.modules, "scrna_deseq", SimpleNamespace(run_pydeseq2=lambda *a, **kw: (table, {})))
    case = next(
        c
        for c in load_eval_cases(suite="l3_scientific_outcomes")
        if c.data_metadata["planted_signal"] == "pseudobulk_de"
    )
    result = run_single_case(case)
    assert not result.passed
    assert result.actual_status == "OUTCOME_MISMATCH"
    assert any("padj" in reason for reason in result.failure_reasons)


def test_marker_verifier_uses_yaml_expected_genes(monkeypatch):
    import sys

    monkeypatch.setitem(sys.modules, "anndata", SimpleNamespace(read_h5ad=lambda *a: object()))
    monkeypatch.setitem(sys.modules, "make_tiny", SimpleNamespace(write_tiny_scrna=lambda *a: None))
    markers = pd.DataFrame({"names": ["CD3D", "MS4A1", "CD14"]})
    monkeypatch.setitem(
        sys.modules, "scrna_pipeline", SimpleNamespace(run_scrna_gold_chain=lambda *a, **kw: (None, markers, {}))
    )
    case = load_eval_cases(suite="l3_scientific_outcomes")[0]
    case = replace(case, data_metadata={**case.data_metadata, "expected_genes": ["UNRECOVERED"]})
    result = run_single_case(case)
    assert not result.passed
    assert "UNRECOVERED" in " ".join(result.failure_reasons)


@pytest.mark.parametrize(
    "data", [{"cases": []}, [], ["bad"], [{"id": "broken"}], [{"id": "a", "known_limitation": "false"}]]
)
def test_invalid_suite_cannot_disappear_from_denominator(tmp_path, data):
    (tmp_path / "bad.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(ValueError):
        load_eval_cases(datasets_dir=tmp_path)


def test_duplicate_case_ids_fail_closed(tmp_path):
    case = load_eval_cases(suite="l3_scientific_outcomes")[0].to_dict()
    (tmp_path / "duplicate.yaml").write_text(yaml.safe_dump([case, case]), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        load_eval_cases(datasets_dir=tmp_path)


def test_missing_suite_cannot_return_green(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_eval_cases(suite="typo", datasets_dir=tmp_path)


def test_failed_download_never_materializes_synthetic_reference(tmp_path, monkeypatch):
    def fail(url, target):
        target.write_bytes(b"partial")
        raise OSError("offline")

    monkeypatch.setattr("urllib.request.urlretrieve", fail)
    with pytest.raises(OSError, match="offline"):
        download_benchmark("pbmc3k_scrna", tmp_path, expected_sha256="a" * 64)
    assert not list(tmp_path.iterdir())


def test_pinned_download_and_cache_require_matching_bytes(tmp_path, monkeypatch):
    data = b"public dataset fixture bytes"
    digest = hashlib.sha256(data).hexdigest()
    monkeypatch.setattr("urllib.request.urlretrieve", lambda url, path: path.write_bytes(data))
    path = download_benchmark("pbmc3k_scrna", tmp_path, expected_sha256=digest)
    assert path.read_bytes() == data
    assert download_benchmark("pbmc3k_scrna", tmp_path, expected_sha256=digest) == path
    path.write_bytes(b"substituted cache")
    with pytest.raises(ValueError, match="mismatch"):
        download_benchmark("pbmc3k_scrna", tmp_path, expected_sha256=digest)
    assert path.read_bytes() == b"substituted cache"


def test_unpinned_cache_is_rejected(tmp_path):
    (tmp_path / "pbmc3k_raw.h5ad").write_bytes(b"legacy synthetic cache")
    with pytest.raises(ValueError, match="expected_sha256"):
        download_benchmark("pbmc3k_scrna", tmp_path)


@pytest.mark.parametrize("dataset", ["visium_mouse_brain", "clinvar_controls"])
def test_unconfigured_sources_do_not_create_fake_controls(tmp_path, dataset):
    with pytest.raises(ValueError, match="No public download source"):
        download_benchmark(dataset, tmp_path, expected_sha256="a" * 64)
    assert not list(tmp_path.iterdir())
