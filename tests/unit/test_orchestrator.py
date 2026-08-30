"""Unit tests for Run Capsule chain orchestration (bionexus.orchestrator)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from bionexus.orchestrator import ChainSpec, ChainValidationError, run_chain

PY = sys.executable


def _write_spec(tmp_path: Path, steps: list, name: str = "test-chain") -> Path:
    spec = tmp_path / "chain.yaml"
    spec.write_text(yaml.safe_dump({"name": name, "steps": steps}), encoding="utf-8")
    return spec


def test_spec_rejects_dependency_cycle(tmp_path: Path):
    spec = _write_spec(
        tmp_path,
        [
            {"id": "a", "command": [PY, "-c", "print(1)"], "depends_on": ["b"]},
            {"id": "b", "command": [PY, "-c", "print(2)"], "depends_on": ["a"]},
        ],
    )
    with pytest.raises(ChainValidationError, match="cycle"):
        ChainSpec.load(spec)


def test_spec_rejects_unknown_dependency_and_duplicates(tmp_path: Path):
    with pytest.raises(ChainValidationError, match="unknown step"):
        ChainSpec.from_mapping(
            {"steps": [{"id": "a", "command": [PY, "-c", "print(1)"], "depends_on": ["ghost"]}]}
        )
    with pytest.raises(ChainValidationError, match="Duplicate step ids"):
        ChainSpec.from_mapping(
            {
                "steps": [
                    {"id": "a", "command": [PY, "-c", "print(1)"]},
                    {"id": "a", "command": [PY, "-c", "print(2)"]},
                ]
            }
        )


def test_spec_rejects_shell_string_and_sudo(tmp_path: Path):
    with pytest.raises(ChainValidationError, match="argv"):
        ChainSpec.from_mapping({"steps": [{"id": "a", "command": "echo hello > file"}]})
    with pytest.raises(ChainValidationError, match="sudo"):
        ChainSpec.from_mapping({"steps": [{"id": "a", "command": ["sudo", "rm", "-rf", "/"]}]})
    with pytest.raises(ChainValidationError, match="non-empty"):
        ChainSpec.from_mapping({"steps": [{"id": "a", "command": []}]})


def test_dry_run_plans_without_executing(tmp_path: Path):
    spec = _write_spec(
        tmp_path,
        [
            {"id": "second", "command": [PY, "-c", "print(2)"], "depends_on": ["first"]},
            {"id": "first", "command": [PY, "-c", "print(1)"]},
        ],
    )
    workdir = tmp_path / "runs"
    payload = run_chain(spec, workdir, dry_run=True)
    assert payload["chain"]["chain_status"] == "PLANNED"
    # Topological order must put 'first' before 'second' regardless of listing order.
    assert payload["chain"]["planned_order"] == ["first", "second"]
    assert not workdir.exists() or not any(workdir.iterdir())


def test_chain_executes_topologically_and_captures_capsules(tmp_path: Path):
    marker = tmp_path / "marker.txt"
    spec = _write_spec(
        tmp_path,
        [
            {
                "id": "second",
                "command": [PY, "-c", "print('second ran')"],
                "depends_on": ["first"],
                "inputs": [str(marker)],
            },
            {
                "id": "first",
                "command": [PY, "-c", f"open({str(marker)!r}, 'w').write('done')"],
            },
        ],
    )
    payload = run_chain(spec, tmp_path / "runs")
    chain = payload["chain"]
    assert chain["chain_status"] == "COMPLETED"
    assert chain["planned_order"] == ["first", "second"]
    assert payload["abstain"] is False

    for step_id in ("first", "second"):
        run_json = tmp_path / "runs" / step_id / "run.json"
        assert run_json.is_file(), step_id
        manifest = json.loads(run_json.read_text(encoding="utf-8"))
        assert manifest["status"] == "COMPLETED"
        assert manifest["execution_state"] == "EXECUTED"
        assert (tmp_path / "runs" / step_id / "provenance.json").is_file()

    summary = json.loads((tmp_path / "runs" / "chain_summary.json").read_text(encoding="utf-8"))
    assert summary["chain_status"] == "COMPLETED"
    assert marker.read_text(encoding="utf-8") == "done"


def test_chain_fails_closed_and_skips_downstream(tmp_path: Path):
    spec = _write_spec(
        tmp_path,
        [
            {"id": "ok_stage", "command": [PY, "-c", "print('fine')"]},
            {"id": "boom", "command": [PY, "-c", "import sys; sys.exit(3)"], "depends_on": ["ok_stage"]},
            {"id": "never", "command": [PY, "-c", "print('must not run')"], "depends_on": ["boom"]},
        ],
    )
    payload = run_chain(spec, tmp_path / "runs")
    chain = payload["chain"]
    assert chain["chain_status"] == "FAILED"
    assert payload["abstain"] is True
    by_id = {s["step_id"]: s for s in chain["steps"]}
    assert by_id["ok_stage"]["status"] == "EXECUTED"
    assert by_id["boom"]["status"] == "FAILED"
    assert by_id["boom"]["returncode"] == 3
    assert by_id["never"]["status"] == "SKIPPED_FAIL_CLOSED"

    # The failed stage's own capsule records the failure honestly.
    boom_manifest = json.loads((tmp_path / "runs" / "boom" / "run.json").read_text(encoding="utf-8"))
    assert boom_manifest["status"] == "FAILED"
    assert boom_manifest["execution_state"] == "FAILED"
    summary = json.loads((tmp_path / "runs" / "chain_summary.json").read_text(encoding="utf-8"))
    assert summary["chain_status"] == "FAILED"


def test_chain_handles_missing_executable_fail_closed(tmp_path: Path):
    spec = _write_spec(tmp_path, [{"id": "ghost", "command": ["definitely-not-a-real-binary-xyz"]}],)
    payload = run_chain(spec, tmp_path / "runs")
    assert payload["chain"]["chain_status"] == "FAILED"
    assert payload["chain"]["steps"][0]["status"] == "FAILED"


def test_stage_capsules_do_not_fabricate_scientific_evidence(tmp_path: Path):
    spec = _write_spec(tmp_path, [{"id": "only", "command": [PY, "-c", "print(1)"]}])
    run_chain(spec, tmp_path / "runs")
    evidence = json.loads((tmp_path / "runs" / "only" / "evidence.json").read_text(encoding="utf-8"))
    assert evidence["execution_state"] == "EXECUTED"
    assert evidence["input_integrity"] == "UNTESTED"
    assert evidence["statistical_support"] == "UNTESTED"

    manifest = json.loads((tmp_path / "runs" / "only" / "run.json").read_text(encoding="utf-8"))
    assert manifest["conclusion_maturity"] == "PRELIMINARY"
