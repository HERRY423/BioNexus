"""Restart, corruption, and cooperating local-process ledger regressions."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from bionexus.compliance_ledger import ComplianceAuditLedger


def _append(ledger, name="fixture"):
    return ledger.append_audit_entry(name, "RESEARCHER", "VIEW_DATA", "synthetic", {"value": 1})


def test_restart_and_stale_writer_continue_existing_chain(tmp_path):
    path = tmp_path / "audit.jsonl"
    first = ComplianceAuditLedger(path)
    stale = ComplianceAuditLedger(path)
    a = _append(first)
    original = path.read_bytes()
    b = _append(ComplianceAuditLedger(path))
    c = _append(stale)
    assert [a.entry_index, b.entry_index, c.entry_index] == [0, 1, 2]
    assert b.previous_entry_hash == a.entry_hash
    assert c.previous_entry_hash == b.entry_hash
    assert path.read_bytes().startswith(original)
    assert first.verify_ledger_integrity() == (True, [])
    assert len(first.entries) == 3


@pytest.mark.parametrize("damage", ["payload", "index", "schema", "truncated", "blank", "duplicate_key", "delete", "rollback"])
def test_disk_damage_blocks_verify_and_append_without_repair(tmp_path, damage):
    path = tmp_path / "audit.jsonl"
    ledger = ComplianceAuditLedger(path)
    _append(ledger)
    first_bytes = path.read_bytes()
    _append(ledger)
    data = [json.loads(line) for line in path.read_text().splitlines()]
    if damage in {"payload", "index", "schema"}:
        field, value = {"payload": ("target_resource", "tampered"),
                        "index": ("entry_index", 8), "schema": ("schema_version", "other")}[damage]
        data[1][field] = value
        # Index/schema checks must reject even self-consistently rehashed records.
        from bionexus.compliance_ledger import GxPAuditEntry
        data[1]["entry_hash"] = "sha256:" + GxPAuditEntry(**data[1]).compute_entry_hash()
        if damage == "payload":
            data[1]["entry_hash"] = "sha256:" + "0" * 64
        path.write_text("\n".join(json.dumps(row) for row in data) + "\n")
    elif damage == "truncated":
        path.write_bytes(path.read_bytes() + b'{"entry_index":')
    elif damage == "blank":
        path.write_bytes(path.read_bytes() + b"\n")
    elif damage == "duplicate_key":
        path.write_text(path.read_text().replace('"entry_index": 0', '"entry_index": 9, "entry_index": 0'))
    elif damage == "delete":
        path.unlink()
    else:
        path.write_bytes(first_bytes)
    before = path.read_bytes() if path.exists() else None
    assert not ledger.verify_ledger_integrity()[0]
    with pytest.raises(ValueError):
        _append(ledger)
    assert (path.read_bytes() if path.exists() else None) == before
    if damage not in {"delete", "rollback"}:
        with pytest.raises(ValueError):
            ComplianceAuditLedger(path)


def test_valid_last_line_without_newline_is_preserved(tmp_path):
    path = tmp_path / "audit.jsonl"
    _append(ComplianceAuditLedger(path))
    path.write_bytes(path.read_bytes().rstrip(b"\n"))
    original = path.read_bytes()
    _append(ComplianceAuditLedger(path))
    assert path.read_bytes().startswith(original + b"\n")
    assert ComplianceAuditLedger(path).verify_ledger_integrity()[0]


def test_cooperating_processes_do_not_create_multiple_genesis_entries(tmp_path):
    path = tmp_path / "audit.jsonl"
    script = """
import sys
from bionexus.compliance_ledger import ComplianceAuditLedger
ledger = ComplianceAuditLedger(sys.argv[1])
for i in range(12):
    ledger.append_audit_entry(sys.argv[2], 'RESEARCHER', 'VIEW_DATA', str(i))
"""
    env = dict(os.environ)
    import bionexus.compliance_ledger as module
    env["PYTHONPATH"] = str(Path(module.__file__).resolve().parents[1])
    processes = [subprocess.Popen([sys.executable, "-c", script, str(path), str(i)],
                                 env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                 for i in range(3)]
    try:
        for process in processes:
            stdout, stderr = process.communicate(timeout=30)
            assert process.returncode == 0, (stdout, stderr)
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
                process.wait()
    ledger = ComplianceAuditLedger(path)
    assert ledger.verify_ledger_integrity() == (True, [])
    assert len(ledger.entries) == 36
    assert [entry.entry_index for entry in ledger.entries] == list(range(36))


def test_memory_does_not_advance_on_disk_flush_failure(tmp_path, monkeypatch):
    ledger = ComplianceAuditLedger(tmp_path / "audit.jsonl")
    def fail(_):
        raise OSError("synthetic fsync failure")
    monkeypatch.setattr(os, "fsync", fail)
    with pytest.raises(OSError, match="synthetic"):
        _append(ledger)
    assert ledger.entries == []
    # A complete write may already be present: the caller must inspect/recover,
    # not assume rollback or blindly retry an event after an uncertain write.
    assert len(ComplianceAuditLedger(ledger.ledger_file).entries) == 1
