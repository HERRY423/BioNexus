"""Unit tests for lab-grade deployment artifacts.

Covers:
1. Offline deployment mode: BIONEXUS_OFFLINE=1 forces OFFLINE_STRICT egress
   and cannot be relaxed; hosted requests are refused before any connection.
2. `bionexus offline-check` / `bionexus doctor --offline` deployment gates.
3. The scale-benchmark harness is memory-bounded and honest (controlled
   density, recorded peak-memory method, machine fingerprint).
4. Deployment supply-chain integrity: DEPLOYMENT_MANIFEST digests match the
   lockfile/SBOM on disk, the SBOM carries the exact locked versions, and
   the container definition pins the base image by digest.
"""

import hashlib
import json
import re
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SRC = _REPO_ROOT / "src"
for _path in (str(_REPO_ROOT), str(_SRC)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from bionexus.egress_guard import DataGovernanceGuard, EgressMode  # noqa: E402
from bionexus.offline_mode import (  # noqa: E402
    OFFLINE_ENV_VAR,
    OfflineModeError,
    assert_offline_ready,
    is_offline_enforced,
    offline_readiness,
)

try:
    from evals.scale_benchmark import _peak_memory_gb, make_csr, run_benchmark
except ImportError:  # evals not packaged in some layouts
    make_csr = run_benchmark = _peak_memory_gb = None


# ------------------------------------------------------------------------------
# 1. Offline deployment mode
# ------------------------------------------------------------------------------


@pytest.fixture()
def offline_env(monkeypatch):
    monkeypatch.setenv(OFFLINE_ENV_VAR, "1")
    yield
    monkeypatch.delenv(OFFLINE_ENV_VAR, raising=False)


def test_offline_flag_detected():
    import os

    monkeypatched = pytest.MonkeyPatch()
    try:
        monkeypatched.setenv(OFFLINE_ENV_VAR, "1")
        assert is_offline_enforced() is True
        monkeypatched.setenv(OFFLINE_ENV_VAR, "0")
        assert is_offline_enforced() is False
        monkeypatched.delenv(OFFLINE_ENV_VAR)
        assert is_offline_enforced() is False
    finally:
        monkeypatched.undo()
        assert not os.environ.get(OFFLINE_ENV_VAR)


def test_offline_flag_forces_offline_strict(offline_env):
    guard = DataGovernanceGuard()  # would be ALLOWLIST without the flag
    assert guard.mode is EgressMode.OFFLINE_STRICT


def test_offline_mode_cannot_be_relaxed(offline_env):
    guard = DataGovernanceGuard()
    with pytest.raises(ValueError, match="BIONEXUS_OFFLINE"):
        guard.set_mode(EgressMode.ALLOWLIST)
    with pytest.raises(ValueError, match="BIONEXUS_OFFLINE"):
        guard.set_mode("CONNECTED")


def test_guard_without_flag_defaults_to_policy_mode(monkeypatch):
    monkeypatch.delenv(OFFLINE_ENV_VAR, raising=False)
    guard = DataGovernanceGuard()
    assert guard.mode is EgressMode.ALLOWLIST


def test_offline_readiness_report_shape(offline_env):
    report = offline_readiness()
    assert report["schema_version"] == "bionexus.offline-readiness.v1"
    assert report["offline_enforced"] is True
    assert report["offline_ready"] is True
    assert report["egress_mode"] == "OFFLINE_STRICT"
    names = {check["name"] for check in report["checks"]}
    assert {"egress_mode_offline_strict", "replay_eval_provider", "local_mcp_tools",
            "hosted_endpoints_refused"} <= names
    assert assert_offline_ready() == report


def test_offline_readiness_fails_closed_without_flag(monkeypatch):
    monkeypatch.delenv(OFFLINE_ENV_VAR, raising=False)
    report = offline_readiness()
    assert report["offline_ready"] is False
    with pytest.raises(OfflineModeError):
        assert_offline_ready()


def test_hosted_request_refused_before_connection(offline_env):
    guard = DataGovernanceGuard()
    permitted, record = guard.evaluate_request(
        endpoint="https://pubmed.mcp.claude.com/mcp",
        purpose="unit test: hosted endpoint",
    )
    assert permitted is False
    assert record.outcome == "BLOCKED"
    assert "OFFLINE_STRICT" in (record.block_reason or "")


def test_cli_offline_check_gate(capsys, monkeypatch):
    from bionexus.cli import main

    monkeypatch.setenv(OFFLINE_ENV_VAR, "1")
    code = main(["offline-check"])
    assert code == 0
    capsys.readouterr()
    code = main(["offline-check", "--json"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["offline_ready"] is True

    monkeypatch.delenv(OFFLINE_ENV_VAR)
    code = main(["offline-check"])
    assert code == 1  # fail-closed without enforcement
    capsys.readouterr()


def test_doctor_offline_flag_in_report_and_gate(capsys, monkeypatch):
    from bionexus.cli import main

    monkeypatch.setenv(OFFLINE_ENV_VAR, "1")
    code = main(["doctor", "--offline", "--json"])
    assert code == 0
    out, err = capsys.readouterr()
    print(err, file=sys.stderr)
    report = json.loads(out)
    assert report["offline_profile"]["offline_ready"] is True

    monkeypatch.delenv(OFFLINE_ENV_VAR)
    code = main(["doctor", "--require-offline"])
    assert code == 1  # fail-closed: gate fails without enforcement
    capsys.readouterr()


# ------------------------------------------------------------------------------
# 2. Scale benchmark harness (memory-bounded, honest)
# ------------------------------------------------------------------------------


@pytest.mark.skipif(make_csr is None, reason="evals package unavailable")
def test_make_csr_hits_target_density_and_stays_sparse():
    x = make_csr(2000, 400, seed=7, target_density=0.2, chunk_cells=500)
    assert x.shape == (2000, 400)
    observed = x.nnz / (2000 * 400)
    assert abs(observed - 0.2) < 0.05


@pytest.mark.skipif(make_csr is None, reason="evals package unavailable")
def test_run_benchmark_small_end_to_end():
    results = run_benchmark(2000, 400, seed=7, target_density=0.15, chunk_cells=500, svd_k=5)
    assert set(results["stages"]) == {"generate", "qc_mask", "normalize_log1p", "hvg_select", "pca"}
    assert results["stages"]["generate"]["density_observed"] == pytest.approx(0.15, abs=0.05)
    assert results["peak_memory_gb"] is not None or results["peak_memory_method"] == "unavailable"
    # On POSIX and Windows the peak-memory method must be real, not "unavailable".
    if sys.platform != "emscripten":
        assert results["peak_memory_method"] != "unavailable"
    assert results["total_wall_seconds"] > 0


@pytest.mark.skipif(_peak_memory_gb is None, reason="evals package unavailable")
def test_peak_memory_measurement_method_recorded():
    value, method = _peak_memory_gb()
    assert method in {"ru_maxrss", "windows_peak_working_set_psutil", "windows_peak_working_set", "unavailable"}
    if sys.platform in ("win32", "linux", "darwin"):
        assert method != "unavailable"
        assert value > 0


# ------------------------------------------------------------------------------
# 3. Deployment supply-chain integrity
# ------------------------------------------------------------------------------


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_deployment_manifest_digests_match_files():
    manifest = json.loads((_REPO_ROOT / "container" / "DEPLOYMENT_MANIFEST.json").read_text(encoding="utf-8"))
    lock_path = _REPO_ROOT / manifest["lockfile"]["path"]
    sbom_path = _REPO_ROOT / manifest["sbom"]["path"]
    assert _sha256(lock_path) == manifest["lockfile"]["sha256"]
    assert _sha256(sbom_path) == manifest["sbom"]["sha256"]


def test_lockfile_is_hash_checked_and_version_pinned():
    text = (_REPO_ROOT / "container" / "requirements-lock.txt").read_text(encoding="utf-8")
    pinned = [line for line in text.splitlines() if "==" in line and not line.strip().startswith("#")]
    assert len(pinned) >= 100
    assert "-e ." not in text  # editable targets break pip hash-checking mode
    hashes = text.count("--hash=sha256:")
    assert hashes >= len(pinned)
    for probe in ("scanpy==", "squidpy==", "pydeseq2==", "psutil==", "setuptools=="):
        assert probe in text


def test_sbom_components_match_lockfile_pins():
    sbom = json.loads((_REPO_ROOT / "container" / "sbom-python.json").read_text(encoding="utf-8"))
    assert sbom["bomFormat"] == "CycloneDX"
    lock_text = (_REPO_ROOT / "container" / "requirements-lock.txt").read_text(encoding="utf-8")
    pinned = {}
    for line in lock_text.splitlines():
        line = line.strip()
        if "==" in line and not line.startswith("#"):
            name, _, rest = line.partition("==")
            pinned[name] = rest.split()[0].rstrip("\\").strip()
    by_name = {c["name"]: c["version"] for c in sbom["components"]}
    for name, version in pinned.items():
        assert by_name.get(name) == version, f"SBOM drift for {name}"


def test_container_def_pins_base_digest_and_lockfile():
    text = (_REPO_ROOT / "container" / "apptainer.def").read_text(encoding="utf-8")
    match = re.search(r"From:\s*python@sha256:([0-9a-f]{64})", text)
    assert match, "base image is not pinned by digest"
    assert match.group(1) == "0bee7276f83efd4a1ee05bbbf4281d95ed28e079220a9457f25a93e3f1e3c31b"
    assert "requirements-lock.txt" in text
    assert "--no-deps -e ." in text
    assert "offline-check" in text


def test_deployment_manifest_records_benchmark_evidence_and_honesty():
    manifest = json.loads((_REPO_ROOT / "container" / "DEPLOYMENT_MANIFEST.json").read_text(encoding="utf-8"))
    entries = manifest["scale_benchmark_evidence"]
    assert {e["scale"] for e in entries} >= {
        "500k cells x 5k genes @ 8% nonzero density",
        "1M cells x 5k genes @ 5% nonzero density",
    }
    for entry in entries:
        report_path = _REPO_ROOT / entry["report"]
        assert report_path.is_file(), entry["report"]
        report = json.loads(report_path.read_text(encoding="utf-8"))
        assert report["machine"]["cpu_count"] and report["machine"]["ram_total_gb"]
        assert report["peak_memory_method"] != "unavailable"
        assert report["peak_memory_gb"] is not None
        assert "small" in entry["machine_class"]  # honest machine-class labeling
    assert "not independent scientific validation" in manifest["honesty"]["adoption_boundary"]


def test_slurm_reference_profiles_exist_and_gate_offline():
    profiles = _REPO_ROOT / "cluster" / "slurm" / "profiles"
    for name in ("hpc-cpu.sbatch", "hpc-gpu.sbatch", "run_scale_benchmark.sbatch", "README.md"):
        assert (profiles / name).is_file()
    cpu = (profiles / "hpc-cpu.sbatch").read_text(encoding="utf-8")
    assert "BIONEXUS_OFFLINE=1" in cpu and "offline-check" in cpu
    gpu = (profiles / "hpc-gpu.sbatch").read_text(encoding="utf-8")
    assert "--nv" in gpu and "torch.cuda.is_available" in gpu
    bench = (profiles / "run_scale_benchmark.sbatch").read_text(encoding="utf-8")
    assert "--cells 1000000" in bench and "scale_benchmark.py" in bench
