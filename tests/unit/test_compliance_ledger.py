"""Unit tests for BioNexus 21 CFR Part 11 & GxP Compliance Ledger (BNS-COMP-001)."""

from bionexus.compliance_ledger import (
    ActionType,
    ComplianceAuditLedger,
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
    assert sig.schema_version == "bionexus.electronic-signature.v1"
    assert sig.signer_name == "Dr. Eleanor Vance"
    assert sig.signature_hash.startswith("sha256:")

    valid, reason = ledger.verify_signature(sig, artifact_content)
    assert valid is True
    assert reason is None

    tampered_content = b"FLAGSHIP_REPORT_DATA_MOCK_TP53_TAMPERED"
    valid, reason = ledger.verify_signature(sig, tampered_content)
    assert valid is False
    assert "Artifact SHA-256 mismatch" in reason


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
