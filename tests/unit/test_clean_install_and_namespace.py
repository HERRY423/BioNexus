"""Unit tests for BioNexus import namespace safety and clean packaging smoke."""

from __future__ import annotations

import importlib
import zipfile
from pathlib import Path

from bionexus.versions import VERSION

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def test_bionexus_import_namespace_cleanliness():
    """Verify bionexus import namespace loads cleanly without standard library collision."""
    import bionexus

    assert hasattr(bionexus, "__version__")
    assert bionexus.__version__ == VERSION

    submodules = [
        "bionexus.abi",
        "bionexus.capabilities",
        "bionexus.claim_checker",
        "bionexus.evidence_model",
        "bionexus.tool_receipt",
        "bionexus.validation_network",
        "bionexus.bctk.profiles",
        "bionexus.versions",
    ]
    for sub in submodules:
        mod = importlib.import_module(sub)
        assert mod is not None


def test_no_shadowed_stdlib_or_third_party_names():
    """Ensure no BioNexus module name shadows built-in stdlib top-level modules."""
    src_dir = _REPO_ROOT / "src" / "bionexus"
    assert src_dir.is_dir()

    prohibited_top_levels = {
        "os", "sys", "re", "json", "math", "time", "typing", "pathlib",
        "datetime", "hashlib", "subprocess", "logging", "unittest", "pytest"
    }

    for py_file in src_dir.glob("*.py"):
        stem = py_file.stem
        assert stem not in prohibited_top_levels, f"Module '{stem}.py' shadows standard library module!"


def test_wheel_package_contents_and_metadata():
    """Verify that built wheel in dist/ contains all required packages and data files."""
    dist_dir = _REPO_ROOT / "dist"
    wheels = list(dist_dir.glob("*.whl"))
    if not wheels:
        return

    latest_wheel = sorted(wheels, key=lambda p: p.stat().st_mtime)[-1]
    with zipfile.ZipFile(latest_wheel, "r") as z:
        names = z.namelist()
        assert "bionexus/__init__.py" in names
        assert "bionexus/versions.py" in names
        assert "bionexus/validation_network.py" in names
        assert "bionexus/nextflow_bridge.py" in names
        assert "bionexus/bctk/profiles.py" in names
        assert "bionexus/data/rule_registry.json" in names
