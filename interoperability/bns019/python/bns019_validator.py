#!/usr/bin/env python3
"""Independent, standard-library-only BNS-019 producer validator.

This implementation intentionally does not import ``bionexus``.  It verifies
the language-neutral release manifest, reads the public registry, and executes
the published producer conformance cases.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

MANIFEST_SCHEMA = "urn:bionexus:scientific-semantic-release-manifest:1"
RESULT_SCHEMA = "urn:bionexus:bns019-implementation-result:1"
STANDARD_ID = "BNS-019"
ARTIFACT_NAME = "bionexus-scientific-semantic-conventions"
ATTRIBUTE_NAME = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")


class ValidationError(RuntimeError):
    """Release or suite failure that prevents a conformance conclusion."""


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_relative_path(raw: str) -> PurePosixPath:
    path = PurePosixPath(raw)
    if path.is_absolute() or not path.parts or "." in path.parts or ".." in path.parts:
        raise ValidationError(f"unsafe manifest path: {raw!r}")
    return path


def read_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"cannot read {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValidationError(f"{label} must be a JSON object")
    return value


def load_verified_release(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    root = root.resolve()
    manifest = read_object(root / "release-manifest.json", "release manifest")
    if manifest.get("schema") != MANIFEST_SCHEMA:
        raise ValidationError("unsupported release manifest schema")
    if manifest.get("standard_id") != STANDARD_ID or manifest.get("artifact_name") != ARTIFACT_NAME:
        raise ValidationError("release identity mismatch")
    version_path = root / "VERSION"
    try:
        version = version_path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise ValidationError(f"cannot read VERSION: {exc}") from exc
    if not version or manifest.get("version") != version:
        raise ValidationError("release version mismatch")

    records = manifest.get("files")
    if not isinstance(records, list) or not records:
        raise ValidationError("manifest files must be a non-empty array")
    seen: set[str] = set()
    for record in records:
        if not isinstance(record, dict):
            raise ValidationError("manifest file record must be an object")
        relative = safe_relative_path(str(record.get("path", "")))
        relative_text = relative.as_posix()
        if relative_text in seen:
            raise ValidationError(f"duplicate manifest path: {relative_text}")
        seen.add(relative_text)
        path = root.joinpath(*relative.parts)
        if not path.is_file():
            raise ValidationError(f"manifest file is missing: {relative_text}")
        if record.get("sha256") != sha256_file(path):
            raise ValidationError(f"SHA-256 mismatch: {relative_text}")
        if record.get("size_bytes") != path.stat().st_size:
            raise ValidationError(f"size mismatch: {relative_text}")

    distributed = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path.name != "release-manifest.json" and "__pycache__" not in path.parts
    }
    if seen != distributed:
        raise ValidationError(
            f"manifest inventory mismatch; unlisted={sorted(distributed - seen)}, absent={sorted(seen - distributed)}"
        )
    expected_digest = hashlib.sha256(canonical_json(records)).hexdigest()
    if manifest.get("release_digest_sha256") != expected_digest:
        raise ValidationError("release_digest_sha256 mismatch")

    registry = read_object(root / "registry.json", "registry")
    if registry.get("schema_version") != version:
        raise ValidationError("registry version mismatch")
    return manifest, registry


def _failure_class(message: str) -> str:
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


def validate_attributes(registry: Mapping[str, Any], convention: str, attributes: Mapping[str, Any]) -> dict[str, Any]:
    groups = registry.get("groups", {})
    definitions = registry.get("attributes", {})
    if convention not in groups:
        errors = [f"unknown convention group: {convention}"]
        return _report({}, errors, [])
    if not isinstance(attributes, Mapping):
        return _report({}, ["attributes must be an object"], [])

    aliases = registry.get("attribute_aliases", {})
    canonical: dict[str, Any] = {}
    errors: list[str] = []
    warnings: list[str] = []
    for supplied_name, supplied_value in attributes.items():
        name = str(supplied_name)
        target = str(aliases.get(name, name))
        if target in canonical and canonical[target] != supplied_value:
            errors.append(f"conflicting values supplied for {target} through an alias")
            continue
        canonical[target] = supplied_value

    extension_pattern = re.compile(str(registry.get("extension_namespace_pattern", "")))
    normalized: dict[str, Any] = {}
    for name in sorted(canonical):
        value = canonical[name]
        if name not in definitions:
            if extension_pattern.fullmatch(name):
                if isinstance(value, str):
                    normalized[name] = value
                elif isinstance(value, list) and all(isinstance(item, str) for item in value):
                    normalized[name] = sorted(set(value))
                else:
                    errors.append(f"extension attribute {name} must be a string or string array")
            else:
                errors.append(f"unknown attribute {name}; custom attributes must use x.<vendor>.*")
            continue

        definition = definitions[name]
        many = definition.get("cardinality") == "many"
        if many:
            if not isinstance(value, list):
                errors.append(f"{name} must be a string array")
                continue
            if not value:
                errors.append(f"{name} must contain at least one value")
                continue
            if not all(isinstance(item, str) for item in value):
                errors.append(f"{name} must contain only strings")
                continue
            values = value
        else:
            if not isinstance(value, str):
                errors.append(f"{name} must be a string")
                continue
            values = [value]

        allowed = set(definition.get("values", []))
        value_aliases = registry.get("value_aliases", {}).get(name, {})
        blocked = registry.get("blocked_legacy_values", {}).get(name, {})
        output: list[str] = []
        item_errors: list[str] = []
        for raw in values:
            if raw in blocked:
                item_errors.append(f"{name}={raw!r} is blocked: {blocked[raw]}")
                continue
            item = str(value_aliases.get(raw, raw))
            if item not in allowed:
                item_errors.append(f"unknown value for {name}: {item!r}")
                continue
            output.append(item)
        errors.extend(item_errors)
        if not item_errors:
            normalized[name] = sorted(set(output)) if many else output[0]

    requirements = groups[convention].get("attributes", {})
    for name, requirement in requirements.items():
        if requirement == "required" and name not in normalized:
            errors.append(f"missing required attribute: {name}")
        elif requirement == "recommended" and name not in normalized:
            warnings.append(f"missing recommended attribute: {name}")
    return _report(normalized, errors, warnings)


def _report(normalized: dict[str, Any], errors: list[str], warnings: list[str]) -> dict[str, Any]:
    failure_classes = list(dict.fromkeys(_failure_class(message) for message in errors))
    return {
        "valid": not errors,
        "normalized_attributes": normalized,
        "failure_classes": failure_classes,
        "errors": errors,
        "warnings": warnings,
    }


def run_conformance_suite(standard_root: Path) -> dict[str, Any]:
    manifest, registry = load_verified_release(standard_root)
    conformance_root = standard_root.resolve() / "conformance"
    suite = read_object(conformance_root / "manifest.json", "conformance manifest")
    case_results: list[dict[str, Any]] = []
    for case in suite.get("cases", []):
        fixture = read_object(conformance_root / str(case["input"]), f"case {case['id']}")
        observed = validate_attributes(registry, fixture.get("convention", ""), fixture.get("attributes", {}))
        matched = observed["valid"] is case["expected_valid"]
        if case["expected_valid"]:
            matched = matched and observed["normalized_attributes"] == case["expected_normalized_attributes"]
        else:
            matched = matched and case["expected_failure_class"] in observed["failure_classes"]
        case_results.append(
            {
                "case_id": case["id"],
                "status": "PASS" if matched else "FAIL",
                "expected_valid": case["expected_valid"],
                "observed_valid": observed["valid"],
                "normalized_attributes": observed["normalized_attributes"],
                "failure_classes": observed["failure_classes"],
            }
        )
    status = "PASS" if case_results and all(case["status"] == "PASS" for case in case_results) else "FAIL"
    return {
        "schema": RESULT_SCHEMA,
        "implementation": {
            "id": "bns019-python-stdlib",
            "track": "independent_validator",
            "language": "python",
        },
        "standard": {
            "id": STANDARD_ID,
            "version": manifest["version"],
            "release_digest_sha256": manifest["release_digest_sha256"],
        },
        "status": status,
        "case_results": case_results,
        "claim_boundary": "Software-contract conformance only; not certification or biological validation.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--standard-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        result = run_conformance_suite(args.standard_root)
    except ValidationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    payload = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.write_text(payload, encoding="utf-8", newline="\n")
    else:
        print(payload, end="")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
