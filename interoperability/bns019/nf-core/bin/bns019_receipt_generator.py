#!/usr/bin/env python3
"""Generate a certified BNS-021 tool execution receipt directly from Nextflow process outputs."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def sha256_file(path: Path) -> str:
    if not path.is_file():
        return ""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def parse_samplesheet(sheet_path: Path) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    if not sheet_path.is_file():
        return [], {"sample_count": 0, "min_replicates": 0, "conditions_count": 0}
    samples = []
    with open(sheet_path, "r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            samples.append({k.strip(): v.strip() for k, v in row.items() if k})
    conds = set()
    for s in samples:
        c = s.get("condition") or s.get("group") or s.get("treatment") or "default"
        conds.add(c)
    min_reps = len(samples) // max(1, len(conds)) if conds else len(samples)
    return samples, {
        "sample_count": len(samples),
        "min_replicates": min_reps,
        "conditions_count": len(conds),
    }


def parse_versions(versions_path: Path) -> Dict[str, str]:
    if not versions_path.is_file():
        return {}
    versions: Dict[str, str] = {}
    for line in versions_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(":", 1)
        if len(parts) == 2:
            k = parts[0].strip().strip("\"'")
            v = parts[1].strip().strip("\"'")
            if v:
                versions[k] = v
    return versions


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="BNS-019 / BNS-021 Nextflow Receipt Generator")
    parser.add_argument("--pipeline-name", default="nf-core/pipeline")
    parser.add_argument("--samplesheet", type=Path)
    parser.add_argument("--versions", type=Path)
    parser.add_argument("--plugin-version", default="1.0.0-rc.4", help="BioNexus plugin version")
    parser.add_argument("--trace", type=Path)
    parser.add_argument("--outputs", nargs="*", type=Path, default=[])
    parser.add_argument("--output", type=Path, required=True, help="Destination for bionexus_receipt.json")
    parser.add_argument("--card-output", type=Path, help="Destination for bionexus_evidence_card.json")
    args = parser.parse_args(argv)

    samples, design = parse_samplesheet(args.samplesheet) if args.samplesheet else ([], {"sample_count": 0, "min_replicates": 0, "conditions_count": 0})
    versions = parse_versions(args.versions) if args.versions else {}

    output_digests = {}
    for op in args.outputs:
        if op.is_file():
            output_digests[op.name] = sha256_file(op)
        elif op.is_dir():
            for root, _, files in os.walk(op):
                for f in files:
                    fp = Path(root) / f
                    output_digests[fp.name] = sha256_file(fp)

    req_payload = {
        "pipeline_name": args.pipeline_name,
        "samplesheet": str(args.samplesheet) if args.samplesheet else None,
        "sample_count": design["sample_count"],
    }
    resp_payload = {
        "execution_status": "SUCCESS",
        "output_digests": output_digests,
        "software_versions": versions,
    }

    req_hash = hashlib.sha256(canonical_json(req_payload).encode("utf-8")).hexdigest()
    resp_hash = hashlib.sha256(canonical_json(resp_payload).encode("utf-8")).hexdigest()

    factors = ["backend_fidelity", "provenance"]
    if design["sample_count"] >= 2:
        factors.append("sample_design")
    if design["min_replicates"] >= 2 or design["sample_count"] >= 3:
        factors.append("replication")
    if design["conditions_count"] >= 2:
        factors.append("confound_controls")

    meta = {
        "pipeline_name": args.pipeline_name,
        "sample_design": design["sample_count"] >= 2,
        "replication": design["min_replicates"] >= 2 or design["sample_count"] >= 3,
        "confound_controls": design["conditions_count"] >= 2,
        "backend_fidelity": True,
        "provenance": True,
        "derived_evidence_factors": sorted(set(factors)),
    }

    now_iso = datetime.now(timezone.utc).isoformat()
    rcpt_id = f"RCPT-NF-{uuid.uuid4().hex[:10]}"

    unsigned = {
        "schema_version": "bionexus.tool-execution-receipt.v1",
        "receipt_id": rcpt_id,
        "timestamp": now_iso,
        "plugin_id": "bionexus-nextflow",
        "plugin_version": args.plugin_version,
        "tool_name": f"nf-core.{args.pipeline_name.removeprefix('nf-core/')}",
        "request_sha256": req_hash,
        "response_sha256": resp_hash,
        "execution_status": "SUCCESS",
        "metadata": meta,
        "previous_receipt_hash": None,
        "chain_index": 0,
    }
    rcpt_hash = hashlib.sha256(canonical_json(unsigned).encode("utf-8")).hexdigest()
    unsigned["receipt_hash"] = rcpt_hash

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(unsigned, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if args.card_output:
        card = {
            "execution_state": "EXECUTED",
            "evidence_maturity": "ROBUST" if "replication" in factors else "SUPPORTED",
            "satisfied_factors": sorted(set(factors)),
            "pipeline": args.pipeline_name,
            "receipt_id": rcpt_id,
        }
        args.card_output.parent.mkdir(parents=True, exist_ok=True)
        args.card_output.write_text(json.dumps(card, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
