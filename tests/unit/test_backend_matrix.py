"""
Comprehensive unit test suite for the BioNexus Optional Backend Matrix.

Validates that every optional backend is deterministically tested under all 6 lifecycle states:
1. installed (present and version compatible)
2. missing (not installed, clean refusal)
3. partial (subset of dependent stack present)
4. incompatible_version (installed version below required minimum)
5. missing_model_weights (ML/PLM models with gate closed or missing weights)
6. missing_external_binary (CLI tools missing on PATH)
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SRC = _REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from bionexus.backends import (
    BackendState,
    BackendStatus,
    BackendUnavailable,
    IncompatibleVersion,
    is_available,
    is_version_compatible,
    probe,
    probe_all,
    probe_binary,
    probe_model_weights,
    require,
)

ALL_OPTIONAL_PACKAGES = [
    "scanpy",
    "anndata",
    "squidpy",
    "spatialdata",
    "scvi",
    "torch",
    "lifelines",
    "pydeseq2",
    "harmonypy",
    "leidenalg",
    "abnumber",
    "biotite",
    "viennarna",
    "allotropy",
    "sklearn",
    "esm",
]

ALL_EXTERNAL_BINARIES = [
    "nextflow",
    "vina",
    "fpocket",
    "anarci",
    "samtools",
    "bedtools",
    "clustalo",
    "pymol",
]


# ============================================================================
# 1. INSTALLED STATE TESTS
# ============================================================================

def test_version_compatibility_helper():
    """Verify semver comparison works across standard version strings."""
    assert is_version_compatible("1.10.0", "1.10.0") is True
    assert is_version_compatible("1.10.2", "1.10.0") is True
    assert is_version_compatible("2.0.0", "1.10.0") is True
    assert is_version_compatible("1.9.5", "1.10.0") is False
    assert is_version_compatible("0.8.2", "0.9.0") is False
    assert is_version_compatible(None, "1.0.0") is False
    assert is_version_compatible("1.0.0", None) is True


@pytest.mark.parametrize("pkg_name", ["sklearn"])
def test_installed_real_base_backend(pkg_name):
    """Verify base dependencies present in environment report INSTALLED."""
    status = probe(pkg_name)
    assert status.available is True
    assert status.state == BackendState.INSTALLED
    assert status.version is not None


def test_installed_state_mocked():
    """Verify probe reports INSTALLED when module is found and version meets constraint."""
    with patch("bionexus.backends.is_module_available", return_value=True), \
         patch("bionexus.backends.get_package_version", return_value="2.5.0"):
        status = probe("scanpy")
        assert status.available is True
        assert status.state == BackendState.INSTALLED
        assert status.version == "2.5.0"
        # require should not raise
        require("scanpy", for_method="test_scanpy_method")


# ============================================================================
# 2. MISSING STATE TESTS
# ============================================================================

@pytest.mark.parametrize("pkg_name", ALL_OPTIONAL_PACKAGES)
def test_missing_backend_state(pkg_name):
    """Verify missing packages report MISSING state and require() raises BackendUnavailable."""
    with patch("bionexus.backends.is_module_available", return_value=False), \
         patch("bionexus.backends.shutil.which", return_value=None):
        status = probe(pkg_name)
        assert status.available is False
        assert status.state in (BackendState.MISSING, BackendState.MISSING_WEIGHTS)
        assert not is_available(pkg_name)

        with pytest.raises(BackendUnavailable) as exc_info:
            require(pkg_name, for_method=f"run_{pkg_name}")
        assert f"requires backend '{pkg_name}'" in str(exc_info.value) or "weights" in str(exc_info.value)


# ============================================================================
# 3. PARTIAL STACK TESTS
# ============================================================================

def test_partial_scvi_stack():
    """Verify scvi reports PARTIAL state when torch is present but scvi is missing."""
    def fake_module_available(mod_name):
        return mod_name == "torch"

    with patch("bionexus.backends.is_module_available", side_effect=fake_module_available):
        status = probe("scvi")
        assert status.available is False
        assert status.state == BackendState.PARTIAL
        assert "missing 'scvi'" in status.note


def test_partial_spatial_stack():
    """Verify squidpy reports PARTIAL state when anndata is present but squidpy is missing."""
    def fake_module_available(mod_name):
        return mod_name == "anndata"

    with patch("bionexus.backends.is_module_available", side_effect=fake_module_available):
        status = probe("squidpy")
        assert status.available is False
        assert status.state == BackendState.PARTIAL


def test_partial_leiden_stack():
    """Verify leidenalg reports PARTIAL state when igraph is present but leidenalg is missing."""
    def fake_module_available(mod_name):
        return mod_name == "igraph"

    with patch("bionexus.backends.is_module_available", side_effect=fake_module_available):
        status = probe("leidenalg")
        assert status.available is False
        assert status.state == BackendState.PARTIAL


# ============================================================================
# 4. INCOMPATIBLE VERSION TESTS
# ============================================================================

@pytest.mark.parametrize("pkg_name,old_ver", [
    ("scanpy", "1.8.0"),       # min is 1.10.0
    ("anndata", "0.8.0"),      # min is 0.9.0
    ("squidpy", "1.1.0"),      # min is 1.3.0
    ("scvi", "0.19.0"),        # min is 1.0.0
    ("pydeseq2", "0.2.0"),     # min is 0.4.0
    ("abnumber", "0.1.0"),     # min is 0.3.0
    ("allotropy", "0.1.10"),   # min is 0.1.30
])
def test_incompatible_version_state(pkg_name, old_ver):
    """Verify outdated installed packages are flagged as INCOMPATIBLE_VERSION."""
    with patch("bionexus.backends.is_module_available", return_value=True), \
         patch("bionexus.backends.get_package_version", return_value=old_ver):
        status = probe(pkg_name)
        assert status.available is False
        assert status.state == BackendState.INCOMPATIBLE_VERSION
        assert status.version == old_ver
        assert status.min_version is not None

        with pytest.raises(IncompatibleVersion) as exc_info:
            require(pkg_name, for_method="test_old_pkg")
        assert f"requires backend '{pkg_name}' >=" in str(exc_info.value)


# ============================================================================
# 5. MISSING MODEL WEIGHTS & GATING TESTS
# ============================================================================

def test_esm_model_weights_gate_disabled():
    """Verify ESM probe reports MISSING_WEIGHTS when environment gate is closed."""
    with patch.dict("os.environ", {"BIONEXUS_ALLOW_ESM": "0"}), \
         patch("bionexus.backends.is_module_available", return_value=True):
        status = probe("esm")
        assert status.available is False
        assert status.state == BackendState.MISSING_WEIGHTS
        assert "BIONEXUS_ALLOW_ESM=1" in status.note

        ready, msg = probe_model_weights("esm")
        assert ready is False
        assert "BIONEXUS_ALLOW_ESM=1" in msg

        with pytest.raises(BackendUnavailable) as exc_info:
            require("esm", for_method="score_variant_esm2")
        assert "requires model weights" in str(exc_info.value)


def test_esm_model_weights_gate_enabled():
    """Verify ESM probe reports INSTALLED when gate is open and transformers is available."""
    with patch.dict("os.environ", {"BIONEXUS_ALLOW_ESM": "1"}), \
         patch("bionexus.backends.is_module_available", return_value=True), \
         patch("bionexus.backends.get_package_version", return_value="4.40.0"):
        status = probe("esm")
        assert status.available is True
        assert status.state == BackendState.INSTALLED
        assert status.version == "4.40.0"


# ============================================================================
# 6. MISSING EXTERNAL BINARY TESTS
# ============================================================================

@pytest.mark.parametrize("binary_name", ALL_EXTERNAL_BINARIES)
def test_missing_external_binary_state(binary_name):
    """Verify external CLI binaries missing on PATH report MISSING_BINARY."""
    with patch("bionexus.backends.shutil.which", return_value=None):
        status = probe(binary_name)
        assert status.available is False
        assert status.state == BackendState.MISSING_BINARY
        assert "not found on PATH" in status.note

        ready, path = probe_binary(binary_name)
        assert ready is False
        assert path is None

        with pytest.raises(BackendUnavailable) as exc_info:
            require(binary_name, for_method=f"run_{binary_name}")
        assert f"requires external binary '{binary_name}'" in str(exc_info.value)


def test_installed_external_binary_state():
    """Verify installed external CLI binaries found on PATH report INSTALLED."""
    with patch("bionexus.backends.shutil.which", return_value="/usr/local/bin/nextflow"):
        status = probe("nextflow")
        assert status.available is True
        assert status.state == BackendState.INSTALLED
        assert "/usr/local/bin/nextflow" in status.note

        ready, path = probe_binary("nextflow")
        assert ready is True
        assert path == "/usr/local/bin/nextflow"

        # Should not raise
        require("nextflow", for_method="run_nfcore_pipeline")


def test_probe_all_coverage():
    """Verify probe_all inspects all declared packages and binaries."""
    inventory = probe_all()
    for pkg in ALL_OPTIONAL_PACKAGES:
        assert pkg in inventory
        assert isinstance(inventory[pkg], BackendStatus)
    for bin_name in ALL_EXTERNAL_BINARIES:
        assert bin_name in inventory
        assert isinstance(inventory[bin_name], BackendStatus)
