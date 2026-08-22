from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timezone

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from bionexus.trust_cli import main as trust_cli_main
from bionexus.trust_evidence import (
    EvidenceSubject,
    TrustDecision,
    TrustKey,
    TrustRegistry,
    create_attestation,
    create_revocation,
    public_key_id,
    sha256_file,
    verify_attestation,
)


def _fixture(tmp_path):
    artifact = tmp_path / "review.json"
    artifact.write_text('{"decision":"supported"}', encoding="utf-8")
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    key_id = public_key_id(public_key)
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")
    key = TrustKey(
        key_id=key_id,
        signer_id="review-board:test-only",
        public_key_pem=public_pem,
        valid_from="2026-01-01T00:00:00+00:00",
        valid_until="2027-01-01T00:00:00+00:00",
        allowed_predicates=("scientific-review", "revocation"),
    )
    registry = TrustRegistry(keys={key_id: key}, status="TEST_FIXTURE")
    attestation = create_attestation(
        attestation_id="att:test:001",
        predicate_type="scientific-review",
        subject=EvidenceSubject(
            subject_type="rule-review",
            subject_id="rule:test",
            version="1.0.0",
            artifact_uri="review.json",
            artifact_sha256=sha256_file(artifact),
        ),
        scope={"regime": "test-only"},
        claims={"review_status": "approved-for-test"},
        issued_at="2026-08-01T00:00:00+00:00",
        expires_at="2026-12-01T00:00:00+00:00",
        signer_id=key.signer_id,
        key_id=key_id,
        private_key=private_key,
    )
    return artifact, private_key, registry, attestation


def test_verified_attestation_is_bound_to_artifact(tmp_path):
    artifact, _, registry, attestation = _fixture(tmp_path)
    result = verify_attestation(
        attestation,
        registry,
        artifact_path=artifact,
        at_time=datetime(2026, 8, 2, tzinfo=timezone.utc),
    )
    assert result.decision == TrustDecision.VERIFIED
    assert result.accepted is True


def test_missing_or_changed_artifact_fails_closed(tmp_path):
    artifact, _, registry, attestation = _fixture(tmp_path)
    no_bytes = verify_attestation(attestation, registry, at_time=datetime(2026, 8, 2, tzinfo=timezone.utc))
    assert no_bytes.decision == TrustDecision.NOT_ASSESSED
    artifact.write_text("tampered", encoding="utf-8")
    changed = verify_attestation(
        attestation,
        registry,
        artifact_path=artifact,
        at_time=datetime(2026, 8, 2, tzinfo=timezone.utc),
    )
    assert changed.decision == TrustDecision.ARTIFACT_MISMATCH


def test_payload_tampering_invalidates_signature(tmp_path):
    artifact, _, registry, attestation = _fixture(tmp_path)
    tampered = replace(attestation, claims={"review_status": "different"})
    result = verify_attestation(
        tampered,
        registry,
        artifact_path=artifact,
        at_time=datetime(2026, 8, 2, tzinfo=timezone.utc),
    )
    assert result.decision == TrustDecision.INVALID_SIGNATURE


def test_signed_revocation_blocks_attestation(tmp_path):
    artifact, private_key, registry, attestation = _fixture(tmp_path)
    registry.revocations.append(
        create_revocation(
            revocation_id="rev:test:001",
            target_type="attestation",
            target_id=attestation.attestation_id,
            reason="test withdrawal",
            revoked_at="2026-08-02T00:00:00+00:00",
            signer_id=attestation.signer_id,
            key_id=attestation.key_id,
            private_key=private_key,
        )
    )
    result = verify_attestation(
        attestation,
        registry,
        artifact_path=artifact,
        at_time=datetime(2026, 8, 3, tzinfo=timezone.utc),
    )
    assert result.decision == TrustDecision.REVOKED


def test_signed_key_revocation_blocks_all_key_attestations(tmp_path):
    artifact, private_key, registry, attestation = _fixture(tmp_path)
    registry.revocations.append(
        create_revocation(
            revocation_id="rev:test:key-001",
            target_type="key",
            target_id=attestation.key_id,
            reason="test key compromise",
            revoked_at="2026-08-02T00:00:00+00:00",
            signer_id=attestation.signer_id,
            key_id=attestation.key_id,
            private_key=private_key,
        )
    )
    result = verify_attestation(
        attestation,
        registry,
        artifact_path=artifact,
        at_time=datetime(2026, 8, 3, tzinfo=timezone.utc),
    )
    assert result.decision == TrustDecision.REVOKED


def test_untrusted_key_and_expiry_are_not_accepted(tmp_path):
    artifact, _, registry, attestation = _fixture(tmp_path)
    assert verify_attestation(attestation, TrustRegistry(), artifact_path=artifact).decision == TrustDecision.UNTRUSTED_KEY
    expired = verify_attestation(
        attestation,
        registry,
        artifact_path=artifact,
        at_time=datetime(2027, 1, 2, tzinfo=timezone.utc),
    )
    assert expired.decision == TrustDecision.EXPIRED


def test_cli_default_registry_trusts_nobody(tmp_path, capsys):
    artifact, _, _, attestation = _fixture(tmp_path)
    attestation_path = tmp_path / "attestation.json"
    attestation_path.write_text(json.dumps(attestation.to_dict()), encoding="utf-8")
    assert trust_cli_main([str(attestation_path), "--artifact", str(artifact)]) == 2
    output = json.loads(capsys.readouterr().out)
    assert output["decision"] == "UNTRUSTED_KEY"
    assert output["accepted"] is False
