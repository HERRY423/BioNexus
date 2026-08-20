"""
Cross-Host Execution Evidence Framework (BNS-HC-007).

Generates structured reports proving that the same BioNexus capability
produces consistent refusal/warrant behavior across different host agents
(Codex, Claude Code, etc.).

This module provides:
- CrossHostExecutionRecord: atomic evidence record per trap per host
- generate_host_report(): per-host REPORT.json generator
- generate_comparison_report(): cross-host COMPARISON.json generator
- validate_cross_host_schema(): schema validation for report integrity
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from bionexus.versions import VERSION


@dataclass
class CrossHostExecutionRecord:
    """
    Atomic evidence record: one trap executed on one host.

    Each record captures the complete execution context needed to verify
    that a capability behaves consistently regardless of which host agent
    invoked it.
    """

    host_name: str  # e.g. "codex" | "claude-code" | "antigravity"
    host_version: str  # host agent version string
    capability_id: str  # e.g. "scrna.pseudobulk_de"
    input_hash: str  # SHA-256 of canonical input (prompt + metadata)
    trap_id: str  # BioFailureBench trap ID (e.g. "BF-001")
    expected_status: str  # expected behavior from corpus
    observed_status: str  # actual behavior from host execution
    refusal_correct: bool  # whether refusal matches expected
    warrant_text: str  # warrant/provenance text produced by host
    timestamp: str  # ISO 8601 execution timestamp
    metadata: Dict[str, Any] = field(default_factory=dict)  # host-specific metadata

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for JSON output."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> CrossHostExecutionRecord:
        """Deserialize from dictionary."""
        return cls(
            host_name=data["host_name"],
            host_version=data["host_version"],
            capability_id=data["capability_id"],
            input_hash=data["input_hash"],
            trap_id=data["trap_id"],
            expected_status=data["expected_status"],
            observed_status=data["observed_status"],
            refusal_correct=data["refusal_correct"],
            warrant_text=data["warrant_text"],
            timestamp=data["timestamp"],
            metadata=data.get("metadata", {}),
        )


def compute_input_hash(prompt: str, data_metadata: Optional[Dict[str, Any]] = None) -> str:
    """
    Compute SHA-256 hash of canonical input for reproducibility.

    The hash covers the prompt and data_metadata to ensure identical inputs
    produce identical hashes across hosts.
    """
    canonical = {"prompt": prompt, "data_metadata": data_metadata or {}}
    serialized = json.dumps(canonical, sort_keys=True, ensure_ascii=False)
    return f"sha256:{hashlib.sha256(serialized.encode('utf-8')).hexdigest()}"


def generate_host_report(
    records: List[CrossHostExecutionRecord],
    host_name: str,
    host_version: str = "",
    plugin_version: str = VERSION,
    integration: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Generate a single-host REPORT.json from execution records.

    The report summarizes per-trap execution results and computes aggregate
    metrics (correct refusals, false positives, agreement rate).
    """
    if not records:
        report = {
            "host": host_name,
            "host_version": host_version,
            "execution_date": datetime.now(timezone.utc).isoformat(),
            "plugin_version": plugin_version,
            "records": [],
            "summary": {
                "total_traps": 0,
                "correct_refusals": 0,
                "incorrect_refusals": 0,
                "false_positives": 0,
                "agreement_rate": None,
            },
        }
        if integration is not None:
            report["integration"] = integration
        return report

    # Verify all records belong to the same host
    host_names = {r.host_name for r in records}
    if len(host_names) > 1:
        raise ValueError(f"Records contain multiple hosts: {host_names}. Use one host per report.")

    total = len(records)
    correct_refusals = sum(1 for r in records if r.refusal_correct and r.expected_status == "ABSTAIN")
    incorrect_refusals = sum(1 for r in records if not r.refusal_correct and r.expected_status == "ABSTAIN")
    false_positives = sum(1 for r in records if not r.refusal_correct and r.expected_status != "ABSTAIN")
    agreement_rate = sum(1 for r in records if r.refusal_correct) / total if total > 0 else None

    report = {
        "host": host_name,
        "host_version": host_version,
        "execution_date": datetime.now(timezone.utc).isoformat(),
        "plugin_version": plugin_version,
        "records": [r.to_dict() for r in records],
        "summary": {
            "total_traps": total,
            "correct_refusals": correct_refusals,
            "incorrect_refusals": incorrect_refusals,
            "false_positives": false_positives,
            "agreement_rate": round(agreement_rate, 4) if agreement_rate is not None else None,
        },
    }
    if integration is not None:
        report["integration"] = integration
    return report



def generate_comparison_report(
    first_report: Dict[str, Any],
    second_report: Dict[str, Any],
    plugin_version: str = VERSION,
) -> Dict[str, Any]:
    """
    Generate COMPARISON.json comparing two host execution reports.

    Compares per-trap behavior across hosts and computes overall consistency.
    Single-host reports are not compared (consistency requires >= 2 hosts).
    """
    first_host = str(first_report.get("host", "first-host"))
    second_host = str(second_report.get("host", "second-host"))
    first_records = {r["trap_id"]: r for r in first_report.get("records", [])}
    second_records = {r["trap_id"]: r for r in second_report.get("records", [])}

    # Find common traps
    common_trap_ids = sorted(set(first_records.keys()) & set(second_records.keys()))

    per_trap: List[Dict[str, Any]] = []
    consistent_count = 0

    for trap_id in common_trap_ids:
        first_rec = first_records[trap_id]
        second_rec = second_records[trap_id]

        first_status = first_rec.get("observed_status", "")
        second_status = second_rec.get("observed_status", "")
        consistent = first_status == second_status

        if consistent:
            consistent_count += 1

        comparison_row = {
            "trap_id": trap_id,
            "statuses": {first_host: first_status, second_host: second_status},
            "consistent": consistent,
            "notes": "",
        }
        # Preserve the original BNS-HC-007 wire fields for existing consumers.
        if [first_host, second_host] == ["codex", "claude-code"]:
            comparison_row["codex_status"] = first_status
            comparison_row["claude_code_status"] = second_status
        per_trap.append(comparison_row)

    total_compared = len(common_trap_ids)
    inconsistent_count = total_compared - consistent_count
    agreement_rate = consistent_count / total_compared if total_compared > 0 else None

    # Conformance verdict: pass if agreement >= 90%
    if agreement_rate is None:
        verdict = "not_evaluated"
    elif agreement_rate >= 0.90:
        verdict = "pass"
    else:
        verdict = "fail"

    return {
        "comparison_date": datetime.now(timezone.utc).isoformat(),
        "hosts": [first_host, second_host],
        "plugin_version": plugin_version,
        "traps_compared": total_compared,
        "per_trap": per_trap,
        "overall": {
            "consistent_traps": consistent_count,
            "inconsistent_traps": inconsistent_count,
            "agreement_rate": round(agreement_rate, 4) if agreement_rate is not None else None,
            "conformance_verdict": verdict,
        },
    }


def validate_cross_host_schema(report: Dict[str, Any], report_type: str = "host") -> List[str]:
    """
    Validate cross-host report schema integrity.

    Returns a list of validation errors (empty list = valid report).
    Supports both "host" (REPORT.json) and "comparison" (COMPARISON.json) types.
    """
    errors: List[str] = []

    if report_type == "host":
        required_fields = ["host", "host_version", "execution_date", "plugin_version", "records", "summary"]
        for field_name in required_fields:
            if field_name not in report:
                errors.append(f"Missing required field: '{field_name}'")

        # Validate records structure
        records = report.get("records", [])
        if not isinstance(records, list):
            errors.append("'records' must be a list")
        else:
            record_required_fields = [
                "trap_id",
                "capability_id",
                "input_hash",
                "expected_status",
                "observed_status",
                "refusal_correct",
                "warrant_text",
                "timestamp",
            ]
            for i, rec in enumerate(records):
                for field_name in record_required_fields:
                    if field_name not in rec:
                        errors.append(f"Record {i}: missing required field '{field_name}'")

        # Validate summary structure
        summary = report.get("summary", {})
        summary_required_fields = [
            "total_traps",
            "correct_refusals",
            "incorrect_refusals",
            "false_positives",
            "agreement_rate",
        ]
        for field_name in summary_required_fields:
            if field_name not in summary:
                errors.append(f"Summary: missing required field '{field_name}'")

    elif report_type == "comparison":
        required_fields = ["comparison_date", "hosts", "plugin_version", "traps_compared", "per_trap", "overall"]
        for field_name in required_fields:
            if field_name not in report:
                errors.append(f"Missing required field: '{field_name}'")

        # Validate per_trap structure
        per_trap = report.get("per_trap", [])
        if not isinstance(per_trap, list):
            errors.append("'per_trap' must be a list")
        else:
            trap_required_fields = ["trap_id", "consistent", "notes"]
            for i, trap in enumerate(per_trap):
                for field_name in trap_required_fields:
                    if field_name not in trap:
                        errors.append(f"Per-trap {i}: missing required field '{field_name}'")
                statuses = trap.get("statuses")
                has_legacy_statuses = "codex_status" in trap and "claude_code_status" in trap
                if not isinstance(statuses, dict) and not has_legacy_statuses:
                    errors.append(f"Per-trap {i}: missing generic 'statuses' mapping")

        # Validate overall structure
        overall = report.get("overall", {})
        overall_required_fields = ["consistent_traps", "inconsistent_traps", "agreement_rate", "conformance_verdict"]
        for field_name in overall_required_fields:
            if field_name not in overall:
                errors.append(f"Overall: missing required field '{field_name}'")

    else:
        errors.append(f"Unknown report_type: '{report_type}'. Use 'host' or 'comparison'.")

    return errors


def save_host_report(
    report: Dict[str, Any],
    output_dir: Optional[Path] = None,
) -> Path:
    """Save a host report to cross-host/<host_name>/REPORT.json."""
    host_name = report.get("host", "unknown")
    base_dir = output_dir or (Path(__file__).resolve().parent.parent / "cross-host")
    host_dir = base_dir / host_name
    host_dir.mkdir(parents=True, exist_ok=True)
    output_path = host_dir / "REPORT.json"
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return output_path


def save_comparison_report(
    report: Dict[str, Any],
    output_dir: Optional[Path] = None,
) -> Path:
    """Save a comparison report to cross-host/COMPARISON.json."""
    base_dir = output_dir or (Path(__file__).resolve().parent.parent / "cross-host")
    base_dir.mkdir(parents=True, exist_ok=True)
    output_path = base_dir / "COMPARISON.json"
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return output_path
