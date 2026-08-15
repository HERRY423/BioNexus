"""
Unit tests for BioNexus Unified CLI.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC = _REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from bionexus.cli import main
from bionexus.versions import PLUGIN_VERSION


def test_cli_version(capsys):
    """Test bionexus --version."""
    with pytest.raises(SystemExit) as excinfo:
        main(["--version"])
    assert excinfo.value.code == 0
    captured = capsys.readouterr()
    assert PLUGIN_VERSION in captured.out


def test_cli_help(capsys):
    """Test bionexus without arguments prints help."""
    ret = main([])
    assert ret == 0
    captured = capsys.readouterr()
    assert "create-plugin" in captured.out
    assert "doctor" in captured.out
    assert "list-skills" in captured.out
    assert "registry" in captured.out


def test_cli_doctor(capsys):
    """Test bionexus doctor."""
    ret = main(["doctor"])
    assert ret == 0
    captured = capsys.readouterr()
    assert "BioNexus Environment Doctor" in captured.out
    assert "Plugin Version:" in captured.out


def test_cli_doctor_json(capsys):
    """Test bionexus doctor --json."""
    ret = main(["doctor", "--json"])
    assert ret == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert "plugin_version" in data
    assert "ready" in data
    assert "backends" in data



def test_cli_list_skills(capsys):
    """Test bionexus list-skills."""
    ret = main(["list-skills"])
    assert ret == 0
    captured = capsys.readouterr()
    assert "single-cell-rna-qc" in captured.out
    assert "spatial-transcriptomics" in captured.out
    assert "canonical" in captured.out


def test_cli_list_skills_filter_tier(capsys):
    """Test bionexus list-skills --tier core."""
    ret = main(["list-skills", "--tier", "core"])
    assert ret == 0
    captured = capsys.readouterr()
    assert "single-cell-rna-qc" in captured.out
    assert "variant-interpretation" not in captured.out


def test_cli_list_skills_json(capsys):
    """Test bionexus list-skills --json."""
    ret = main(["list-skills", "--json"])
    assert ret == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert isinstance(data, list)
    assert len(data) == 17
    names = {s["name"] for s in data}
    assert "single-cell-rna-qc" in names


def test_cli_registry_check(capsys):
    """Test bionexus registry --check."""
    ret = main(["registry", "--check"])
    assert ret == 0
    captured = capsys.readouterr()
    assert "strictly in sync" in captured.out


def test_cli_registry_validate_endpoints(capsys):
    """Test bionexus registry --validate-endpoints."""
    ret = main(["registry", "--validate-endpoints"])
    assert ret == 0
    captured = capsys.readouterr()
    assert "Validating BioNexus MCP Endpoints" in captured.out
    assert "Endpoint syntax validated successfully" in captured.out


def test_cli_audit_nonexistent(capsys):
    """Test bionexus audit on missing file returns error."""
    ret = main(["audit", "nonexistent_file_xyz.h5ad"])
    assert ret == 1
    captured = capsys.readouterr()
    assert "not found" in captured.err
