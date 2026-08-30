"""Unit tests for nf-core real execution and Sarek launch artifacts."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = PROJECT_ROOT / "skills" / "nextflow-development" / "scripts"
for p in (PROJECT_ROOT / "src", SCRIPTS):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import nfcore_execute
import nfcore_sarek_launch as sarek
from nfcore_execute import execute_launch_script, probe_execution_environment


@pytest.fixture()
def fake_bins(monkeypatch):
    """Pretend nextflow + bash exist and the first container engine is docker."""
    monkeypatch.setattr(nfcore_execute.shutil, "which", lambda name: f"/usr/bin/{name}")


def _fake_proc(monkeypatch, returncode=0, stdout="ok", stderr=""):
    class FakeProc:
        pass

    proc = FakeProc()
    proc.returncode = returncode
    proc.stdout = stdout
    proc.stderr = stderr
    calls = {}

    def fake_run(cmd, **kwargs):
        calls["cmd"] = cmd
        calls["kwargs"] = kwargs
        return proc

    monkeypatch.setattr(nfcore_execute.subprocess, "run", fake_run)
    return calls


# ------------------------------------------------------------------ execute


def test_probe_environment_shape():
    probes = probe_execution_environment()
    assert set(probes) == {"nextflow", "bash", "container_engine"}


def test_execute_refuses_when_nextflow_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(nfcore_execute.shutil, "which", lambda name: None)
    script = tmp_path / "run.sh"
    script.write_text("nextflow run nf-core/rnaseq\n", encoding="utf-8")
    payload = execute_launch_script(script, capsule_root=tmp_path / "capsules")
    assert payload["refused"] is True
    assert "nextflow is not on PATH" in payload["abstain_reason"]


def test_execute_refuses_missing_script(fake_bins, tmp_path):
    payload = execute_launch_script(tmp_path / "nope.sh", capsule_root=tmp_path / "capsules")
    assert payload["refused"] is True


def test_execute_dry_run_does_not_run(fake_bins, tmp_path, monkeypatch):
    script = tmp_path / "run.sh"
    script.write_text("nextflow run nf-core/rnaseq\n", encoding="utf-8")
    ran = []

    def boom(*args, **kwargs):
        ran.append(args)
        raise AssertionError("subprocess must not run in dry-run mode")

    monkeypatch.setattr(nfcore_execute.subprocess, "run", boom)
    payload = execute_launch_script(script, capsule_root=tmp_path / "capsules", dry_run=True)
    assert payload["refused"] is False
    assert payload["execution_state"] == "PERMITTED"
    assert ran == []


def test_execute_success_creates_capsule(fake_bins, tmp_path, monkeypatch):
    script = tmp_path / "run_rnaseq.sh"
    script.write_text("nextflow run nf-core/rnaseq\n", encoding="utf-8")
    outdir = tmp_path / "results"
    outdir.mkdir()
    (outdir / "multiqc_report.html").write_text("<html></html>", encoding="utf-8")
    calls = _fake_proc(monkeypatch, returncode=0)

    payload = execute_launch_script(script, outdir=str(outdir), capsule_root=tmp_path / "capsules")
    assert payload["refused"] is False
    assert payload["execution_state"] == "EXECUTED"
    assert payload["execution"]["returncode"] == 0
    assert payload["execution"]["outdir_entries"] == ["multiqc_report.html"]
    assert calls["cmd"][0].endswith("bash")

    capsule = Path(payload["execution"]["capsule_dir"])
    manifest = json.loads((capsule / "run.json").read_text(encoding="utf-8"))
    assert manifest["capability_id"] == "nextflow.pipeline_execute"
    assert manifest["status"] == "COMPLETED"
    assert (capsule / "logs" / "pipeline_stderr.log").is_file()
    assert (capsule / "provenance.json").is_file()


def test_execute_failure_abstains_fail_closed(fake_bins, tmp_path, monkeypatch):
    script = tmp_path / "run_bad.sh"
    script.write_text("nextflow run nf-core/rnaseq\n", encoding="utf-8")
    _fake_proc(monkeypatch, returncode=2, stderr="process crashed")

    payload = execute_launch_script(script, capsule_root=tmp_path / "capsules")
    assert payload["abstain"] is True
    assert "returncode 2" in payload["abstain_reason"]
    capsule = Path(payload["execution"]["capsule_dir"])
    manifest = json.loads((capsule / "run.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "FAILED"
    assert manifest["execution_state"] == "FAILED"


def test_execute_timeout_fail_closed(fake_bins, tmp_path, monkeypatch):
    script = tmp_path / "run_slow.sh"
    script.write_text("nextflow run nf-core/rnaseq\n", encoding="utf-8")

    def fake_run(cmd, **kwargs):
        raise nfcore_execute.subprocess.TimeoutExpired(cmd=cmd, timeout=1)

    monkeypatch.setattr(nfcore_execute.subprocess, "run", fake_run)
    payload = execute_launch_script(script, capsule_root=tmp_path / "capsules", timeout_seconds=1)
    assert payload["abstain"] is True
    assert "timed out" in payload["execution"]["stderr_tail"]


# -------------------------------------------------------------------- sarek


def _write_sheet(tmp_path: Path, header: str, rows: list) -> Path:
    p = tmp_path / "sarek_samplesheet.csv"
    lines = [header, *rows]
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


GOOD_HEADER = "patient,sample,fastq_1,fastq_2"


def test_valid_samplesheet_schema(tmp_path):
    sheet = _write_sheet(tmp_path, GOOD_HEADER, ["P1,S1,a.fq.gz,b.fq.gz", "P1,S2T,a.fq.gz,b.fq.gz"])
    schema = sarek.validate_sarek_samplesheet(sheet)
    assert schema["rows"] == 2
    assert schema["patients"] == ["P1"]
    assert schema["has_status_column"] is False


def test_missing_required_column_raises(tmp_path):
    sheet = _write_sheet(tmp_path, "patient,sample,fastq_1", ["P1,S1,a.fq.gz"])
    with pytest.raises(sarek.SarekSheetError, match="missing required Sarek column"):
        sarek.validate_sarek_samplesheet(sheet)


def test_invalid_status_value_raises(tmp_path):
    sheet = _write_sheet(
        tmp_path,
        f"{GOOD_HEADER},status",
        ["P1,S1,a.fq.gz,b.fq.gz,unclear"],
    )
    with pytest.raises(sarek.SarekSheetError, match="status"):
        sarek.validate_sarek_samplesheet(sheet)


def test_status_normalization_tumor_normal(tmp_path):
    sheet = _write_sheet(
        tmp_path,
        f"{GOOD_HEADER},status",
        ["P1,N,a.fq.gz,b.fq.gz,normal", "P1,T,c.fq.gz,d.fq.gz,tumor"],
    )
    out = tmp_path / "normalized.csv"
    result = sarek.normalize_status_column(sheet, out)
    content = result.read_text(encoding="utf-8").strip().splitlines()
    assert content[1].endswith(",0")
    assert content[2].endswith(",1")


def test_unknown_step_rejected():
    with pytest.raises(ValueError, match="Unknown Sarek step"):
        sarek.build_sarek_command(samplesheet="s.csv", outdir="o", step="teleport")


def test_build_sarek_command_shape():
    cmd = sarek.build_sarek_command(
        samplesheet="sheet.csv", outdir="results", step="germline", profile="singularity"
    )
    assert cmd[:3] == ["nextflow", "run", "nf-core/sarek"]
    assert "--step" in cmd and cmd[cmd.index("--step") + 1] == "germline"
    assert "--input" in cmd and "sheet.csv" in cmd


def test_sarek_cli_writes_launch_script(tmp_path):
    sheet = _write_sheet(
        tmp_path,
        f"{GOOD_HEADER},status",
        ["P1,N,a.fq.gz,b.fq.gz,normal", "P1,T,c.fq.gz,d.fq.gz,tumor"],
    )
    normalized = tmp_path / "normalized.csv"
    out_script = tmp_path / "run_sarek.sh"
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "nfcore_sarek_launch.py"),
            "--samplesheet",
            str(sheet),
            "--outdir",
            "results",
            "--step",
            "somatic",
            "--normalized-sheet",
            str(normalized),
            "-o",
            str(out_script),
        ],
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["method"] == "nf-core_sarek_launch_artifact"
    assert "--step" in payload["command"] and "somatic" in payload["command"]
    assert out_script.is_file()
    assert "nf-core/sarek" in out_script.read_text(encoding="utf-8")
    assert normalized.read_text(encoding="utf-8").strip().splitlines()[1].endswith(",0")


def test_sarek_cli_refuses_bad_sheet(tmp_path):
    sheet = _write_sheet(tmp_path, "sample,fastq_1", ["S1,a.fq.gz"])
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "nfcore_sarek_launch.py"),
            "--samplesheet",
            str(sheet),
            "--outdir",
            "results",
            "--step",
            "germline",
            "-o",
            str(tmp_path / "run.sh"),
        ],
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
    )
    assert proc.returncode == 2
    payload = json.loads(proc.stdout)
    assert payload["refused"] is True
    assert not (tmp_path / "run.sh").exists()
