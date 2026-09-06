"""BioNexus Scientific Semantic Conventions runtime.

This module turns the versioned convention registry into an executable
producer/consumer contract. Producers fail closed on unknown or ambiguous
registered semantics. Consumers preserve unknown future attributes and enum
values with warnings so that an additive registry release does not destroy
information.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from jsonschema import Draft202012Validator

from bionexus.contracts import ConclusionMaturity

SEMANTIC_STANDARD_ROOT_ENV = "BIONEXUS_SEMCONV_ROOT"
DEFAULT_SEMANTIC_STANDARD_ROOT = (
    Path(__file__).resolve().parents[2] / "standards" / "scientific-semantic-conventions"
)
DEFAULT_SEMANTIC_REGISTRY_PATH = DEFAULT_SEMANTIC_STANDARD_ROOT / "registry.json"
DEFAULT_SEMANTIC_ENVELOPE_SCHEMA_PATH = DEFAULT_SEMANTIC_STANDARD_ROOT / "schemas" / "envelope.schema.json"
_RELEASE_MANIFEST_SCHEMA = "urn:bionexus:scientific-semantic-release-manifest:1"
_STANDARD_ID = "BNS-019"
_ARTIFACT_NAME = "bionexus-scientific-semantic-conventions"
_ATTRIBUTE_NAME = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
_STABILITY_ORDER = {
    "development": 0,
    "alpha": 1,
    "beta": 2,
    "release_candidate": 3,
    "stable": 4,
}


class ScientificSemanticError(ValueError):
    """Raised when a semantic record violates a convention contract."""


class SemanticValidationMode(str, Enum):
    """Validation posture for convention writers and readers."""

    PRODUCER = "producer"
    CONSUMER = "consumer"


@dataclass(frozen=True)
class SemanticValidationReport:
    """Normalized attributes plus deterministic errors and warnings."""

    valid: bool
    normalized_attributes: Dict[str, Any]
    errors: Tuple[str, ...] = ()
    warnings: Tuple[str, ...] = ()

    @property
    def failure_classes(self) -> Tuple[str, ...]:
        """Stable, language-neutral classes for conformance comparisons."""

        return tuple(dict.fromkeys(_semantic_failure_class(message) for message in self.errors))

    def require_valid(self) -> Dict[str, Any]:
        if not self.valid:
            raise ScientificSemanticError("; ".join(self.errors))
        return dict(self.normalized_attributes)


@dataclass(frozen=True)
class SemanticCompatibilityReport:
    """Compatibility result for evolving one registry version to another."""

    compatible: bool
    breaking_changes: Tuple[str, ...]
    additions: Tuple[str, ...]
    warnings: Tuple[str, ...] = ()


@dataclass(frozen=True)
class SemanticStandardRelease:
    """Verified, language-neutral BNS-019 distribution consumed by this runtime."""

    root: Path
    version: str
    release_digest_sha256: str
    registry_document: Dict[str, Any]
    envelope_schema: Dict[str, Any]

    @classmethod
    def load(cls, root: Optional[Path | str] = None) -> "SemanticStandardRelease":
        standard_root = resolve_semantic_standard_root(root)
        manifest = _read_json_object(standard_root / "release-manifest.json", "release manifest")
        if manifest.get("schema") != _RELEASE_MANIFEST_SCHEMA:
            raise ScientificSemanticError("unsupported semantic standard release manifest schema")
        if manifest.get("standard_id") != _STANDARD_ID or manifest.get("artifact_name") != _ARTIFACT_NAME:
            raise ScientificSemanticError("semantic standard release identity mismatch")

        try:
            version = (standard_root / "VERSION").read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise ScientificSemanticError(f"cannot read semantic standard VERSION: {exc}") from exc
        if not version or manifest.get("version") != version:
            raise ScientificSemanticError("semantic standard release version mismatch")

        raw_records = manifest.get("files")
        if not isinstance(raw_records, list) or not raw_records:
            raise ScientificSemanticError("semantic standard manifest files must be a non-empty array")
        records: list[Dict[str, Any]] = []
        actual_paths: set[str] = set()
        for raw_record in raw_records:
            record = _as_plain_mapping(raw_record, label="release manifest file record")
            relative = _safe_manifest_path(str(record.get("path", "")))
            relative_text = relative.as_posix()
            if relative_text in actual_paths:
                raise ScientificSemanticError(f"duplicate semantic standard manifest path: {relative_text}")
            actual_paths.add(relative_text)
            target = standard_root.joinpath(*relative.parts)
            try:
                content = target.read_bytes()
            except OSError as exc:
                raise ScientificSemanticError(f"cannot read semantic standard file {relative_text}: {exc}") from exc
            if record.get("sha256") != hashlib.sha256(content).hexdigest():
                raise ScientificSemanticError(f"semantic standard SHA-256 mismatch: {relative_text}")
            if record.get("size_bytes") != len(content):
                raise ScientificSemanticError(f"semantic standard size mismatch: {relative_text}")
            records.append(record)
        distributed_paths = {
            path.relative_to(standard_root).as_posix()
            for path in standard_root.rglob("*")
            if path.is_file() and path.name != "release-manifest.json" and "__pycache__" not in path.parts
        }
        if actual_paths != distributed_paths:
            unlisted = sorted(distributed_paths - actual_paths)
            absent = sorted(actual_paths - distributed_paths)
            raise ScientificSemanticError(
                f"semantic standard manifest inventory mismatch; unlisted={unlisted}, absent={absent}"
            )
        expected_digest = _canonical_sha256(records)
        if manifest.get("release_digest_sha256") != expected_digest:
            raise ScientificSemanticError("semantic standard release_digest_sha256 mismatch")
        attestation_profile = _as_plain_mapping(
            manifest.get("attestation_profile"), label="semantic standard attestation_profile"
        )
        required_claims = _as_plain_mapping(
            attestation_profile.get("required_claims"),
            label="semantic standard attestation_profile.required_claims",
        )
        expected_profile = {
            "schema_version": "bionexus.evidence-attestation.v1",
            "predicate_type": "standard-release",
            "subject_type": "scientific-semantic-conventions-release",
            "subject_id": _STANDARD_ID,
            "subject_version": version,
        }
        for name, expected in expected_profile.items():
            if attestation_profile.get(name) != expected:
                raise ScientificSemanticError(f"semantic standard attestation_profile {name} mismatch")
        if required_claims.get("release_digest_sha256") != expected_digest:
            raise ScientificSemanticError("semantic standard attestation_profile release digest mismatch")

        required_paths = {
            "VERSION",
            "registry.json",
            "schemas/registry.schema.json",
            "schemas/envelope.schema.json",
            "schemas/conformance-manifest.schema.json",
            "conformance/manifest.json",
        }
        missing_paths = sorted(required_paths - actual_paths)
        if missing_paths:
            raise ScientificSemanticError(f"semantic standard is incomplete: missing {missing_paths}")

        registry = _read_json_object(standard_root / "registry.json", "semantic registry")
        registry_schema = _read_json_object(
            standard_root / "schemas" / "registry.schema.json", "semantic registry schema"
        )
        schema_errors = sorted(
            Draft202012Validator(registry_schema).iter_errors(registry), key=lambda error: list(error.path)
        )
        if schema_errors:
            raise ScientificSemanticError(
                "semantic registry schema violation: " + "; ".join(error.message for error in schema_errors)
            )
        if registry.get("schema_version") != version:
            raise ScientificSemanticError("semantic registry schema_version does not match release version")
        envelope_schema = _read_json_object(
            standard_root / "schemas" / "envelope.schema.json", "semantic envelope schema"
        )
        schema_url = registry.get("schema_url")
        if envelope_schema.get("properties", {}).get("schema_url", {}).get("const") != schema_url:
            raise ScientificSemanticError("semantic envelope schema is not bound to registry schema_url")
        conformance = _read_json_object(
            standard_root / "conformance" / "manifest.json", "semantic conformance manifest"
        )
        conformance_schema = _read_json_object(
            standard_root / "schemas" / "conformance-manifest.schema.json",
            "semantic conformance manifest schema",
        )
        conformance_errors = sorted(
            Draft202012Validator(conformance_schema).iter_errors(conformance),
            key=lambda error: list(error.path),
        )
        if conformance_errors:
            raise ScientificSemanticError(
                "semantic conformance manifest schema violation: "
                + "; ".join(error.message for error in conformance_errors)
            )
        if conformance.get("standard_version") != version:
            raise ScientificSemanticError("semantic conformance manifest version mismatch")
        case_ids: set[str] = set()
        for raw_case in conformance.get("cases", []):
            case = _as_plain_mapping(raw_case, label="semantic conformance case")
            case_id = str(case.get("id", ""))
            if case_id in case_ids:
                raise ScientificSemanticError(f"duplicate semantic conformance case id: {case_id}")
            case_ids.add(case_id)
            fixture_relative = _safe_manifest_path(f"conformance/{case.get('input', '')}")
            fixture_text = fixture_relative.as_posix()
            if fixture_text not in actual_paths:
                raise ScientificSemanticError(f"semantic conformance fixture is not distributed: {fixture_text}")
            fixture = _read_json_object(
                standard_root.joinpath(*fixture_relative.parts), f"semantic conformance fixture {case_id}"
            )
            if not isinstance(fixture.get("convention"), str) or not isinstance(fixture.get("attributes"), Mapping):
                raise ScientificSemanticError(f"semantic conformance fixture {case_id} is malformed")
        return cls(
            root=standard_root,
            version=version,
            release_digest_sha256=expected_digest,
            registry_document=registry,
            envelope_schema=envelope_schema,
        )


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _semantic_failure_class(message: str) -> str:
    if " is blocked:" in message:
        return "blocked_legacy_value"
    if message.startswith("missing required attribute:"):
        return "missing_required_attribute"
    if message.startswith("unknown attribute "):
        return "unknown_attribute"
    if message.startswith("unknown value for "):
        return "unknown_registered_value"
    if message.startswith("conflicting values supplied for "):
        return "conflicting_alias"
    if message.startswith("unknown convention group:"):
        return "unknown_convention"
    if " must be " in message or " must contain " in message:
        return "type_or_cardinality"
    return "semantic_validation_error"


def _read_json_object(path: Path, label: str) -> Dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ScientificSemanticError(f"cannot read {label}: {exc}") from exc
    return _as_plain_mapping(value, label=label)


def _safe_manifest_path(raw: str) -> PurePosixPath:
    path = PurePosixPath(raw)
    if path.is_absolute() or not path.parts or ".." in path.parts or "." in path.parts:
        raise ScientificSemanticError(f"unsafe semantic standard manifest path: {raw!r}")
    return path


def resolve_semantic_standard_root(root: Optional[Path | str] = None) -> Path:
    """Resolve the public standard distribution; never fall back to product data."""

    if root is not None:
        candidate = Path(root)
    else:
        configured = os.environ.get(SEMANTIC_STANDARD_ROOT_ENV)
        candidate = Path(configured) if configured else DEFAULT_SEMANTIC_STANDARD_ROOT
    resolved = candidate.expanduser().resolve()
    if not resolved.is_dir():
        raise ScientificSemanticError(
            f"BNS-019 standard distribution not found at {resolved}; "
            f"set {SEMANTIC_STANDARD_ROOT_ENV} to an unpacked verified release"
        )
    return resolved


def _as_plain_mapping(value: Any, *, label: str) -> Dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ScientificSemanticError(f"{label} must be an object")
    return {str(key): item for key, item in value.items()}


class ScientificSemanticRegistry:
    """Versioned registry and executable validation policy."""

    def __init__(
        self,
        document: Mapping[str, Any],
        *,
        release: Optional[SemanticStandardRelease] = None,
    ) -> None:
        self.document = _as_plain_mapping(document, label="semantic registry")
        self.release = release
        self.envelope_schema = dict(release.envelope_schema) if release is not None else None
        self.schema_version = str(self.document.get("schema_version", ""))
        self.schema_url = str(self.document.get("schema_url", ""))
        self.stability = str(self.document.get("stability", ""))
        self.attributes = _as_plain_mapping(self.document.get("attributes"), label="attributes")
        self.groups = _as_plain_mapping(self.document.get("groups"), label="groups")
        self.attribute_aliases = _as_plain_mapping(
            self.document.get("attribute_aliases", {}), label="attribute_aliases"
        )
        self.value_aliases = {
            str(name): _as_plain_mapping(aliases, label=f"value_aliases.{name}")
            for name, aliases in _as_plain_mapping(
                self.document.get("value_aliases", {}), label="value_aliases"
            ).items()
        }
        self.blocked_legacy_values = {
            str(name): _as_plain_mapping(values, label=f"blocked_legacy_values.{name}")
            for name, values in _as_plain_mapping(
                self.document.get("blocked_legacy_values", {}), label="blocked_legacy_values"
            ).items()
        }
        pattern = str(self.document.get("extension_namespace_pattern", ""))
        try:
            self.extension_namespace_pattern = re.compile(pattern)
        except re.error as exc:
            raise ScientificSemanticError(f"invalid extension_namespace_pattern: {exc}") from exc
        self.registry_sha256 = _canonical_sha256(self.document)
        self._validate_registry()

    @classmethod
    def load(cls, standard_root: Optional[Path | str] = None) -> "ScientificSemanticRegistry":
        release = SemanticStandardRelease.load(standard_root)
        return cls(release.registry_document, release=release)

    def _validate_registry(self) -> None:
        errors: list[str] = []
        if not self.schema_version or not self.schema_url:
            errors.append("schema_version and schema_url are required")
        if self.stability not in _STABILITY_ORDER:
            errors.append(f"unknown registry stability: {self.stability!r}")
        for name, raw_definition in self.attributes.items():
            if not _ATTRIBUTE_NAME.fullmatch(name):
                errors.append(f"invalid canonical attribute name: {name!r}")
                continue
            definition = _as_plain_mapping(raw_definition, label=f"attributes.{name}")
            value_type = definition.get("type")
            cardinality = definition.get("cardinality")
            if (value_type, cardinality) not in {("string", "one"), ("string_array", "many")}:
                errors.append(f"{name} has inconsistent type/cardinality")
            if definition.get("stability") not in _STABILITY_ORDER:
                errors.append(f"{name} has unknown stability")
            values = definition.get("values")
            if not isinstance(values, list) or not values or len(values) != len(set(values)):
                errors.append(f"{name} values must be a non-empty unique list")
        for group_id, raw_group in self.groups.items():
            if not _ATTRIBUTE_NAME.fullmatch(group_id):
                errors.append(f"invalid group id: {group_id!r}")
                continue
            group = _as_plain_mapping(raw_group, label=f"groups.{group_id}")
            if group.get("stability") not in _STABILITY_ORDER:
                errors.append(f"{group_id} has unknown stability")
            requirements = _as_plain_mapping(group.get("attributes"), label=f"groups.{group_id}.attributes")
            for name, requirement in requirements.items():
                if name not in self.attributes:
                    errors.append(f"{group_id} references unknown attribute {name}")
                if requirement not in {"required", "recommended", "opt_in"}:
                    errors.append(f"{group_id}.{name} has unknown requirement {requirement!r}")
        for alias, target in self.attribute_aliases.items():
            if target not in self.attributes:
                errors.append(f"attribute alias {alias!r} targets unknown attribute {target!r}")
        if errors:
            raise ScientificSemanticError("; ".join(errors))

    def inventory(self) -> Dict[str, Any]:
        inventory = {
            "schema_version": self.schema_version,
            "schema_url": self.schema_url,
            "stability": self.stability,
            "registry_sha256": self.registry_sha256,
            "attributes": sorted(self.attributes),
            "groups": sorted(self.groups),
        }
        if self.release is not None:
            inventory["standard_id"] = _STANDARD_ID
            inventory["release_digest_sha256"] = self.release.release_digest_sha256
            inventory["standard_root"] = str(self.release.root)
        return inventory

    def validate_attributes(
        self,
        convention: str,
        attributes: Mapping[str, Any],
        *,
        mode: SemanticValidationMode | str = SemanticValidationMode.PRODUCER,
    ) -> SemanticValidationReport:
        try:
            validation_mode = SemanticValidationMode(mode)
        except ValueError as exc:
            raise ScientificSemanticError(f"unknown validation mode: {mode!r}") from exc
        if convention not in self.groups:
            return SemanticValidationReport(False, {}, (f"unknown convention group: {convention}",))
        if not isinstance(attributes, Mapping):
            return SemanticValidationReport(False, {}, ("attributes must be an object",))

        errors: list[str] = []
        warnings: list[str] = []
        canonical: Dict[str, Any] = {}
        for supplied_name, supplied_value in attributes.items():
            name = str(supplied_name)
            target = str(self.attribute_aliases.get(name, name))
            if target in canonical and canonical[target] != supplied_value:
                errors.append(f"conflicting values supplied for {target} through an alias")
                continue
            canonical[target] = supplied_value

        normalized: Dict[str, Any] = {}
        for name in sorted(canonical):
            value = canonical[name]
            if name not in self.attributes:
                if self.extension_namespace_pattern.fullmatch(name):
                    extension_value, extension_error = self._normalize_extension(name, value)
                    if extension_error:
                        errors.append(extension_error)
                    else:
                        normalized[name] = extension_value
                    continue
                if validation_mode == SemanticValidationMode.CONSUMER and _ATTRIBUTE_NAME.fullmatch(name):
                    normalized[name] = value
                    warnings.append(f"unknown future attribute preserved: {name}")
                    continue
                errors.append(f"unknown attribute {name}; custom attributes must use x.<vendor>.*")
                continue
            definition = _as_plain_mapping(self.attributes[name], label=f"attributes.{name}")
            item, item_errors, item_warnings = self._normalize_registered_value(
                name, value, definition, validation_mode
            )
            errors.extend(item_errors)
            warnings.extend(item_warnings)
            if not item_errors:
                normalized[name] = item

        requirements = _as_plain_mapping(
            _as_plain_mapping(self.groups[convention], label=f"groups.{convention}").get("attributes"),
            label=f"groups.{convention}.attributes",
        )
        for name, requirement in requirements.items():
            if requirement == "required" and name not in normalized:
                errors.append(f"missing required attribute: {name}")
            elif requirement == "recommended" and name not in normalized:
                warnings.append(f"missing recommended attribute: {name}")
        return SemanticValidationReport(not errors, normalized, tuple(errors), tuple(warnings))

    def _normalize_extension(self, name: str, value: Any) -> Tuple[Any, Optional[str]]:
        if isinstance(value, str):
            return value, None
        if isinstance(value, (list, tuple)) and all(isinstance(item, str) for item in value):
            return sorted(set(value)), None
        return None, f"extension attribute {name} must be a string or string array"

    def _normalize_registered_value(
        self,
        name: str,
        value: Any,
        definition: Mapping[str, Any],
        mode: SemanticValidationMode,
    ) -> Tuple[Any, list[str], list[str]]:
        errors: list[str] = []
        warnings: list[str] = []
        many = definition.get("cardinality") == "many"
        if many:
            if not isinstance(value, (list, tuple)) or isinstance(value, str):
                return None, [f"{name} must be a string array"], warnings
            if not value:
                return None, [f"{name} must contain at least one value"], warnings
            if not all(isinstance(item, str) for item in value):
                return None, [f"{name} must contain only strings"], warnings
            raw_values: Sequence[str] = value
        else:
            if not isinstance(value, str):
                return None, [f"{name} must be a string"], warnings
            raw_values = (value,)

        allowed = set(definition.get("values", []))
        aliases = self.value_aliases.get(name, {})
        blocked = self.blocked_legacy_values.get(name, {})
        output: list[str] = []
        for raw in raw_values:
            if raw in blocked:
                errors.append(f"{name}={raw!r} is blocked: {blocked[raw]}")
                continue
            normalized_value = str(aliases.get(raw, raw))
            if normalized_value not in allowed:
                if mode == SemanticValidationMode.PRODUCER:
                    errors.append(f"unknown value for {name}: {normalized_value!r}")
                    continue
                warnings.append(f"unknown future value preserved for {name}: {normalized_value!r}")
            output.append(normalized_value)
        if errors:
            return None, errors, warnings
        if many:
            return sorted(set(output)), errors, warnings
        return output[0], errors, warnings

    def compare_to(self, previous: "ScientificSemanticRegistry") -> SemanticCompatibilityReport:
        """Check whether this registry is a compatible successor to ``previous``."""

        breaking: list[str] = []
        additions: list[str] = []
        warnings: list[str] = []
        if self.schema_url == previous.schema_url and self.registry_sha256 != previous.registry_sha256:
            breaking.append("registry content changed without changing schema_url")
        if _STABILITY_ORDER[self.stability] < _STABILITY_ORDER[previous.stability]:
            breaking.append(f"registry stability regressed: {previous.stability} -> {self.stability}")

        for name, old_raw in previous.attributes.items():
            if name not in self.attributes:
                breaking.append(f"removed attribute: {name}")
                continue
            old = _as_plain_mapping(old_raw, label=f"previous.attributes.{name}")
            new = _as_plain_mapping(self.attributes[name], label=f"attributes.{name}")
            for field in ("type", "cardinality"):
                if new.get(field) != old.get(field):
                    breaking.append(f"changed {field} for {name}: {old.get(field)} -> {new.get(field)}")
            if _STABILITY_ORDER[str(new.get("stability"))] < _STABILITY_ORDER[str(old.get("stability"))]:
                breaking.append(f"stability regressed for {name}")
            old_values = set(old.get("values", []))
            new_values = set(new.get("values", []))
            for removed in sorted(old_values - new_values):
                breaking.append(f"removed value {name}={removed}")
            for added in sorted(new_values - old_values):
                additions.append(f"added value {name}={added}")
        for name in sorted(set(self.attributes) - set(previous.attributes)):
            additions.append(f"added attribute: {name}")

        for group_id, old_raw in previous.groups.items():
            if group_id not in self.groups:
                breaking.append(f"removed group: {group_id}")
                continue
            old_req = _as_plain_mapping(
                _as_plain_mapping(old_raw, label=f"previous.groups.{group_id}").get("attributes"),
                label=f"previous.groups.{group_id}.attributes",
            )
            new_req = _as_plain_mapping(
                _as_plain_mapping(self.groups[group_id], label=f"groups.{group_id}").get("attributes"),
                label=f"groups.{group_id}.attributes",
            )
            for name, old_requirement in old_req.items():
                if name not in new_req:
                    breaking.append(f"removed {group_id} attribute reference: {name}")
                elif old_requirement != "required" and new_req[name] == "required":
                    breaking.append(f"made {group_id}.{name} required")
            for name, requirement in new_req.items():
                if name not in old_req:
                    message = f"added {group_id} attribute {name} ({requirement})"
                    if requirement == "required":
                        breaking.append(message)
                    else:
                        additions.append(message)
        for group_id in sorted(set(self.groups) - set(previous.groups)):
            additions.append(f"added group: {group_id}")
        return SemanticCompatibilityReport(not breaking, tuple(breaking), tuple(additions), tuple(warnings))


@dataclass(frozen=True)
class ScientificSemanticEnvelope:
    """Portable, fingerprinted scientific meaning attached to a result."""

    schema_url: str
    convention: str
    producer: str
    attributes: Dict[str, Any]
    semantic_fingerprint_sha256: str
    record_id: Optional[str] = None
    source_record_sha256: Optional[str] = None

    @classmethod
    def create(
        cls,
        convention: str,
        producer: str,
        attributes: Mapping[str, Any],
        *,
        record_id: Optional[str] = None,
        source_record_sha256: Optional[str] = None,
        registry: Optional[ScientificSemanticRegistry] = None,
    ) -> "ScientificSemanticEnvelope":
        active_registry = registry or default_scientific_semantic_registry()
        normalized = active_registry.validate_attributes(
            convention, attributes, mode=SemanticValidationMode.PRODUCER
        ).require_valid()
        payload = {
            "schema_url": active_registry.schema_url,
            "convention": convention,
            "producer": producer,
            "record_id": record_id,
            "source_record_sha256": source_record_sha256,
            "attributes": normalized,
        }
        fingerprint = _canonical_sha256(payload)
        return cls(semantic_fingerprint_sha256=fingerprint, **payload)

    @classmethod
    def from_dict(
        cls,
        payload: Mapping[str, Any],
        *,
        registry: Optional[ScientificSemanticRegistry] = None,
        mode: SemanticValidationMode | str = SemanticValidationMode.CONSUMER,
    ) -> Tuple["ScientificSemanticEnvelope", SemanticValidationReport]:
        data = dict(payload)
        active_registry = registry or default_scientific_semantic_registry()
        if active_registry.envelope_schema is None:
            raise ScientificSemanticError(
                "envelope validation requires a registry loaded from a verified BNS-019 release"
            )
        schema = active_registry.envelope_schema
        shape_errors = sorted(Draft202012Validator(schema).iter_errors(data), key=lambda error: list(error.path))
        if shape_errors:
            raise ScientificSemanticError("; ".join(error.message for error in shape_errors))
        expected = str(data.pop("semantic_fingerprint_sha256"))
        actual = _canonical_sha256(data)
        if actual != expected:
            raise ScientificSemanticError("semantic_fingerprint_sha256 does not match envelope content")
        if data["schema_url"] != active_registry.schema_url:
            raise ScientificSemanticError(
                f"schema_url mismatch: {data['schema_url']!r} != {active_registry.schema_url!r}"
            )
        report = active_registry.validate_attributes(data["convention"], data["attributes"], mode=mode)
        if not report.valid:
            raise ScientificSemanticError("; ".join(report.errors))
        if report.normalized_attributes != data["attributes"]:
            raise ScientificSemanticError(
                "fingerprinted envelope attributes are not canonical; aliases may be normalized only before creation"
            )
        envelope = cls(
            schema_url=data["schema_url"],
            convention=data["convention"],
            producer=data["producer"],
            record_id=data.get("record_id"),
            source_record_sha256=data.get("source_record_sha256"),
            attributes=report.normalized_attributes,
            semantic_fingerprint_sha256=expected,
        )
        return envelope, report

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_url": self.schema_url,
            "convention": self.convention,
            "producer": self.producer,
            "record_id": self.record_id,
            "source_record_sha256": self.source_record_sha256,
            "attributes": dict(self.attributes),
            "semantic_fingerprint_sha256": self.semantic_fingerprint_sha256,
        }


def default_scientific_semantic_registry() -> ScientificSemanticRegistry:
    """Load and verify the current public standard release.

    The small distribution is intentionally reverified on every load so a
    process cannot silently continue after an on-disk contract is replaced or
    tampered with.
    """

    return ScientificSemanticRegistry.load()


def warrant_semantics_from_maturity(maturity: ConclusionMaturity | str) -> Tuple[str, str]:
    """Map maturity without pretending that abstention/conflict are ordinal support."""

    value = maturity.value if isinstance(maturity, ConclusionMaturity) else str(maturity).upper()
    mapping = {
        "UNASSESSED": ("unassessed", "unassessed"),
        "ABSTAIN": ("unassessed", "abstained"),
        "FRAGILE": ("fragile", "assessed"),
        "CONFLICTED": ("fragile", "conflicted"),
        "PRELIMINARY": ("preliminary", "assessed"),
        "SUPPORTED": ("supported", "assessed"),
        "ROBUST": ("robust", "assessed"),
        "REPLICATED": ("replicated", "assessed"),
    }
    try:
        return mapping[value]
    except KeyError as exc:
        raise ScientificSemanticError(f"unknown conclusion maturity: {maturity!r}") from exc


def matrix_state_from_legacy(value: str) -> str:
    """Translate only lossless ABI matrix states; ambiguity is a hard error."""

    mapping = {
        "raw_counts": "raw_counts",
        "scaled_expression": "scaled",
        "normalized_counts": "normalized_counts",
        "log_normalized": "log_normalized",
    }
    if value == "normalized_expression":
        raise ScientificSemanticError(
            "normalized_expression is ambiguous; declare normalized_counts or log_normalized explicitly"
        )
    try:
        return mapping[value]
    except KeyError as exc:
        raise ScientificSemanticError(f"unknown matrix state: {value!r}") from exc


def spatial_battery_semantic_envelope(result: Any, data: Any) -> ScientificSemanticEnvelope:
    """Create the first native convention producer from a spatial battery result."""

    level, status = warrant_semantics_from_maturity(result.verdict.verdict)
    diagnostic_names = set(result.diagnostics)
    confound_mapping = {
        "segmentation_uncertainty": "segmentation",
        "transcript_leakage": "transcript_leakage",
        "cell_size": "cell_size",
        "nuclear_eccentricity": "nuclear_eccentricity",
        "transcript_density": "spatial_density",
        "local_cell_density": "spatial_density",
        "contact_geometry": "contact_geometry",
        "batch_fov": "batch",
        "neighborhood_radius": "neighborhood_definition",
        "cell_label_perturbation": "cell_label",
        "spatial_autocorrelation": "spatial_autocorrelation",
    }
    confounds = sorted({value for key, value in confound_mapping.items() if key in diagnostic_names})
    attributes = {
        "biological.unit": "cell" if data.resolution == "cell" else "spot",
        "matrix.state": "raw_counts" if data.expression_scale == "counts" else "log_normalized",
        "claim.type": "associative",
        "evidence.type": ["computational_result"],
        "confound.type": confounds,
        "warrant.level": level,
        "warrant.status": status,
    }
    return ScientificSemanticEnvelope.create(
        "scientific.observation",
        "bionexus.spatial.inference_validity",
        attributes,
        record_id=result.observation.observation_id,
        source_record_sha256=result.provenance.get("battery_run_sha256"),
    )
