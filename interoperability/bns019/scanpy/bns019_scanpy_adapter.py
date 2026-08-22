#!/usr/bin/env python3
"""Attach a verified BNS-019 envelope to Scanpy's AnnData interchange object.

The adapter changes only ``adata.uns``. It does not inspect, normalize, or
modify ``X``, ``obs``, ``var``, layers, embeddings, or biological labels.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

INTEROP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(INTEROP_ROOT / "python"))

from bns019_validator import (  # noqa: E402
    ValidationError,
    canonical_json,
    load_verified_release,
    read_object,
    sha256_file,
    validate_attributes,
)

HOST_KEY = "bionexus"
ENVELOPE_KEY = "scientific_semantic_envelope_json"
RELEASE_DIGEST_KEY = "bns019_release_digest_sha256"


def build_envelope(
    registry: dict[str, Any],
    convention: str,
    attributes: dict[str, Any],
    producer: str,
    record_id: str | None,
    source_record_sha256: str | None,
) -> dict[str, Any]:
    report = validate_attributes(registry, convention, attributes)
    if not report["valid"]:
        raise ValidationError("; ".join(report["errors"]))
    payload = {
        "schema_url": registry["schema_url"],
        "convention": convention,
        "producer": producer,
        "record_id": record_id,
        "source_record_sha256": source_record_sha256,
        "attributes": report["normalized_attributes"],
    }
    payload["semantic_fingerprint_sha256"] = hashlib.sha256(canonical_json(payload)).hexdigest()
    return payload


def attach_semantics(
    adata: Any,
    *,
    standard_root: Path,
    convention: str,
    attributes: dict[str, Any],
    producer: str,
    record_id: str | None = None,
    source_record_sha256: str | None = None,
) -> dict[str, Any]:
    manifest, registry = load_verified_release(standard_root)
    envelope = build_envelope(
        registry,
        convention,
        attributes,
        producer,
        record_id,
        source_record_sha256,
    )
    existing = adata.uns.get(HOST_KEY, {})
    if existing is None:
        existing = {}
    if not isinstance(existing, dict):
        raise ValidationError(f"adata.uns[{HOST_KEY!r}] already exists and is not a mapping")
    namespace = dict(existing)
    namespace[RELEASE_DIGEST_KEY] = manifest["release_digest_sha256"]
    namespace[ENVELOPE_KEY] = canonical_json(envelope).decode("utf-8")
    adata.uns[HOST_KEY] = namespace
    return envelope


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--standard-root", type=Path, required=True)
    parser.add_argument("--semantics", type=Path, required=True)
    parser.add_argument("--producer", default="bns019.interop.scanpy")
    parser.add_argument("--record-id")
    parser.add_argument("--result", type=Path)
    args = parser.parse_args(argv)

    try:
        import anndata as ad

        semantic_input = read_object(args.semantics, "semantic input")
        source_sha256 = sha256_file(args.input)
        adata = ad.read_h5ad(args.input)
        shape_before = tuple(adata.shape)
        envelope = attach_semantics(
            adata,
            standard_root=args.standard_root,
            convention=str(semantic_input.get("convention", "")),
            attributes=semantic_input.get("attributes", {}),
            producer=args.producer,
            record_id=args.record_id,
            source_record_sha256=source_sha256,
        )
        if tuple(adata.shape) != shape_before:
            raise ValidationError("adapter changed the AnnData shape")
        adata.write_h5ad(args.output)
        round_trip = ad.read_h5ad(args.output)
        stored = round_trip.uns[HOST_KEY]
        stored_envelope = json.loads(str(stored[ENVELOPE_KEY]))
        if stored_envelope != envelope:
            raise ValidationError("AnnData round trip changed the semantic envelope")
        result = {
            "schema": "urn:bionexus:bns019-host-adapter-result:1",
            "implementation": {
                "id": "bns019-scanpy-anndata-adapter",
                "track": "host_adapter",
                "host": "scanpy_anndata",
            },
            "standard": {
                "id": "BNS-019",
                "version": envelope["schema_url"].rsplit(":", 1)[-1],
                "release_digest_sha256": str(stored[RELEASE_DIGEST_KEY]),
            },
            "status": "PASS",
            "checks": {
                "registry_verified": True,
                "uns_only_contract": True,
                "shape_preserved": True,
                "anndata_h5ad_round_trip": True,
                "fingerprint_preserved": True,
            },
            "claim_boundary": "Metadata interoperability only; no Scanpy analysis or biological result was validated.",
        }
    except (ImportError, KeyError, OSError, ValidationError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    payload = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.result:
        args.result.write_text(payload, encoding="utf-8", newline="\n")
    else:
        print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
