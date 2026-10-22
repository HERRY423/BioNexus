"""Crate-first Nextflow provenance: nf-prov WRROC is authoritative over trace.txt."""

from __future__ import annotations

import json
from pathlib import Path

from nf_prov_crate_util import write_nf_prov_crate

from bionexus.cli import main as cli_main
from bionexus.nextflow_bridge import create_nextflow_tool_receipt, harvest_nextflow_run
from bionexus.roc_validator import run_rocrate_validator
from bionexus.wrroc import ingest_wrroc_crate, locate_wrroc_crate


def test_locate_prefers_pipeline_info(tmp_path: Path):
    run_dir = tmp_path / "run"
    crate = write_nf_prov_crate(run_dir)
    (run_dir / "ro-crate-metadata.json").write_text("{}", encoding="utf-8")
    found = locate_wrroc_crate(run_dir)
    assert found == crate


def test_locate_does_not_use_work_directory_crate(tmp_path: Path):
    run_dir = tmp_path / "run"
    work = run_dir / "work" / "ab" / "cd"
    work.mkdir(parents=True)
    (work / "ro-crate-metadata.json").write_text("{}", encoding="utf-8")
    crate = write_nf_prov_crate(run_dir)
    assert locate_wrroc_crate(run_dir) == crate
    (crate).unlink()
    (run_dir / "salmon.merged.gene_counts.tsv").unlink()
    assert locate_wrroc_crate(run_dir) is None or locate_wrroc_crate(run_dir) != work / "ro-crate-metadata.json"


def test_ingest_wrroc_crate_without_trace(tmp_path: Path):
    run_dir = tmp_path / "run"
    crate = write_nf_prov_crate(run_dir)
    summary = ingest_wrroc_crate(crate, run_dir=run_dir, official_validation="skip")
    assert summary.provenance_source == "WRROC"
    assert summary.pipeline_name == "nf-core/rnaseq"
    assert summary.pipeline_version == "3.14.0"
    assert summary.nextflow_version == "23.10.0"
    assert summary.execution_status == "SUCCESS"
    assert summary.derived_evidence_factors == []
    assert summary.sample_count == 0
    assert summary.total_processes == 2
    assert "salmon.merged.gene_counts.tsv" in summary.primary_outputs
    assert len(summary.primary_outputs["salmon.merged.gene_counts.tsv"]) == 64


def test_harvest_prefers_crate_over_trace(tmp_path: Path):
    run_dir = tmp_path / "run"
    write_nf_prov_crate(run_dir)
    (run_dir / "pipeline_info" / "execution_trace.txt").write_text(
        "task_id\tname\tstatus\texit\n1\tOLD\tFAILED\t1\n",
        encoding="utf-8",
    )
    summary = harvest_nextflow_run(run_dir, pipeline_name="nf-core/rnaseq")
    assert summary.provenance_source == "WRROC"
    assert summary.execution_status == "SUCCESS"
    assert summary.crate_path is not None
    assert summary.derived_evidence_factors == []


def test_harvest_falls_back_to_trace_when_crate_missing(tmp_path: Path):
    run_dir = tmp_path / "run"
    pipe_info = run_dir / "pipeline_info"
    pipe_info.mkdir(parents=True)
    (pipe_info / "execution_trace.txt").write_text(
        "task_id\tname\tstatus\texit\n1\tPROCESS_A\tCOMPLETED\t0\n",
        encoding="utf-8",
    )
    (run_dir / "out.tsv").write_text("x\n", encoding="utf-8")
    summary = harvest_nextflow_run(run_dir)
    assert summary.provenance_source == "TRACE_FALLBACK"
    assert summary.execution_status == "SUCCESS"
    assert summary.crate_path is None


def test_receipt_attestation_type_follows_crate(tmp_path: Path):
    run_dir = tmp_path / "run"
    write_nf_prov_crate(run_dir)
    receipt = create_nextflow_tool_receipt(run_dir, pipeline_name="nf-core/rnaseq")
    assert receipt["metadata"]["provenance_source"] == "WRROC"
    assert receipt["attestation"]["attestation_type"] == "wrroc_ingest"
    assert receipt["metadata"]["scientific_evidence_effect"] == "NONE"


def test_cli_inspect_reports_wrroc_source(tmp_path: Path, capsys):
    run_dir = tmp_path / "run"
    write_nf_prov_crate(run_dir)
    assert cli_main(["nextflow", "inspect", str(run_dir)]) == 0
    out = capsys.readouterr().out
    assert "Provenance source: WRROC" in out
    assert "SUCCESS" in out


def test_howto_steps_are_not_counted_as_process_success(tmp_path: Path):
    run_dir = tmp_path / "run"
    crate = write_nf_prov_crate(run_dir)
    doc = json.loads(crate.read_text(encoding="utf-8"))
    doc["@graph"].append(
        {
            "@id": "#step/fastqc",
            "@type": "HowToStep",
            "name": "FASTQC recipe step",
        }
    )
    crate.write_text(json.dumps(doc), encoding="utf-8")
    summary = ingest_wrroc_crate(crate, run_dir=run_dir, official_validation="skip")
    assert summary.total_processes == 2
    assert summary.execution_status == "SUCCESS"


def test_crate_path_escape_is_ignored(tmp_path: Path):
    run_dir = tmp_path / "run"
    crate = write_nf_prov_crate(run_dir)
    outside = tmp_path / "secret.txt"
    outside.write_text("secret", encoding="utf-8")
    doc = json.loads(crate.read_text(encoding="utf-8"))
    for entity in doc["@graph"]:
        if entity.get("@id") == "#workflow-run":
            entity["result"].append({"@id": "../secret.txt"})
    crate.write_text(json.dumps(doc), encoding="utf-8")
    summary = ingest_wrroc_crate(crate, run_dir=run_dir, official_validation="skip")
    joined = " ".join(summary.primary_outputs)
    assert "secret" not in joined


def test_ingest_keeps_validator_unavailable_status(monkeypatch, tmp_path: Path):
    run_dir = tmp_path / "run"
    crate = write_nf_prov_crate(run_dir)
    monkeypatch.setattr("bionexus.roc_validator.discover_rocrate_validator", lambda: None)
    summary = ingest_wrroc_crate(crate, run_dir=run_dir, official_validation="auto")
    assert summary.official_validation_status == "VALIDATOR_UNAVAILABLE"


def test_rocrate_validator_unavailable_is_not_a_pass(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("bionexus.roc_validator.discover_rocrate_validator", lambda: None)
    result = run_rocrate_validator(tmp_path)
    assert result.available is False
    assert result.passed is False
    assert result.status == "VALIDATOR_UNAVAILABLE"


def test_rocrate_validator_require_records_failure(monkeypatch, tmp_path: Path):
    crate_dir = tmp_path / "crate"
    crate_dir.mkdir()
    (crate_dir / "ro-crate-metadata.json").write_text("{}", encoding="utf-8")

    class _Proc:
        returncode = 1
        stdout = "not valid"
        stderr = ""

    monkeypatch.setattr("bionexus.roc_validator.discover_rocrate_validator", lambda: "rocrate-validator")
    monkeypatch.setattr("bionexus.roc_validator._installed_package_version", lambda: "0.11.2")
    monkeypatch.setattr("bionexus.roc_validator.subprocess.run", lambda *a, **k: _Proc())
    result = run_rocrate_validator(crate_dir)
    assert result.ran is True
    assert result.passed is False
    assert result.status == "FAILED"
