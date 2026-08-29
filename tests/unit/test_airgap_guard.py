"""Unit tests for BioNexus Airgap & Zero-Egress DLP Guard (BNS-SEC-011)."""

from bionexus.airgap_guard import (
    AirgapNetworkGuard,
    AirgapPolicyMode,
    DLPScanner,
)


def test_dlp_scanner_detects_phi_and_keys():
    safe, entities, violations = DLPScanner.scan_payload({"gene": "TP53", "lfc": 2.5})
    assert safe is True
    assert len(violations) == 0

    safe, entities, violations = DLPScanner.scan_payload({"patient": "John", "ssn": "000-12-3456"})
    assert safe is False
    assert any("Social Security Number" in v for v in violations)

    safe, entities, violations = DLPScanner.scan_payload({"token": "ghp_123456789012345678901234567890123456"})
    assert safe is False
    assert any("API key" in v for v in violations)


def test_airgap_policy_strict():
    guard = AirgapNetworkGuard(mode=AirgapPolicyMode.AIRGAP_STRICT)

    permitted, reason, receipt = guard.evaluate_egress("http://127.0.0.1:8000/v1/models")
    assert permitted is True
    assert reason is None
    assert receipt["execution_status"] == "SUCCESS"

    permitted, reason, receipt = guard.evaluate_egress("http://vllm.internal/v1/chat")
    assert permitted is True

    permitted, reason, receipt = guard.evaluate_egress("https://api.openai.com/v1/chat/completions")
    assert permitted is False
    assert "AIRGAP_STRICT denies all external egress" in reason
    assert receipt["execution_status"] == "REJECTED"

    report = guard.get_summary_report()
    assert report["total_requests_inspected"] == 3
    assert report["requests_blocked"] == 1
    assert report["requests_permitted"] == 2
