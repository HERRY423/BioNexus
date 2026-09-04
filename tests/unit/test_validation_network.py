import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from jsonschema import Draft202012Validator

from bionexus.trust_evidence import (
    EvidenceSubject,
    TrustKey,
    TrustRegistry,
    create_attestation,
    public_key_id,
    sha256_file,
)
from bionexus.validation_network import append_packet, compute_state_from_log, verify_log

NOW = datetime(2026, 8, 31, tzinfo=timezone.utc)


def _key(signer_id: str, predicates: tuple[str, ...]):
    private = Ed25519PrivateKey.generate()
    public = private.public_key()
    pem = public.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")
    key_id = public_key_id(public)
    return private, TrustKey(key_id, signer_id, pem, "2026-01-01T00:00:00Z", None, "ACTIVE", predicates)


def _packet(tmp_path, *, event_id="VN-001", event_type="EXTERNAL_LAB_REPLICATION", result="PASS"):
    evidence_path = tmp_path / f"{event_id}-evidence.json"
    evidence_path.write_text('{"observed":"result"}\n', encoding="utf-8")
    packet = {
        "schema_version": "bionexus.validation-event-packet.v1",
        "event_id": event_id,
        "event_type": event_type,
        "subject": {"project_id": "outside-project", "capability_id": "cap.x", "artifact_sha256": "a" * 64},
        "issuer": {
            "issuer_id": "scientist@example.org",
            "institution_id": "independent-lab",
            "relationship_to_subject": "INDEPENDENT",
        },
        "bns_release": "0.1.0",
        "bctk_release": "0.3.0",
        "profile_ids": ["BNS-Warrant"],
        "result": result,
        "evidence": {
            "artifact_uri": evidence_path.as_uri(),
            "artifact_sha256": sha256_file(evidence_path),
            "dataset_sha256": "b" * 64,
            "host_ids": ["host-a", "host-b"] if event_type == "CROSS_HOST_COMPARISON" else [],
        },
        "occurred_at": "2026-08-30T00:00:00Z",
    }
    packet_path = tmp_path / f"{event_id}.json"
    packet_path.write_text(json.dumps(packet, sort_keys=True), encoding="utf-8")
    return packet, packet_path, evidence_path


def _attestations(packet, packet_path):
    issuer_private, issuer_key = _key("scientist@example.org", ("bns-validation-event",))
    assessor_private, assessor_key = _key("assessor@example.net", ("bns-independence-assessment",))
    subject = EvidenceSubject(
        "bns-validation-event-packet", packet["event_id"], packet["schema_version"], packet_path.as_uri(), sha256_file(packet_path)
    )
    issuer = create_attestation(
        attestation_id=f"att-{packet['event_id']}", predicate_type="bns-validation-event", subject=subject,
        scope={"profile_ids": packet["profile_ids"]}, claims={"result": packet["result"]},
        issued_at="2026-08-30T01:00:00Z", expires_at=None, signer_id="scientist@example.org",
        key_id=issuer_key.key_id, private_key=issuer_private,
    )
    independence = create_attestation(
        attestation_id=f"ind-{packet['event_id']}", predicate_type="bns-independence-assessment", subject=subject,
        scope={"event_id": packet["event_id"]},
        claims={"relationship_to_subject": "INDEPENDENT", "issuer_id": "scientist@example.org"},
        issued_at="2026-08-30T02:00:00Z", expires_at=None, signer_id="assessor@example.net",
        key_id=assessor_key.key_id, private_key=assessor_private,
    )
    registry = TrustRegistry(
        keys={issuer_key.key_id: issuer_key, assessor_key.key_id: assessor_key},
        status="TEST_TRUST_ANCHORS",
    )
    return issuer, independence, registry


def test_dual_attested_event_is_append_only_and_state_is_derived(tmp_path):
    packet, packet_path, evidence_path = _packet(tmp_path)
    schema_path = (
        Path(__file__).resolve().parents[2]
        / "standards/validation-transparency-network/validation-event-packet.schema.json"
    )
    Draft202012Validator(json.loads(schema_path.read_text(encoding="utf-8"))).validate(packet)
    issuer, independence, registry = _attestations(packet, packet_path)
    log_path = tmp_path / "validation.jsonl"
    event = append_packet(
        log_path, packet_path, evidence_artifact_path=evidence_path, issuer_attestation=issuer,
        independence_attestation=independence, trust_registry=registry, at_time=NOW,
    )
    events, errors = verify_log(
        log_path, expected_head=event["event_hash"], trust_registry=registry, at_time=NOW
    )
    assert errors == []
    state = compute_state_from_log(
        log_path, trust_registry=registry, expected_head=event["event_hash"], at_time=NOW
    )
    assert state["candidate_slot_counts"]["independent_datasets"] == 1
    assert state["candidate_slot_counts"]["external_labs"] == 1
    assert state["certification_status"] == "NOT_ASSESSED"
    assert state["verified_log_head"] == event["event_hash"]


def test_tampered_packet_is_rejected_by_artifact_binding(tmp_path):
    packet, packet_path, evidence_path = _packet(tmp_path)
    issuer, independence, registry = _attestations(packet, packet_path)
    packet["result"] = "FAIL"
    packet_path.write_text(json.dumps(packet, sort_keys=True), encoding="utf-8")
    with pytest.raises(ValueError, match="issuer attestation not verified: ARTIFACT_MISMATCH"):
        append_packet(
            tmp_path / "validation.jsonl", packet_path, evidence_artifact_path=evidence_path,
            issuer_attestation=issuer,
            independence_attestation=independence, trust_registry=registry, at_time=NOW,
        )


def test_tampered_evidence_artifact_is_rejected(tmp_path):
    packet, packet_path, evidence_path = _packet(tmp_path)
    issuer, independence, registry = _attestations(packet, packet_path)
    evidence_path.write_text('{"observed":"changed"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="evidence artifact SHA-256"):
        append_packet(
            tmp_path / "validation.jsonl", packet_path, evidence_artifact_path=evidence_path,
            issuer_attestation=issuer, independence_attestation=independence,
            trust_registry=registry, at_time=NOW,
        )


def test_self_assessed_independence_is_rejected(tmp_path):
    packet, packet_path, evidence_path = _packet(tmp_path)
    issuer, _, registry = _attestations(packet, packet_path)
    with pytest.raises(ValueError, match="independence assessor must differ"):
        append_packet(
            tmp_path / "validation.jsonl", packet_path, evidence_artifact_path=evidence_path,
            issuer_attestation=issuer,
            independence_attestation=issuer, trust_registry=registry, at_time=NOW,
        )


def test_truncated_mirror_is_detected_with_external_head(tmp_path):
    packet, packet_path, evidence_path = _packet(tmp_path)
    issuer, independence, registry = _attestations(packet, packet_path)
    log_path = tmp_path / "validation.jsonl"
    event = append_packet(
        log_path, packet_path, evidence_artifact_path=evidence_path, issuer_attestation=issuer,
        independence_attestation=independence, trust_registry=registry, at_time=NOW,
    )
    log_path.write_text("", encoding="utf-8")
    _, errors = verify_log(log_path, expected_head=event["event_hash"])
    assert "log head does not match external expected_head" in errors


def test_connector_conformance_execution_event(tmp_path):
    """Verifies that CONNECTOR_CONFORMANCE_EXECUTION packets are validated, appended, and reduced into state."""
    evidence_path = tmp_path / "connector-evidence.json"
    evidence_path.write_text('{"connector_bctk_score": 1.0}\n', encoding="utf-8")
    packet = {
        "schema_version": "bionexus.validation-event-packet.v1",
        "event_id": "VN-CONN-001",
        "event_type": "CONNECTOR_CONFORMANCE_EXECUTION",
        "subject": {
            "project_id": "external-connector-repo",
            "capability_id": "bioactivity.affinity_audit",
            "artifact_sha256": "c" * 64,
        },
        "issuer": {
            "issuer_id": "scientist@example.org",
            "institution_id": "independent-lab",
            "relationship_to_subject": "INDEPENDENT",
        },
        "bns_release": "0.1.0",
        "bctk_release": "0.3.0",
        "profile_ids": ["BNS-Connector"],
        "result": "PASS",
        "evidence": {
            "artifact_uri": evidence_path.as_uri(),
            "artifact_sha256": sha256_file(evidence_path),
            "connector_id": "chembl-mcp-v1",
        },
        "occurred_at": "2026-08-30T00:00:00Z",
    }
    schema_path = (
        Path(__file__).resolve().parents[2]
        / "standards/validation-transparency-network/validation-event-packet.schema.json"
    )
    Draft202012Validator(json.loads(schema_path.read_text(encoding="utf-8"))).validate(packet)
    packet_path = tmp_path / "VN-CONN-001.json"
    packet_path.write_text(json.dumps(packet, sort_keys=True), encoding="utf-8")

    issuer, independence, registry = _attestations(packet, packet_path)
    log_path = tmp_path / "connector_validation.jsonl"
    event = append_packet(
        log_path,
        packet_path,
        evidence_artifact_path=evidence_path,
        issuer_attestation=issuer,
        independence_attestation=independence,
        trust_registry=registry,
        at_time=NOW,
    )
    assert event["event_hash"].startswith("sha256:")

    state = compute_state_from_log(log_path, trust_registry=registry, expected_head=event["event_hash"], at_time=NOW)
    assert state["candidate_slot_counts"]["connector_conformance_runs"] == 1
    assert state["candidate_slot_counts"]["validated_connectors"] == 1
    assert state["certification_status"] == "NOT_ASSESSED"
