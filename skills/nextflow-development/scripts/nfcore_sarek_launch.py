#!/usr/bin/env python3
"""Write an nf-core/sarek launch artifact (germline / somatic variant calling).

Does not reimplement Sarek. Mirrors the nfcore_launch.py contract: validates the
Sarek samplesheet schema (patient/sample/fastq_1/fastq_2 with optional lane and
tumor/normal status), writes run.sh, and optionally runs `nextflow -preview`
(Nextflow on PATH required). Explicit --step is mandatory: BioNexus never silently
assumes a Sarek entry point on the user's behalf.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

_SRC = Path(__file__).resolve().parents[3] / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from bionexus.contracts import GRADE_A, attach_meta, refuse

# Canonical --step choices of nf-core/sarek (v3.x).
SAREK_STEPS = (
    "ubam",
    "mapping",
    "markdup",
    "prepare_recalibration",
    "recalibrate",
    "germline",
    "somatic",
    "controlfreec",
)

REQUIRED_COLUMNS = ("patient", "sample", "fastq_1", "fastq_2")
OPTIONAL_COLUMNS = ("lane", "status")
STATUS_NORMAL = {"0", "normal"}
STATUS_TUMOR = {"1", "tumor"}


class SarekSheetError(ValueError):
    """Raised when a Sarek samplesheet violates the schema."""


def validate_sarek_samplesheet(samplesheet: str | Path) -> Dict:
    """Validate a Sarek samplesheet; returns a schema summary dict.

    Enforced schema (nf-core/sarek v3.x FASTQ input):
      required: patient, sample, fastq_1, fastq_2
      optional: lane, status (0/normal or 1/tumor; used for somatic calling)
    """
    path = Path(samplesheet)
    if not path.is_file():
        raise SarekSheetError(f"Samplesheet not found: {path}")
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.reader(handle))
    if not rows:
        raise SarekSheetError("Samplesheet is empty")
    header = [h.strip().lower() for h in rows[0]]
    missing = [c for c in REQUIRED_COLUMNS if c not in header]
    if missing:
        raise SarekSheetError(
            f"Samplesheet missing required Sarek column(s): {missing}. "
            f"Required: {list(REQUIRED_COLUMNS)}; optional: {list(OPTIONAL_COLUMNS)}"
        )
    unknown = [h for h in header if h not in REQUIRED_COLUMNS and h not in OPTIONAL_COLUMNS]
    if unknown:
        raise SarekSheetError(f"Samplesheet contains column(s) unknown to the Sarek FASTQ schema: {unknown}")

    patients = set()
    status_seen = False
    n_rows = 0
    for line_no, row in enumerate(rows[1:], start=2):
        if not row or all(not cell.strip() for cell in row):
            continue
        record = dict(zip(header, (cell.strip() for cell in row)))
        for col in REQUIRED_COLUMNS:
            if not record.get(col):
                raise SarekSheetError(f"Samplesheet row {line_no}: required column '{col}' is empty")
        status = (record.get("status") or "").lower()
        if status:
            status_seen = True
            if status not in STATUS_NORMAL and status not in STATUS_TUMOR:
                raise SarekSheetError(
                    f"Samplesheet row {line_no}: status must be one of 0/normal or 1/tumor, got '{status}'"
                )
        patients.add(record["patient"])
        n_rows += 1
    if n_rows == 0:
        raise SarekSheetError("Samplesheet has a header but no data rows")
    return {
        "rows": n_rows,
        "patients": sorted(patients),
        "has_status_column": status_seen,
        "columns": header,
    }


def normalize_status_column(samplesheet: str | Path, dest: Path) -> Path:
    """Rewrite the samplesheet with tumor/normal status normalized to 1/0 (Sarek convention)."""
    path = Path(samplesheet)
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        rows = [row for row in reader if row]
    if not rows:
        raise SarekSheetError(f"Samplesheet is empty: {path}")
    header = [h.strip().lower() for h in rows[0]]
    if "status" not in header:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(",".join(header) + "\n", encoding="utf-8")
        return dest
    status_idx = header.index("status")
    out_rows = [header]
    for row in rows[1:]:
        if not row or all(not cell.strip() for cell in row):
            continue
        record = dict(zip(header, (cell.strip() for cell in row)))
        status = (record.get("status") or "").lower()
        if status in STATUS_TUMOR:
            row[status_idx] = "1"
        elif status in STATUS_NORMAL:
            row[status_idx] = "0"
        out_rows.append(row)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerows(out_rows)
    return dest


def build_sarek_command(
    *,
    samplesheet: str,
    outdir: str,
    step: str,
    profile: str = "docker",
    extra: Optional[List[str]] = None,
) -> List[str]:
    if step not in SAREK_STEPS:
        raise ValueError(f"Unknown Sarek step '{step}'. Allowed steps: {list(SAREK_STEPS)}")
    cmd = [
        "nextflow",
        "run",
        "nf-core/sarek",
        "-profile",
        profile,
        "--input",
        samplesheet,
        "--outdir",
        outdir,
        "--step",
        step,
    ]
    if extra:
        cmd.extend(extra)
    return cmd


def write_launch_script(cmd: List[str], dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("#!/usr/bin/env bash\nset -euo pipefail\n" + " ".join(cmd) + "\n", encoding="utf-8")
    return dest


def run_preview(cmd: List[str], timeout: int = 180) -> dict:
    """Reuse the shared nextflow -preview helper from the rnaseq/scrnaseq launcher."""
    from nfcore_launch import run_preview as _shared_preview

    return _shared_preview(cmd, timeout=timeout)


def main() -> None:
    parser = argparse.ArgumentParser(description="nf-core/sarek launch artifact + optional -preview")
    parser.add_argument("--samplesheet", required=True)
    parser.add_argument("--outdir", required=True)
    parser.add_argument("--step", required=True, choices=list(SAREK_STEPS))
    parser.add_argument("--profile", default="docker")
    parser.add_argument("-o", "--output", required=True, help="Path to write run.sh")
    parser.add_argument("--normalized-sheet", default=None, help="Where to write the status-normalized sheet")
    parser.add_argument("--preview", action="store_true")
    parser.add_argument("--extra", nargs="*", default=None)
    args = parser.parse_args()

    try:
        schema = validate_sarek_samplesheet(args.samplesheet)
    except SarekSheetError as e:
        print(
            json.dumps(
                refuse(
                    method="nf-core_sarek_launch",
                    reason=str(e),
                    extra={"samplesheet": args.samplesheet},
                ),
                indent=2,
            )
        )
        sys.exit(2)

    sheet_path = Path(args.samplesheet)
    if schema["has_status_column"] and args.normalized_sheet:
        sheet_path = normalize_status_column(args.samplesheet, Path(args.normalized_sheet))

    cmd = build_sarek_command(
        samplesheet=str(sheet_path),
        outdir=args.outdir,
        step=args.step,
        profile=args.profile,
        extra=args.extra,
    )
    script = write_launch_script(cmd, Path(args.output))
    contract = attach_meta(
        {
            "command": cmd,
            "script": str(script),
            "samplesheet": str(sheet_path),
            "samplesheet_schema": schema,
            "step": args.step,
        },
        method="nf-core_sarek_launch_artifact",
        backend="nextflow + nf-core/sarek",
        evidence_grade=GRADE_A,
        limitations=[
            "Writes a Sarek launch script. Does not run the pipeline unless --preview.",
            "Somatic (tumor/normal) calling additionally requires the status column and matched normals.",
        ],
    )
    if args.preview:
        contract["preview"] = run_preview(cmd)
    print(json.dumps(contract, indent=2, default=str))


if __name__ == "__main__":
    main()
