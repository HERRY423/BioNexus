"""Regression tests for fail-closed laboratory-facing CLI routes."""

import json
from pathlib import Path

from bionexus.cli import main


def _json_output(capsys):
    return json.loads(capsys.readouterr().out)


def test_instrument_detect_refuses_missing_input(capsys, tmp_path):
    rc = main(["instrument", "detect", str(tmp_path / "missing.csv"), "--json"])

    payload = _json_output(capsys)
    assert rc == 1
    assert payload["status"] == "REFUSED_MISSING_INPUT"
    assert payload["source_exists"] is False


def test_lims_sync_does_not_report_mock_success(capsys):
    rc = main(["lims", "sync-samples", "--json"])

    payload = _json_output(capsys)
    assert rc == 2
    assert payload["status"] == "REFUSED_NOT_CONFIGURED"
    assert payload["executed"] is False


def test_airgap_external_destination_abstains(capsys):
    rc = main(
        [
            "airgap",
            "evaluate",
            "https://api.example.org/upload",
            "--mode",
            "AIRGAP_STRICT",
            "--json",
        ]
    )

    payload = _json_output(capsys)
    assert rc == 1
    assert payload["status"] == "ABSTAIN"
    assert payload["certification"] == "NOT_ASSESSED"


def test_compliance_sign_refuses_missing_artifact(capsys, tmp_path):
    rc = main(["compliance", "sign", str(tmp_path / "missing.json"), "--json"])

    payload = _json_output(capsys)
    assert rc == 1
    assert payload["status"] == "REFUSED_MISSING_INPUT"
    assert payload["regulatory_compliance"] == "NOT_ASSESSED"


def test_container_workflow_creates_apptainer_temp_directory():
    workflow = Path(".github/workflows/container.yml").read_text(encoding="utf-8")
    create_index = workflow.index('mkdir -p "$PWD/.apptainer-tmp"')
    build_index = workflow.index("APPTAINER_TMPDIR=$PWD/.apptainer-tmp apptainer build")

    assert create_index < build_index
