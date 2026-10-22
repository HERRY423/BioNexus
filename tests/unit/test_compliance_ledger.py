"""Unit tests for BioNexus 21 CFR Part 11 & GxP Compliance Ledger (BNS-COMP-001)."""

import dataclasses
import hashlib

from bionexus.compliance_ledger import (
    ActionType,
    ComplianceAuditLedger,
    ElectronicSignature,
    RBACController,
    UserRole,
)


def test_rbac_permissions():
    assert RBACController.is_authorized(UserRole.GUEST_VIEWER, ActionType.VIEW_DATA) is True
    assert RBACController.is_authorized(UserRole.GUEST_VIEWER, ActionType.EXECUTE_PIPELINE) is False
    assert RBACController.is_authorized(UserRole.GUEST_VIEWER, ActionType.ELECTRONIC_SIGN) is False

    assert RBACController.is_authorized(UserRole.RESEARCHER, ActionType.EXECUTE_PIPELINE) is True
    assert RBACController.is_authorized(UserRole.RESEARCHER, ActionType.ELECTRONIC_SIGN) is False

    assert RBACController.is_authorized(UserRole.PI_SIGNER, ActionType.ELECTRONIC_SIGN) is True
    assert RBACController.is_authorized(UserRole.QA_AUDITOR, ActionType.REVOKE_SIGNATURE) is True


def test_electronic_signature_and_verification():
    ledger = ComplianceAuditLedger()
    artifact_content = b"FLAGSHIP_REPORT_DATA_MOCK_TP53"

    sig = ledger.sign_artifact(
        signer_name="Dr. Eleanor Vance",
        signer_email="e.vance@genentech.com",
        signer_role=UserRole.PI_SIGNER,
        signing_reason="APPROVAL_OF_CANDIDATE_TARGET",
        artifact_path_or_bytes=artifact_content,
    )
    assert sig.schema_version == "bionexus.electronic-signature.v2"
    assert sig.signer_name == "Dr. Eleanor Vance"
    assert sig.signature_hash.startswith("sha256:")
    assert sig.signature_algorithm == "ed25519"
    assert sig.public_key_pem.startswith("-----BEGIN PUBLIC KEY-----")
    assert len(sig.signature_bytes_b64) > 0
    assert sig.tsa_timestamp_token is not None

    valid, reason = ledger.verify_signature(sig, artifact_content)
    assert valid is True
    assert reason is None

    tampered_content = b"FLAGSHIP_REPORT_DATA_MOCK_TP53_TAMPERED"
    valid, reason = ledger.verify_signature(sig, tampered_content)
    assert valid is False
    assert "Artifact SHA-256 mismatch" in reason


def test_ed25519_pki_explicit_key_and_tamper_defense():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ed25519

    ledger = ComplianceAuditLedger()
    artifact_content = b"GENOMIC_VARIANT_EVIDENCE_BRCA1"

    # Generate dedicated keypairs
    signer_priv = ed25519.Ed25519PrivateKey.generate()
    signer_pub_pem = signer_priv.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")

    tsa_priv = ed25519.Ed25519PrivateKey.generate()
    tsa_pub_pem = tsa_priv.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")

    sig = ledger.sign_artifact(
        signer_name="Dr. Alice Smith",
        signer_email="a.smith@institute.org",
        signer_role=UserRole.PI_SIGNER,
        signing_reason="VALIDATION_OF_TARGET",
        artifact_path_or_bytes=artifact_content,
        private_key=signer_priv,
        tsa_private_key=tsa_priv,
    )

    # 1. Successful verification with explicit public key and TSA key
    valid, reason = ledger.verify_signature(
        sig,
        artifact_content,
        expected_public_key_pem=signer_pub_pem,
        tsa_public_key_pem=tsa_pub_pem,
    )
    assert valid is True
    assert reason is None

    # 2. Reject mismatched public key
    wrong_key = ed25519.Ed25519PrivateKey.generate()
    wrong_pub_pem = wrong_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")
    valid_wrong, reason_wrong = ledger.verify_signature(
        sig,
        artifact_content,
        expected_public_key_pem=wrong_pub_pem,
    )
    assert valid_wrong is False
    assert "Signer public key mismatch" in reason_wrong

    # 3. Reject tampered signature bytes
    sig_tampered = dataclasses.replace(sig, signature_bytes_b64="AAAA" + sig.signature_bytes_b64[4:])
    valid_sig_tamp, reason_sig_tamp = ledger.verify_signature(sig_tampered, artifact_content)
    assert valid_sig_tamp is False

    # 4. Reject tampered metadata (e.g. modifying signer name while retaining signature hash)
    sig_metadata_tamp = dataclasses.replace(sig, signer_name="Attacker Impersonator")
    valid_meta, reason_meta = ledger.verify_signature(sig_metadata_tamp, artifact_content)
    assert valid_meta is False
    assert "Signature hash corrupted" in reason_meta


def test_legacy_v1_signature_compatibility():
    ledger = ComplianceAuditLedger()
    artifact_content = b"LEGACY_DATASET"

    # Simulate legacy v1 signature (no PKI fields)
    sig_v1 = ElectronicSignature(
        schema_version="bionexus.electronic-signature.v1",
        signature_id="sig_legacy_001",
        signer_name="Legacy Signer",
        signer_email="legacy@lab.org",
        signer_role=UserRole.PI_SIGNER.value,
        signing_reason="LEGACY_AUDIT",
        target_artifact_sha256=f"sha256:{hashlib.sha256(artifact_content).hexdigest()}",
        timestamp_utc="2025-01-01T00:00:00Z",
    )
    sig_v1.signature_hash = f"sha256:{sig_v1.compute_signature_hash()}"

    valid, reason = ledger.verify_signature(sig_v1, artifact_content)
    assert valid is True
    assert "LEGACY_HASH_ONLY" in reason
    assert ledger.verify_signature_assessment(sig_v1, artifact_content)["status"] == "LEGACY_HASH_ONLY"


def test_gxp_audit_trail_hash_chain():
    ledger = ComplianceAuditLedger()

    e1 = ledger.append_audit_entry("user1@lab.org", UserRole.RESEARCHER, ActionType.EXECUTE_PIPELINE, "study_001")
    e2 = ledger.append_audit_entry("user2@lab.org", UserRole.BIOINFORMATICIAN, ActionType.OVERRIDE_CONSTRAINT, "rule_004")
    e3 = ledger.append_audit_entry("pi@lab.org", UserRole.PI_SIGNER, ActionType.ELECTRONIC_SIGN, "cert_001")

    assert len(ledger.entries) == 3
    assert e2.previous_entry_hash == e1.entry_hash
    assert e3.previous_entry_hash == e2.entry_hash

    ok, issues = ledger.verify_ledger_integrity()
    assert ok is True
    assert len(issues) == 0

    ledger.entries[1].target_resource = "tampered_resource"
    ok_tampered, issues_tampered = ledger.verify_ledger_integrity()
    assert ok_tampered is False
    assert len(issues_tampered) > 0
