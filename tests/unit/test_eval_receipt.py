"""
Unit tests for the eval receipt chain: tamper-evident benchmark history
(BNS-006 provenance / eval-receipt chain v1).

Invariants under test:
- Append-only hash chain with sequence + previous-hash links.
- Any mutation of a historical event is detected by verify_eval_log.
- Appending refuses to extend a corrupted chain (fail-closed).
- The ABI manifest digest is deterministic and anchors receipts to an
  exact contract set.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from bionexus.eval_receipt import (
    GENESIS_HASH,
    abi_manifest_digest,
    append_eval_receipt,
    build_abi_manifest,
    default_log_path,
    summarize_report_for_receipt,
    verify_eval_log,
)


def _append(tmp_path: Path, sequence_hint: str = "") -> dict:
    return append_eval_receipt(
        log_path=tmp_path / "eval_audit.jsonl",
        suite="biofailurebench",
        provider="replay",
        model="simulated_trace_v1",
        strict_mode=False,
        gating_summary={"total_cases": 2, "passed_cases": 2, "failed_cases": 0},
        frontier_summary={"total_cases": 1, "passed_cases": 1},
        union_summary={"total": 3, "passed": 3, "accuracy": 1.0},
        case_digests=[
            {"case_id": f"case-a{sequence_hint}", "passed": True, "actual_status": "PERMITTED"},
            {"case_id": f"case-b{sequence_hint}", "passed": True, "actual_status": "ABSTAIN"},
        ],
        plugin_version="test",
        repo_root=tmp_path,
    )


def test_chain_appends_and_verifies(tmp_path):
    first = _append(tmp_path)
    second = _append(tmp_path, "x")
    assert first["sequence"] == 1 and first["previous_event_hash"] == GENESIS_HASH
    assert second["sequence"] == 2
    assert second["previous_event_hash"] == first["event_hash"]

    events, errors = verify_eval_log(tmp_path / "eval_audit.jsonl")
    assert errors == []
    assert len(events) == 2


def test_tampered_history_is_detected(tmp_path):
    _append(tmp_path)
    _append(tmp_path, "x")
    log = tmp_path / "eval_audit.jsonl"
    events = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line.strip()]
    events[0]["gating_summary"]["passed_cases"] = 99  # rewrite history
    log.write_text(
        "\n".join(json.dumps(e, sort_keys=True, separators=(",", ":")) for e in events) + "\n",
        encoding="utf-8",
    )
    _, errors = verify_eval_log(log)
    assert any("event_hash mismatch" in e for e in errors)


def test_deleted_middle_event_is_detected(tmp_path):
    _append(tmp_path)
    _append(tmp_path, "x")
    _append(tmp_path, "y")
    log = tmp_path / "eval_audit.jsonl"
    lines = [ln for ln in log.read_text(encoding="utf-8").splitlines() if ln.strip()]
    del lines[1]  # remove middle receipt -> sequence + hash links break
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    _, errors = verify_eval_log(log)
    assert errors, "removing a middle event must break the chain"


def test_append_refuses_corrupted_chain(tmp_path):
    _append(tmp_path)
    log = tmp_path / "eval_audit.jsonl"
    lines = [ln for ln in log.read_text(encoding="utf-8").splitlines() if ln.strip()]
    mutated = json.loads(lines[0])
    mutated["union_summary"]["accuracy"] = 0.42
    lines[0] = json.dumps(mutated, sort_keys=True, separators=(",", ":"))
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid eval receipt chain"):
        _append(tmp_path, "z")


def test_case_digest_changes_change_event_hash(tmp_path):
    a = _append(tmp_path)
    b = _append(tmp_path, "different")
    assert a["event_hash"] != b["event_hash"]
    assert a["case_results_sha256"] != b["case_results_sha256"]


def test_abi_manifest_deterministic_and_anchored():
    d1 = abi_manifest_digest()
    d2 = abi_manifest_digest()
    assert d1 == d2
    manifest = build_abi_manifest()
    assert manifest["manifest_schema"] == "bionexus.abi-manifest.v1"
    records = manifest["abi_records"]
    assert len(records) > 0
    sample = next(iter(records.values()))
    assert "forbidden_claims" in sample and "evidence_ceiling" in sample


def test_default_log_path_under_repo_root():
    p = default_log_path(PROJECT_ROOT)
    assert p.name == "eval_audit.jsonl" and p.parent.name == "logs"


def test_summarize_report_for_receipt_shape():
    class _FakeReport:
        total_cases = 3
        passed_cases = 3
        failed_cases = 0
        skipped_cases = 0
        overall_accuracy = 1.0
        metrics = {"composite_reliability_index": 100.0}
        detailed_results = [
            type("R", (), {"case_id": "c1", "passed": True, "actual_status": "PERMITTED"})()
        ]
        frontier_results = [
            type("R", (), {"case_id": "f1", "passed": False, "actual_status": "PERMITTED"})()
        ]
        frontier_metrics = {"pass_rate": 0.5}
        union_total = 2
        union_passed = 1
        union_accuracy = 0.5

    payload = summarize_report_for_receipt(_FakeReport())
    assert payload["gating_summary"]["cri"] == 100.0
    assert payload["frontier_summary"]["passed_cases"] == 0
    assert len(payload["case_digests"]) == 2


def test_extract_evidence_factors_from_valid_tool_receipt():
    from bionexus.tool_receipt import create_tool_receipt, extract_evidence_factors_from_receipt

    receipt = create_tool_receipt(
        plugin_id="bionexus-gold",
        plugin_version="1.0.0-rc.3",
        tool_name="scrna.pseudobulk_de",
        request_payload={"adata_path": "data/kang.h5ad", "design": "~condition"},
        response_payload={"de_table_sha256": "abcdef1234567890"},
        execution_status="SUCCESS",
        metadata={
            "min_replicates_per_condition": 3,
            "confound_controls": True,
            "sensitivity_analysis": True,
            "external_validation": True,
        },
    )
    factors, notes = extract_evidence_factors_from_receipt(receipt)
    assert "backend_fidelity" in factors
    assert "provenance" in factors
    assert "sample_design" in factors
    assert "replication" in factors
    assert "confound_controls" in factors
    assert "sensitivity_analysis" in factors
    assert "external_validation" in factors
    assert any("verified cryptographic execution proof" in n for n in notes)


def test_tampered_tool_receipt_fails_verification_and_grants_no_factors():
    from bionexus.tool_receipt import create_tool_receipt, extract_evidence_factors_from_receipt

    receipt = create_tool_receipt(
        plugin_id="bionexus-gold",
        plugin_version="1.0.0-rc.3",
        tool_name="scrna.pseudobulk_de",
        request_payload={"data": "real"},
        response_payload={"result": "valid"},
        execution_status="SUCCESS",
        metadata={"min_replicates_per_condition": 5},
    )
    tampered = dict(receipt)
    tampered["request_sha256"] = "0000000000000000000000000000000000000000000000000000000000000000"
    factors, notes = extract_evidence_factors_from_receipt(tampered)
    assert len(factors) == 0
    assert any("verification failed" in n for n in notes)


def test_failed_tool_execution_status_grants_no_factors():
    from bionexus.tool_receipt import create_tool_receipt, extract_evidence_factors_from_receipt

    receipt = create_tool_receipt(
        plugin_id="bionexus-gold",
        plugin_version="1.0.0-rc.3",
        tool_name="scrna.pseudobulk_de",
        request_payload={"data": "bad"},
        response_payload={"error": "failed"},
        execution_status="ERROR",
        metadata={"min_replicates_per_condition": 3},
    )
    factors, notes = extract_evidence_factors_from_receipt(receipt)
    assert len(factors) == 0
    assert any("not SUCCESS" in n for n in notes)


def test_tool_receipt_log_chain_extraction(tmp_path):
    from bionexus.tool_receipt import append_receipt_log, create_tool_receipt, extract_evidence_factors_from_receipt_log

    log_path = tmp_path / "audit_receipts.jsonl"
    r1 = create_tool_receipt(
        plugin_id="bionexus-gold",
        plugin_version="1.0.0-rc.3",
        tool_name="scrna.qc_filter",
        request_payload={"in": "raw.h5ad"},
        response_payload={"out": "qc.h5ad"},
        execution_status="SUCCESS",
        metadata={"min_replicates_per_condition": 3},
        chain_index=0,
    )
    append_receipt_log(r1, log_path)
    r2 = create_tool_receipt(
        plugin_id="bionexus-gold",
        plugin_version="1.0.0-rc.3",
        tool_name="scrna.pseudobulk_de",
        request_payload={"in": "qc.h5ad"},
        response_payload={"out": "de.csv"},
        execution_status="SUCCESS",
        metadata={"confound_controls": True, "sensitivity_analysis": True},
        previous_receipt_hash=r1["receipt_hash"],
        chain_index=1,
    )
    append_receipt_log(r2, log_path)
    factors, notes = extract_evidence_factors_from_receipt_log(log_path)
    assert "sample_design" in factors
    assert "replication" in factors
    assert "confound_controls" in factors
    assert "sensitivity_analysis" in factors
    assert "backend_fidelity" in factors
    assert "provenance" in factors


def test_e2e_route_scientific_intent_with_tool_receipts(canonical_backends_available):
    from bionexus.evidence_model import ClaimClass, SufficiencyVerdict
    from bionexus.intent_router import route_scientific_intent
    from bionexus.tool_receipt import create_tool_receipt

    receipt = create_tool_receipt(
        plugin_id="bionexus-gold",
        plugin_version="1.0.0-rc.3",
        tool_name="scrna.pseudobulk_de",
        request_payload={"kang_counts": "verified"},
        response_payload={"pvalues_computed": True},
        execution_status="SUCCESS",
        metadata={
            "min_replicates_per_condition": 3,
            "confound_controls": True,
            "sensitivity_analysis": True,
        },
    )
    decision = route_scientific_intent(
        "pseudobulk differential expression analysis",
        research_purpose="confirmatory",
        claim_context=ClaimClass.POPULATION_EFFECT,
        data_metadata={"is_integer_like": True, "is_normalized": False, "conditions": 2},
        tool_receipts=[receipt],
    )
    assert decision.status.value == "PERMITTED"
    card = decision.evidence_card_template
    assert card is not None
    assert card.details["evidence_assessment"]["evidence_maturity"] == "ROBUST"
    assert "backend_fidelity" in card.details["evidence_assessment"]["satisfied_factors"]
    assert "provenance" in card.details["evidence_assessment"]["satisfied_factors"]
    assert "sample_design" in card.details["evidence_assessment"]["satisfied_factors"]
    assert "replication" in card.details["evidence_assessment"]["satisfied_factors"]
    assert "confound_controls" in card.details["evidence_assessment"]["satisfied_factors"]
    assert "sensitivity_analysis" in card.details["evidence_assessment"]["satisfied_factors"]
    assert card.details["sufficiency"]["verdict"] == SufficiencyVerdict.WARRANTED.value
