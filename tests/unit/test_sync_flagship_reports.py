"""Regression: metadata synchronization must never manufacture a new run."""
import copy
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from bionexus.validation_history import (
    ARCHIVE,
    REPORTS,
    assess_history,
    has_current_run_receipt,
    is_quarantined_history,
)
from bionexus.validation_runs import record_validation_run
from scripts.sync_flagship_reports import sync_nested_provenance

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def history_root(tmp_path):
    shutil.copytree(ROOT / ARCHIVE, tmp_path / ARCHIVE)
    for rel in REPORTS:
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / ARCHIVE / rel, path)
    return tmp_path


def test_unsafe_legacy_api_refuses_without_mutation():
    document = {"commit_sha": "old", "source_snapshot_sha256": "old", "git_dirty": True,
                "timestamp": "old", "generator_version": "old", "metrics": [{"observed": 0.66}]}
    before = copy.deepcopy(document)
    with pytest.raises(RuntimeError, match="immutable"):
        sync_nested_provenance(document, "new", "new", update_commit=True)
    assert document == before


def test_inventory_preserves_every_byte_and_grants_no_execution(history_root):
    before = {p: p.read_bytes() for p in history_root.rglob("*.json")}
    result = assess_history(history_root)
    assert result["archive_integrity"] == "VERIFIED"
    assert {r["relationship"] for r in result["records"]} == {"PRESERVED_LEGACY"}
    assert result["current_execution_verification"] == "NOT_PERFORMED"
    assert result["original_execution_authenticity"] == "NOT_ESTABLISHED"
    assert {p: p.read_bytes() for p in before} == before
    rel = REPORTS[0]
    assert is_quarantined_history(history_root, rel, json.loads((history_root / rel).read_bytes()))


def test_inventory_detects_archive_tampering(history_root):
    (history_root / ARCHIVE / REPORTS[0]).write_text("{}")
    assert assess_history(history_root)["archive_integrity"] == "INVALID"


def test_changed_view_is_not_a_new_execution(history_root):
    path = history_root / REPORTS[0]
    data = json.loads(path.read_bytes())
    data["timestamp"] = "NEW"
    path.write_text(json.dumps(data))
    result = assess_history(history_root)
    assert result["records"][0]["relationship"] == "CHANGED_REQUIRES_NEW_EXECUTION_EVIDENCE"
    assert result["current_execution_verification"] == "NOT_PERFORMED"


def test_output_cannot_overwrite_input_report(history_root):
    path = history_root / REPORTS[0]
    before = path.read_bytes()
    process = subprocess.run([sys.executable, str(ROOT / "scripts/sync_flagship_reports.py"),
                              "--root", str(history_root), "--output", str(path)], capture_output=True)
    assert process.returncode != 0
    assert path.read_bytes() == before


@pytest.mark.parametrize("failure", [False, True])
def test_run_capsule_preserves_old_new_and_failure(tmp_path, failure):
    path = tmp_path / "validation/pseudobulk/REPORT.json"
    path.parent.mkdir(parents=True)
    path.write_bytes(b'{"execution":"old"}')
    @record_validation_run(tmp_path)
    def run():
        path.write_bytes(b'{"execution":"new"}')
        if failure:
            raise ValueError("scientific run failed")
        return 0
    if failure:
        with pytest.raises(ValueError):
            run()
    else:
        run()
    capsule, = (tmp_path / "validation/runs").iterdir()
    receipt = json.loads((capsule / "receipt.json").read_bytes())
    relative = "validation/pseudobulk/REPORT.json"
    assert (capsule / "before" / relative).read_bytes() == b'{"execution":"old"}'
    assert (capsule / "after" / relative).read_bytes() == b'{"execution":"new"}'
    assert receipt["after"][relative] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert receipt["error"] == ("ValueError" if failure else None)
    assert receipt["status"] == ("FAILED" if failure else "COMPLETED_LOCAL_ONLY")
    assert receipt["changed"] == [relative]
    assert receipt["scientific_authorization"] == "NONE"
    assert has_current_run_receipt(tmp_path, relative, receipt["source_after"]) is (not failure)
    assert not has_current_run_receipt(tmp_path, relative, "different-source")
    path.write_text('{"execution":"tampered"}')
    assert not has_current_run_receipt(tmp_path, relative, receipt["source_after"])
    assert not (tmp_path / "validation/runs/.writer.lock").exists()


def test_unchanged_report_is_not_attributed_to_new_run(tmp_path):
    path = tmp_path / "validation/pseudobulk/REPORT.json"
    path.parent.mkdir(parents=True)
    path.write_text("{}")
    @record_validation_run(tmp_path)
    def run():
        return 0
    run()
    capsule, = (tmp_path / "validation/runs").iterdir()
    receipt = json.loads((capsule / "receipt.json").read_bytes())
    assert receipt["changed"] == []
    assert not has_current_run_receipt(tmp_path, "validation/pseudobulk/REPORT.json", receipt["source_after"])


def test_source_change_rejects_run_and_retains_both_snapshots(tmp_path):
    source = tmp_path / "src/bionexus/example.py"
    source.parent.mkdir(parents=True)
    source.write_text("VALUE = 1")
    (tmp_path / "validation").mkdir()
    @record_validation_run(tmp_path)
    def run():
        source.write_text("VALUE = 2")
        return 0
    with pytest.raises(RuntimeError, match="source changed"):
        run()
    capsule, = (tmp_path / "validation/runs").iterdir()
    receipt = json.loads((capsule / "receipt.json").read_bytes())
    assert receipt["status"] == "FAILED_SOURCE_CHANGED"
    assert receipt["source_before"] != receipt["source_after"]


def test_overlapping_writer_cannot_borrow_another_runs_outputs(tmp_path):
    path = tmp_path / "validation/pseudobulk/REPORT.json"
    path.parent.mkdir(parents=True)
    path.write_text("old")
    @record_validation_run(tmp_path)
    def second():
        path.write_text("incorrectly attributed")
        return 0
    @record_validation_run(tmp_path)
    def first():
        with pytest.raises(RuntimeError, match="writer lock"):
            second()
        assert path.read_text() == "old"
        path.write_text("first runner output")
        return 0
    first()
    capsule, = (tmp_path / "validation/runs").iterdir()
    receipt = json.loads((capsule / "receipt.json").read_bytes())
    assert receipt["status"] == "COMPLETED_LOCAL_ONLY"
    assert receipt["changed"] == ["validation/pseudobulk/REPORT.json"]


def test_interrupted_writer_lock_is_not_silently_removed(tmp_path):
    lock = tmp_path / "validation/runs/.writer.lock"
    lock.parent.mkdir(parents=True)
    lock.write_text("interrupted execution")
    @record_validation_run(tmp_path)
    def run():
        pytest.fail("A stale lock must not authorize a new run")
    with pytest.raises(RuntimeError, match="writer lock"):
        run()
    assert lock.read_text() == "interrupted execution"
