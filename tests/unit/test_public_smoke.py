"""Fixture gold-chain smoke; optional public pbmc3k inspect."""

from __future__ import annotations

from pathlib import Path
import sys

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from goldchain_smoke import smoke_scrna, smoke_spatial, try_pbmc3k


def test_fixture_scrna_smoke():
    pytest.importorskip("scanpy")
    path = PROJECT_ROOT / "tests" / "fixtures" / "tiny_scrna.h5ad"
    if not path.is_file():
        pytest.skip("tiny_scrna.h5ad fixture missing")
    report = smoke_scrna(path)
    assert report["method"] == "scanpy_gold_chain"
    assert report["inspect_n_obs"] > 0


def test_fixture_spatial_smoke():
    pytest.importorskip("squidpy")
    path = PROJECT_ROOT / "tests" / "fixtures" / "tiny_spatial.h5ad"
    if not path.is_file():
        pytest.skip("tiny_spatial.h5ad fixture missing")
    report = smoke_spatial(path)
    assert report["method"] == "squidpy_spatial_gold_chain"


def test_optional_pbmc3k_inspect():
    pytest.importorskip("scanpy")
    try:
        info = try_pbmc3k()
    except Exception as exc:
        pytest.skip(f"pbmc3k unavailable: {exc}")
    assert info["n_obs"] > 0
    assert info["method"] == "anndata_inspect"
