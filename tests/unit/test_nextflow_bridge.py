"""Tests for the passive Nextflow execution-provenance harvester (BNS-021)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from bionexus.cli import main as cli_main
from bionexus.nextflow_bridge import (
    NextflowExecutionSummary,
    create_nextflow_tool_receipt,
    harvest_nextflow_run,
    parse_samplesheet,
    parse_trace_file,
    parse_versions_file,
)
from bionexus.tool_receipt import extract_evidence_factors_from_receipt, verify_tool_receipt


@pytest.fixture
def mock_nextflow_run(tmp_path: Path) -> Path:
    run_dir = tmp_path / "nf_run_001"
    run_dir.mkdir(parents=True)
    pipe_info = run_dir / "pipeline_info"
    pipe_info.mkdir()

    # 1. execution_trace.txt
    trace_content = (
        "task_id\thash\tnative_id\tname\tstatus\texit\tsubmit\tduration\trealtime\t%cpu\tpeak_rss\tpeak_vmem\n"
        "1\tab/123456\t101\tNFCORE_RNASEQ:FASTQC (sample1)\tCOMPLETED\t0\t2026-08-29 08:00:00\t12000\t11500\t95.0\t536870912\t1073741824\n"
        "2\tcd/234567\t102\tNFCORE_RNASEQ:SALMON_QUANT (sample1)\tCOMPLETED\t0\t2026-08-29 08:02:00\t45000\t44000\t190.0\t2147483648\t4294967296\n"
        "3\tef/345678\t103\tNFCORE_RNASEQ:DESEQ2_QC (all)\tCACHED\t0\t2026-08-29 08:05:00\t5000\t4500\t50.0\t268435456\t536870912\n"
    )
    (pipe_info / "execution_trace.txt").write_text(trace_content, encoding="utf-8")

    # 2. software_versions.yml
    versions_content = (
        "NFCORE_RNASEQ:\n"
        "  nextflow: 23.10.0\n"
        "  pipeline: 3.14.0\n"
        "FASTQC:\n"
        "  fastqc: 0.12.1\n"
        "SALMON:\n"
        "  salmon: 1.10.2\n"
        "DESEQ2:\n"
        "  deseq2: 1.42.0\n"
    )
    (pipe_info / "software_versions.yml").write_text(versions_content, encoding="utf-8")

    # 3. samplesheet.csv
    sheet_content = (
        "sample,fastq_1,fastq_2,strandedness,condition,donor\n"
        "CTRL_1,/data/c1_1.fq.gz,/data/c1_2.fq.gz,auto,control,donorA\n"
        "CTRL_2,/data/c2_1.fq.gz,/data/c2_2.fq.gz,auto,control,donorB\n"
        "CTRL_3,/data/c3_1.fq.gz,/data/c3_2.fq.gz,auto,control,donorC\n"
        "TREAT_1,/data/t1_1.fq.gz,/data/t1_2.fq.gz,auto,treated,donorD\n"
        "TREAT_2,/data/t2_1.fq.gz,/data/t2_2.fq.gz,auto,treated,donorE\n"
        "TREAT_3,/data/t3_1.fq.gz,/data/t3_2.fq.gz,auto,treated,donorF\n"
    )
    (run_dir / "samplesheet.csv").write_text(sheet_content, encoding="utf-8")

    # 4. output files
    (run_dir / "salmon.merged.gene_counts.tsv").write_text("gene\tCTRL_1\tCTRL_2\tTREAT_1\nG1\t10\t12\t50\n", encoding="utf-8")
    (run_dir / "multiqc_report.html").write_text("<html>MultiQC Complete</html>", encoding="utf-8")

    return run_dir


def test_parse_trace_file_success(mock_nextflow_run: Path):
    trace_path = mock_nextflow_run / "pipeline_info" / "execution_trace.txt"
    stats = parse_trace_file(trace_path)
    assert stats["total_processes"] == 3
    assert stats["succeeded_processes"] == 3
    assert stats["failed_processes"] == 0
    assert stats["cached_processes"] == 1
    assert stats["execution_status"] == "SUCCESS"
    assert stats["total_cpu_hours"] > 0
    assert stats["peak_rss_gb"] == 2.0  # 2147483648 bytes = 2.0 GB


def test_parse_trace_file_failed(tmp_path: Path):
    trace_path = tmp_path / "failed_trace.txt"
    trace_path.write_text(
        "task_id\tname\tstatus\texit\n"
        "1\tPROCESS_A\tCOMPLETED\t0\n"
        "2\tPROCESS_B\tFAILED\t1\n",
        encoding="utf-8",
    )
    stats = parse_trace_file(trace_path)
    assert stats["total_processes"] == 2
    assert stats["failed_processes"] == 1
    assert stats["execution_status"] == "FAILED"


def test_parse_versions_file(mock_nextflow_run: Path):
    v_path = mock_nextflow_run / "pipeline_info" / "software_versions.yml"
    versions = parse_versions_file(v_path)
    assert "SALMON.salmon" in versions or "salmon" in versions
    assert "DESEQ2.deseq2" in versions or "deseq2" in versions


def test_parse_samplesheet(mock_nextflow_run: Path):
    sheet_path = mock_nextflow_run / "samplesheet.csv"
    samples, facts = parse_samplesheet(sheet_path)
    assert len(samples) == 6
    assert facts["sample_count"] == 6
    assert facts["min_replicates_per_condition"] == 3
    assert facts["conditions_count"] == 2
    assert facts["biological_replicates_count"] == 6


def test_harvest_nextflow_run_e2e_does_not_infer_samplesheet_or_scientific_evidence(mock_nextflow_run: Path):
    summary = harvest_nextflow_run(mock_nextflow_run, pipeline_name="nf-core/rnaseq")
    assert isinstance(summary, NextflowExecutionSummary)
    assert summary.pipeline_name == "nf-core/rnaseq"
    assert summary.execution_status == "SUCCESS"
    assert summary.samplesheet_path is None
    assert summary.sample_count == 0
    assert summary.derived_evidence_factors == []
    assert "salmon.merged.gene_counts.tsv" in summary.primary_outputs
    assert "multiqc_report.html" in summary.primary_outputs


def test_harvest_missing_trace_stays_unknown(tmp_path: Path):
    (tmp_path / "result.tsv").write_text("x\n", encoding="utf-8")
    summary = harvest_nextflow_run(tmp_path)
    assert summary.execution_status == "UNKNOWN"
    assert summary.total_processes == 0


def test_create_nextflow_tool_receipt_and_cryptographic_verification(mock_nextflow_run: Path):
    receipt = create_nextflow_tool_receipt(mock_nextflow_run, pipeline_name="nf-core/rnaseq")
    assert receipt["schema_version"] == "bionexus.tool-execution-receipt.v1"
    assert receipt["plugin_id"] == "bionexus-nextflow"
    assert receipt["tool_name"] == "nf-core.rnaseq"
    assert receipt["execution_status"] == "SUCCESS"

    # Cryptographic integrity verification
    ver_ok, ver_err = verify_tool_receipt(receipt)
    assert ver_ok is True
    assert not ver_err


def test_nextflow_receipt_is_provenance_only_and_does_not_mint_scientific_factors(mock_nextflow_run: Path):
    receipt = create_nextflow_tool_receipt(mock_nextflow_run, pipeline_name="nf-core/rnaseq")
    factors, notes = extract_evidence_factors_from_receipt(receipt)
    assert len(notes) > 0
    assert "backend_fidelity" in factors
    assert "provenance" in factors
    assert not {"sample_design", "replication", "confound_controls", "sensitivity_analysis"} & factors
    assert receipt["metadata"]["scientific_evidence_effect"] == "NONE"


def test_nextflow_receipt_refuses_scientific_factor_injection(mock_nextflow_run: Path):
    with pytest.raises(ValueError, match="cannot declare scientific evidence factors"):
        create_nextflow_tool_receipt(
            mock_nextflow_run,
            extra_metadata={"replication": True},
        )


def test_cli_nextflow_inspect(mock_nextflow_run: Path, capsys: pytest.CaptureFixture):
    ret = cli_main(["nextflow", "inspect", str(mock_nextflow_run)])
    assert ret == 0
    captured = capsys.readouterr()
    assert "Nextflow Execution Summary" in captured.out
    assert "SUCCESS" in captured.out


def test_cli_nextflow_ingest(mock_nextflow_run: Path, tmp_path: Path):
    out_receipt = tmp_path / "out_receipt.json"
    ret = cli_main([
        "nextflow",
        "ingest",
        "--run-dir",
        str(mock_nextflow_run),
        "-o",
        str(out_receipt),
    ])
    assert ret == 0
    assert out_receipt.is_file()
    data = json.loads(out_receipt.read_text(encoding="utf-8"))
    assert data["plugin_id"] == "bionexus-nextflow"
    assert data["tool_name"] == "nf-core.pipeline"


def test_unsafe_bns019_pipeline_injection_generator_is_retired(mock_nextflow_run: Path, tmp_path: Path):
    script = Path(__file__).resolve().parents[2] / "interoperability" / "bns019" / "nf-core" / "bin" / "bns019_receipt_generator.py"
    module = script.parents[1] / "modules" / "local" / "bns019_receipt" / "main.nf"
    assert not script.exists()
    assert not module.exists()

    zero_touch = script.parents[2] / "ro-crate" / "bns019_artifact_annotator.py"
    source = zero_touch.read_text(encoding="utf-8")
    assert "parse_samplesheet" not in source
    assert "evidence_maturity" not in source


def test_nfcore_launch_extended_pipelines(tmp_path: Path):
    script_dir = Path(__file__).resolve().parents[2] / "skills" / "nextflow-development" / "scripts"
    if str(script_dir) not in sys.path:
        sys.path.insert(0, str(script_dir))
    from nfcore_launch import build_launch_command

    for p in ("differentialabundance", "sarek", "spatialtranscriptomics", "ampliseq"):
        cmd = build_launch_command(
            pipeline=p,
            samplesheet="samples.csv",
            outdir=str(tmp_path / "out"),
        )
        assert cmd[0] == "nextflow"
        assert cmd[1] == "run"
        assert cmd[2] == f"nf-core/{p}"
