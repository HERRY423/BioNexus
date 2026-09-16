"""
BioNexus Eval Receipt Chain: tamper-evident audit log for benchmark runs.

Every ``bionexus eval`` run appends one hash-chained receipt recording WHAT was
evaluated, WHAT the results were, and WHICH capability-contract set (ABI
manifest) the run enforced. The append-only chain makes silent editing of
published accuracy claims detectable: a number that cannot be re-derived from
an unbroken chain is not an auditable claim.

Design (mirrors scripts/mcp_host_audit.py):

- JSONL append-only log; each event carries ``sequence``,
  ``previous_event_hash``, and ``event_hash = SHA256(canonical_json(event))``.
- Appending refuses to extend a corrupted chain (fail-closed).
- The ABI manifest digest anchors the run to an exact contract state: if a
  forbidden-claims catalog or evidence ceiling changes, old receipts remain
  verifiable against the manifest they were actually run under.

Boundary: this is tamper-EVIDENCE, not a signature over truth. A receipt proves
the log entry exists unmodified in sequence — it does not prove the benchmark
was executed correctly, and it is never biological or clinical evidence.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

EVAL_RECEIPT_SCHEMA = "bionexus.eval-receipt.v1"
GENESIS_HASH = "GENESIS"
DEFAULT_LOG_RELPATH = Path("logs") / "eval_audit.jsonl"
_APPEND_LOCK = threading.Lock()


def canonical_json(value: Any) -> str:
    """Stable JSON used by every receipt hash."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_json(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _event_hash(event: Dict[str, Any]) -> str:
    unsigned = {key: value for key, value in event.items() if key != "event_hash"}
    return sha256_json(unsigned)


def read_events(path: Path) -> Tuple[List[Dict[str, Any]], List[str]]:
    events: List[Dict[str, Any]] = []
    errors: List[str] = []
    if not path.exists():
        return events, errors
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw_line.strip():
            continue
        try:
            event = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            errors.append(f"line {line_number}: invalid JSON: {exc.msg}")
            continue
        if not isinstance(event, dict):
            errors.append(f"line {line_number}: event must be a JSON object")
            continue
        events.append(event)
    return events, errors


def verify_eval_log(path: Path) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Verify schema, sequence continuity, previous-hash links, and event hashes."""
    events, errors = read_events(path)
    previous_hash = GENESIS_HASH
    expected_sequence = 1
    for index, event in enumerate(events, start=1):
        if event.get("schema_version") != EVAL_RECEIPT_SCHEMA:
            errors.append(f"event {index}: unsupported schema_version")
        if event.get("sequence") != expected_sequence:
            errors.append(f"event {index}: expected sequence {expected_sequence}")
        if event.get("previous_event_hash") != previous_hash:
            errors.append(f"event {index}: previous_event_hash mismatch")
        if event.get("event_type") != "eval_run":
            errors.append(f"event {index}: unknown event_type {event.get('event_type')!r}")
        computed = _event_hash(event)
        if event.get("event_hash") != computed:
            errors.append(f"event {index}: event_hash mismatch")
        previous_hash = str(event.get("event_hash", ""))
        expected_sequence += 1
    return events, errors


def _git_commit(repo_root: Optional[Path]) -> str:
    configured = os.environ.get("BIONEXUS_GIT_COMMIT", "").strip()
    if configured:
        return configured
    if repo_root is None:
        return "unknown"
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def _git_dirty(repo_root: Optional[Path]) -> Optional[bool]:
    configured = os.environ.get("BIONEXUS_GIT_DIRTY", "").strip().lower()
    if configured:
        if configured in {"false", "0", "no"}:
            return False
        if configured in {"true", "1", "yes"}:
            return True
        return None
    if repo_root is None:
        return None
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=normal"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return bool(result.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        return None


# ---------------------------------------------------------------------------
# ABI manifest anchoring
# ---------------------------------------------------------------------------


def build_abi_manifest(include_frontier: bool = True) -> Dict[str, Any]:
    """
    Canonical snapshot of every Biological Capability ABI record.

    The manifest is the verifiable answer to "which contract set did this run
    enforce?": forbidden-claim catalogs, evidence ceilings, validation policies,
    and provenance requirements, serialized in canonical form.
    """
    from bionexus.abi import capability_abis

    abis = capability_abis(include_frontier=include_frontier)
    return {
        "manifest_schema": "bionexus.abi-manifest.v1",
        "abi_records": {cap_id: abi.to_dict() for cap_id, abi in sorted(abis.items())},
    }


def abi_manifest_digest(include_frontier: bool = True) -> str:
    """Deterministic SHA-256 of the canonical ABI manifest."""
    return sha256_json(build_abi_manifest(include_frontier=include_frontier))


# ---------------------------------------------------------------------------
# Receipt appending
# ---------------------------------------------------------------------------


def default_log_path(repo_root: Optional[Path] = None) -> Path:
    root = repo_root if repo_root is not None else _discover_repo_root()
    return (root / DEFAULT_LOG_RELPATH).resolve() if root else DEFAULT_LOG_RELPATH.resolve()


def _discover_repo_root() -> Optional[Path]:
    env = os.environ.get("BIONEXUS_REPO_ROOT", "").strip()
    if env:
        return Path(env)
    here = Path(__file__).resolve().parent.parent.parent
    return here if (here / "bionexus.registry.yaml").exists() else None


def audit_enabled() -> bool:
    flag = os.environ.get("BIONEXUS_EVAL_AUDIT_LOG", "").strip().lower()
    return flag not in {"0", "off", "false", "no"}


def append_eval_receipt(
    *,
    log_path: Optional[Path] = None,
    suite: str,
    provider: str,
    model: str,
    strict_mode: bool,
    gating_summary: Dict[str, Any],
    frontier_summary: Dict[str, Any],
    union_summary: Dict[str, Any],
    case_digests: Iterable[Dict[str, Any]],
    plugin_version: str,
    repo_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Append one eval-run receipt to the hash chain and return it.

    ``case_digests`` items should be minimal per-case facts
    (case_id / passed / actual_status); they are hashed into
    ``case_results_sha256`` so the aggregate numbers can be re-derived without
    embedding the full report.
    """
    resolved = (log_path or default_log_path(repo_root)).resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    if repo_root is None:
        repo_root = _discover_repo_root()

    digests = list(case_digests)
    with _APPEND_LOCK:
        events, errors = verify_eval_log(resolved)
        if errors:
            raise ValueError("refusing to append to invalid eval receipt chain: " + "; ".join(errors))

        previous_hash = events[-1]["event_hash"] if events else GENESIS_HASH
        event: Dict[str, Any] = {
            "schema_version": EVAL_RECEIPT_SCHEMA,
            "sequence": len(events) + 1,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": "eval_run",
            "plugin_version": plugin_version,
            "suite": suite,
            "provider": provider,
            "model": model,
            "strict_mode": bool(strict_mode),
            "gating_summary": dict(gating_summary),
            "frontier_summary": dict(frontier_summary),
            "union_summary": dict(union_summary),
            "case_count": len(digests),
            "case_results_sha256": sha256_json(digests),
            "abi_manifest_sha256": abi_manifest_digest(),
            "git_commit": _git_commit(repo_root),
            "git_dirty": _git_dirty(repo_root),
            "previous_event_hash": previous_hash,
        }
        event["event_hash"] = _event_hash(event)
        with resolved.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(canonical_json(event) + "\n")
            handle.flush()
            if os.name != "nt":
                os.fsync(handle.fileno())
        return event


def summarize_report_for_receipt(report: Any) -> Dict[str, Any]:
    """Extract the receipt payload fields from a BenchmarkReport."""
    gating_cases = [
        {"case_id": r.case_id, "passed": bool(r.passed), "actual_status": r.actual_status}
        for r in getattr(report, "detailed_results", []) or []
    ]
    frontier_cases = [
        {"case_id": r.case_id, "passed": bool(r.passed), "actual_status": r.actual_status}
        for r in getattr(report, "frontier_results", []) or []
    ]
    gating_summary = {
        "total_cases": getattr(report, "total_cases", 0),
        "passed_cases": getattr(report, "passed_cases", 0),
        "failed_cases": getattr(report, "failed_cases", 0),
        "skipped_cases": getattr(report, "skipped_cases", 0),
        "overall_accuracy": getattr(report, "overall_accuracy", 0.0),
        "cri": (getattr(report, "metrics", {}) or {}).get("composite_reliability_index"),
    }
    frontier_metrics = getattr(report, "frontier_metrics", {}) or {}
    frontier_summary = {
        "total_cases": len(frontier_cases),
        "passed_cases": sum(1 for c in frontier_cases if c["passed"]),
        "pass_rate": frontier_metrics.get("pass_rate"),
    }
    union_summary = {
        "total": getattr(report, "union_total", 0),
        "passed": getattr(report, "union_passed", 0),
        "accuracy": getattr(report, "union_accuracy", 0.0),
    }
    return {
        "gating_summary": gating_summary,
        "frontier_summary": frontier_summary,
        "union_summary": union_summary,
        "case_digests": gating_cases + frontier_cases,
    }
