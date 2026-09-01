#!/usr/bin/env python3
"""Frozen adapter core for the historical standalone Nextflow trial fixture.

This is not a supported nf-core integration surface. New workflow work consumes
an existing RO-Crate with the zero-touch artifact annotator under ../ro-crate/.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path


def load_validator(path: Path):
    spec = importlib.util.spec_from_file_location("bns019_trial_validator", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load validator: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validator", type=Path, required=True)
    parser.add_argument("--standard-root", type=Path, required=True)
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--semantics", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--versions", type=Path, required=True)
    parser.add_argument("--producer", default="bns019.interop.nfcore")
    args = parser.parse_args(argv)

    try:
        validator = load_validator(args.validator)
        manifest, registry = validator.load_verified_release(args.standard_root)
        record = validator.read_object(args.record, "workflow record")
        semantic_input = validator.read_object(args.semantics, "semantic input")
        report = validator.validate_attributes(
            registry,
            str(semantic_input.get("convention", "")),
            semantic_input.get("attributes", {}),
        )
        if not report["valid"]:
            raise validator.ValidationError("; ".join(report["errors"]))
        envelope = {
            "schema_url": registry["schema_url"],
            "convention": semantic_input["convention"],
            "producer": args.producer,
            "record_id": str(record.get("id")) if record.get("id") is not None else None,
            "source_record_sha256": hashlib.sha256(validator.canonical_json(record)).hexdigest(),
            "attributes": report["normalized_attributes"],
        }
        envelope["semantic_fingerprint_sha256"] = hashlib.sha256(validator.canonical_json(envelope)).hexdigest()
        output = {
            "schema": "urn:bionexus:bns019-workflow-record:1",
            "record": record,
            "scientific_semantics": envelope,
            "standard": {
                "id": "BNS-019",
                "version": manifest["version"],
                "release_digest_sha256": manifest["release_digest_sha256"],
            },
            "claim_boundary": "Workflow metadata transport only; no nf-core analysis result was validated.",
        }
        args.output.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        args.versions.write_text(
            '"BNS019_SEMCONV":\n'
            '  python: "' + sys.version.split()[0] + '"\n'
            '  bns019_standard: "' + manifest["version"] + '"\n'
            '  bns019_release_digest_sha256: "' + manifest["release_digest_sha256"] + '"\n',
            encoding="utf-8",
            newline="\n",
        )
    except (OSError, RuntimeError, KeyError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
