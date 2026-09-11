"""Unit tests for BioNexus import namespace safety and clean packaging smoke."""

from __future__ import annotations

import importlib
import subprocess
import sys
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


def test_wheel_package_contents_and_metadata(tmp_path):
    """Build and inspect a fresh wheel, independent of ambient dist artifacts."""
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            ".",
            "--no-deps",
            "--no-build-isolation",
            "--wheel-dir",
            str(tmp_path),
        ],
        cwd=_REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    wheels = list(tmp_path.glob("*.whl"))
    assert len(wheels) == 1
    with zipfile.ZipFile(wheels[0], "r") as z:
        names = z.namelist()
        assert "bionexus/__init__.py" in names
        assert "bionexus/versions.py" in names
        assert "bionexus/validation_network.py" in names
        assert "bionexus/nextflow_bridge.py" in names
        assert "bionexus/bctk/profiles.py" in names
        assert "bionexus/data/rule_registry.json" in names
        assert "bionexus/mcp_server.py" in names
        assert "bionexus/mcp_host_audit.py" in names


def test_requirements_txt_matches_pyproject_dependencies():
    """Verify requirements.txt and pyproject.toml core dependencies stay 100% in sync."""
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib  # type: ignore

    pyproject_data = tomllib.loads((_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    pyproject_deps = pyproject_data.get("project", {}).get("dependencies", [])

    req_lines = [
        line.strip()
        for line in (_REPO_ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]

    assert set(req_lines) == set(pyproject_deps), (
        f"Mismatch between requirements.txt and pyproject.toml dependencies:\n"
        f"In pyproject.toml only: {set(pyproject_deps) - set(req_lines)}\n"
        f"In requirements.txt only: {set(req_lines) - set(pyproject_deps)}"
    )
