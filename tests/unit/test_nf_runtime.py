"""P0 Nextflow admission control: admit blocks the engine; warrant exit 3."""

from __future__ import annotations

import json
from pathlib import Path

from nf_prov_crate_util import write_nf_prov_crate

from bionexus.cli import main as cli_main
from bionexus.contracts import ConclusionMaturity
from bionexus.ledger import ClaimLedger, ClaimRecord, EvidenceRef
from bionexus.nf_runtime import (
    EXIT_CLAIMS_REFUSED,
    EXIT_MISSING,
    EXIT_OK,
    EXIT_REFUSED,
    admit_nextflow_run,
    generate_bionexus_config,
    run_nextflow_gated,
    warrant_nextflow_run,
)
from bionexus.verification import write_example_ledger


def _good_sheet(tmp_path: Path) -> Path:
    sheet = tmp_path / "samplesheet.csv"
    sheet.write_text("sample,fastq_1,fastq_2\ns1,a.fq.gz,b.fq.gz\n", encoding="utf-8")
    return sheet


def _confounded_metadata(tmp_path: Path) -> Path:
    path = tmp_path / "metadata.json"
    path.write_text(
        json.dumps(
            {
                "min_replicates_per_condition": 2,
                "is_integer_like": True,
                "condition_confounded_with": "donor",
            }
        ),
        encoding="utf-8",
    )
    return path


def test_admit_refuses_confounded_design(tmp_path: Path):
    sheet = _good_sheet(tmp_path)
    meta = _confounded_metadata(tmp_path)
    result = admit_nextflow_run(
        samplesheet=sheet,
        intent="differential-expression",
        metadata_path=meta,
    )
    assert result.allowed is False
    assert result.exit_code == EXIT_REFUSED
    assert result.scientific_admission == "REFUSED"


def test_cli_admit_refuses_before_any_engine(tmp_path: Path, capsys):
    sheet = _good_sheet(tmp_path)
    meta = _confounded_metadata(tmp_path)
    rc = cli_main(
        [
            "nf",
            "admit",
            "--samplesheet",
            str(sheet),
            "--intent",
            "differential-expression",
            "--metadata",
            str(meta),
        ]
    )
    assert rc == EXIT_REFUSED
    out = capsys.readouterr().out
    assert "allowed: False" in out


def test_run_does_not_start_nextflow_when_admit_refuses(tmp_path: Path):
    sheet = _good_sheet(tmp_path)
    meta = _confounded_metadata(tmp_path)
    calls: list[list[str]] = []

    def runner(cmd: list[str]) -> int:
        calls.append(cmd)
        return 0

    outcome = run_nextflow_gated(
        pipeline="rnaseq",
        samplesheet=sheet,
        outdir=tmp_path / "results",
        intent="differential-expression",
        metadata_path=meta,
        runner=runner,
    )
    assert outcome["exit_code"] == EXIT_REFUSED
    assert outcome["nextflow_started"] is False
    assert calls == []
    assert not (tmp_path / "results" / "pipeline_info" / "bionexus.config").exists()


def test_run_starts_nextflow_only_after_admit_and_warrants_crate(tmp_path: Path):
    sheet = _good_sheet(tmp_path)
    outdir = tmp_path / "results"
    calls: list[list[str]] = []

    def runner(cmd: list[str]) -> int:
        calls.append(cmd)
        write_nf_prov_crate(outdir)
        return 0

    outcome = run_nextflow_gated(
        pipeline="rnaseq",
        samplesheet=sheet,
        outdir=outdir,
        runner=runner,
        skip_scientific_preflight=True,
    )
    assert outcome["nextflow_started"] is True
    assert calls, "nextflow runner must be invoked after admit"
    assert calls[0][1] == "run"
    assert "-c" in calls[0]
    assert outcome["exit_code"] == EXIT_OK
    warrant = outcome["warrant"]
    assert warrant["provenance_source"] == "WRROC"
    assert warrant["warrant_status"] == "PROVENANCE_ONLY"
    config = (outdir / "pipeline_info" / "bionexus.config").read_text(encoding="utf-8")
    assert "id 'nf-prov'" in config
    assert "wrroc" in config


def test_warrant_exit_three_when_claims_refused(tmp_path: Path):
    run_dir = tmp_path / "run"
    write_nf_prov_crate(run_dir)
    ledger = ClaimLedger()
    ledger.add_evidence(
        EvidenceRef("E1", "method_run", "enrichment test", ConclusionMaturity.SUPPORTED.value)
    )
    ledger.add_claim(
        ClaimRecord(
            claim_id="C1",
            statement="CXCL13+ T cells drive tumor progression",
            capability_id="scrna.pseudobulk_de",
            supported_by=["E1"],
        )
    )
    ledger_path = run_dir / "bionexus.ledger.json"
    ledger.save(ledger_path)
    result = warrant_nextflow_run(run_dir, ledger_path=ledger_path)
    assert result.exit_code == EXIT_CLAIMS_REFUSED
    assert result.warrant_status == "CLAIMS_REFUSED"
    assert result.provenance_source == "WRROC"


def test_cli_warrant_provenance_only(tmp_path: Path, capsys):
    run_dir = tmp_path / "run"
    write_nf_prov_crate(run_dir)
    rc = cli_main(["nextflow", "warrant", str(run_dir), "--json"])
    assert rc == EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    assert payload["warrant_status"] == "PROVENANCE_ONLY"
    assert payload["provenance_source"] == "WRROC"
    assert payload["scientific_evidence_effect"] == "NONE"


def test_cli_warrant_exit_three(tmp_path: Path):
    run_dir = tmp_path / "run"
    write_nf_prov_crate(run_dir)
    ledger = ClaimLedger()
    ledger.add_evidence(
        EvidenceRef("E1", "method_run", "enrichment test", ConclusionMaturity.SUPPORTED.value)
    )
    ledger.add_claim(
        ClaimRecord(
            claim_id="C1",
            statement="CXCL13+ T cells drive tumor progression",
            capability_id="scrna.pseudobulk_de",
            supported_by=["E1"],
        )
    )
    ledger_path = run_dir / "bad.ledger.json"
    ledger.save(ledger_path)
    rc = cli_main(["nextflow", "warrant", str(run_dir), "--ledger", str(ledger_path)])
    assert rc == EXIT_CLAIMS_REFUSED


def test_unrelated_example_ledger_cannot_warrant_run(tmp_path: Path):
    run_dir = tmp_path / "run"
    write_nf_prov_crate(run_dir)
    ledger_path = write_example_ledger(run_dir / "bionexus.ledger.json")
    result = warrant_nextflow_run(run_dir, ledger_path=ledger_path)
    assert result.exit_code == EXIT_CLAIMS_REFUSED
    assert result.warrant_status == "CLAIMS_REFUSED"


def test_run_without_intent_does_not_start_nextflow(tmp_path: Path):
    sheet = _good_sheet(tmp_path)
    calls: list[list[str]] = []

    def runner(cmd: list[str]) -> int:
        calls.append(cmd)
        return 0

    outcome = run_nextflow_gated(
        pipeline="rnaseq",
        samplesheet=sheet,
        outdir=tmp_path / "results",
        runner=runner,
    )
    assert outcome["exit_code"] == EXIT_MISSING
    assert outcome["nextflow_started"] is False
    assert calls == []


def test_generated_config_enables_nf_prov_only():
    cfg = generate_bionexus_config(outdir="results")
    assert "id 'nf-prov'" in cfg
    assert "process {" not in cfg
    assert "workflow.nf" not in cfg


def test_cli_run_dry_run_does_not_need_nextflow(tmp_path: Path, capsys):
    sheet = _good_sheet(tmp_path)
    rc = cli_main(
        [
            "nextflow",
            "run",
            "--pipeline",
            "rnaseq",
            "--samplesheet",
            str(sheet),
            "--outdir",
            str(tmp_path / "results"),
            "--dry-run",
            "--skip-scientific-preflight",
        ]
    )
    assert rc == EXIT_OK
    out = capsys.readouterr().out
    assert "nextflow_started: False" in out
    assert "nextflow run nf-core/rnaseq" in out
