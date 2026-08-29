"""Portable, tamper-evident research state artifacts.

Snapshots are passive records for a host or researcher to create and verify.
They are not a workspace service, workflow engine, or autonomous agent.
"""

from __future__ import annotations

import hashlib
import json
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

from bionexus.provenance import sidecar

SCHEMA_VERSION = "bionexus.research-snapshot.v1"
CAPSULE_VERSION = "bionexus.evidence-capsule.v1"


class IntegrityError(ValueError):
    """Raised when persisted bytes or a revision chain fail verification."""


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


@dataclass(frozen=True)
class SnapshotRevision:
    revision_id: str
    state: Mapping[str, Any]
    parent_digest: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    digest: str = ""

    def unsigned_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "revision_id": self.revision_id,
            "parent_digest": self.parent_digest,
            "state": dict(self.state),
            "metadata": dict(self.metadata),
        }

    def computed_digest(self) -> str:
        return sha256_bytes(canonical_json_bytes(self.unsigned_dict()))

    def signed(self) -> "SnapshotRevision":
        return SnapshotRevision(
            revision_id=self.revision_id,
            state=self.state,
            parent_digest=self.parent_digest,
            metadata=self.metadata,
            digest=self.computed_digest(),
        )

    def to_dict(self) -> dict[str, Any]:
        result = self.unsigned_dict()
        result["digest"] = self.digest or self.computed_digest()
        return result

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "SnapshotRevision":
        if value.get("schema_version") != SCHEMA_VERSION:
            raise IntegrityError("Unsupported research snapshot schema")
        return cls(
            revision_id=str(value["revision_id"]),
            state=dict(value.get("state", {})),
            parent_digest=value.get("parent_digest"),
            metadata=dict(value.get("metadata", {})),
            digest=str(value.get("digest", "")),
        )


class SnapshotJournal:
    """An in-memory append-only chain that can be persisted as canonical JSON."""

    def __init__(self, revisions: Sequence[SnapshotRevision] = ()) -> None:
        self.revisions = list(revisions)
        self.verify()

    def append(
        self,
        revision_id: str,
        state: Mapping[str, Any],
        *,
        metadata: Mapping[str, Any] | None = None,
    ) -> SnapshotRevision:
        if any(item.revision_id == revision_id for item in self.revisions):
            raise ValueError(f"Duplicate revision ID '{revision_id}'")
        parent = self.revisions[-1].digest if self.revisions else None
        revision = SnapshotRevision(revision_id, dict(state), parent, dict(metadata or {})).signed()
        self.revisions.append(revision)
        return revision

    def verify(self, *, expected_head_digest: str | None = None) -> None:
        seen_ids: set[str] = set()
        parent: str | None = None
        for index, revision in enumerate(self.revisions):
            if revision.revision_id in seen_ids:
                raise IntegrityError(f"Duplicate revision ID at position {index}")
            seen_ids.add(revision.revision_id)
            if revision.parent_digest != parent:
                raise IntegrityError(f"Broken parent chain at revision '{revision.revision_id}'")
            if not revision.digest or revision.digest != revision.computed_digest():
                raise IntegrityError(f"Digest mismatch at revision '{revision.revision_id}'")
            parent = revision.digest
        if expected_head_digest is not None and parent != expected_head_digest:
            raise IntegrityError("Snapshot journal head does not match the externally retained digest")

    def to_dict(self) -> dict[str, Any]:
        self.verify()
        return {"schema_version": SCHEMA_VERSION, "revisions": [item.to_dict() for item in self.revisions]}

    def save(self, path: str | Path) -> None:
        Path(path).write_bytes(canonical_json_bytes(self.to_dict()))

    @classmethod
    def load(cls, path: str | Path, *, expected_head_digest: str | None = None) -> "SnapshotJournal":
        value = json.loads(Path(path).read_bytes())
        if value.get("schema_version") != SCHEMA_VERSION:
            raise IntegrityError("Unsupported research snapshot journal schema")
        journal = cls([SnapshotRevision.from_dict(item) for item in value.get("revisions", [])])
        journal.verify(expected_head_digest=expected_head_digest)
        return journal


def _safe_member(name: str) -> str:
    normalized = name.replace("\\", "/")
    pure = PurePosixPath(normalized)
    if not normalized or pure.is_absolute() or ".." in pure.parts or normalized.endswith("/"):
        raise ValueError(f"Unsafe or invalid capsule member '{name}'")
    return str(pure)


def _zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o600 << 16
    return info


def create_evidence_capsule(
    path: str | Path,
    artifacts: Mapping[str, bytes | str | Path],
    *,
    activity_name: str,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Create an exact-byte-verified ZIP; paths are logical capsule names."""

    payloads: dict[str, bytes] = {}
    input_files: list[Path] = []
    for raw_name, source in artifacts.items():
        name = _safe_member(raw_name)
        if name == "capsule.json" or name in payloads:
            raise ValueError(f"Duplicate/reserved capsule member '{name}'")
        if isinstance(source, Path):
            data = source.read_bytes()
            input_files.append(source)
        elif isinstance(source, str):
            data = source.encode("utf-8")
        else:
            data = bytes(source)
        payloads[name] = data

    manifest_core = {
        "schema_version": CAPSULE_VERSION,
        "activity_name": activity_name,
        "artifacts": {
            name: {"sha256": sha256_bytes(data), "size_bytes": len(data)}
            for name, data in sorted(payloads.items())
        },
        "metadata": dict(metadata or {}),
        "provenance": sidecar(activity_name=activity_name, input_files=input_files),
    }
    manifest = {
        **manifest_core,
        "manifest_digest": sha256_bytes(canonical_json_bytes(manifest_core)),
    }
    with zipfile.ZipFile(Path(path), "w") as archive:
        archive.writestr(_zip_info("capsule.json"), canonical_json_bytes(manifest))
        for name, data in sorted(payloads.items()):
            archive.writestr(_zip_info(name), data)
    return manifest


def verify_evidence_capsule(
    path: str | Path,
    *,
    expected_manifest_digest: str | None = None,
) -> dict[str, Any]:
    """Verify duplicate names, exact membership, sizes, and raw-byte hashes."""

    with zipfile.ZipFile(Path(path), "r") as archive:
        names = [info.filename for info in archive.infolist()]
        if len(names) != len(set(names)):
            raise IntegrityError("Capsule contains duplicate member names")
        for name in names:
            try:
                _safe_member(name)
            except ValueError as exc:
                raise IntegrityError(str(exc)) from exc
        if "capsule.json" not in names:
            raise IntegrityError("Capsule manifest is missing")
        manifest = json.loads(archive.read("capsule.json"))
        if manifest.get("schema_version") != CAPSULE_VERSION:
            raise IntegrityError("Unsupported evidence capsule schema")
        recorded_digest = manifest.get("manifest_digest")
        unsigned_manifest = {key: value for key, value in manifest.items() if key != "manifest_digest"}
        computed_digest = sha256_bytes(canonical_json_bytes(unsigned_manifest))
        if recorded_digest != computed_digest:
            raise IntegrityError("Capsule manifest digest is invalid")
        if expected_manifest_digest is not None and recorded_digest != expected_manifest_digest:
            raise IntegrityError("Capsule does not match the externally retained manifest digest")
        declared = manifest.get("artifacts")
        if not isinstance(declared, Mapping):
            raise IntegrityError("Capsule artifact manifest is invalid")
        if set(names) != {"capsule.json", *declared.keys()}:
            raise IntegrityError("Capsule membership does not match its manifest")
        for name, record in declared.items():
            data = archive.read(name)
            if len(data) != record.get("size_bytes") or sha256_bytes(data) != record.get("sha256"):
                raise IntegrityError(f"Artifact integrity check failed for '{name}'")
        return manifest
