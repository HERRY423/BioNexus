"""A version bump must not rebrand historical assessments or erase an index."""
import hashlib
import json
import shutil
from pathlib import Path

import pytest

from bionexus.validation_history import is_preserved_internal_assessment
from scripts.check_evidence_index import save_current_index

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("capability", ["pseudobulk", "annotation", "spatial"])
def test_preserved_assessment_requires_exact_bytes_and_bounded_authority(tmp_path, capability):
    relative = f"validation/{capability}/CERTIFICATION.json"
    record = "review/trust-restoration-2026-09-19/CORRECTIONS.json"
    for name in (relative, record):
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    assert is_preserved_internal_assessment(tmp_path, relative)
    target = tmp_path / relative
    original = target.read_bytes()
    for field, value in (("project_version", "1.0.0-rc.9"), ("certification_effect", "CERTIFIED")):
        data = json.loads(original)
        data[field] = value
        target.write_text(json.dumps(data), encoding="utf-8")
        assert not is_preserved_internal_assessment(tmp_path, relative)
    assert not is_preserved_internal_assessment(tmp_path, "validation/annotation/REPORT.json")


def test_index_refresh_archives_previous_bytes_and_records_no_authority(tmp_path):
    path = tmp_path / "validation/EVIDENCE_INDEX.json"
    path.parent.mkdir()
    original = b'{"historical_index": true}\n'
    path.write_bytes(original)
    assert save_current_index(tmp_path) == 0
    receipts = list((tmp_path / "validation/runs").glob("*/receipt.json"))
    assert len(receipts) == 1
    receipt = json.loads(receipts[0].read_text())
    relative = "validation/EVIDENCE_INDEX.json"
    assert receipt["status"] == "COMPLETED_LOCAL_ONLY"
    assert receipt["before"][relative] == hashlib.sha256(original).hexdigest()
    assert receipt["after"][relative] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert (receipts[0].parent / "before" / relative).read_bytes() == original
    assert receipt["scientific_authorization"] == "NONE"
