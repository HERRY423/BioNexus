"""Deployment-surface commands: lab exchange, matrix, schema migration, reports."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _emit(payload: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
        return
    for key, value in payload.items():
        if key in {"gates", "products", "report"}:
            continue
        print(f"{key}: {value}")
    for gate in payload.get("gates") or []:
        mark = "PASS" if gate.get("passed") else "FAIL"
        print(f"  [{mark}] {gate.get('name')}: {gate.get('detail')}")
    for item in payload.get("products") or []:
        print(f"  {item.get('id')}: {item.get('status')} ({item.get('acceptance_id')})")


def handle_deploy(args: argparse.Namespace) -> int:
    action = getattr(args, "deploy_action", None)
    as_json = bool(getattr(args, "json", False))

    if action == "import":
        from bionexus.lab_exchange import import_lab_source, write_envelope

        detection, envelope = import_lab_source(
            args.path, product=getattr(args, "product", None), data_classification=args.data_classification,
        )
        dest = Path(args.output) if args.output else Path(args.path).resolve().parent / "lab-exchange-envelope.json"
        if dest.is_dir() or str(dest).endswith(("\\", "/")):
            dest = dest / "lab-exchange-envelope.json"
        write_envelope(envelope, dest)
        payload = {"status": "IMPORTED", "product": detection.product, "envelope": str(dest), **detection.to_dict()}
        _emit(payload, as_json)
        return 0

    if action == "export":
        from bionexus.lab_exchange import export_lab_capsule, import_lab_source

        detection, envelope = import_lab_source(
            args.path, product=getattr(args, "product", None), data_classification=args.data_classification,
        )
        artifacts = export_lab_capsule(
            envelope,
            args.path,
            args.output,
            ro_crate=not getattr(args, "skip_ro_crate", False),
            bco=not getattr(args, "skip_bco", False),
        )
        payload = {"status": "EXPORTED", "product": detection.product, **{k: str(v) for k, v in artifacts.items()}}
        _emit(payload, as_json)
        return 0

    if action == "accept":
        from bionexus.lab_exchange import accept_lab_roundtrip

        report = accept_lab_roundtrip(
            args.path, args.output, product=getattr(args, "product", None), data_classification=args.data_classification,
        )
        _emit(report.to_dict(), as_json)
        return 0 if report.passed else 1

    if action == "matrix":
        from bionexus.compatibility_matrix import matrix_summary

        payload = matrix_summary(product=getattr(args, "product", None))
        _emit(payload, as_json)
        return 0

    if action == "migrate":
        from bionexus.schema_registry import load_and_migrate

        migrated = load_and_migrate(args.path, family=getattr(args, "family", None))
        dest = Path(args.output) if args.output else None
        if dest is not None:
            dest.parent.mkdir(parents=True, exist_ok=True)
            with dest.open("x", encoding="utf-8") as handle:
                handle.write(json.dumps(migrated, indent=2, ensure_ascii=False) + "\n")
        payload = {
            "status": "MIGRATED",
            "schema_version": migrated.get("schema_version"),
            "output": str(dest) if dest else None,
            "document": migrated if as_json else None,
        }
        if as_json:
            print(json.dumps({k: v for k, v in payload.items() if v is not None or k == "document"}, indent=2, ensure_ascii=False))
        else:
            print("status: MIGRATED")
            print(f"schema_version: {migrated.get('schema_version')}")
            if dest is not None:
                print(f"output: {dest}")
            else:
                print(json.dumps(migrated, indent=2, ensure_ascii=False))
        return 0

    if action == "telemetry":
        from bionexus.failure_report import telemetry_status

        _emit(telemetry_status(), as_json)
        return 0

    if action == "report-failure":
        from bionexus.failure_report import (
            build_failure_report,
            persist_failure_report,
            transmit_failure_report,
        )

        traceback_text = None
        if getattr(args, "traceback_file", None):
            traceback_text = Path(args.traceback_file).read_text(encoding="utf-8", errors="replace")
        report = build_failure_report(
            exception_type=args.exception_type,
            traceback_text=traceback_text or args.message,
            command=getattr(args, "command_name", None),
            capability_id=getattr(args, "capability_id", None),
            notes=args.message or "",
            data_classification=args.data_classification,
        )
        path = persist_failure_report(report, dest_dir=Path(args.output) if args.output else None)
        payload = {"status": "WRITTEN", "path": str(path), "report": report.to_dict()}
        if getattr(args, "opt_in_transmit", False):
            payload["transmit"] = transmit_failure_report(report, opt_in=True)
        _emit(payload, as_json)
        return 0

    print("Error: choose import, export, accept, matrix, migrate, telemetry, or report-failure", file=sys.stderr)
    return 2


def register_deploy_arguments(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    from bionexus.lab_exchange import DATA_CLASSIFICATIONS

    parser = subparsers.add_parser(
        "deploy",
        help="Lab import/export acceptance, compatibility matrix, schema migration, failure reports",
    )
    subs = parser.add_subparsers(dest="deploy_action", help="Deployment actions")

    p_import = subs.add_parser("import", help="Import a lab product directory or results table")
    p_import.add_argument("path", help="Cell Ranger outs/, Scanpy/Seurat export, DE table, or nf-core results")
    p_import.add_argument("-o", "--output", default=None, help="Envelope JSON path")
    p_import.add_argument("--product", default=None, choices=["cellranger", "scanpy", "seurat", "deseq2", "edger", "nf-core"])
    p_import.add_argument("--json", action="store_true", help="JSON output")
    p_import.add_argument("--data-classification", choices=DATA_CLASSIFICATIONS, default="UNKNOWN", help="Operator-declared data classification; UNKNOWN remains local-only")

    p_export = subs.add_parser("export", help="Import then export a run capsule, RO-Crate, and BCO")
    p_export.add_argument("path", help="Lab source path")
    p_export.add_argument("-o", "--output", required=True, help="Destination capsule directory")
    p_export.add_argument("--product", default=None, choices=["cellranger", "scanpy", "seurat", "deseq2", "edger", "nf-core"])
    p_export.add_argument("--skip-ro-crate", action="store_true", help="Skip RO-Crate projection")
    p_export.add_argument("--skip-bco", action="store_true", help="Skip BioCompute Object projection")
    p_export.add_argument("--json", action="store_true", help="JSON output")
    p_export.add_argument("--data-classification", choices=DATA_CLASSIFICATIONS, default="UNKNOWN", help="Operator-declared data classification; UNKNOWN remains local-only")

    p_accept = subs.add_parser("accept", help="End-to-end lab import/export acceptance")
    p_accept.add_argument("path", help="Lab source path")
    p_accept.add_argument("-o", "--output", required=True, help="Acceptance output directory")
    p_accept.add_argument("--product", default=None, choices=["cellranger", "scanpy", "seurat", "deseq2", "edger", "nf-core"])
    p_accept.add_argument("--json", action="store_true", help="JSON output")
    p_accept.add_argument("--data-classification", choices=DATA_CLASSIFICATIONS, default="UNKNOWN", help="Operator-declared data classification; UNKNOWN remains local-only")

    p_matrix = subs.add_parser("matrix", help="Show the analysis-product compatibility matrix")
    p_matrix.add_argument("--product", default=None, choices=["cellranger", "scanpy", "seurat", "deseq2", "edger", "nf-core"])
    p_matrix.add_argument("--json", action="store_true", help="JSON output")

    p_migrate = subs.add_parser("migrate", help="Migrate a historical schema document to the current version")
    p_migrate.add_argument("path", help="JSON document with schema_version")
    p_migrate.add_argument("-o", "--output", default=None, help="Write migrated JSON to this path")
    p_migrate.add_argument("--family", default=None, help="Optional schema family override")
    p_migrate.add_argument("--json", action="store_true", help="JSON output")

    p_tel = subs.add_parser("telemetry", help="Show opt-in failure-report status (default off)")
    p_tel.add_argument("--json", action="store_true", help="JSON output")

    p_fail = subs.add_parser("report-failure", help="Write a sanitized local failure report")
    p_fail.add_argument("--exception-type", required=True, help="Exception class name only")
    p_fail.add_argument("--message", default="", help="Operator note; paths and PHI are redacted")
    p_fail.add_argument("--traceback-file", default=None, help="Optional traceback text to sanitize")
    p_fail.add_argument("--command-name", default=None, help="CLI command name, not argv")
    p_fail.add_argument("--capability-id", default=None, help="Optional capability id")
    p_fail.add_argument("-o", "--output", default=None, help="Directory for the local JSON report")
    p_fail.add_argument("--opt-in-transmit", action="store_true", help="Attempt lab-configured transmit (never default)")
    p_fail.add_argument("--json", action="store_true", help="JSON output")
    p_fail.add_argument("--data-classification", choices=DATA_CLASSIFICATIONS, default="UNKNOWN", help="Only explicit PUBLIC_BENCHMARK may be eligible for opt-in transmit")
    return parser
