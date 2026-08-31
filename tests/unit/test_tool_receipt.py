"""Unit tests for BioNexus Tool Execution Receipt Engine (BNS-021)."""

from __future__ import annotations

import json
from pathlib import Path

from bionexus.tool_receipt import (
    SCHEMA_VERSION,
    append_receipt_log,
    canonical_json,
    create_tool_receipt,
    hash_canonical_payload,
    verify_receipt_log_chain,
    verify_tool_receipt,
)


def test_canonical_json_and_payload_hashing():
    """Verify deterministic formatting and hashing regardless of dict key ordering."""
    dict_a = {"b": 2, "a": 1, "nested": {"z": 10, "y": 9}}
    dict_b = {"nested": {"y": 9, "z": 10}, "a": 1, "b": 2}

    assert canonical_json(dict_a) == canonical_json(dict_b)
    assert hash_canonical_payload(dict_a) == hash_canonical_payload(dict_b)

    # String vs object normalization
    json_str = '{"a": 1, "b": 2}'
    assert hash_canonical_payload(json_str) == hash_canonical_payload({"b": 2, "a": 1})


def test_create_and_verify_valid_receipt():
    """Verify standard tool receipt creation and validation passes."""
    req = {"query": "P04637", "database": "uniprotkb"}
    resp = {"entry": "P53_HUMAN", "gene": "TP53", "organism": "Homo sapiens"}

    receipt = create_tool_receipt(
        plugin_id="bionexus-reliability",
        plugin_version="1.0.0-rc.3",
        tool_name="search_uniprot",
        request_payload=req,
        response_payload=resp,
        execution_status="SUCCESS",
        metadata={"caller": "chatgpt_rosalind"},
    )

    assert receipt["schema_version"] == SCHEMA_VERSION
    assert receipt["plugin_id"] == "bionexus-reliability"
    assert receipt["plugin_version"] == "1.0.0-rc.3"
    assert receipt["tool_name"] == "search_uniprot"
    assert receipt["execution_status"] == "SUCCESS"
    assert len(receipt["request_sha256"]) == 64
    assert len(receipt["response_sha256"]) == 64
    assert len(receipt["receipt_hash"]) == 64

    # Verify matching payloads
    valid, errors = verify_tool_receipt(
        receipt,
        expected_request=req,
        expected_response=resp,
        expected_plugin_id="bionexus-reliability",
        expected_plugin_version="1.0.0-rc.3",
        expected_tool_name="search_uniprot",
    )
    assert valid is True
    assert len(errors) == 0


def test_tamper_detection_on_receipt():
    """Altering any payload or receipt attribute must fail verification."""
    req = {"seq": "ACGT"}
    resp = {"length": 4}

    receipt = create_tool_receipt(
        plugin_id="bionexus",
        plugin_version="1.0.0-rc.3",
        tool_name="calculate_len",
        request_payload=req,
        response_payload=resp,
    )

    # 1. Tampered payload
    tampered_resp = {"length": 5}
    valid, errors = verify_tool_receipt(receipt, expected_response=tampered_resp)
    assert valid is False
    assert any("Response payload hash mismatch" in e for e in errors)

    # 2. Tampered tool name in receipt body
    tampered_receipt = dict(receipt)
    tampered_receipt["tool_name"] = "fake_tool"
    valid, errors = verify_tool_receipt(tampered_receipt)
    assert valid is False
    assert any("Receipt hash mismatch" in e for e in errors)

    # 3. Tampered status
    tampered_receipt2 = dict(receipt)
    tampered_receipt2["execution_status"] = "ERROR"
    valid, errors = verify_tool_receipt(tampered_receipt2)
    assert valid is False
    assert any("Receipt hash mismatch" in e for e in errors)


def test_receipt_log_hash_chaining(tmp_path: Path):
    """Verify append-only hash-chained logging and chain verification."""
    log_file = tmp_path / "receipts.jsonl"

    receipts = []
    prev_hash = None
    for idx in range(4):
        req = {"step": idx}
        resp = {"result": idx * 10}
        r = create_tool_receipt(
            plugin_id="bionexus",
            plugin_version="1.0.0-rc.3",
            tool_name=f"step_{idx}",
            request_payload=req,
            response_payload=resp,
            previous_receipt_hash=prev_hash,
            chain_index=idx,
        )
        receipts.append(r)
        append_receipt_log(r, log_file)
        prev_hash = r["receipt_hash"]

    # Verify intact chain
    valid, errors = verify_receipt_log_chain(log_file)
    assert valid is True
    assert len(errors) == 0

    # Tamper with an intermediate line in the log
    lines = log_file.read_text(encoding="utf-8").splitlines()
    tampered_item = json.loads(lines[1])
    tampered_item["plugin_version"] = "2.0.0"
    lines[1] = json.dumps(tampered_item)
    tampered_log = tmp_path / "tampered_receipts.jsonl"
    tampered_log.write_text("\n".join(lines) + "\n", encoding="utf-8")

    tampered_valid, tampered_errors = verify_receipt_log_chain(tampered_log)
    assert tampered_valid is False
    assert len(tampered_errors) >= 1
