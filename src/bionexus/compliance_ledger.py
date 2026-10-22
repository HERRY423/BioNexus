"""
BioNexus Compliance & Cryptographic Audit Ledger (BNS-COMP-001..010).

Provides content signatures and local hash-chained audit records:
- Electronic Signatures: Schema bionexus.electronic-signature.v2 with Ed25519
  asymmetric digital signature, SubjectPublicKeyInfo PEM binding, RFC 3161-shaped
  timestamp fixtures. Signer metadata is caller-declared, not authenticated.
- Audit Trail: Append-only, tamper-evident SHA-256 hash-chained ledger.
- Role-Based Access Control (RBAC): Enforces fail-closed permissions.
- These controls do not establish external identity, non-repudiation, trusted
  time, regulatory compliance, or scientific approval.
"""

from __future__ import annotations

import base64
import dataclasses
import enum
import hashlib
import json
import os
import threading
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

from bionexus.attestation_authority import (
    canonical_json_bytes,
    generate_tsa_timestamp_token,
    load_private_key_from_env,
    verify_tsa_timestamp_token,
)
from bionexus.versions import VERSION


class UserRole(str, enum.Enum):
    """Laboratory personnel roles for Role-Based Access Control (RBAC)."""
    GUEST_VIEWER = "GUEST_VIEWER"
    RESEARCHER = "RESEARCHER"
    BIOINFORMATICIAN = "BIOINFORMATICIAN"
    PI_SIGNER = "PI_SIGNER"
    QA_AUDITOR = "QA_AUDITOR"
    SYSTEM_ADMIN = "SYSTEM_ADMIN"


class ActionType(str, enum.Enum):
    """Actions subject to RBAC and compliance audit logging."""
    VIEW_DATA = "VIEW_DATA"
    EXECUTE_PIPELINE = "EXECUTE_PIPELINE"
    OVERRIDE_CONSTRAINT = "OVERRIDE_CONSTRAINT"
    EXPORT_DATA = "EXPORT_DATA"
    ELECTRONIC_SIGN = "ELECTRONIC_SIGN"
    REVOKE_SIGNATURE = "REVOKE_SIGNATURE"
    MODIFY_SECURITY_POLICY = "MODIFY_SECURITY_POLICY"


ROLE_PERMISSIONS: Dict[UserRole, Set[ActionType]] = {
    UserRole.GUEST_VIEWER: {ActionType.VIEW_DATA},
    UserRole.RESEARCHER: {ActionType.VIEW_DATA, ActionType.EXECUTE_PIPELINE, ActionType.EXPORT_DATA},
    UserRole.BIOINFORMATICIAN: {ActionType.VIEW_DATA, ActionType.EXECUTE_PIPELINE, ActionType.OVERRIDE_CONSTRAINT, ActionType.EXPORT_DATA},
    UserRole.PI_SIGNER: {ActionType.VIEW_DATA, ActionType.EXECUTE_PIPELINE, ActionType.OVERRIDE_CONSTRAINT, ActionType.EXPORT_DATA, ActionType.ELECTRONIC_SIGN},
    UserRole.QA_AUDITOR: {ActionType.VIEW_DATA, ActionType.EXPORT_DATA, ActionType.ELECTRONIC_SIGN, ActionType.REVOKE_SIGNATURE},
    UserRole.SYSTEM_ADMIN: set(ActionType),
}


class RBACController:
    """Evaluates user permissions fail-closed."""

    @staticmethod
    def is_authorized(role: UserRole | str, action: ActionType | str) -> bool:
        try:
            r = UserRole(role) if isinstance(role, str) else role
            a = ActionType(action) if isinstance(action, str) else action
            return a in ROLE_PERMISSIONS.get(r, set())
        except ValueError:
            return False


@dataclass
class ElectronicSignature:
    """
    Content-bound signature record. Human identity and authority require external
    verification; possession of the embedded key does not establish them.
    """
    schema_version: str = "bionexus.electronic-signature.v2"
    signature_id: str = ""
    signer_name: str = ""
    signer_email: str = ""
    signer_role: str = UserRole.PI_SIGNER.value
    signing_reason: str = "APPROVAL_OF_SCIENTIFIC_EVIDENCE"
    target_artifact_sha256: str = ""
    timestamp_utc: str = ""
    signature_hash: str = ""
    # Cryptographic PKI Identity fields (Ed25519 asymmetric signature)
    public_key_pem: str = ""
    key_id: str = ""
    signature_algorithm: str = "ed25519"
    signature_bytes_b64: str = ""
    tsa_timestamp_token: Optional[Dict[str, Any]] = None
    rekor_entry: Optional[Dict[str, Any]] = None
    is_ephemeral_key: bool = False

    def compute_signature_hash(self) -> str:
        """Calculate canonical SHA-256 digest of signature contents."""
        if self.schema_version == "bionexus.electronic-signature.v1":
            fields_to_hash = {
                "schema_version": self.schema_version,
                "signer_name": self.signer_name,
                "signer_email": self.signer_email,
                "signer_role": self.signer_role,
                "signing_reason": self.signing_reason,
                "target_artifact_sha256": self.target_artifact_sha256,
                "timestamp_utc": self.timestamp_utc,
            }
        else:
            fields_to_hash = {
                "schema_version": self.schema_version,
                "signer_name": self.signer_name,
                "signer_email": self.signer_email,
                "signer_role": self.signer_role,
                "signing_reason": self.signing_reason,
                "target_artifact_sha256": self.target_artifact_sha256,
                "timestamp_utc": self.timestamp_utc,
                "public_key_pem": self.public_key_pem,
                "key_id": self.key_id,
                "signature_algorithm": self.signature_algorithm,
            }
        canonical = json.dumps(fields_to_hash, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    def get_payload_to_sign(self) -> bytes:
        """Return canonical bytes representing the electronic signature declaration to be signed."""
        data = {
            "schema_version": self.schema_version,
            "signature_id": self.signature_id,
            "signer_name": self.signer_name,
            "signer_email": self.signer_email,
            "signer_role": self.signer_role,
            "signing_reason": self.signing_reason,
            "target_artifact_sha256": self.target_artifact_sha256,
            "timestamp_utc": self.timestamp_utc,
            "public_key_pem": self.public_key_pem,
            "key_id": self.key_id,
        }
        return canonical_json_bytes(data)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ElectronicSignature":
        if data.get("schema_version") not in (
            "bionexus.electronic-signature.v1", "bionexus.electronic-signature.v2"
        ):
            raise ValueError("Missing or unsupported electronic signature schema_version")
        if data["schema_version"] == "bionexus.electronic-signature.v2":
            required = {"public_key_pem", "key_id", "signature_algorithm", "signature_bytes_b64"}
            if not required.issubset(data):
                raise ValueError("v2 signature is missing required cryptographic fields")
        valid_fields = {f.name for f in dataclasses.fields(cls)}
        filtered = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered)


@dataclass
class GxPAuditEntry:
    """Immutable entry in the GxP hash-chained audit ledger."""
    schema_version: str = "bionexus.gxp-audit-entry.v1"
    entry_index: int = 0
    timestamp_utc: str = ""
    operator_id: str = ""
    operator_role: str = ""
    action_type: str = ""
    target_resource: str = ""
    payload_sha256: str = ""
    previous_entry_hash: str = ""
    entry_hash: str = ""

    def compute_entry_hash(self) -> str:
        """Compute canonical hash of this entry chained to previous hash."""
        fields_to_hash = {
            "schema_version": self.schema_version,
            "entry_index": self.entry_index,
            "timestamp_utc": self.timestamp_utc,
            "operator_id": self.operator_id,
            "operator_role": self.operator_role,
            "action_type": self.action_type,
            "target_resource": self.target_resource,
            "payload_sha256": self.payload_sha256,
            "previous_entry_hash": self.previous_entry_hash,
        }
        canonical = json.dumps(fields_to_hash, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ComplianceAuditLedger:
    """Manages immutable GxP audit trails and cryptographically verified electronic signatures."""

    def __init__(self, ledger_file: Optional[Path | str] = None) -> None:
        self.ledger_file = Path(ledger_file) if ledger_file else None
        self.entries: List[GxPAuditEntry] = []
        self.signatures: List[ElectronicSignature] = []
        self.plugin_id = "bionexus"
        self.plugin_version = VERSION
        self._mutex = threading.RLock()
        self._known_hashes: List[str] = []
        if self.ledger_file:
            with self._locked():
                self.entries = self._read_disk_entries()
                self._known_hashes = [entry.entry_hash for entry in self.entries]

    @contextmanager
    def _locked(self):
        """Serialize cooperating writers on a local filesystem, including reopen.

        The stable sidecar must not be removed while the ledger is in use.
        Network filesystems and writers bypassing this lock are not supported.
        """
        with self._mutex:
            if self.ledger_file is None:
                yield
                return
            self.ledger_file.parent.mkdir(parents=True, exist_ok=True)
            lock_path = self.ledger_file.with_name(self.ledger_file.name + ".lock")
            with lock_path.open("a+b") as handle:
                handle.seek(0, os.SEEK_END)
                if handle.tell() == 0:
                    handle.write(b"\0")
                    handle.flush()
                deadline = time.monotonic() + 5.0
                while True:
                    try:
                        handle.seek(0)
                        if os.name == "nt":
                            import msvcrt
                            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                        else:
                            import fcntl
                            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                        break
                    except OSError as exc:
                        if time.monotonic() >= deadline:
                            raise TimeoutError("Ledger lock unavailable; no entry written") from exc
                        time.sleep(0.01)
                try:
                    yield
                finally:
                    handle.seek(0)
                    if os.name == "nt":
                        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    @staticmethod
    def _chain_issues(entries: List[GxPAuditEntry]) -> List[str]:
        issues = []
        previous = "sha256:" + "0" * 64
        for index, entry in enumerate(entries):
            if entry.schema_version != "bionexus.gxp-audit-entry.v1":
                issues.append(f"Entry {index} unsupported schema")
            if type(entry.entry_index) is not int or entry.entry_index != index:
                issues.append(f"Entry {index} invalid entry_index")
            if entry.entry_hash != f"sha256:{entry.compute_entry_hash()}":
                issues.append(f"Entry {index} hash mismatch")
            if entry.previous_entry_hash != previous:
                issues.append(f"Entry {index} chain broken")
            previous = entry.entry_hash
        return issues

    def _read_disk_entries(self) -> List[GxPAuditEntry]:
        def unique_object(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError(f"Duplicate ledger field: {key}")
                result[key] = value
            return result

        entries = []
        required = {field.name for field in dataclasses.fields(GxPAuditEntry)}
        if self.ledger_file.exists():
            for index, line in enumerate(self.ledger_file.read_text(encoding="utf-8").splitlines()):
                try:
                    data = json.loads(line, object_pairs_hook=unique_object)
                    if not isinstance(data, dict) or set(data) != required:
                        raise ValueError("Missing or unknown entry fields")
                    if any(not isinstance(value, str) for key, value in data.items() if key != "entry_index"):
                        raise ValueError("Non-string entry field")
                    entries.append(GxPAuditEntry(**data))
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"Invalid ledger record {index}; existing bytes preserved: {exc}") from exc
        issues = self._chain_issues(entries)
        hashes = [entry.entry_hash for entry in entries]
        if hashes[:len(self._known_hashes)] != self._known_hashes:
            issues.append("Ledger history changed or was truncated since it was opened")
        if issues:
            raise ValueError("Invalid ledger; existing bytes preserved: " + "; ".join(issues))
        return entries

    def append_audit_entry(
        self,
        operator_id: str,
        operator_role: UserRole | str,
        action_type: ActionType | str,
        target_resource: str,
        payload_data: Any = None,
    ) -> GxPAuditEntry:
        """Append a new action to the hash-chained audit trail."""
        r = UserRole(operator_role) if isinstance(operator_role, str) else operator_role
        a = ActionType(action_type) if isinstance(action_type, str) else action_type

        if not RBACController.is_authorized(r, a):
            raise PermissionError(f"Role '{r.value}' is not authorized to perform '{a.value}'")

        payload_bytes = json.dumps(payload_data, sort_keys=True, default=str).encode("utf-8") if payload_data is not None else b"{}"
        payload_sha256 = f"sha256:{hashlib.sha256(payload_bytes).hexdigest()}"

        with self._locked():
            entries = self._read_disk_entries() if self.ledger_file else list(self.entries)
            issues = self._chain_issues(entries)
            if issues:
                raise ValueError("Cannot append to invalid ledger: " + "; ".join(issues))
            entry = GxPAuditEntry(
                entry_index=len(entries),
                timestamp_utc=datetime.now(timezone.utc).isoformat(),
                operator_id=operator_id, operator_role=r.value, action_type=a.value,
                target_resource=target_resource, payload_sha256=payload_sha256,
                previous_entry_hash=entries[-1].entry_hash if entries else "sha256:" + "0" * 64,
            )
            entry.entry_hash = f"sha256:{entry.compute_entry_hash()}"
            if self.ledger_file:
                # Persist before updating memory. A partial write is intentionally
                # left as evidence and will block later reads/appends, never reset.
                with self.ledger_file.open("a+b") as handle:
                    handle.seek(0, os.SEEK_END)
                    separator = b""
                    if handle.tell():
                        handle.seek(-1, os.SEEK_END)
                        if handle.read(1) != b"\n":
                            separator = b"\n"
                    handle.write(separator + json.dumps(entry.to_dict()).encode("utf-8") + b"\n")
                    handle.flush()
                    os.fsync(handle.fileno())
            self.entries = entries + [entry]
            self._known_hashes = [item.entry_hash for item in self.entries]
            return entry

    def verify_ledger_integrity(self) -> Tuple[bool, List[str]]:
        """Verify unbroken cryptographic hash chain across all entries."""
        try:
            with self._locked():
                entries = self._read_disk_entries() if self.ledger_file else self.entries
                issues = self._chain_issues(entries)
                if not issues and self.ledger_file:
                    self.entries = entries
                    self._known_hashes = [entry.entry_hash for entry in entries]
                return not issues, issues
        except (OSError, ValueError) as exc:
            return False, [str(exc)]

    def sign_artifact(
        self,
        signer_name: str,
        signer_email: str,
        signer_role: UserRole | str,
        signing_reason: str,
        artifact_path_or_bytes: Path | str | bytes,
        private_key: Optional[ed25519.Ed25519PrivateKey | str] = None,
        include_tsa_token: bool = True,
        tsa_private_key: Optional[ed25519.Ed25519PrivateKey] = None,
        schema_version: str = "bionexus.electronic-signature.v2",
    ) -> ElectronicSignature:
        """
        Sign artifact content, optionally adding a local timestamp-shaped fixture.
        """
        r = UserRole(signer_role) if isinstance(signer_role, str) else signer_role
        if schema_version not in (
            "bionexus.electronic-signature.v1", "bionexus.electronic-signature.v2"
        ):
            raise ValueError("Unsupported electronic signature schema_version")
        if not RBACController.is_authorized(r, ActionType.ELECTRONIC_SIGN):
            raise PermissionError(f"Role '{r.value}' is not authorized to apply electronic signatures")

        if isinstance(artifact_path_or_bytes, bytes):
            target_sha256 = f"sha256:{hashlib.sha256(artifact_path_or_bytes).hexdigest()}"
        elif isinstance(artifact_path_or_bytes, (str, Path)) and Path(artifact_path_or_bytes).is_file():
            target_sha256 = f"sha256:{hashlib.sha256(Path(artifact_path_or_bytes).read_bytes()).hexdigest()}"
        else:
            target_sha256 = f"sha256:{hashlib.sha256(str(artifact_path_or_bytes).encode()).hexdigest()}"

        # Resolve or generate Ed25519 signing keypair
        priv: ed25519.Ed25519PrivateKey
        is_ephemeral = False
        if isinstance(private_key, ed25519.Ed25519PrivateKey):
            priv = private_key
        elif isinstance(private_key, str) and private_key.strip():
            loaded = load_private_key_from_env(private_key)
            if loaded is None:
                try:
                    loaded = serialization.load_pem_private_key(private_key.encode("ascii"), password=None)
                except Exception:
                    pass
            if isinstance(loaded, ed25519.Ed25519PrivateKey):
                priv = loaded
            else:
                priv = ed25519.Ed25519PrivateKey.generate()
                is_ephemeral = True
        else:
            env_key = load_private_key_from_env("BIONEXUS_SIGNING_KEY")
            if env_key is not None:
                priv = env_key
            else:
                priv = ed25519.Ed25519PrivateKey.generate()
                is_ephemeral = True

        pub = priv.public_key()
        pub_pem = pub.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("ascii")
        key_id = f"sha256:{hashlib.sha256(pub_pem.encode('ascii')).hexdigest()}"

        timestamp_iso = datetime.now(timezone.utc).isoformat()
        sig_id = f"sig_{int(time.time())}_{len(self.signatures)+1:03d}"

        sig = ElectronicSignature(
            schema_version=schema_version,
            signature_id=sig_id,
            signer_name=signer_name,
            signer_email=signer_email,
            signer_role=r.value,
            signing_reason=signing_reason,
            target_artifact_sha256=target_sha256,
            timestamp_utc=timestamp_iso,
            public_key_pem=pub_pem,
            key_id=key_id,
            signature_algorithm="ed25519",
            is_ephemeral_key=is_ephemeral,
        )

        # Cryptographically sign the canonical signature declaration
        payload_bytes = sig.get_payload_to_sign()
        raw_signature = priv.sign(payload_bytes)
        sig.signature_bytes_b64 = base64.b64encode(raw_signature).decode("ascii")

        # Timestamp anchoring via TSA
        if include_tsa_token:
            try:
                sig.tsa_timestamp_token = generate_tsa_timestamp_token(
                    study_id=sig_id,
                    raw_signature=raw_signature,
                    tsa_private_key=tsa_private_key,
                    timestamp_iso=timestamp_iso,
                )
            except Exception:
                sig.tsa_timestamp_token = None

        sig.signature_hash = f"sha256:{sig.compute_signature_hash()}"
        self.signatures.append(sig)

        self.append_audit_entry(
            operator_id=signer_email,
            operator_role=r,
            action_type=ActionType.ELECTRONIC_SIGN,
            target_resource=target_sha256,
            payload_data=sig.to_dict(),
        )

        return sig

    def verify_signature(
        self,
        signature: ElectronicSignature | Dict[str, Any],
        artifact_path_or_bytes: Path | str | bytes,
        expected_public_key_pem: Optional[str] = None,
        tsa_public_key_pem: Optional[str] = None,
        *,
        require_tsa_token: bool = False,
    ) -> Tuple[bool, Optional[str]]:
        """
        Verify content binding; v2 also requires a valid Ed25519 signature.

        An embedded key is not an externally trusted identity. Legacy v1 remains
        readable but returns an explicit LEGACY_HASH_ONLY notice, never PKI proof.
        """
        try:
            sig = ElectronicSignature.from_dict(signature) if isinstance(signature, dict) else signature
            if not isinstance(sig, ElectronicSignature):
                return False, "Invalid electronic signature record"
            if sig.schema_version not in (
                "bionexus.electronic-signature.v1", "bionexus.electronic-signature.v2"
            ):
                return False, "Unsupported electronic signature schema_version"
            for name in ("signature_id", "signer_name", "signer_email", "signer_role",
                         "signing_reason", "target_artifact_sha256", "timestamp_utc", "signature_hash"):
                value = getattr(sig, name)
                if not isinstance(value, str) or not value.strip():
                    return False, f"Signature missing required field: {name}"
            timestamp = datetime.fromisoformat(sig.timestamp_utc.replace("Z", "+00:00"))
            if timestamp.tzinfo is None:
                return False, "Signature timestamp must include a timezone"
        except (TypeError, ValueError) as exc:
            return False, f"Invalid electronic signature record: {exc}"

        computed_hash = f"sha256:{sig.compute_signature_hash()}"
        if sig.signature_hash != computed_hash:
            return False, f"Signature hash corrupted: expected {computed_hash}, got {sig.signature_hash}"

        if isinstance(artifact_path_or_bytes, bytes):
            actual_target_sha256 = f"sha256:{hashlib.sha256(artifact_path_or_bytes).hexdigest()}"
        elif isinstance(artifact_path_or_bytes, (str, Path)) and Path(artifact_path_or_bytes).is_file():
            actual_target_sha256 = f"sha256:{hashlib.sha256(Path(artifact_path_or_bytes).read_bytes()).hexdigest()}"
        else:
            actual_target_sha256 = f"sha256:{hashlib.sha256(str(artifact_path_or_bytes).encode()).hexdigest()}"

        if sig.target_artifact_sha256 != actual_target_sha256:
            return False, f"Artifact SHA-256 mismatch: signature signed {sig.target_artifact_sha256}, actual artifact is {actual_target_sha256}"

        if sig.schema_version == "bionexus.electronic-signature.v1":
            if expected_public_key_pem is not None or tsa_public_key_pem is not None or require_tsa_token:
                return False, "LEGACY_HASH_ONLY: v1 cannot satisfy signer or timestamp trust requirements"
            return True, "LEGACY_HASH_ONLY: content hash matches; signer identity and signature are not verified"

        # Every v2 record must carry crypto fields, even without a trust anchor.
        if sig.signature_algorithm != "ed25519":
            return False, "Unsupported signature_algorithm; v2 requires ed25519"
        for name in ("signature_bytes_b64", "public_key_pem", "key_id"):
            value = getattr(sig, name)
            if not isinstance(value, str) or not value.strip():
                return False, f"v2 signature missing required cryptographic field: {name}"
        expected_key_id = "sha256:" + hashlib.sha256(sig.public_key_pem.encode("utf-8")).hexdigest()
        if sig.key_id != expected_key_id:
            return False, "Signature key_id does not match public key"
        if expected_public_key_pem is not None:
            if not expected_public_key_pem.strip() or sig.public_key_pem.strip() != expected_public_key_pem.strip():
                return False, "Signer public key mismatch: signature public key does not match expected authority key"

        try:
            pubkey = serialization.load_pem_public_key(sig.public_key_pem.encode("ascii"))
            if not isinstance(pubkey, ed25519.Ed25519PublicKey):
                return False, f"Unsupported public key type: expected Ed25519, got {type(pubkey).__name__}"
            raw_sig = base64.b64decode(sig.signature_bytes_b64, validate=True)
            payload = sig.get_payload_to_sign()
            pubkey.verify(raw_sig, payload)
        except InvalidSignature:
            return False, "Invalid Ed25519 cryptographic signature: payload was forged or tampered"
        except Exception as ex:
            return False, f"Cryptographic verification error: {str(ex)}"

        if tsa_public_key_pem is not None or require_tsa_token:
            if not isinstance(sig.tsa_timestamp_token, dict) or not sig.tsa_timestamp_token:
                return False, "Required TSA timestamp token is missing"
            if not tsa_public_key_pem:
                return False, "Required TSA verification needs an explicit public key"
            valid_tsa, tsa_errs = verify_tsa_timestamp_token(
                token=sig.tsa_timestamp_token,
                raw_signature=raw_sig,
                tsa_public_key_pem=tsa_public_key_pem,
            )
            if not valid_tsa:
                return False, f"TSA timestamp verification failed: {'; '.join(tsa_errs)}"

        return True, None

    def verify_signature_assessment(
        self, signature: ElectronicSignature | Dict[str, Any],
        artifact_path_or_bytes: Path | str | bytes,
        expected_public_key_pem: Optional[str] = None,
        tsa_public_key_pem: Optional[str] = None,
        *, require_tsa_token: bool = False,
    ) -> Dict[str, Any]:
        """Expose integrity strength without treating self-supplied keys as identity proof."""
        valid, reason = self.verify_signature(
            signature, artifact_path_or_bytes, expected_public_key_pem,
            tsa_public_key_pem, require_tsa_token=require_tsa_token,
        )
        schema = signature.get("schema_version") if isinstance(signature, dict) else getattr(signature, "schema_version", None)
        legacy = schema == "bionexus.electronic-signature.v1"
        status = "INVALID"
        if valid:
            status = "LEGACY_HASH_ONLY" if legacy else (
                "SIGNATURE_VALID_EXPECTED_KEY" if expected_public_key_pem else "SIGNATURE_VALID_UNTRUSTED_KEY"
            )
        return {
            "valid": valid, "status": status, "reason": reason,
            "signer_key_binding": "EXPECTED_KEY_MATCHED" if valid and not legacy and expected_public_key_pem else "NOT_ESTABLISHED",
            "external_identity_trust": "NOT_ESTABLISHED",
            "scientific_authorization": "NONE",
            "timestamp_status": "EXPLICIT_KEY_VERIFIED" if valid and tsa_public_key_pem else "NOT_VERIFIED",
        }
