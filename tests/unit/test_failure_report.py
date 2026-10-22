"""Compliant opt-in failure reports: default off, redacted, airgap/PHI blocked."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

from bionexus.cli import main
from bionexus.egress_guard import DataClassification, EgressMode
from bionexus.failure_report import (
    MODE_OFF,
    build_failure_report,
    persist_failure_report,
    report_mode,
    sanitize_text,
    telemetry_status,
    transmit_failure_report,
)


def test_default_mode_is_off(monkeypatch):
    monkeypatch.delenv("BIONEXUS_FAILURE_REPORTS", raising=False)
    assert report_mode() == MODE_OFF
    status = telemetry_status()
    assert status["vendor_backend"] == "NONE"
    assert status["mode"] == MODE_OFF


def test_sanitize_redacts_paths_emails_and_phi():
    raw = (
        "Error in C:\\Users\\alice\\secret.h5ad for patient_id=123 "
        "contact pi@lab.org at 10.0.0.8 ghp_abcdefghijklmnopqrstuvwxyz0123456789"
    )
    cleaned = sanitize_text(raw)
    assert "alice" not in cleaned
    assert "secret.h5ad" not in cleaned
    assert "pi@lab.org" not in cleaned
    assert "10.0.0.8" not in cleaned
    assert "ghp_" not in cleaned
    assert "<PATH>" in cleaned
    assert "<EMAIL>" in cleaned
    assert "<IP>" in cleaned
    assert "<SECRET>" in cleaned


def test_phi_report_is_not_transmit_eligible(monkeypatch, tmp_path):
    monkeypatch.setenv("BIONEXUS_FAILURE_REPORTS", "transmit")
    monkeypatch.setenv("BIONEXUS_FAILURE_REPORTS_ENDPOINT", "https://example.invalid/reports")
    monkeypatch.setenv("BIONEXUS_EGRESS_MODE", EgressMode.CONNECTED.value)
    report = build_failure_report(
        exception_type="ValueError",
        traceback_text="failed for patient_id MRN 000",
        data_classification=DataClassification.RESTRICTED_CLINICAL_PHI.value,
    )
    assert report.contains_phi is True
    assert report.transmit_eligible is False
    outcome = transmit_failure_report(report, opt_in=True)
    assert outcome["status"] == "REFUSED"
    path = persist_failure_report(report, dest_dir=tmp_path)
    assert path.is_file()


def test_offline_strict_never_transmits(monkeypatch):
    monkeypatch.setenv("BIONEXUS_FAILURE_REPORTS", "transmit")
    monkeypatch.setenv("BIONEXUS_FAILURE_REPORTS_ENDPOINT", "https://example.invalid/reports")
    monkeypatch.setenv("BIONEXUS_EGRESS_MODE", "OFFLINE_STRICT")
    report = build_failure_report(exception_type="RuntimeError", traceback_text="boom")
    assert report.transmit_eligible is False
    assert transmit_failure_report(report, opt_in=True)["status"] == "REFUSED"


def test_cli_report_failure_writes_local_json(tmp_path, capsys):
    code = main(
        [
            "deploy",
            "report-failure",
            "--exception-type",
            "RuntimeError",
            "--message",
            "failed at C:\\Users\\bob\\private.csv",
            "-o",
            str(tmp_path),
            "--json",
        ]
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "WRITTEN"
    written = json.loads(Path(payload["path"]).read_text(encoding="utf-8"))
    assert written["schema_version"] == "bionexus.failure-report.v1"
    assert "bob" not in written["notes"]
    assert "private.csv" not in written["sanitized_traceback"]
    assert written["transmit_eligible"] is False
    assert written["data_classification"] == "UNKNOWN"


def test_unknown_classification_never_transmits_even_when_opted_in(monkeypatch):
    monkeypatch.setenv("BIONEXUS_FAILURE_REPORTS", "transmit")
    monkeypatch.setenv("BIONEXUS_FAILURE_REPORTS_ENDPOINT", "https://example.invalid/reports")
    monkeypatch.setenv("BIONEXUS_EGRESS_MODE", "CONNECTED")
    report = build_failure_report(exception_type="RuntimeError", traceback_text="synthetic error")
    assert report.data_classification == "UNKNOWN"
    assert report.transmit_eligible is False
    assert transmit_failure_report(dataclasses.replace(report, transmit_eligible=True), opt_in=True)["status"] == "REFUSED"


def test_transmit_rechecks_live_mode_after_report_creation(monkeypatch):
    monkeypatch.setenv("BIONEXUS_FAILURE_REPORTS", "transmit")
    monkeypatch.setenv("BIONEXUS_FAILURE_REPORTS_ENDPOINT", "https://example.invalid/reports")
    monkeypatch.setenv("BIONEXUS_EGRESS_MODE", "CONNECTED")
    report = build_failure_report(exception_type="RuntimeError", data_classification="PUBLIC_BENCHMARK")
    assert report.transmit_eligible is True
    monkeypatch.setenv("BIONEXUS_FAILURE_REPORTS", "off")
    assert transmit_failure_report(report, opt_in=True)["status"] == "REFUSED"


def test_explicit_public_report_can_transmit_through_guard_after_opt_in(monkeypatch):
    import io

    monkeypatch.setenv("BIONEXUS_FAILURE_REPORTS", "transmit")
    monkeypatch.setenv("BIONEXUS_FAILURE_REPORTS_ENDPOINT", "https://example.invalid/reports")
    monkeypatch.setenv("BIONEXUS_EGRESS_MODE", "CONNECTED")
    calls = []

    def guarded_transport(request, **kwargs):
        calls.append((request, kwargs))
        response = io.BytesIO(b"")
        response.status = 204
        return response

    monkeypatch.setattr("bionexus.failure_report.guarded_urlopen", guarded_transport)
    report = build_failure_report(exception_type="SyntheticFixtureError", data_classification="PUBLIC_BENCHMARK")
    assert transmit_failure_report(report, opt_in=True) == {"status": "SENT", "http_status": 204}
    assert len(calls) == 1
    assert calls[0][1]["data_classification"] == DataClassification.PUBLIC_BENCHMARK
