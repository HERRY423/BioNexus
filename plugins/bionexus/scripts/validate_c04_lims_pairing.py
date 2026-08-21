#!/usr/bin/env python3
"""Fail-closed preflight for the custodian-held C04 LIMS pairing manifest.

The manifest is read locally and never copied into the repository packet. The
report contains only aggregate checks and hashes, not participant identifiers.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
REQUIRED_COLUMNS = {
    "participant_id_hash",
    "aliquot_id",
    "opaque_arm_id",
    "collection_timestamp_utc",
    "stimulation_start_utc",
    "stimulation_stop_utc",
    "reagent_name",
    "reagent_lot",
    "pbmc_handling_mode",
    "pre_split_viability_percent",
    "library_id",
    "sequencing_run_id",
    "source_lims_record_sha256",
}
FORBIDDEN_PAIRING_HINTS = ("gsm", "filename", "lane", "plate", "position", "similarity")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate(path: Path) -> dict[str, object]:
    issues: list[str] = []
    if not path.is_file():
        return {"status": "ABSTAIN", "issues": [f"missing manifest: {path}"]}
    try:
        frame = pd.read_csv(path, dtype=str).fillna("")
    except Exception as exc:  # pragma: no cover - parser-specific failures
        return {"status": "ABSTAIN", "issues": [f"unreadable manifest: {type(exc).__name__}: {exc}"]}

    missing = sorted(REQUIRED_COLUMNS - set(frame.columns))
    if missing:
        issues.append(f"missing required columns: {missing}")
    if len(frame) != 24:
        issues.append(f"expected exactly 24 aliquot rows, observed {len(frame)}")
    if not missing and len(frame):
        for column in sorted(REQUIRED_COLUMNS):
            if frame[column].astype(str).str.strip().eq("").any():
                issues.append(f"blank required values in {column}")
        if frame["participant_id_hash"].nunique() != 12:
            issues.append("expected exactly 12 authoritative participant_id_hash values")
        pair_sizes = frame.groupby("participant_id_hash").size()
        if len(pair_sizes) == 12 and not (pair_sizes == 2).all():
            issues.append("each authoritative participant_id_hash must have exactly two aliquots")
        arm_counts = frame.groupby("participant_id_hash")["opaque_arm_id"].nunique()
        if len(arm_counts) == 12 and not (arm_counts == 2).all():
            issues.append("each authoritative participant_id_hash must have two distinct opaque arms")
        for column in ("aliquot_id", "library_id", "sequencing_run_id", "source_lims_record_sha256"):
            if frame[column].duplicated().any():
                issues.append(f"duplicate values in {column}")
        starts = pd.to_datetime(frame["stimulation_start_utc"], utc=True, errors="coerce")
        stops = pd.to_datetime(frame["stimulation_stop_utc"], utc=True, errors="coerce")
        if starts.isna().any() or stops.isna().any():
            issues.append("invalid stimulation timestamps")
        else:
            duration_minutes = (stops - starts).dt.total_seconds() / 60.0
            if (duration_minutes.sub(360.0).abs() > 5.0).any():
                issues.append("one or more stimulation durations fall outside 6h +/- 5min")
        viability = pd.to_numeric(frame["pre_split_viability_percent"], errors="coerce")
        if viability.isna().any() or (viability < 80.0).any():
            issues.append("one or more aliquots fail the preregistered 80% viability gate")
        if frame["pbmc_handling_mode"].nunique() != 1:
            issues.append("PBMC handling mode is not uniform across all aliquots")
        reagent_text = frame["reagent_name"].str.lower()
        if int(reagent_text.str.contains("ifn-beta-1a|ifn beta-1a", regex=True).sum()) != 12:
            issues.append("expected exactly 12 recombinant human IFN-beta-1a aliquots")
        if int(reagent_text.str.contains("vehicle|matched carrier", regex=True).sum()) != 12:
            issues.append("expected exactly 12 vehicle aliquots")
        if any(any(hint in column.lower() for hint in FORBIDDEN_PAIRING_HINTS) for column in frame.columns):
            issues.append("manifest contains a forbidden non-authoritative pairing hint column")
        if not frame["source_lims_record_sha256"].str.fullmatch(r"[0-9a-fA-F]{64}").all():
            issues.append("source_lims_record_sha256 must contain 64-hex SHA-256 values")

    return {
        "schema_version": "bionexus.c04-lims-pairing-preflight.v1",
        "assessed_at": datetime.now(timezone.utc).isoformat(),
        "manifest_sha256": _sha256(path),
        "status": "PASS" if not issues else "ABSTAIN",
        "issues": issues,
        "row_count": int(len(frame)),
        "authoritative_pair_count": int(frame["participant_id_hash"].nunique()) if "participant_id_hash" in frame else 0,
        "condition_key_exported": False,
        "participant_identifiers_in_report": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = validate(args.manifest)
    if args.report:
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
