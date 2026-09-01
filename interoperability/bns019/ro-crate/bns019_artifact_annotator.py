#!/usr/bin/env python3
"""Attach explicit BNS-019 semantics to artifacts already described by RO-Crate.

This zero-touch adapter never runs or modifies a workflow, parses a samplesheet,
or infers scientific meaning from filenames, numeric content, workflow success,
or provenance shape.  The producer must explicitly declare every annotation.
Unlisted crate entities remain unannotated.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import unquote, urlparse


class AnnotationError(RuntimeError):
    """Input cannot produce an unambiguous, hash-bound annotation manifest."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_validator(path: Path):
    spec = importlib.util.spec_from_file_location("bns019_rocrate_validator", path)
    if spec is None or spec.loader is None:
        raise AnnotationError(f"cannot load BNS-019 validator: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AnnotationError(f"cannot read {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise AnnotationError(f"{label} must be a JSON object")
    return value


def contained_entity_path(crate_root: Path, entity_id: str) -> Path | None:
    parsed = urlparse(entity_id)
    if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
        return None
    candidate = (crate_root / unquote(parsed.path)).resolve()
    try:
        candidate.relative_to(crate_root.resolve())
    except ValueError as exc:
        raise AnnotationError(f"artifact entity escapes crate root: {entity_id}") from exc
    return candidate


def authoritative_artifact_sha(crate_root: Path, entity_id: str, entity: Mapping[str, Any]) -> str:
    declared = entity.get("sha256")
    if declared is not None and (
        not isinstance(declared, str)
        or len(declared) != 64
        or any(ch not in "0123456789abcdefABCDEF" for ch in declared)
    ):
        raise AnnotationError(f"crate entity {entity_id!r} has an invalid sha256 value")

    local_path = contained_entity_path(crate_root, entity_id)
    observed = sha256_file(local_path) if local_path is not None and local_path.is_file() else None
    if declared and observed and declared.lower() != observed.lower():
        raise AnnotationError(f"crate sha256 does not match artifact bytes: {entity_id}")
    digest = observed or (declared.lower() if isinstance(declared, str) else None)
    if not digest:
        raise AnnotationError(
            f"artifact {entity_id!r} is not locally hashable and has no authoritative crate sha256"
        )
    return digest


def build_manifest(
    *,
    validator_path: Path,
    standard_root: Path,
    crate_metadata: Path,
    declarations_path: Path,
) -> dict[str, Any]:
    validator = load_validator(validator_path)
    try:
        release, registry = validator.load_verified_release(standard_root)
    except (OSError, RuntimeError, KeyError, json.JSONDecodeError) as exc:
        raise AnnotationError(str(exc)) from exc

    crate = read_object(crate_metadata, "RO-Crate metadata")
    graph = crate.get("@graph")
    if not isinstance(graph, list) or not graph:
        raise AnnotationError("RO-Crate metadata must contain a non-empty @graph")
    entities: dict[str, Mapping[str, Any]] = {}
    for item in graph:
        if not isinstance(item, Mapping) or not isinstance(item.get("@id"), str):
            raise AnnotationError("every RO-Crate @graph entity must be an object with string @id")
        entity_id = item["@id"]
        if entity_id in entities:
            raise AnnotationError(f"duplicate RO-Crate entity id: {entity_id}")
        entities[entity_id] = item

    declarations = read_object(declarations_path, "artifact semantic declarations")
    if declarations.get("schema_version") != "bionexus.bns019-artifact-declarations.v1":
        raise AnnotationError("unsupported artifact declaration schema_version")
    if "attributes" in declarations:
        raise AnnotationError("run-level attributes are forbidden; declare semantics per artifact")
    producer = declarations.get("producer")
    if not isinstance(producer, str) or not producer.strip():
        raise AnnotationError("declarations require a named producer")
    requested = declarations.get("annotations")
    if not isinstance(requested, list):
        raise AnnotationError("declarations require an annotations array")

    crate_root = crate_metadata.resolve().parent
    annotations: list[dict[str, Any]] = []
    seen: set[str] = set()
    for position, declaration in enumerate(requested):
        if not isinstance(declaration, Mapping):
            raise AnnotationError(f"annotation {position} must be an object")
        entity_id = declaration.get("entity_id")
        if not isinstance(entity_id, str) or not entity_id:
            raise AnnotationError(f"annotation {position} requires entity_id")
        if entity_id in seen:
            raise AnnotationError(f"duplicate semantic annotation for entity: {entity_id}")
        seen.add(entity_id)
        if entity_id not in entities:
            raise AnnotationError(f"semantic annotation references an unknown crate entity: {entity_id}")

        observed_sha = authoritative_artifact_sha(crate_root, entity_id, entities[entity_id])
        expected_sha = declaration.get("expected_sha256")
        if not isinstance(expected_sha, str) or expected_sha.lower() != observed_sha:
            raise AnnotationError(f"expected_sha256 does not bind the authoritative artifact: {entity_id}")

        convention = declaration.get("convention")
        attributes = declaration.get("attributes")
        if not isinstance(convention, str) or not isinstance(attributes, Mapping):
            raise AnnotationError(f"annotation {entity_id!r} requires convention and attributes")
        report = validator.validate_attributes(registry, convention, attributes)
        if not report["valid"]:
            raise AnnotationError(f"invalid BNS-019 attributes for {entity_id}: {'; '.join(report['errors'])}")
        envelope = {
            "schema_url": registry["schema_url"],
            "convention": convention,
            "producer": producer,
            "record_id": entity_id,
            "source_record_sha256": observed_sha,
            "attributes": report["normalized_attributes"],
        }
        envelope["semantic_fingerprint_sha256"] = hashlib.sha256(
            validator.canonical_json(envelope)
        ).hexdigest()
        annotations.append(
            {
                "entity_id": entity_id,
                "artifact_sha256": observed_sha,
                "semantic_envelope": envelope,
                "warnings": report["warnings"],
            }
        )

    observable_entities = sorted(
        entity_id
        for entity_id in entities
        if entity_id not in seen and contained_entity_path(crate_root, entity_id) is not None
    )
    metadata_entity = entities.get("ro-crate-metadata.json")
    about = metadata_entity.get("about") if isinstance(metadata_entity, Mapping) else None
    root_entity_id = about.get("@id") if isinstance(about, Mapping) else None
    return {
        "schema_version": "bionexus.bns019-artifact-annotation-manifest.v1",
        "provenance_container": {
            "kind": "RO-Crate",
            "metadata_path": crate_metadata.name,
            "metadata_sha256": sha256_file(crate_metadata),
            "root_entity_id": root_entity_id,
            "mutated": False,
        },
        "standard": {
            "id": "BNS-019",
            "version": release["version"],
            "release_digest_sha256": release["release_digest_sha256"],
        },
        "producer": producer,
        "annotations": annotations,
        "unannotated_entities_observed": observable_entities,
        "inference_policy": "EXPLICIT_ONLY_NO_FILENAME_CONTENT_OR_WORKFLOW_SHAPE_INFERENCE",
        "claim_boundary": (
            "RO-Crate remains authoritative for what ran. This optional manifest records only "
            "producer-declared semantics for individually hash-bound artifacts; unlisted entities "
            "remain unassessed and workflow success creates no scientific warrant."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validator", type=Path, required=True)
    parser.add_argument("--standard-root", type=Path, required=True)
    parser.add_argument("--crate", type=Path, required=True, help="Path to ro-crate-metadata.json")
    parser.add_argument("--declarations", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = build_manifest(
            validator_path=args.validator,
            standard_root=args.standard_root,
            crate_metadata=args.crate,
            declarations_path=args.declarations,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    except (AnnotationError, OSError, RuntimeError, KeyError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
