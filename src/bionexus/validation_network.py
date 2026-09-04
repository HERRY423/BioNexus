"""BNS validation transparency event log.

The log is portable and mirrorable.  Admission requires two verified,
artifact-bound attestations: one from the event issuer and one from a distinct
independence assessor.  The resulting chain is tamper-evident, not proof that a
scientific claim is true and not a certification mechanism.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from bionexus.trust_evidence import (
    EvidenceAttestation,
    TrustDecision,
    TrustRegistry,
    sha256_file,
    verify_attestation,
)

NETWORK_SCHEMA = "bionexus.validation-transparency-event.v1"
PACKET_SCHEMA = "bionexus.validation-event-packet.v1"
GENESIS_HASH = "GENESIS"
_APPEND_LOCK = threading.Lock()

EVENT_TYPES = {
    "DATASET_EXECUTION",
    "EXTERNAL_LAB_REPLICATION",
    "NON_AUTHOR_REVIEW",
    "CROSS_HOST_COMPARISON",
    "CALIBRATION_FREEZE",
    "CONNECTOR_CONFORMANCE_EXECUTION",
    "CONNECTOR_BENCHMARK_EXECUTION",
    "REVOCATION",
}
RESULTS = {"PASS", "FAIL", "NEGATIVE", "INCONCLUSIVE", "NOT_ASSESSED"}
COUNTABLE_RESULTS = {"PASS", "FAIL", "NEGATIVE"}
SHA256_PREFIX = "sha256:"


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_json(value: Any) -> str:
    return SHA256_PREFIX + hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _valid_digest(value: object) -> bool:
    if not isinstance(value, str):
        return False
    raw = value.removeprefix(SHA256_PREFIX)
    if len(raw) != 64:
        return False
    try:
        int(raw, 16)
    except ValueError:
        return False
    return True


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamps must include a timezone")
    return parsed.astimezone(timezone.utc)


def validate_packet(packet: Mapping[str, Any]) -> tuple[str, ...]:
    errors: list[str] = []
    required = {
        "schema_version",
        "event_id",
        "event_type",
        "subject",
        "issuer",
        "bns_release",
        "bctk_release",
        "profile_ids",
        "result",
        "evidence",
        "occurred_at",
    }
    missing = sorted(required - set(packet))
    if missing:
        errors.append("missing fields: " + ", ".join(missing))
        return tuple(errors)
    if packet.get("schema_version") != PACKET_SCHEMA:
        errors.append("unsupported packet schema_version")
    if packet.get("event_type") not in EVENT_TYPES:
        errors.append("unsupported event_type")
    if packet.get("result") not in RESULTS:
        errors.append("unsupported result")
    if not isinstance(packet.get("profile_ids"), list) or not packet["profile_ids"]:
        errors.append("profile_ids must be a non-empty list")
    for section, fields in {
        "subject": ("project_id", "capability_id", "artifact_sha256"),
        "issuer": ("issuer_id", "institution_id", "relationship_to_subject"),
        "evidence": ("artifact_uri", "artifact_sha256"),
    }.items():
        value = packet.get(section)
        if not isinstance(value, Mapping):
            errors.append(f"{section} must be an object")
            continue
        for field in fields:
            if not value.get(field):
                errors.append(f"{section}.{field} is required")
    subject = packet.get("subject", {})
    evidence = packet.get("evidence", {})
    if isinstance(subject, Mapping) and not _valid_digest(subject.get("artifact_sha256")):
        errors.append("subject.artifact_sha256 must be SHA-256")
    if isinstance(evidence, Mapping) and not _valid_digest(evidence.get("artifact_sha256")):
        errors.append("evidence.artifact_sha256 must be SHA-256")
    issuer = packet.get("issuer", {})
    if isinstance(issuer, Mapping) and issuer.get("relationship_to_subject") not in {
        "INDEPENDENT",
        "SAME_TEAM",
        "UNKNOWN",
    }:
        errors.append("issuer.relationship_to_subject is invalid")
    try:
        _parse_time(str(packet.get("occurred_at")))
        if packet.get("expires_at"):
            _parse_time(str(packet["expires_at"]))
    except ValueError as exc:
        errors.append(str(exc))
    if packet.get("event_type") == "CROSS_HOST_COMPARISON":
        hosts = evidence.get("host_ids", []) if isinstance(evidence, Mapping) else []
        if not isinstance(hosts, list) or len(set(hosts)) < 2:
            errors.append("cross-host comparison requires at least two distinct host_ids")
    if packet.get("event_type") == "REVOCATION" and not packet.get("revokes"):
        errors.append("revocation event requires revokes")
    return tuple(errors)


def _event_hash(event: Mapping[str, Any]) -> str:
    return sha256_json({key: value for key, value in event.items() if key != "event_hash"})


def read_log(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    events: list[dict[str, Any]] = []
    errors: list[str] = []
    if not path.exists():
        return events, errors
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"line {line_number}: invalid JSON: {exc.msg}")
            continue
        if not isinstance(value, dict):
            errors.append(f"line {line_number}: event must be an object")
        else:
            events.append(value)
    return events, errors


def verify_log(
    path: Path,
    *,
    expected_head: str | None = None,
    trust_registry: TrustRegistry | None = None,
    at_time: datetime | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    events, errors = read_log(path)
    previous = GENESIS_HASH
    seen_ids: set[str] = set()
    for sequence, event in enumerate(events, 1):
        if event.get("schema_version") != NETWORK_SCHEMA:
            errors.append(f"event {sequence}: unsupported schema_version")
        if event.get("sequence") != sequence:
            errors.append(f"event {sequence}: sequence mismatch")
        if event.get("previous_event_hash") != previous:
            errors.append(f"event {sequence}: previous_event_hash mismatch")
        if event.get("event_hash") != _event_hash(event):
            errors.append(f"event {sequence}: event_hash mismatch")
        event_id = str(event.get("event_id", ""))
        if not event_id or event_id in seen_ids:
            errors.append(f"event {sequence}: missing or duplicate event_id")
        seen_ids.add(event_id)
        if trust_registry is not None:
            try:
                packet_bytes = base64.b64decode(str(event["packet_bytes_b64"]), validate=True)
                packet = json.loads(packet_bytes)
                if packet != event.get("packet"):
                    raise ValueError("embedded packet bytes do not match packet object")
                if SHA256_PREFIX + hashlib.sha256(packet_bytes).hexdigest() != event.get("packet_sha256"):
                    raise ValueError("packet_sha256 mismatch")
                issuer = EvidenceAttestation.from_dict(event["issuer_attestation"])
                independence = EvidenceAttestation.from_dict(event["independence_attestation"])
                _require_binding(issuer, packet, "issuer")
                if independence.signer_id == issuer.signer_id:
                    raise ValueError("independence assessor must differ from event issuer")
                _require_binding(independence, packet, "independence")
                issuer_result = verify_attestation(
                    issuer, trust_registry, artifact_bytes=packet_bytes, at_time=at_time
                )
                independence_result = verify_attestation(
                    independence, trust_registry, artifact_bytes=packet_bytes, at_time=at_time
                )
                if issuer_result.decision != TrustDecision.VERIFIED:
                    raise ValueError(f"issuer attestation is {issuer_result.decision.value}")
                if independence_result.decision != TrustDecision.VERIFIED:
                    raise ValueError(f"independence attestation is {independence_result.decision.value}")
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                errors.append(f"event {sequence}: attestation verification failed: {exc}")
        previous = str(event.get("event_hash", ""))
    if expected_head is not None and previous != expected_head:
        errors.append("log head does not match external expected_head")
    return events, errors


def _require_binding(attestation: EvidenceAttestation, packet: Mapping[str, Any], role: str) -> None:
    expected_predicate = "bns-validation-event" if role == "issuer" else "bns-independence-assessment"
    if attestation.predicate_type != expected_predicate:
        raise ValueError(f"{role} attestation predicate must be {expected_predicate}")
    if attestation.subject.subject_type != "bns-validation-event-packet":
        raise ValueError(f"{role} attestation subject_type mismatch")
    if attestation.subject.subject_id != packet.get("event_id"):
        raise ValueError(f"{role} attestation subject_id mismatch")


def append_packet(
    log_path: Path,
    packet_path: Path,
    *,
    evidence_artifact_path: Path,
    issuer_attestation: EvidenceAttestation,
    independence_attestation: EvidenceAttestation,
    trust_registry: TrustRegistry,
    at_time: datetime | None = None,
    transparency_receipt: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Verify a packet and two independent signatures, then append atomically."""
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    if not isinstance(packet, dict):
        raise ValueError("validation packet must be a JSON object")
    errors = validate_packet(packet)
    if errors:
        raise ValueError("invalid validation packet: " + "; ".join(errors))
    observed_evidence_digest = sha256_file(evidence_artifact_path)
    expected_evidence_digest = str(packet["evidence"]["artifact_sha256"]).removeprefix(SHA256_PREFIX)
    if observed_evidence_digest != expected_evidence_digest:
        raise ValueError("evidence artifact SHA-256 does not match the validation packet")
    _require_binding(issuer_attestation, packet, "issuer")
    if independence_attestation.signer_id == issuer_attestation.signer_id:
        raise ValueError("independence assessor must differ from event issuer")
    _require_binding(independence_attestation, packet, "independence")
    if issuer_attestation.signer_id != packet["issuer"]["issuer_id"]:
        raise ValueError("issuer attestation signer does not match packet issuer")
    if independence_attestation.claims.get("relationship_to_subject") != "INDEPENDENT":
        raise ValueError("independence attestation does not assess an INDEPENDENT relationship")
    if independence_attestation.claims.get("issuer_id") != packet["issuer"]["issuer_id"]:
        raise ValueError("independence attestation issuer binding mismatch")

    issuer_verification = verify_attestation(
        issuer_attestation, trust_registry, artifact_path=packet_path, at_time=at_time
    )
    independence_verification = verify_attestation(
        independence_attestation, trust_registry, artifact_path=packet_path, at_time=at_time
    )
    if issuer_verification.decision != TrustDecision.VERIFIED:
        raise ValueError(f"issuer attestation not verified: {issuer_verification.decision.value}")
    if independence_verification.decision != TrustDecision.VERIFIED:
        raise ValueError(f"independence attestation not verified: {independence_verification.decision.value}")

    log_path.parent.mkdir(parents=True, exist_ok=True)
    with _APPEND_LOCK:
        events, chain_errors = verify_log(log_path, trust_registry=trust_registry, at_time=at_time)
        if chain_errors:
            raise ValueError("refusing to append to invalid validation log: " + "; ".join(chain_errors))
        if any(item.get("event_id") == packet["event_id"] for item in events):
            raise ValueError("event_id already exists")
        event: dict[str, Any] = {
            "schema_version": NETWORK_SCHEMA,
            "sequence": len(events) + 1,
            "event_id": packet["event_id"],
            "packet": packet,
            "packet_sha256": SHA256_PREFIX + sha256_file(packet_path),
            "evidence_artifact_sha256": SHA256_PREFIX + observed_evidence_digest,
            "packet_bytes_b64": base64.b64encode(packet_path.read_bytes()).decode("ascii"),
            "issuer_attestation_id": issuer_attestation.attestation_id,
            "independence_attestation_id": independence_attestation.attestation_id,
            "issuer_attestation": issuer_attestation.to_dict(),
            "independence_attestation": independence_attestation.to_dict(),
            "admission": "DUAL_ATTESTATION_VERIFIED",
            "transparency_receipt": dict(transparency_receipt or {}),
            "previous_event_hash": events[-1]["event_hash"] if events else GENESIS_HASH,
        }
        event["event_hash"] = _event_hash(event)
        with log_path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(canonical_json(event) + "\n")
            handle.flush()
            if os.name != "nt":
                os.fsync(handle.fileno())
        return event


def compute_state(events: Sequence[Mapping[str, Any]], *, at_time: datetime | None = None) -> dict[str, Any]:
    """Pure reducer for an event stream already accepted by :func:`verify_log`."""
    now = (at_time or datetime.now(timezone.utc)).astimezone(timezone.utc)
    revoked: set[str] = set()
    superseded: set[str] = set()
    for event in events:
        packet = event.get("packet", {})
        if isinstance(packet, Mapping):
            if packet.get("event_type") == "REVOCATION" and packet.get("revokes"):
                revoked.add(str(packet["revokes"]))
            if packet.get("supersedes"):
                superseded.add(str(packet["supersedes"]))

    active: list[Mapping[str, Any]] = []
    for event in events:
        packet = event.get("packet", {})
        if not isinstance(packet, Mapping) or event.get("admission") != "DUAL_ATTESTATION_VERIFIED":
            continue
        event_id = str(packet.get("event_id", ""))
        if event_id in revoked or event_id in superseded or packet.get("event_type") == "REVOCATION":
            continue
        expires_at = packet.get("expires_at")
        if expires_at and _parse_time(str(expires_at)) < now:
            continue
        active.append(packet)

    datasets: set[str] = set()
    labs: set[str] = set()
    reviewers: set[str] = set()
    connectors: set[str] = set()
    cross_host = 0
    calibration_freezes = 0
    connector_runs = 0
    outcomes = {result: 0 for result in sorted(RESULTS)}
    for packet in active:
        result = str(packet.get("result"))
        outcomes[result] = outcomes.get(result, 0) + 1
        if result not in COUNTABLE_RESULTS:
            continue
        evidence = packet.get("evidence", {})
        issuer = packet.get("issuer", {})
        if not isinstance(evidence, Mapping) or not isinstance(issuer, Mapping):
            continue
        event_type = packet.get("event_type")
        if result == "PASS" and evidence.get("dataset_sha256"):
            datasets.add(str(evidence["dataset_sha256"]))
        if event_type == "EXTERNAL_LAB_REPLICATION" and result == "PASS":
            labs.add(str(issuer.get("institution_id")))
        if event_type == "NON_AUTHOR_REVIEW":
            reviewers.add(str(issuer.get("issuer_id")))
        if event_type == "CROSS_HOST_COMPARISON" and result == "PASS":
            cross_host += 1
        if event_type == "CALIBRATION_FREEZE" and result == "PASS":
            calibration_freezes += 1
        if event_type in ("CONNECTOR_CONFORMANCE_EXECUTION", "CONNECTOR_BENCHMARK_EXECUTION") and result == "PASS":
            connector_runs += 1
            if evidence.get("connector_id"):
                connectors.add(str(evidence["connector_id"]))

    return {
        "schema_version": "bionexus.validation-network-state.v1",
        "active_event_count": len(active),
        "candidate_slot_counts": {
            "independent_datasets": len(datasets),
            "external_labs": len(labs),
            "non_author_reviewers": len(reviewers),
            "cross_host_comparisons": cross_host,
            "calibration_freezes": calibration_freezes,
            "connector_conformance_runs": connector_runs,
            "validated_connectors": len(connectors),
        },
        "outcome_counts": outcomes,
        "certification_status": "NOT_ASSESSED",
        "claim_boundary": (
            "Cryptographically admitted event history only; candidate slots do not establish "
            "scientific truth, accreditation, certification, or institutional authority."
        ),
    }


def compute_state_from_log(
    path: Path,
    *,
    trust_registry: TrustRegistry,
    expected_head: str,
    at_time: datetime | None = None,
) -> dict[str, Any]:
    """Verify chain, rollback anchor, embedded signatures, and then reduce state."""
    events, errors = verify_log(
        path,
        expected_head=expected_head,
        trust_registry=trust_registry,
        at_time=at_time,
    )
    if errors:
        raise ValueError("validation log verification failed: " + "; ".join(errors))
    state = compute_state(events, at_time=at_time)
    state["verified_log_head"] = expected_head
    return state
