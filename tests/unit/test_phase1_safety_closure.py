"""Regression gates for the Phase-1 laboratory safety closure."""

from __future__ import annotations

import inspect
import json
import sys
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRNA_SCRIPTS = PROJECT_ROOT / "skills" / "single-cell-rna-qc" / "scripts"
SPATIAL_SCRIPTS = PROJECT_ROOT / "skills" / "spatial-transcriptomics" / "scripts"
if str(SCRNA_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRNA_SCRIPTS))
if str(SPATIAL_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SPATIAL_SCRIPTS))

from scrna_deseq import run_pydeseq2
from spatial_pipeline import prepare_spatial_expression_input

from bionexus.artifacts import RunBundle, verify_run_bundle
from bionexus.egress_guard import DataGovernanceGuard, EgressBlockedError, EgressMode, guarded_urlopen
from bionexus.integrity import (
    ScientificInputError,
    require_raw_count_matrix,
    require_replicate_design,
    require_spatial_coordinates,
)
from bionexus.scfm import simulate_gene_perturbation


def test_raw_count_gate_rejects_normalized_values_without_rounding():
    normalized = np.array([[0.0, 1.25], [2.0, 3.0]])
    with pytest.raises(ScientificInputError, match="non-integer"):
        require_raw_count_matrix(normalized)

    counts = pd.DataFrame(
        normalized,
        index=["a1", "a2"],
        columns=["G1", "G2"],
    )
    design = pd.DataFrame({"sample_id": ["a1", "a2"], "condition": ["A", "B"]})
    with pytest.raises(ScientificInputError):
        run_pydeseq2(counts, design, condition="condition")


def test_replicate_gate_requires_exact_alignment_and_two_per_level():
    counts = pd.DataFrame(
        np.ones((4, 2), dtype=int),
        index=["a1", "a2", "b1", "b2"],
    )
    under_replicated = pd.DataFrame(
        {"condition": ["A", "A", "A", "B"]},
        index=counts.index,
    )
    with pytest.raises(ScientificInputError, match="biological replicates"):
        require_replicate_design(counts, under_replicated, condition="condition")

    misaligned = pd.DataFrame(
        {"condition": ["A", "A", "B", "B"]},
        index=["a1", "a2", "b1", "other"],
    )
    with pytest.raises(ScientificInputError, match="match exactly"):
        require_replicate_design(counts, misaligned, condition="condition")


def test_spatial_gate_rejects_coordinate_observation_mismatch():
    coords = np.column_stack([np.arange(6), np.arange(6) ** 2]).astype(float)
    with pytest.raises(ScientificInputError, match="not aligned"):
        require_spatial_coordinates(coords, n_observations=7)


def test_spatial_expression_gate_preserves_normalized_state_and_promotes_only_raw_counts():
    class MinimalAnnData:
        def __init__(self, matrix):
            self.X = matrix
            self.layers = {}

    normalized = MinimalAnnData(np.array([[0.1, 1.2], [2.3, 0.0]]))
    _matrix, has_counts, grade, _notes, _stats = prepare_spatial_expression_input(normalized)
    assert has_counts is False
    assert "counts" not in normalized.layers
    assert grade == "A"

    raw = MinimalAnnData(np.array([[0, 1], [2, 3]], dtype=int))
    _matrix, has_counts, grade, _notes, _stats = prepare_spatial_expression_input(raw)
    assert has_counts is True
    assert "counts" in raw.layers
    assert grade == "A"


def test_run_bundle_verifies_inputs_figures_descriptors_and_manifest(tmp_path: Path):
    source = tmp_path / "source.txt"
    source.write_text("source-v1", encoding="utf-8")
    run_dir = tmp_path / "run"
    bundle = RunBundle.create(run_dir, "test.capability", "test-skill")
    bundle.record_input("source", source, "raw_counts")
    result = bundle.results_dir / "result.txt"
    result.write_text("result-v1", encoding="utf-8")
    bundle.add_result("result", result, is_primary=True)
    figure = bundle.figures_dir / "figure.svg"
    figure.write_text("<svg/>", encoding="utf-8")
    bundle.add_figure("figure", figure)
    bundle.finalize()

    assert verify_run_bundle(run_dir).valid
    source.write_text("source-v2", encoding="utf-8")
    verification = verify_run_bundle(run_dir)
    assert not verification.valid
    assert any(item.startswith("input:") for item in verification.tampered_files)

    source.write_text("source-v1", encoding="utf-8")
    figure.write_text("tampered", encoding="utf-8")
    assert any("figure.svg" in item for item in verify_run_bundle(run_dir).tampered_files)

    figure.write_text("<svg/>", encoding="utf-8")
    (run_dir / "parameters.json").write_text('{"changed": true}', encoding="utf-8")
    assert any("parameters.json" in item for item in verify_run_bundle(run_dir).tampered_files)


def test_run_bundle_rejects_output_path_escape(tmp_path: Path):
    run_dir = tmp_path / "run"
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    bundle = RunBundle.create(run_dir, "test.capability", "test-skill")
    with pytest.raises(ValueError, match="must remain inside"):
        bundle.add_result("outside", outside)


def test_run_bundle_manifest_hash_binds_integrity_metadata(tmp_path: Path):
    run_dir = tmp_path / "run"
    bundle = RunBundle.create(run_dir, "test.capability", "test-skill")
    result = bundle.results_dir / "result.txt"
    result.write_text("result", encoding="utf-8")
    bundle.add_result("result", result)
    bundle.finalize()

    run_path = run_dir / "run.json"
    manifest = json.loads(run_path.read_text(encoding="utf-8"))
    manifest["integrity"]["scope"] = "forged-scope"
    run_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    verification = verify_run_bundle(run_dir)
    assert not verification.valid
    assert any("manifest payload checksum mismatch" in item for item in verification.tampered_files)


def test_offline_guard_blocks_transport_before_urlopen(tmp_path: Path):
    guard = DataGovernanceGuard(mode=EgressMode.OFFLINE_STRICT, audit_log_path=tmp_path / "egress.jsonl")
    request = urllib.request.Request("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/einfo.fcgi")
    with pytest.raises(EgressBlockedError, match="OFFLINE_STRICT"):
        guarded_urlopen(request, guard=guard, purpose="test request")


def test_project_network_calls_are_routed_through_egress_guard():
    roots = [PROJECT_ROOT / "src", PROJECT_ROOT / "skills", PROJECT_ROOT / "scripts"]
    direct_urllib = []
    unguarded_requests = []
    for root in roots:
        for path in root.rglob("*.py"):
            if path.name == "egress_guard.py" or "__pycache__" in path.parts:
                continue
            source = path.read_text(encoding="utf-8")
            if "urllib.request.urlopen(" in source or "import urlopen" in source:
                direct_urllib.append(path.relative_to(PROJECT_ROOT).as_posix())
            if "requests.get(" in source and "guarded_requests_get" not in source:
                unguarded_requests.append(path.relative_to(PROJECT_ROOT).as_posix())
    assert direct_urllib == []
    assert unguarded_requests == []


def test_foundation_model_proxy_is_opt_in_by_default():
    parameter = inspect.signature(simulate_gene_perturbation).parameters["allow_proxy_fallback"]
    assert parameter.default is False
