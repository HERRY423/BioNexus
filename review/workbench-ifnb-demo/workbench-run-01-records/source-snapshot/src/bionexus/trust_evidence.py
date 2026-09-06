"""Target-bound scientific evidence signatures and revocation verification.

This module deliberately separates integrity from scientific endorsement.  A valid
Ed25519 signature proves that a trusted key signed a payload bound to a concrete
artifact digest.  It does not prove that the scientific claim is true, and it is
not a regulatory electronic-signature implementation.
"""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence, Union

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

PathLike = Union[str, Path]
EVIDENCE_SCHEMA_VERSION = "bionexus.evidence-attestation.v1"
REVOCATION_SCHEMA_VERSION = "bionexus.signed-revocation.v1"


class TrustDecision(str, Enum):
    VERIFIED = "VERIFIED"
    NOT_ASSESSED = "NOT_ASSESSED"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"
    UNTRUSTED_KEY = "UNTRUSTED_KEY"
    INVALID_SIGNATURE = "INVALID_SIGNATURE"
    ARTIFACT_MISMATCH = "ARTIFACT_MISMATCH"
    MALFORMED = "MALFORMED"


@dataclass(frozen=True)
class EvidenceSubject:
    subject_type: str
    subject_id: str
    version: str
    artifact_uri: str
    artifact_sha256: str


@dataclass(frozen=True)
class EvidenceAttestation:
    attestation_id: str
    predicate_type: str
    subject: EvidenceSubject
    scope: Mapping[str, Any]
    claims: Mapping[str, Any]
    issued_at: str
    expires_at: Optional[str]
    signer_id: str
    key_id: str
    signature_b64: str
    schema_version: str = EVIDENCE_SCHEMA_VERSION
    signature_algorithm: str = "Ed25519"

    def unsigned_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("signature_b64")
        return payload

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "EvidenceAttestation":
        payload = dict(data)
        payload["subject"] = EvidenceSubject(**payload["subject"])
        return cls(**payload)


@dataclass(frozen=True)
class TrustKey:
    key_id: str
    signer_id: str
    public_key_pem: str
    valid_from: str
    valid_until: Optional[str] = None
    status: str = "ACTIVE"
    allowed_predicates: Sequence[str] = field(default_factory=tuple)


@dataclass(frozen=True)
class SignedRevocation:
    revocation_id: str
    target_type: str
    target_id: str
    reason: str
    revoked_at: str
    signer_id: str
    key_id: str
    signature_b64: str
    schema_version: str = REVOCATION_SCHEMA_VERSION
    signature_algorithm: str = "Ed25519"

    def unsigned_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("signature_b64")
        return payload

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AttestationVerification:
    decision: TrustDecision
    reasons: tuple[str, ...]
    attestation_id: str = ""
    artifact_sha256: str = ""

    @property
    def accepted(self) -> bool:
        return self.decision == TrustDecision.VERIFIED


@dataclass
class TrustRegistry:
    """Explicit trust anchors and signed revocations; empty by default."""

    keys: dict[str, TrustKey] = field(default_factory=dict)
    revocations: list[SignedRevocation] = field(default_factory=list)
    registry_version: str = "1.0.0"
    status: str = "DEVELOPMENT_NO_TRUST_ANCHORS"

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TrustRegistry":
        keys = {item["key_id"]: TrustKey(**item) for item in data.get("keys", [])}
        revocations = [SignedRevocation(**item) for item in data.get("revocations", [])]
        return cls(
            keys=keys,
            revocations=revocations,
            registry_version=str(data.get("registry_version", "1.0.0")),
            status=str(data.get("status", "DEVELOPMENT_NO_TRUST_ANCHORS")),
        )

    @classmethod
    def load(cls, path: PathLike) -> "TrustRegistry":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    def to_dict(self) -> dict[str, Any]:
        return {
            "registry_version": self.registry_version,
            "status": self.status,
            "keys": [asdict(key) for key in self.keys.values()],
            "revocations": [item.to_dict() for item in self.revocations],
        }


def canonical_json_bytes(payload: Any) -> bytes:
    """Return deterministic UTF-8 JSON bytes for signing."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_file(path: PathLike) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def public_key_id(public_key: Ed25519PublicKey) -> str:
    raw = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return f"ed25519:{hashlib.sha256(raw).hexdigest()}"


def _iso(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return parsed.astimezone(timezone.utc)


def _load_public_key(pem: str) -> Ed25519PublicKey:
    key = serialization.load_pem_public_key(pem.encode("ascii"))
    if not isinstance(key, Ed25519PublicKey):
        raise ValueError("trust key is not Ed25519")
    return key


def _sign(payload: Mapping[str, Any], private_key: Ed25519PrivateKey) -> str:
    return base64.b64encode(private_key.sign(canonical_json_bytes(payload))).decode("ascii")


def create_attestation(
    *,
    attestation_id: str,
    predicate_type: str,
    subject: EvidenceSubject,
    scope: Mapping[str, Any],
    claims: Mapping[str, Any],
    issued_at: str,
    expires_at: Optional[str],
    signer_id: str,
    key_id: str,
    private_key: Ed25519PrivateKey,
) -> EvidenceAttestation:
    """Create an explicitly keyed, artifact-bound attestation."""
    draft = EvidenceAttestation(
        attestation_id=attestation_id,
        predicate_type=predicate_type,
        subject=subject,
        scope=dict(scope),
        claims=dict(claims),
        issued_at=issued_at,
        expires_at=expires_at,
        signer_id=signer_id,
        key_id=key_id,
        signature_b64="",
    )
    return EvidenceAttestation(**{**draft.to_dict(), "subject": subject, "signature_b64": _sign(draft.unsigned_payload(), private_key)})


def create_revocation(
    *,
    revocation_id: str,
    target_type: str,
    target_id: str,
    reason: str,
    revoked_at: str,
    signer_id: str,
    key_id: str,
    private_key: Ed25519PrivateKey,
) -> SignedRevocation:
    """Create a signed attestation- or key-revocation record."""
    if target_type not in {"attestation", "key"}:
        raise ValueError("target_type must be 'attestation' or 'key'")
    draft = SignedRevocation(
        revocation_id=revocation_id,
        target_type=target_type,
        target_id=target_id,
        reason=reason,
        revoked_at=revoked_at,
        signer_id=signer_id,
        key_id=key_id,
        signature_b64="",
    )
    return SignedRevocation(**{**draft.to_dict(), "signature_b64": _sign(draft.unsigned_payload(), private_key)})


def _signature_valid(payload: Mapping[str, Any], signature_b64: str, key: TrustKey) -> bool:
    try:
        signature = base64.b64decode(signature_b64, validate=True)
        _load_public_key(key.public_key_pem).verify(signature, canonical_json_bytes(payload))
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False


def _revocation_valid(item: SignedRevocation, registry: TrustRegistry, at_time: datetime) -> bool:
    if (
        item.schema_version != REVOCATION_SCHEMA_VERSION
        or item.signature_algorithm != "Ed25519"
        or item.target_type not in {"attestation", "key"}
    ):
        return False
    key = registry.keys.get(item.key_id)
    if key is None or key.status != "ACTIVE" or key.signer_id != item.signer_id:
        return False
    if "revocation" not in key.allowed_predicates:
        return False
    try:
        if _iso(item.revoked_at) > at_time or _iso(key.valid_from) > at_time:
            return False
        if key.valid_until and _iso(key.valid_until) < at_time:
            return False
    except ValueError:
        return False
    return _signature_valid(item.unsigned_payload(), item.signature_b64, key)


def verify_attestation(
    attestation: EvidenceAttestation,
    registry: TrustRegistry,
    *,
    artifact_path: Optional[PathLike] = None,
    artifact_bytes: Optional[bytes] = None,
    at_time: Optional[datetime] = None,
) -> AttestationVerification:
    """Verify trust, signature, revocation, expiry, and concrete artifact binding."""
    now = (at_time or datetime.now(timezone.utc)).astimezone(timezone.utc)
    aid = attestation.attestation_id

    try:
        if attestation.schema_version != EVIDENCE_SCHEMA_VERSION:
            raise ValueError("unsupported attestation schema")
        if attestation.signature_algorithm != "Ed25519":
            raise ValueError("unsupported signature algorithm")
        if len(attestation.subject.artifact_sha256) != 64:
            raise ValueError("artifact_sha256 must be 64 hexadecimal characters")
        int(attestation.subject.artifact_sha256, 16)
        issued = _iso(attestation.issued_at)
        if issued > now:
            raise ValueError("attestation issuance time is in the future")
    except (ValueError, TypeError, KeyError) as exc:
        return AttestationVerification(TrustDecision.MALFORMED, (str(exc),), aid)

    key = registry.keys.get(attestation.key_id)
    if key is None or key.signer_id != attestation.signer_id or key.status != "ACTIVE":
        return AttestationVerification(TrustDecision.UNTRUSTED_KEY, ("signing key is not an active configured trust anchor",), aid)
    if attestation.predicate_type not in key.allowed_predicates:
        return AttestationVerification(TrustDecision.UNTRUSTED_KEY, ("key is not authorized for this predicate type",), aid)

    try:
        if _iso(key.valid_from) > issued or (key.valid_until and _iso(key.valid_until) < issued):
            return AttestationVerification(TrustDecision.UNTRUSTED_KEY, ("key was not valid when the attestation was issued",), aid)
        if attestation.expires_at and _iso(attestation.expires_at) < now:
            return AttestationVerification(TrustDecision.EXPIRED, ("attestation has expired",), aid)
    except ValueError as exc:
        return AttestationVerification(TrustDecision.MALFORMED, (str(exc),), aid)

    valid_revocations = [item for item in registry.revocations if _revocation_valid(item, registry, now)]
    if any(item.target_type == "key" and item.target_id == key.key_id for item in valid_revocations):
        return AttestationVerification(TrustDecision.REVOKED, ("signing key has a valid revocation",), aid)
    if any(item.target_type == "attestation" and item.target_id == aid for item in valid_revocations):
        return AttestationVerification(TrustDecision.REVOKED, ("attestation has a valid revocation",), aid)

    if not _signature_valid(attestation.unsigned_payload(), attestation.signature_b64, key):
        return AttestationVerification(TrustDecision.INVALID_SIGNATURE, ("Ed25519 signature verification failed",), aid)

    if artifact_path is not None and artifact_bytes is not None:
        return AttestationVerification(
            TrustDecision.MALFORMED,
            ("supply artifact_path or artifact_bytes, not both",),
            aid,
            attestation.subject.artifact_sha256,
        )
    if artifact_path is None and artifact_bytes is None:
        return AttestationVerification(
            TrustDecision.NOT_ASSESSED,
            ("artifact bytes were not supplied; digest binding was not verified",),
            aid,
            attestation.subject.artifact_sha256,
        )
    actual_digest = (
        hashlib.sha256(artifact_bytes).hexdigest()
        if artifact_bytes is not None
        else sha256_file(artifact_path)
    )
    if actual_digest != attestation.subject.artifact_sha256:
        return AttestationVerification(
            TrustDecision.ARTIFACT_MISMATCH,
            ("artifact SHA-256 does not match the signed subject",),
            aid,
            actual_digest,
        )
    return AttestationVerification(
        TrustDecision.VERIFIED,
        ("trusted signature, revocation state, validity interval, and artifact digest verified",),
        aid,
        actual_digest,
    )
