"""Nextflow samplesheet / config preflight."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "skills" / "nextflow-development" / "scripts"))

from check_environment import check_pipeline_config, check_samplesheet, run_all_checks


def test_samplesheet_requires_fastq_or_bam():
    bad = PROJECT_ROOT / "tests" / "_tmp_bad_samplesheet.csv"
    good = PROJECT_ROOT / "tests" / "_tmp_good_samplesheet.csv"
    try:
        bad.write_text("foo,bar\n1,2\n", encoding="utf-8")
        result = check_samplesheet(str(bad))
        assert result.passed is False

        good.write_text("sample,fastq_1,fastq_2\ns1,a.fq.gz,b.fq.gz\n", encoding="utf-8")
        result = check_samplesheet(str(good))
        assert result.passed is True
    finally:
        for path in (bad, good):
            if path.exists():
                path.unlink()


def test_missing_samplesheet_fails():
    result = check_samplesheet(str(PROJECT_ROOT / "no_such_samplesheet.csv"))
    assert result.passed is False


def test_config_detects_profiles():
    cfg = PROJECT_ROOT / "tests" / "_tmp_nextflow.config"
    try:
        cfg.write_text("profiles {\n  docker { docker.enabled = true }\n}\n", encoding="utf-8")
        result = check_pipeline_config(str(cfg))
        assert result.passed is True
    finally:
        if cfg.exists():
            cfg.unlink()


def test_preflight_skip_network_includes_samplesheet():
    sheet = PROJECT_ROOT / "tests" / "_tmp_preflight_samplesheet.csv"
    try:
        sheet.write_text("sample,fastq_1\ns1,a.fq.gz\n", encoding="utf-8")
        report = run_all_checks(samplesheet=str(sheet), skip_network=True)
        names = [c.name for c in report.checks]
        assert "Samplesheet" in names
        assert "Network" not in names
    finally:
        if sheet.exists():
            sheet.unlink()
