"""Tests for the Slurm three-gate chain script (cluster/slurm/run_three_gates.sh).

The gate-chain semantics are tested through the real shell script with a stub
`bionexus` executable on PATH: exit codes must propagate unchanged and a
refused preflight must prevent the analysis command from ever running.
These tests require bash; they are skipped where bash is unavailable
(e.g. Windows CI runners without Git Bash on PATH).
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CHAIN = PROJECT_ROOT / "cluster" / "slurm" / "run_three_gates.sh"

pytestmark = pytest.mark.skipif(
    os.name == "nt" or shutil.which("bash") is None,
    reason="Slurm gate-chain contract requires a POSIX bash environment",
)

# The chain script invokes `bionexus preflight <arg>` / `bionexus verify <arg>`;
# the stub switches on the subcommand plus the caller-supplied argument word.
STUB = r"""#!/usr/bin/env bash
case "$1 $2" in
  "preflight pass")    echo "[stub] preflight permitted"; exit 0 ;;
  "preflight refuse")  echo "[stub] refused" >&2; exit 1 ;;
  "preflight evidence") echo "[stub] missing evidence" >&2; exit 2 ;;
  "verify reject")     echo "[stub] unwarranted claims" >&2; exit 1 ;;
  "verify pass")       echo "[stub] results verified"; exit 0 ;;
  *) echo "[stub] unhandled: $@" >&2; exit 99 ;;
esac
"""

GOOD_ANALYSIS = "echo analysis-ran > $ANALYSIS_MARKER"


@pytest.fixture()
def gate_env(tmp_path: Path) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stub = bin_dir / "bionexus"
    stub.write_text(STUB, encoding="utf-8", newline="\n")
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return bin_dir


def _run_chain(gate_env: Path, tmp_path: Path, preflight_arg: str, analysis: str, verify_arg: str):
    env = dict(os.environ)
    env["PATH"] = f"{gate_env}{os.pathsep}{env['PATH']}"
    env["ANALYSIS_MARKER"] = str(tmp_path / "analysis.marker")
    return subprocess.run(
        ["bash", str(CHAIN), preflight_arg, analysis, verify_arg],
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )


def test_all_gates_pass_chain_exits_zero(gate_env: Path, tmp_path: Path):
    proc = _run_chain(gate_env, tmp_path, "pass", GOOD_ANALYSIS, "pass")
    assert proc.returncode == 0, proc.stderr
    assert "[gate 3/3] verification passed" in proc.stdout
    assert (tmp_path / "analysis.marker").read_text().strip() == "analysis-ran"


def test_refused_preflight_blocks_analysis_and_propagates_exit_one(gate_env: Path, tmp_path: Path):
    proc = _run_chain(gate_env, tmp_path, "refuse", GOOD_ANALYSIS, "pass")
    assert proc.returncode == 1
    assert "computation blocked before it started" in proc.stderr
    # Fail-closed: the analysis command must never have executed.
    assert not (tmp_path / "analysis.marker").exists()


def test_missing_evidence_exit_two_propagates(gate_env: Path, tmp_path: Path):
    proc = _run_chain(gate_env, tmp_path, "evidence", GOOD_ANALYSIS, "pass")
    assert proc.returncode == 2
    assert not (tmp_path / "analysis.marker").exists()


def test_failed_analysis_skips_verify_gate(gate_env: Path, tmp_path: Path):
    proc = _run_chain(gate_env, tmp_path, "pass", "exit 3", "pass")
    assert proc.returncode == 3
    assert "ANALYSIS FAILED" in proc.stderr
    assert "[gate 3/3]" not in proc.stdout


def test_rejected_results_fail_the_job_despite_good_compute(gate_env: Path, tmp_path: Path):
    proc = _run_chain(gate_env, tmp_path, "pass", GOOD_ANALYSIS, "reject")
    assert proc.returncode == 1
    assert "results do not carry their claims" in proc.stderr
    # The compute DID run; the chain still fails the job so dependent jobs
    # (--dependency=afterok) cannot consume unwarranted results.
    assert (tmp_path / "analysis.marker").exists()


def test_chain_script_requires_three_arguments():
    proc = subprocess.run(["bash", str(CHAIN)], capture_output=True, text=True, timeout=60)
    assert proc.returncode != 0
    assert "usage:" in (proc.stderr + proc.stdout)
