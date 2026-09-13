"""Stable publication needs explicit human acceptance, bound scope and evidence."""
import hashlib
import importlib
import json
import shutil
from pathlib import Path

import pytest
import yaml

from bionexus.release_contract import SCOPE_PATH, check_release

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def release_root(tmp_path):
    path = tmp_path / SCOPE_PATH
    path.parent.mkdir(parents=True)
    shutil.copyfile(ROOT / SCOPE_PATH, path)
    (tmp_path / "release").mkdir()
    shutil.copyfile(ROOT / "release/GA_ACTIVATION.json", tmp_path / "release/GA_ACTIVATION.json")
    return tmp_path


def activated_record(root):
    # Synthetic gate fixture, not an actual accepting maintainer or release.
    records = []
    for cat in ("core_quality", "de_contract", "installed_wheel", "static_checks", "validation_history", "evidence_index"):
        evidence = root / f"test-{cat}.json"
        evidence.write_text(f'{{"category":"{cat}","status":"PASSED"}}')
        records.append({
            "category": cat,
            "status": "PASSED",
            "candidate_version": "1.0.0",
            "path": evidence.name,
            "sha256": hashlib.sha256(evidence.read_bytes()).hexdigest(),
        })
    return {"schema": "bionexus.ga-activation.v1", "status": "ACTIVATED", "version": "1.0.0",
            "release_date": "2026-09-13", "support_end_date": "2027-09-13",
            "scope_sha256": hashlib.sha256((root / SCOPE_PATH).read_bytes().replace(b"\r\n", b"\n")).hexdigest(),
            "maintainers": [{"name": "Synthetic Test Maintainer", "accepted": True,
                             "accepted_on": "2026-09-12", "acceptance_reference": "fixture-only"}],
            "release_security_contact": "fixture-contact", "limitations": ["Synthetic fixture only"],
            "verification_records": records,
            "scientific_authorization": "NONE"}


def store(root, record):
    (root / "release/GA_ACTIVATION.json").write_text(json.dumps(record), encoding="utf-8")


def test_rc_scope_valid_does_not_activate_ga(release_root):
    assert check_release(release_root, "1.0.0-rc.8")["status"] == "RC_SCOPE_VALID"
    assert check_release(release_root, "1.0.0")["status"] == "BLOCKED"


def test_complete_record_validates_only_record_not_identity(release_root):
    store(release_root, activated_record(release_root))
    result = check_release(release_root, "1.0.0")
    assert result["status"] == "ACTIVATION_RECORD_VALID"
    assert result["identity_authentication"] == "NOT_PERFORMED"
    assert result["maintainer_signoff_verification"] == "MANUAL_INSPECTION_REQUIRED"
    assert result["scientific_authorization"] == "NONE"


def test_later_minor_reuses_original_support_clock(release_root):
    record = activated_record(release_root)
    store(release_root, record)
    assert check_release(release_root, "1.1.0")["status"] == "ACTIVATION_RECORD_VALID"
    record["version"] = "1.1.0"
    record["release_date"] = "2027-01-01"
    record["support_end_date"] = "2028-01-01"
    store(release_root, record)
    assert check_release(release_root, "1.1.0")["status"] == "BLOCKED"


@pytest.mark.parametrize("field,value", [
    ("version", "1.0.1"), ("status", "PROPOSED"), ("scope_sha256", "a" * 64),
    ("release_date", "invalid"), ("support_end_date", "2026-10-13"), ("maintainers", []),
    ("maintainers", [{"name": "[PENDING]", "accepted": True}]),
    ("maintainers", [{"name": "Test", "accepted": "true"}]),
    ("release_security_contact", ""), ("verification_records", []),
    ("verification_records", [{"path": "../outside", "sha256": "a" * 64}]),
    ("limitations", []), ("scientific_authorization", "CERTIFIED"),
])
def test_incomplete_or_escalated_activation_blocks(release_root, field, value):
    record = activated_record(release_root)
    record[field] = value
    store(release_root, record)
    assert check_release(release_root, "1.0.0")["status"] == "BLOCKED"


def test_acceptance_summary_checks_category_completeness_and_pass_status(release_root):
    record = activated_record(release_root)
    # Missing a category
    record["verification_records"] = [r for r in record["verification_records"] if r["category"] != "core_quality"]
    store(release_root, record)
    assert check_release(release_root, "1.0.0")["status"] == "BLOCKED"

    # Category failed
    record = activated_record(release_root)
    record["verification_records"][0]["status"] = "FAILED"
    store(release_root, record)
    assert check_release(release_root, "1.0.0")["status"] == "BLOCKED"

    # Candidate version mismatch
    record = activated_record(release_root)
    record["verification_records"][0]["candidate_version"] = "0.9.0"
    store(release_root, record)
    assert check_release(release_root, "1.0.0")["status"] == "BLOCKED"


def test_modified_evidence_blocks(release_root):
    store(release_root, activated_record(release_root))
    (release_root / "test-core_quality.json").write_text("{}")
    assert check_release(release_root, "1.0.0")["status"] == "BLOCKED"


@pytest.mark.parametrize("version", ["1.0", "1.0.0-foo", "1.0.0rc7", "2.0.0", "1.0.0;echo"])
def test_unknown_version_cannot_become_ga(release_root, version):
    assert check_release(release_root, version)["status"] == "BLOCKED"


def test_frozen_surface_resolves_and_does_not_include_experimental_execution():
    scope = json.loads((ROOT / SCOPE_PATH).read_bytes())
    assert scope["supported_cli"] == ["audit-de", "audit-de-verify", "audit-de-summary"]
    for path in scope["supported_python"]:
        module, name = path.rsplit(".", 1)
        assert callable(getattr(importlib.import_module(module), name))
    assert set(scope["experimental"]) == {"annotation", "spatial", "model_backends", "capability_execution", "certification", "external_host_conformance"}


def test_ga_gate_precedes_publication_and_is_not_optional():
    workflow = yaml.load((ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    steps = workflow["jobs"]["build-and-release"]["steps"]
    gate_index = next(i for i, s in enumerate(steps) if "check_release_contract.py" in s.get("run", ""))
    publish_index = next(i for i, s in enumerate(steps) if s.get("uses", "").startswith("softprops/action-gh-release@"))
    gate = steps[gate_index]
    assert gate_index < publish_index
    assert "if" not in gate and "continue-on-error" not in gate
    assert "|| true" not in gate["run"]


def test_support_contract_rejects_duplicate_keys(release_root):
    path = release_root / SCOPE_PATH
    path.write_text(path.read_text().replace('"support_months": 12', '"support_months": 1, "support_months": 12'))
    assert check_release(release_root, "1.0.0-rc.7")["status"] == "BLOCKED"
