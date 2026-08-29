import json
import zipfile

import pytest

from bionexus.research_snapshot import (
    IntegrityError,
    SnapshotJournal,
    create_evidence_capsule,
    verify_evidence_capsule,
)


def test_snapshot_round_trip_and_parent_chain(tmp_path):
    journal = SnapshotJournal()
    first = journal.append("REV-001", {"claim": "unassessed"}, metadata={"actor": "researcher"})
    second = journal.append("REV-002", {"claim": "preliminary"})
    assert second.parent_digest == first.digest
    path = tmp_path / "journal.json"
    journal.save(path)
    loaded = SnapshotJournal.load(path)
    assert loaded.to_dict() == journal.to_dict()
    assert journal.revisions[-1].digest
    SnapshotJournal.load(path, expected_head_digest=journal.revisions[-1].digest)


@pytest.mark.parametrize("field,value", [("state", {"claim": "robust"}), ("parent_digest", "REV-9999")])
def test_snapshot_rejects_state_and_parent_tampering(tmp_path, field, value):
    journal = SnapshotJournal()
    journal.append("REV-001", {"claim": "unassessed"})
    journal.append("REV-002", {"claim": "preliminary"})
    path = tmp_path / "journal.json"
    journal.save(path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["revisions"][1][field] = value
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(IntegrityError):
        SnapshotJournal.load(path)


def test_externally_retained_head_detects_valid_prefix_rollback(tmp_path):
    journal = SnapshotJournal()
    journal.append("REV-001", {"claim": "unassessed"})
    first_only = tmp_path / "first.json"
    journal.save(first_only)
    journal.append("REV-002", {"claim": "preliminary"})
    with pytest.raises(IntegrityError):
        SnapshotJournal.load(first_only, expected_head_digest=journal.revisions[-1].digest)


def test_capsule_verifies_raw_bytes_across_newline_styles(tmp_path):
    path = tmp_path / "capsule.zip"
    create_evidence_capsule(
        path,
        {"results/lf.txt": b"a\nb\n", "results/crlf.txt": b"a\r\nb\r\n"},
        activity_name="unit-test",
    )
    manifest = verify_evidence_capsule(path)
    assert manifest["artifacts"]["results/lf.txt"]["sha256"] != manifest["artifacts"]["results/crlf.txt"]["sha256"]
    assert "not 21 CFR Part 11" in manifest["provenance"]["compliance_note"]
    verify_evidence_capsule(path, expected_manifest_digest=manifest["manifest_digest"])


def test_capsule_detects_byte_tampering(tmp_path):
    original = tmp_path / "capsule.zip"
    altered = tmp_path / "altered.zip"
    create_evidence_capsule(original, {"result.json": b"{}"}, activity_name="unit-test")
    with zipfile.ZipFile(original) as source, zipfile.ZipFile(altered, "w") as target:
        for info in source.infolist():
            data = source.read(info.filename)
            target.writestr(info, b'{"changed":true}' if info.filename == "result.json" else data)
    with pytest.raises(IntegrityError):
        verify_evidence_capsule(altered)


def test_capsule_rejects_unsafe_logical_names(tmp_path):
    with pytest.raises(ValueError):
        create_evidence_capsule(tmp_path / "bad.zip", {"../escape.txt": b"x"}, activity_name="unit-test")
