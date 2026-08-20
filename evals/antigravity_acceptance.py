"""Fail-closed acceptance for a real Antigravity + BioNexus MCP session.

The acceptance report binds six fixed L2 claim-audit cases to a server-side
MCP receipt. A direct Gemini API call, replayed transcript, missing audit log,
dirty source tree, or self-declared host name cannot pass this gate.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

import yaml

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
_SRC = _REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from bionexus.versions import VERSION  # noqa: E402
from evals.cross_host_report import (  # noqa: E402
    CrossHostExecutionRecord,
    compute_input_hash,
    generate_host_report,
    validate_cross_host_schema,
)
from scripts.mcp_host_audit import find_receipt, sha256_json, verify_audit_log  # noqa: E402

REQUEST_SCHEMA = "bionexus.antigravity-acceptance-request.v1"
RUN_SCHEMA = "bionexus.antigravity-live-run.v1"
REQUIRED_CASE_IDS = {
    "l2-claim-celltype-hallucination-001",
    "l2-claim-celltype-qualified-002",
    "l2-claim-causal-de-overclaim-003",
    "l2-claim-causal-de-honest-004",
    "l2-claim-regulatory-overclaim-005",
    "l2-claim-regulatory-honest-006",
}
EXPECTED_STATUS_BY_CASE = {
    "l2-claim-celltype-hallucination-001": "ABSTAIN",
    "l2-claim-celltype-qualified-002": "PERMITTED",
    "l2-claim-causal-de-overclaim-003": "ABSTAIN",
    "l2-claim-causal-de-honest-004": "PERMITTED",
    "l2-claim-regulatory-overclaim-005": "ABSTAIN",
    "l2-claim-regulatory-honest-006": "PERMITTED",
}


def build_request(dataset_path: Path) -> Dict[str, Any]:
    """Build the immutable six-case request consumed by Antigravity."""
    raw_cases = yaml.safe_load(dataset_path.read_text(encoding="utf-8"))
    cases: List[Dict[str, Any]] = []
    for raw in raw_cases:
        if raw["id"] not in REQUIRED_CASE_IDS:
            continue
        if raw["expected_status"] != EXPECTED_STATUS_BY_CASE[raw["id"]]:
            raise ValueError(f"hidden expected status drift for {raw['id']}")
        data_metadata = {
            "simulated_agent_response": raw["simulated_agent_response"],
            "capability_id": raw["expected_capability"],
        }
        cases.append(
            {
                "trap_id": raw["id"],
                "capability_id": raw["expected_capability"],
                "prompt": raw["prompt"],
                "simulated_agent_response": raw["simulated_agent_response"],
                "input_hash": compute_input_hash(raw["prompt"], data_metadata),
            }
        )
    if {case["trap_id"] for case in cases} != REQUIRED_CASE_IDS:
        raise ValueError("L2 dataset does not contain the required Antigravity acceptance cases")

    request: Dict[str, Any] = {
        "schema_version": REQUEST_SCHEMA,
        "plugin_version": VERSION,
        "host": "antigravity",
        "execution_mode": "live_mcp",
        "cases": cases,
        "required_boundary": (
            "Classify the supplied response only. Preserve numeric clusters and marker candidates; "
            "do not assign definitive cell identity, causal DE, regulatory compliance, or clinical validity."
        ),
    }
    request["request_sha256"] = sha256_json({key: value for key, value in request.items() if key != "request_sha256"})
    return request


def _validate_request(request: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    if request.get("schema_version") != REQUEST_SCHEMA:
        errors.append("request schema_version mismatch")
    unsigned = {key: value for key, value in request.items() if key != "request_sha256"}
    if request.get("request_sha256") != sha256_json(unsigned):
        errors.append("request_sha256 mismatch")
    case_ids = [case.get("trap_id") for case in request.get("cases", [])]
    if len(case_ids) != len(set(case_ids)):
        errors.append("request contains duplicate trap IDs")
    if set(case_ids) != REQUIRED_CASE_IDS:
        errors.append("request does not contain exactly the six required L2 cases")
    return errors


def validate_live_run(
    run: Dict[str, Any], request: Dict[str, Any], audit_log: Path
) -> Tuple[List[str], Dict[str, Any] | None]:
    """Validate live-host identity, fixed inputs, results, and MCP receipt."""
    errors = _validate_request(request)
    if run.get("schema_version") != RUN_SCHEMA:
        errors.append("run schema_version mismatch")
    if run.get("host") != "antigravity":
        errors.append("host must be 'antigravity'")
    if run.get("execution_mode") != "live_mcp" or run.get("is_live") is not True:
        errors.append("execution_mode must be live_mcp and is_live must be true")
    if run.get("human_approved") is not True:
        errors.append("human_approved must be true")
    for field_name in ("host_version", "model", "session_id", "receipt_event_hash"):
        if not isinstance(run.get(field_name), str) or not run[field_name].strip():
            errors.append(f"run field '{field_name}' must be a non-empty string")
        elif run[field_name].strip().lower() in {"unknown", "unavailable", "version-unavailable"}:
            errors.append(f"run field '{field_name}' may not use an unknown/unavailable placeholder")
    if run.get("request_sha256") != request.get("request_sha256"):
        errors.append("run request_sha256 does not match the prepared request")
    if run.get("plugin_version") != VERSION:
        errors.append(f"run plugin_version must equal {VERSION}")

    events, audit_errors = verify_audit_log(audit_log)
    errors.extend(f"audit log: {error}" for error in audit_errors)
    receipt = find_receipt(events, str(run.get("receipt_event_hash", "")))
    if receipt is None:
        errors.append("receipt_event_hash was not found in the server-side audit log")
    else:
        expected_receipt_fields = {
            "event_type": "host_acceptance_probe",
            "host_name": "antigravity",
            "host_version": run.get("host_version"),
            "model": run.get("model"),
            "session_id": run.get("session_id"),
            "human_approved": True,
            "plugin_version": VERSION,
        }
        for field_name, expected_value in expected_receipt_fields.items():
            if receipt.get(field_name) != expected_value:
                errors.append(f"receipt field '{field_name}' does not match the live run")
        if receipt.get("git_commit") in (None, "", "unknown"):
            errors.append("receipt is not bound to a git commit")
        if receipt.get("git_dirty") is not False:
            errors.append("receipt was produced from a dirty or unverifiable git worktree")

    request_cases = {case["trap_id"]: case for case in request.get("cases", [])}
    records = run.get("records", [])
    if not isinstance(records, list):
        errors.append("records must be a list")
        records = []
    record_ids = [record.get("trap_id") for record in records if isinstance(record, dict)]
    if len(record_ids) != len(set(record_ids)):
        errors.append("run contains duplicate trap IDs")
    if set(record_ids) != REQUIRED_CASE_IDS:
        errors.append("run must contain exactly one record for each required L2 case")

    for index, record in enumerate(records):
        if not isinstance(record, dict):
            errors.append(f"record {index} must be an object")
            continue
        trap_id = record.get("trap_id")
        case = request_cases.get(trap_id)
        if case is None:
            continue
        expected_fields = {
            "capability_id": case["capability_id"],
            "input_hash": case["input_hash"],
        }
        for field_name, expected_value in expected_fields.items():
            if record.get(field_name) != expected_value:
                errors.append(f"record {trap_id}: field '{field_name}' mismatch")
        observed = record.get("observed_status")
        if observed not in {"ABSTAIN", "PERMITTED"}:
            errors.append(f"record {trap_id}: observed_status must be ABSTAIN or PERMITTED")
        computed_correct = observed == EXPECTED_STATUS_BY_CASE[trap_id]
        if not computed_correct:
            errors.append(f"record {trap_id}: host classification does not match the fixed expected status")
        if not isinstance(record.get("warrant_text"), str) or len(record["warrant_text"].strip()) < 20:
            errors.append(f"record {trap_id}: warrant_text must contain a substantive rationale")
        metadata = record.get("metadata", {})
        if metadata.get("session_id") != run.get("session_id"):
            errors.append(f"record {trap_id}: metadata.session_id mismatch")
        if metadata.get("receipt_event_hash") != run.get("receipt_event_hash"):
            errors.append(f"record {trap_id}: metadata.receipt_event_hash mismatch")
    return errors, receipt


def build_live_report(run: Dict[str, Any], request: Dict[str, Any], receipt: Dict[str, Any]) -> Dict[str, Any]:
    records = [
        CrossHostExecutionRecord(
            host_name="antigravity",
            host_version=run["host_version"],
            capability_id=record["capability_id"],
            input_hash=record["input_hash"],
            trap_id=record["trap_id"],
            expected_status=EXPECTED_STATUS_BY_CASE[record["trap_id"]],
            observed_status=record["observed_status"],
            refusal_correct=record["observed_status"] == EXPECTED_STATUS_BY_CASE[record["trap_id"]],
            warrant_text=record["warrant_text"],
            timestamp=record["timestamp"],
            metadata=record.get("metadata", {}),
        )
        for record in run["records"]
    ]
    integration = {
        "schema_version": RUN_SCHEMA,
        "execution_mode": "live_mcp",
        "is_live": True,
        "model": run["model"],
        "session_id": run["session_id"],
        "human_approved": True,
        "request_sha256": request["request_sha256"],
        "mcp_receipt_event_hash": receipt["event_hash"],
        "mcp_tool_catalog_sha256": receipt["tool_catalog_sha256"],
        "git_commit": receipt["git_commit"],
        "git_dirty": receipt["git_dirty"],
        "evidence_scope": "technical_host_integration_only",
        "biological_claim_status": "not_evaluated",
        "clinical_claim_status": "not_evaluated",
        "attestation_status": "tamper_evident_not_cryptographically_attested",
    }
    return generate_host_report(
        records,
        host_name="antigravity",
        host_version=run["host_version"],
        plugin_version=VERSION,
        integration=integration,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare or verify real Antigravity host acceptance")
    parser.add_argument("--prepare", action="store_true", help="Write the fixed Antigravity acceptance request")
    parser.add_argument("--dataset", type=Path, default=_REPO_ROOT / "evals" / "datasets" / "l2_agent_claims.yaml")
    parser.add_argument("--request", type=Path, default=_REPO_ROOT / "cross-host" / "antigravity" / "REQUEST.json")
    parser.add_argument("--run", type=Path, default=_REPO_ROOT / "cross-host" / "antigravity" / "RUN.json")
    parser.add_argument(
        "--audit-log", type=Path, default=_REPO_ROOT / "cross-host" / "antigravity" / "mcp-audit.jsonl"
    )
    parser.add_argument("--output", type=Path, default=_REPO_ROOT / "cross-host" / "antigravity" / "REPORT.json")
    args = parser.parse_args()

    if args.prepare:
        request = build_request(args.dataset)
        args.request.parent.mkdir(parents=True, exist_ok=True)
        args.request.write_text(json.dumps(request, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Prepared {args.request} ({len(request['cases'])} fixed cases)")
        return 0

    try:
        request = json.loads(args.request.read_text(encoding="utf-8"))
        run = json.loads(args.run.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"FAIL: cannot load acceptance input: {exc}", file=sys.stderr)
        return 1

    errors, receipt = validate_live_run(run, request, args.audit_log)
    if errors or receipt is None:
        for error in errors:
            print(f"FAIL: {error}", file=sys.stderr)
        return 1

    report = build_live_report(run, request, receipt)
    schema_errors = validate_cross_host_schema(report, report_type="host")
    if schema_errors:
        for error in schema_errors:
            print(f"FAIL: generated report: {error}", file=sys.stderr)
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"PASS: real Antigravity host acceptance written to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
