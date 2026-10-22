"""Content-bound positive controls and attacks on signature/run evidence boundaries.

Synthetic engineering fixtures; no external identity or scientific approval.
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import replace
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from nf_prov_crate_util import write_nf_prov_crate

from bionexus.compliance_ledger import ComplianceAuditLedger, UserRole
from bionexus.ledger import ClaimLedger, ClaimRecord, EvidenceRef
from bionexus.nf_runtime import (
    build_nextflow_execution_binding,
    run_nextflow_gated,
    warrant_nextflow_run,
)
from bionexus.verification import verify_ledger, verify_results, write_example_ledger
from bionexus.wrroc import ingest_wrroc_crate


def _public_key(private):
    return private.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")


def _signature():
    audit = ComplianceAuditLedger()
    signature = audit.sign_artifact(
        "Fixture operator", "operator@example.invalid", UserRole.PI_SIGNER,
        "TEST_CONTENT_BINDING_ONLY", b"artifact", include_tsa_token=False,
    )
    return audit, signature


@pytest.mark.parametrize("field", [
    "schema_version", "signature_bytes_b64", "public_key_pem", "key_id",
    "signature_algorithm", "timestamp_utc",
])
@pytest.mark.parametrize("action", ["remove", "empty"])
def test_v2_crypto_fields_cannot_be_removed_or_emptied(field, action):
    audit, signature = _signature()
    payload = signature.to_dict()
    if action == "remove":
        payload.pop(field)
    else:
        payload[field] = ""
    assert audit.verify_signature(payload, b"artifact")[0] is False
    assert audit.verify_signature(payload, b"artifact", expected_public_key_pem="WRONG")[0] is False


def test_unknown_signature_schema_and_algorithm_rejected_even_with_recomputed_hash():
    audit, signature = _signature()
    for field, value in (("schema_version", "bionexus.electronic-signature.v900"),
                         ("signature_algorithm", "none")):
        changed = replace(signature, **{field: value})
        changed.signature_hash = "sha256:" + changed.compute_signature_hash()
        assert audit.verify_signature(changed, b"artifact")[0] is False


def test_legacy_downgrade_has_only_hash_status_and_cannot_satisfy_authority():
    audit, signature = _signature()
    legacy = replace(signature, schema_version="bionexus.electronic-signature.v1",
                     signature_bytes_b64="", public_key_pem="")
    legacy.signature_hash = "sha256:" + legacy.compute_signature_hash()
    result = audit.verify_signature_assessment(legacy, b"artifact")
    assert result["status"] == "LEGACY_HASH_ONLY"
    assert result["external_identity_trust"] == "NOT_ESTABLISHED"
    assert audit.verify_signature(legacy, b"artifact", expected_public_key_pem=signature.public_key_pem)[0] is False


def test_real_signature_passes_but_embedded_key_never_becomes_human_authority():
    audit, signature = _signature()
    result = audit.verify_signature_assessment(signature, b"artifact")
    assert result["status"] == "SIGNATURE_VALID_UNTRUSTED_KEY"
    trusted_key = audit.verify_signature_assessment(
        signature, b"artifact", expected_public_key_pem=signature.public_key_pem,
    )
    assert trusted_key["status"] == "SIGNATURE_VALID_EXPECTED_KEY"
    assert trusted_key["external_identity_trust"] == "NOT_ESTABLISHED"
    assert trusted_key["scientific_authorization"] == "NONE"


def test_required_timestamp_cannot_disappear():
    audit, signature = _signature()
    tsa_key = _public_key(ed25519.Ed25519PrivateKey.generate())
    assert audit.verify_signature(signature, b"artifact", tsa_public_key_pem=tsa_key)[0] is False
    assert audit.verify_signature(signature, b"artifact", require_tsa_token=True)[0] is False


def _ledger():
    ledger = ClaimLedger()
    ledger.add_evidence(EvidenceRef("E1", "statistical_result", "Observed association", "SUPPORTED"))
    ledger.add_claim(ClaimRecord("C1", "Signal is associated with response", supported_by=["E1"]))
    return ledger


def test_standard_verifier_checks_seal_without_mutating_valid_ledger(tmp_path):
    ledger = _ledger()
    signer = ed25519.Ed25519PrivateKey.generate()
    ledger.seal("Fixture operator", "operator@example.invalid", private_key=signer, include_tsa_token=False)
    before = copy.deepcopy(ledger.to_dict())
    report = verify_ledger(ledger)
    assert report.passed
    assert report.seal_status == "VALID_UNTRUSTED_KEY"
    assert report.to_dict()["external_identity_trust"] == "NOT_ESTABLISHED"
    assert ledger.to_dict() == before
    assert ledger.verify_seal()[0] is True
    path = ledger.save(tmp_path / "sealed.json")
    assert verify_results(path, expected_public_key_pem=_public_key(signer)).passed
    payload = json.loads(path.read_text())
    payload["claims"]["C1"]["statement"] = "A different association is observed"
    path.write_text(json.dumps(payload))
    report = verify_results(path)
    assert not report.passed
    assert report.seal_status == "INVALID"
    assert report.integrity_errors


@pytest.mark.parametrize("field,value", [
    ("schema_version", "unknown"), ("signature_algorithm", "none"),
    ("signature_bytes_b64", ""), ("key_id", "sha256:" + "0" * 64),
    ("timestamp_utc", ""),
])
def test_seal_schema_and_crypto_contract_fail_closed(field, value):
    ledger = _ledger()
    ledger.seal("Fixture operator", "operator@example.invalid", include_tsa_token=False)
    ledger.cryptographic_seal[field] = value
    assert not ledger.verify_seal()[0]
    assert not verify_ledger(ledger).passed


def test_unsealed_legacy_ledger_retains_explicit_low_evidence_ceiling():
    ledger = _ledger()
    report = verify_ledger(ledger)
    assert report.passed
    assert report.seal_status == "UNSEALED"
    assert report.to_dict()["verification_scope"] == "LEDGER_CONSISTENCY_ONLY"
    assert not verify_ledger(ledger, require_seal=True).passed
    ledger.cryptographic_seal = {}
    assert not verify_ledger(ledger).passed


def test_duplicate_ledger_keys_and_mismatched_record_ids_rejected(tmp_path):
    path = tmp_path / "ledger.json"
    path.write_text('{"claims": {}, "claims": {}, "evidence": {}}')
    with pytest.raises(ValueError, match="Duplicate"):
        verify_results(path)
    payload = _ledger().to_dict()
    payload["claims"]["C1"]["claim_id"] = "OTHER"
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="claim_id"):
        verify_results(path)


def _mock_official_validator(monkeypatch):
    # Mock only executable discovery and subprocess boundary, exercising the
    # real wrapper's command, exit status and mandatory success marker checks.
    monkeypatch.setattr("bionexus.roc_validator.discover_rocrate_validator", lambda: "fixture-validator")
    monkeypatch.setattr("bionexus.roc_validator._installed_package_version", lambda: "0.11.2")
    monkeypatch.setattr("bionexus.roc_validator.subprocess.run", lambda *a, **k: SimpleNamespace(
        returncode=0, stdout="RO-Crate is a valid provenance-run-crate-0.5", stderr="",
    ))


def _bound_run(tmp_path, monkeypatch):
    _mock_official_validator(monkeypatch)
    run = tmp_path / "run"
    crate = write_nf_prov_crate(run)
    subject = run / "subject_manifest.csv"
    subject.write_bytes(b"sample,condition\nS1,control\nS2,treatment\n")
    doc = json.loads(crate.read_text())
    doc["@graph"].append({
        "@id": subject.name, "@type": "File", "sha256": hashlib.sha256(subject.read_bytes()).hexdigest(),
    })
    for entity in doc["@graph"]:
        if entity["@id"] == "#workflow-run":
            entity["object"] = [{"@id": subject.name}]
    crate.write_text(json.dumps(doc))
    summary = ingest_wrroc_crate(crate, run_dir=run)
    binding = build_nextflow_execution_binding(summary, subject_artifact=subject.name)
    ledger = _ledger()
    ledger.claims["C1"].provenance["nextflow_execution_binding"] = copy.deepcopy(binding)
    output = "salmon.merged.gene_counts.tsv"
    ledger.evidence["E1"].provenance.update({
        "nextflow_execution_binding": copy.deepcopy(binding),
        "artifact_path": output, "artifact_sha256": summary.primary_outputs[output],
    })
    ledger.seal("Fixture operator", "operator@example.invalid", include_tsa_token=False)
    path = ledger.save(run / "bionexus.ledger.json")
    return run, crate, ledger, path


def test_genuine_bound_successful_run_is_verified_without_scientific_authority(tmp_path, monkeypatch):
    run, _, _, path = _bound_run(tmp_path, monkeypatch)
    result = warrant_nextflow_run(run, ledger_path=path)
    assert result.warrant_status == "VERIFIED", result.notes
    assert result.exit_code == 0
    assert result.summary.artifact_integrity_status == "VERIFIED"
    assert result.verification.seal_status == "VALID_UNTRUSTED_KEY"
    assert result.to_dict()["scientific_authorization"] == "NONE"
    assert result.to_dict()["external_identity_trust"] == "NOT_ESTABLISHED"


@pytest.mark.parametrize("mutate", ["output", "input", "missing_output", "missing_producer_hash"])
def test_current_bytes_cannot_replace_original_producer_hash(tmp_path, monkeypatch, mutate):
    run, crate, _, path = _bound_run(tmp_path, monkeypatch)
    original = ingest_wrroc_crate(crate, run_dir=run)
    output = "salmon.merged.gene_counts.tsv"
    if mutate == "output":
        (run / output).write_bytes(b"CORRUPT")
    elif mutate == "input":
        (run / "subject_manifest.csv").write_bytes(b"DIFFERENT STUDY")
    elif mutate == "missing_output":
        (run / output).unlink()
    else:
        doc = json.loads(crate.read_text())
        next(e for e in doc["@graph"] if e["@id"] == output).pop("sha256")
        crate.write_text(json.dumps(doc))
    summary = ingest_wrroc_crate(crate, run_dir=run)
    assert summary.artifact_integrity_status != "VERIFIED"
    if mutate == "output":
        assert summary.primary_outputs[output] == original.primary_outputs[output]
        record = next(r for r in summary.artifact_integrity if r["path"] == output)
        assert record["status"] == "HASH_MISMATCH"
        assert record["observed_sha256"] != record["producer_sha256"]
    assert warrant_nextflow_run(run, ledger_path=path).warrant_status != "VERIFIED"


@pytest.mark.parametrize("field,value", [
    ("workflow_run_id", "#old-run"), ("crate_sha256", "0" * 64),
    ("pipeline_version", "another-version"), ("subject_sha256", "0" * 64),
    ("input_sha256", {}), ("output_sha256", {}),
])
def test_validly_resealed_wrong_execution_binding_is_rejected(tmp_path, monkeypatch, field, value):
    run, _, ledger, path = _bound_run(tmp_path, monkeypatch)
    ledger.claims["C1"].provenance["nextflow_execution_binding"][field] = value
    ledger.seal("Fixture operator", "operator@example.invalid", include_tsa_token=False)
    ledger.save(path)
    result = warrant_nextflow_run(run, ledger_path=path)
    assert result.warrant_status == "CLAIMS_REFUSED"
    assert any("binding differs" in note for note in result.notes)


def test_failed_crate_or_nonzero_runner_cannot_promote_even_good_ledger(tmp_path, monkeypatch):
    run, crate, _, path = _bound_run(tmp_path, monkeypatch)
    assert warrant_nextflow_run(run, ledger_path=path, observed_exit_code=1).warrant_status == "EXECUTION_NOT_SUCCESSFUL"
    doc = json.loads(crate.read_text())
    next(e for e in doc["@graph"] if e["@id"] == "#workflow-run")["actionStatus"] = {"@id": "FailedActionStatus"}
    crate.write_text(json.dumps(doc))
    result = warrant_nextflow_run(run, ledger_path=path)
    assert result.warrant_status == "EXECUTION_NOT_SUCCESSFUL"
    assert result.to_dict()["scientific_evidence_effect"] == "NONE"


def test_validator_unavailable_cannot_upgrade_bound_ledger(tmp_path, monkeypatch):
    run, _, _, path = _bound_run(tmp_path, monkeypatch)
    monkeypatch.setattr("bionexus.roc_validator.discover_rocrate_validator", lambda: None)
    result = warrant_nextflow_run(run, ledger_path=path)
    assert result.summary.official_validation_status == "VALIDATOR_UNAVAILABLE"
    assert result.warrant_status == "CLAIMS_REFUSED"


def test_unrelated_and_tampered_evidence_not_rescued_by_successful_crate(tmp_path, monkeypatch):
    run, _, ledger, path = _bound_run(tmp_path, monkeypatch)
    ledger.evidence["E1"].provenance["artifact_sha256"] = "0" * 64
    ledger.seal("Fixture operator", "operator@example.invalid", include_tsa_token=False)
    ledger.save(path)
    assert warrant_nextflow_run(run, ledger_path=path).warrant_status == "CLAIMS_REFUSED"
    write_example_ledger(path)
    assert warrant_nextflow_run(run, ledger_path=path).warrant_status == "CLAIMS_REFUSED"


def test_no_new_crate_cannot_be_reused_as_current_runner_execution(tmp_path, monkeypatch):
    run, _, _, path = _bound_run(tmp_path, monkeypatch)
    sheet = run / "subject_manifest.csv"
    result = run_nextflow_gated(
        pipeline="rnaseq", samplesheet=sheet, outdir=run, ledger_path=path,
        skip_scientific_preflight=True, runner=lambda _: 0,
    )
    assert result["warrant"]["warrant_status"] == "STALE_PROVENANCE"
    assert result["exit_code"] != 0
