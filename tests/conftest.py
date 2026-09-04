"""
Pytest configuration and shared fixtures for BioNexus.
Provides synthetic datasets, mock AnnData matrices, and temp environments.
"""

import os
import shutil
import sys
import tempfile
from pathlib import Path

# Numba may otherwise select a package-adjacent or system temporary cache that
# is not writable on managed Windows hosts.  Set a repository-local test cache
# before importing NumPy/SciPy or any optional scverse backend.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
NUMBA_TEST_CACHE = PROJECT_ROOT / ".numba-cache"
NUMBA_TEST_CACHE.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("NUMBA_CACHE_DIR", str(NUMBA_TEST_CACHE))

import numpy as np
import pytest
import scipy.sparse as sp

# Ensure project scripts and skill scripts are importable
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
sys.path.insert(0, str(PROJECT_ROOT / "skills" / "single-cell-rna-qc" / "scripts"))
sys.path.insert(0, str(PROJECT_ROOT / "skills" / "scvi-tools" / "scripts"))
sys.path.insert(0, str(PROJECT_ROOT / "skills" / "nextflow-development" / "scripts"))
sys.path.insert(0, str(PROJECT_ROOT / "skills" / "instrument-data-to-allotrope" / "scripts"))


def pytest_configure(config):
    """Ensure pytest tmp_path works gracefully even if Windows Temp/pytest-of-<user> is permission-locked."""
    if config.option.basetemp is None:
        try:
            import getpass
            import os

            user = getpass.getuser()
            candidate = Path(tempfile.gettempdir()) / f"pytest-of-{user}"
            if candidate.exists():
                list(os.scandir(candidate))
        except (PermissionError, OSError):
            config.option.basetemp = tempfile.mkdtemp(prefix="pytest_basetemp_")


@pytest.fixture
def canonical_backends_available(monkeypatch):
    """Make capability-level backend readiness explicit in semantic tests.

    These tests exercise routing, warrant, and accounting behavior after the
    capability's canonical backend has passed its readiness gate.  They do not
    execute the backend itself; execution tests remain in the scientific-stack
    jobs.  Keeping the assumption in an opt-in fixture prevents core-only CI
    from depending on whichever optional packages happen to be installed.
    """
    from bionexus.backends import BackendState, BackendStatus

    def _ready(name: str) -> BackendStatus:
        return BackendStatus(
            name=name,
            available=True,
            import_name=name,
            extra=None,
            note="test fixture: canonical backend readiness already established",
            state=BackendState.INSTALLED,
            version="999.0.0",
        )

    monkeypatch.setattr("bionexus.capabilities.probe", _ready)
    return _ready



@pytest.fixture
def synthetic_sparse_counts():
    """Generate a reproducible synthetic sparse count matrix (cells x genes)."""
    np.random.seed(42)
    n_cells = 150
    n_genes = 200
    density = 0.15
    data = sp.random(n_cells, n_genes, density=density, format="csr", dtype=np.float32, random_state=42)
    data.data = np.random.poisson(lam=5.0, size=data.nnz).astype(np.float32)
    return data


@pytest.fixture
def synthetic_anndata(synthetic_sparse_counts):
    """Create a synthetic AnnData with human gene symbols (including MT- and Rpl/Rps)."""
    try:
        import anndata as ad
    except ImportError:
        pytest.skip("anndata not installed")

    n_cells, n_genes = synthetic_sparse_counts.shape

    gene_names = [f"Gene_{i}" for i in range(n_genes)]
    gene_names[0] = "MT-CO1"
    gene_names[1] = "MT-ND1"
    gene_names[2] = "MT-ATP6"
    gene_names[3] = "RPL13A"
    gene_names[4] = "RPS18"
    gene_names[5] = "HBA1"
    gene_names[6] = "HBB"

    cell_names = [f"Cell_{i}" for i in range(n_cells)]
    batches = ["batch_1"] * (n_cells // 2) + ["batch_2"] * (n_cells - n_cells // 2)
    cell_types = (["T_cell"] * 50 + ["B_cell"] * 50 + ["Monocyte"] * 50)[:n_cells]

    obs = {"batch": batches, "cell_type": cell_types}
    var = {"gene_symbol": gene_names}

    adata = ad.AnnData(X=synthetic_sparse_counts, obs=obs, var=var)
    adata.obs_names = cell_names
    adata.var_names = gene_names
    adata.layers["counts"] = synthetic_sparse_counts.copy()
    return adata


@pytest.fixture
def sample_plate_reader_csv():
    """Create a temporary standard 96-well plate reader output CSV in a managed temp directory."""
    temp_dir = tempfile.mkdtemp(prefix="bionexus_test_")
    csv_file = Path(temp_dir) / "tecan_plate_450nm.csv"
    content = """Tecan Magellan Data Export
User: Dr. Scientist
Date: 2026-08-14
Wavelength: 450nm
Plate Layout: 96-well

<>	1	2	3	4
A	0.125	0.456	0.789	1.234
B	0.118	0.442	0.765	1.198
C	0.130	0.460	0.801	1.250
D	0.050	0.052	0.049	0.051
"""
    csv_file.write_text(content, encoding="utf-8")
    yield str(csv_file)
    # Cleanup
    shutil.rmtree(temp_dir, ignore_errors=True)
