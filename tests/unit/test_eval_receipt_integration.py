"""
Integration test: run_benchmark appends a verifiable receipt to the eval chain.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT))

from bionexus.eval_receipt import verify_eval_log


def test_run_benchmark_appends_verifiable_receipt(tmp_path, monkeypatch):
    from evals.runner import run_benchmark

    log_path = tmp_path / "eval_audit.jsonl"
    monkeypatch.setenv("BIONEXUS_EVAL_AUDIT_LOG", "1")
    monkeypatch.setattr(
        "bionexus.eval_receipt.default_log_path", lambda repo_root=None: log_path
    )

    report = run_benchmark(suite="calibration_edge")

    events, errors = verify_eval_log(log_path)
    assert errors == []
    assert len(events) == 1
    event = events[0]
    assert event["event_type"] == "eval_run"
    assert event["suite"] == "calibration_edge"
    assert event["case_count"] == report.union_total
    assert event["gating_summary"]["total_cases"] == report.total_cases
    assert event["union_summary"]["accuracy"] == report.union_accuracy
    assert report.audit_receipt_hash == event["event_hash"]
    assert event["abi_manifest_sha256"].startswith("sha256:")
