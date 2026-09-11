"""Consumer compatibility and integrity adversarial cases, independent of biology."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import jsonschema
import pytest

from bionexus.cli import main
from bionexus.de_audit import audit_differential_expression
from bionexus.de_bundle import MAX_ARTIFACT_BYTES, verify_de_bundle
from bionexus.de_pilot import demo_inputs, summarize_reviews, write_bundle

ROOT = Path(__file__).resolve().parents[2]
LEGACY = ROOT / "tests/fixtures/de_bundle_legacy_v1"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def save(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


@pytest.fixture
def bundle(tmp_path):
    return write_bundle(audit_differential_expression(**demo_inputs()), tmp_path / "new",
                        inputs={}, claim="synthetic", synthetic=True)


def assert_result_schema(result):
    schema = read(ROOT / "src/bionexus/data/de-bundle-verification.schema.json")
    jsonschema.Draft202012Validator(schema).validate(result)


def test_frozen_legacy_bytes_read_only_and_limited():
    before = {p.name: p.read_bytes() for p in LEGACY.iterdir()}
    expected = read(LEGACY / "FIXTURE.json")["sha256"]
    for name, digest in expected.items():
        assert hashlib.sha256(before[name]).hexdigest() == digest
    result = verify_de_bundle(LEGACY)
    assert result["status"] == "LEGACY_LIMITED"
    assert result["checked_artifacts"] == ["audit.json"]
    assert result["scientific_authorization"] == "NONE"
    assert before == {p.name: p.read_bytes() for p in LEGACY.iterdir()}
    assert_result_schema(result)


def test_new_writer_and_old_reader_contract(bundle):
    manifest = read(bundle / "manifest.json")
    jsonschema.Draft202012Validator(read(ROOT / "src/bionexus/data/de-shadow-bundle.schema.json")).validate(manifest)
    # The previous reader's required schema and byte digest remain unchanged.
    assert manifest["schema"] == "bionexus.de-shadow-bundle.v1"
    assert hashlib.sha256((bundle / "audit.json").read_bytes()).hexdigest() == manifest["audit_sha256"]
    result = verify_de_bundle(bundle)
    assert result["status"] == "CONSISTENT"
    assert result["audit_status"] == "NEEDS_REVISION"
    assert result["scientific_authorization"] == "NONE"
    assert result["analysis_execution_verification"] == "NOT_PERFORMED"
    assert result["producer_authentication"] == "NOT_ESTABLISHED"
    assert_result_schema(result)


@pytest.mark.parametrize("name", ["audit.json", "audit-full.md", "REVIEW.md"])
def test_any_changed_immutable_file_rejected(bundle, name):
    with (bundle / name).open("ab") as stream:
        stream.write(b"\nChanged after review\n")
    result = verify_de_bundle(bundle)
    assert result["status"] == "INVALID"
    assert result["issues"][0]["artifact"] == name
    assert_result_schema(result)
    with pytest.raises(ValueError, match="integrity"):
        summarize_reviews([bundle / "review.json"])


def test_mutable_review_does_not_change_immutable_verdict(bundle):
    review = read(bundle / "review.json")
    review["reviewer_note"] = "An unresolved issue, entered by a human"
    save(bundle / "review.json", review)
    result = verify_de_bundle(bundle)
    assert result["status"] == "CONSISTENT"
    assert result["mutable_reviews"] == "NOT_VERIFIED"


@pytest.mark.parametrize("field,value,expected", [
    ("schema", "bionexus.de-shadow-bundle.v2", "UNSUPPORTED_SCHEMA"),
    ("schema", {}, "UNSUPPORTED_SCHEMA"),
    ("integrity_profile", "future", "UNSUPPORTED_SCHEMA"),
    ("integrity_profile", [], "UNSUPPORTED_SCHEMA"),
    ("scientific_authorization", "APPROVED", "INVALID"),
    ("data_origin", {}, "INVALID"),
    ("immutable_artifacts", {"../outside": "0" * 64}, "INVALID"),
    ("immutable_artifacts", None, "INVALID"),
])
def test_untrusted_manifest_has_no_new_authority(bundle, field, value, expected):
    manifest = read(bundle / "manifest.json")
    manifest[field] = value
    save(bundle / "manifest.json", manifest)
    result = verify_de_bundle(bundle)
    assert result["status"] == expected
    assert result["scientific_authorization"] == "NONE"
    assert_result_schema(result)


def test_additive_metadata_is_ignored(bundle):
    manifest = read(bundle / "manifest.json")
    manifest["future_context"] = {"note": "no extra authority"}
    save(bundle / "manifest.json", manifest)
    assert verify_de_bundle(bundle)["status"] == "CONSISTENT"


def test_rewriting_hashes_requires_external_anchor_to_detect(bundle):
    anchor = hashlib.sha256((bundle / "manifest.json").read_bytes()).hexdigest()
    assert verify_de_bundle(bundle, expected_manifest_sha256=anchor)["manifest_anchor"] == "MATCHED"
    with (bundle / "REVIEW.md").open("ab") as stream:
        stream.write(b"Changed")
    manifest = read(bundle / "manifest.json")
    manifest["immutable_artifacts"]["REVIEW.md"] = hashlib.sha256((bundle / "REVIEW.md").read_bytes()).hexdigest()
    save(bundle / "manifest.json", manifest)
    assert verify_de_bundle(bundle)["status"] == "CONSISTENT"  # Self-consistency alone is not authentication.
    result = verify_de_bundle(bundle, expected_manifest_sha256=anchor)
    assert result["status"] == "INVALID" and result["manifest_anchor"] == "MISMATCH"


def test_removing_new_fields_never_produces_full_verification(bundle):
    manifest = read(bundle / "manifest.json")
    del manifest["immutable_artifacts"]
    save(bundle / "manifest.json", manifest)
    assert verify_de_bundle(bundle)["status"] == "INVALID"
    del manifest["integrity_profile"]
    save(bundle / "manifest.json", manifest)
    assert verify_de_bundle(bundle)["status"] == "LEGACY_LIMITED"
    assert summarize_reviews([bundle / "review.json"])["cases"][0]["bundle_integrity"] == "LEGACY_LIMITED"


@pytest.mark.parametrize("payload", ['{"schema":"x","schema":"y"}', '{"number":NaN}', '{"number":1e999}', '[]'])
def test_ambiguous_json_rejected(bundle, payload):
    (bundle / "manifest.json").write_text(payload, encoding="utf-8")
    result = verify_de_bundle(bundle)
    assert result["status"] == "INVALID"
    assert result["issues"][0]["code"] == "INVALID_JSON"


@pytest.mark.parametrize("status,passed", [("FUTURE_SUCCESS", True), ("NEEDS_DATA", True), ("ROBUST_PASS", 1)])
def test_unknown_or_contradictory_audit_is_not_success(bundle, status, passed):
    audit = read(bundle / "audit.json")
    audit.update(overall_status=status, passed=passed)
    save(bundle / "audit.json", audit)
    manifest = read(bundle / "manifest.json")
    manifest["audit_sha256"] = manifest["immutable_artifacts"]["audit.json"] = hashlib.sha256((bundle / "audit.json").read_bytes()).hexdigest()
    save(bundle / "manifest.json", manifest)
    result = verify_de_bundle(bundle)
    assert result["status"] in {"UNSUPPORTED_SCHEMA", "INVALID"}
    assert_result_schema(result)


def test_bounded_reader_and_missing_file(bundle):
    (bundle / "REVIEW.md").unlink()
    assert verify_de_bundle(bundle)["issues"][0]["code"] == "MISSING_ARTIFACT"
    with (bundle / "REVIEW.md").open("wb") as stream:
        stream.truncate(MAX_ARTIFACT_BYTES + 1)
    assert verify_de_bundle(bundle)["issues"][0]["code"] == "ARTIFACT_TOO_LARGE"


def test_symlink_cannot_escape_bundle(bundle, tmp_path):
    outside = tmp_path / "outside.md"
    shutil.copyfile(bundle / "REVIEW.md", outside)
    (bundle / "REVIEW.md").unlink()
    try:
        (bundle / "REVIEW.md").symlink_to(outside)
    except OSError:
        pytest.skip("Creating symlinks is unavailable on this host")
    assert verify_de_bundle(bundle)["issues"][0]["code"] == "UNSAFE_ARTIFACT"


def test_cli_and_dependency_free_reader(bundle, capsys):
    assert main(["audit-de-verify", str(bundle)]) == 0
    assert json.loads(capsys.readouterr().out)["scientific_authorization"] == "NONE"
    assert main(["audit-de-verify", str(LEGACY)]) == 3
    capsys.readouterr()
    run = subprocess.run([sys.executable, "-S", str(ROOT / "src/bionexus/de_bundle.py"), str(LEGACY)],
                         capture_output=True, text=True, check=False)
    assert run.returncode == 3, run.stderr
    assert json.loads(run.stdout)["status"] == "LEGACY_LIMITED"
