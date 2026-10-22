"""Versioned input schemas, validation, and explicit migrations.

Unknown schema versions fail closed. Historical documents remain readable
through registered migrators; conclusions are never rewritten.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from jsonschema import Draft202012Validator

from bionexus.versions import PLUGIN_VERSION

DATA_PACKAGE = "bionexus.data"
REGISTRY_FILE = "schema-registry.v1.json"
Migrator = Callable[[Dict[str, Any]], Dict[str, Any]]
_PRODUCT_ALIASES = {
    "cellranger": "cellranger",
    "10x": "cellranger",
    "scanpy": "scanpy",
    "anndata": "scanpy",
    "seurat": "seurat",
    "deseq2": "deseq2",
    "pydeseq2": "deseq2",
    "edger": "edger",
    "edgeR": "edger",
    "nf-core": "nf-core",
    "nfcore": "nf-core",
    "nextflow": "nf-core",
}


def _canonical_product(raw: str) -> str:
    key = raw.strip()
    mapped = _PRODUCT_ALIASES.get(key) or _PRODUCT_ALIASES.get(key.lower())
    if mapped is None:
        raise SchemaError(f"historical tool {raw!r} has no v2 product mapping")
    return mapped


class SchemaError(ValueError):
    """Raised when a document fails schema validation or migration."""


@dataclass
class ValidationResult:
    """Outcome of validating a document against a named schema family."""

    family: str
    version: str
    valid: bool
    errors: List[str] = field(default_factory=list)
    document_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "family": self.family,
            "version": self.version,
            "valid": self.valid,
            "errors": list(self.errors),
            "document_id": self.document_id,
        }


def _data_text(name: str) -> str:
    return resources.files(DATA_PACKAGE).joinpath(name).read_text(encoding="utf-8")


def _data_json(name: str) -> Dict[str, Any]:
    return json.loads(_data_text(name))


def load_schema_registry() -> Dict[str, Any]:
    """Load the packaged schema-family registry."""
    return _data_json(REGISTRY_FILE)


def load_json_schema(schema_file: str) -> Dict[str, Any]:
    """Load a packaged JSON Schema document."""
    return _data_json(schema_file)


def canonical_json_sha256(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def parse_schema_version(document: Dict[str, Any]) -> Tuple[str, str]:
    """Return (family, version) from schema_version like bionexus.lab-exchange-envelope.v2."""
    raw = document.get("schema_version")
    if not isinstance(raw, str) or not raw.startswith("bionexus.") or ".v" not in raw:
        raise SchemaError("document is missing a bionexus.<family>.vN schema_version")
    body = raw[len("bionexus.") :]
    family, version = body.rsplit(".", 1)
    if not version.startswith("v") or not version[1:].isdigit():
        raise SchemaError(f"unsupported schema_version: {raw!r}")
    return family, version


def _family_entry(family: str) -> Dict[str, Any]:
    registry = load_schema_registry()
    families = registry.get("families") or {}
    entry = families.get(family)
    if not isinstance(entry, dict):
        raise SchemaError(f"unknown schema family: {family!r}")
    return entry


def current_version(family: str) -> str:
    return str(_family_entry(family)["current"])


def validate_document(document: Dict[str, Any], *, family: Optional[str] = None) -> ValidationResult:
    """Validate a document against the schema version it declares."""
    declared_family, version = parse_schema_version(document)
    target_family = family or declared_family
    if family is not None and family != declared_family:
        return ValidationResult(
            family=target_family,
            version=version,
            valid=False,
            errors=[f"schema family mismatch: declared {declared_family!r}, expected {family!r}"],
            document_id=str(document.get("schema_version", "")),
        )
    entry = _family_entry(target_family)
    versions = entry.get("versions") or {}
    meta = versions.get(version)
    if not isinstance(meta, dict):
        return ValidationResult(
            family=target_family,
            version=version,
            valid=False,
            errors=[f"unregistered schema version: bionexus.{target_family}.{version}"],
            document_id=str(document.get("schema_version", "")),
        )
    schema = load_json_schema(str(meta["schema_file"]))
    validator = Draft202012Validator(schema)
    errors = [f"{'/'.join(str(p) for p in err.path) or '$'}: {err.message}" for err in validator.iter_errors(document)]
    return ValidationResult(
        family=target_family,
        version=version,
        valid=not errors,
        errors=errors,
        document_id=str(meta.get("document_id") or document.get("schema_version", "")),
    )


def _migrate_lab_exchange_v1_to_v2(document: Dict[str, Any]) -> Dict[str, Any]:
    files = []
    for item in document.get("files") or []:
        relpath = str(item.get("path") or "")
        digest = str(item.get("hash") or "")
        if re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise SchemaError("historical file hash is not a SHA-256 digest; original bytes are required")
        files.append(
            {
                "role": "legacy",
                "relpath": relpath,
                "sha256": digest,
                "size_bytes": int(item.get("size_bytes") or 0),
                "integrity_status": "DECLARED_UNVERIFIED",
            }
        )
    source = {
        "kind": "legacy_v1",
        "root_name": str(document.get("root") or document.get("tool") or "legacy"),
        "files": files,
    }
    migrated = {
        "schema_version": "bionexus.lab-exchange-envelope.v2",
        "producer": {
            "product": _canonical_product(str(document["tool"])),
            "product_version": document.get("tool_version"),
            "bionexus_version": str(document.get("bionexus_version") or PLUGIN_VERSION),
        },
        "source": source,
        "semantic_type": str(document.get("semantic_type") or "lab.legacy.v1"),
        "data_classification": str(document.get("data_classification") or "UNKNOWN"),
        "scientific_authorization": "NONE",
        "imported_at": str(document.get("imported_at") or "1970-01-01T00:00:00+00:00"),
        "payload_sha256": canonical_json_sha256(source["files"]),
        "summary": {"migrated_from": "bionexus.lab-exchange-envelope.v1"},
        "warnings": ["Migrated from historical v1 envelope; original bytes were not re-hashed."],
    }
    return migrated


_MIGRATORS: Dict[Tuple[str, str, str], Migrator] = {
    ("lab-exchange-envelope", "v1", "v2"): _migrate_lab_exchange_v1_to_v2,
}


def migrate_document(
    document: Dict[str, Any],
    *,
    family: Optional[str] = None,
    target: Optional[str] = None,
) -> Dict[str, Any]:
    """Walk registered migrations until the family's current (or requested) version."""
    current_family, version = parse_schema_version(document)
    target_family = family or current_family
    if target_family != current_family:
        raise SchemaError(f"cannot migrate {current_family!r} as {target_family!r}")
    initial = validate_document(document, family=target_family)
    if not initial.valid:
        raise SchemaError("source document failed validation: " + "; ".join(initial.errors))
    entry = _family_entry(target_family)
    desired = target or str(entry["current"])
    payload = json.loads(json.dumps(document))
    seen = 0
    while version != desired:
        meta = (entry.get("versions") or {}).get(version) or {}
        nxt = meta.get("next")
        if not nxt:
            raise SchemaError(f"no migration path from bionexus.{target_family}.{version} to {desired}")
        migrator = _MIGRATORS.get((target_family, version, str(nxt)))
        if migrator is None:
            raise SchemaError(f"missing migrator {target_family} {version}->{nxt}")
        payload = migrator(payload)
        _, version = parse_schema_version(payload)
        seen += 1
        if seen > 8:
            raise SchemaError("migration cycle or runaway chain")
    result = validate_document(payload, family=target_family)
    if not result.valid:
        raise SchemaError("migrated document failed validation: " + "; ".join(result.errors))
    return payload


def load_and_migrate(path: str | Path, *, family: Optional[str] = None) -> Dict[str, Any]:
    """Read a JSON document from disk and migrate it to the current schema."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SchemaError("schema document must be a JSON object")
    return migrate_document(payload, family=family)
