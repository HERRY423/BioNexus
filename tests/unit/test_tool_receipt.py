"""Unit tests for BioNexus Tool Execution Receipt Engine (BNS-025)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

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


def test_level_0_content_integrity_receipt_grants_zero_factors_and_blocks_self_promotion():
    """P0-2: Level 0 proves only request/response SHA; zero evidence factors certified."""
    from bionexus.tool_receipt import (
        ToolReceiptLevel,
        create_content_integrity_receipt,
        extract_evidence_factors_from_receipt,
    )

    r0 = create_content_integrity_receipt(
        plugin_id="upstream-connector",
        plugin_version="0.1.0",
        tool_name="untrusted_query",
        request_payload={"query": "test"},
        response_payload={"result": "data"},
        metadata={
            "external_validation": True,
            "independent_validation": True,
            "min_replicates_per_condition": 10,
            "confound_controls": True,
            "backend_fidelity": True,
        },
    )

    assert r0["receipt_level"] == ToolReceiptLevel.LEVEL_0_CONTENT_INTEGRITY.value

    # Cryptographic integrity holds
    ver_ok, ver_err = verify_tool_receipt(r0)
    assert ver_ok is True
    assert not ver_err

    # Zero factors granted: self-declared metadata cannot escalate into evidence factors
    factors, notes = extract_evidence_factors_from_receipt(r0)
    assert len(factors) == 0
    assert any("Level 0 Content Integrity receipt" in n for n in notes)
    assert any("Zero scientific evidence factors certified" in n for n in notes)


def test_level_1_host_declaration_cannot_certify_provenance():
    """Host identity strings are not a trusted observation proof."""
    from bionexus.tool_receipt import (
        ToolReceiptLevel,
        create_host_observed_receipt,
        extract_evidence_factors_from_receipt,
    )

    r1 = create_host_observed_receipt(
        host="claude-code-observer",
        connector_id="chembl-connector",
        tool_name="query_chembl",
        request_payload={"target": "CHEMBL25"},
        response_payload={"ic50": 12.5},
        mcp_server_uri="stdio://chembl-mcp",
        transport="json_rpc_pipe",
        metadata={
            "external_validation": True,
            "backend_fidelity": True,
        },
    )

    assert r1["receipt_level"] == ToolReceiptLevel.LEVEL_1_HOST_OBSERVED.value
    assert r1["host_context"]["host"] == "claude-code-observer"

    # Cryptographic integrity holds
    ver_ok, ver_err = verify_tool_receipt(r1)
    assert ver_ok is True
    assert not ver_err

    # A self-hashed host declaration cannot certify any evidence factor.
    factors, notes = extract_evidence_factors_from_receipt(r1)
    assert factors == set()
    assert "backend_fidelity" not in factors
    assert "external_validation" not in factors
    assert any("Level 1 Host-Observed receipt" in n for n in notes)


def test_level_2_attestation_dictionary_cannot_certify_factors():
    """Naming a provider/independent validation basis does not verify a signature."""
    from bionexus.tool_receipt import (
        ToolReceiptLevel,
        create_attested_tool_receipt,
        extract_evidence_factors_from_receipt,
    )

    # 1. Attested receipt with replication design factors
    r2 = create_attested_tool_receipt(
        plugin_id="bionexus-gold",
        plugin_version="1.0.0-rc.3",
        tool_name="scrna.pseudobulk_de",
        request_payload={"dataset": "kang"},
        response_payload={"de_genes": ["IFNG", "STAT1"]},
        attestation={
            "attested_by": "bionexus-gold-provider",
            "attestation_type": "hardware_signed_execution",
            "external_validation_basis": "independent_replication_cohort",
        },
        metadata={
            "min_replicates_per_condition": 3,
            "confound_controls": True,
            "sensitivity_analysis": True,
            "external_validation": True,
        },
    )

    assert r2["receipt_level"] == ToolReceiptLevel.LEVEL_2_PROVIDER_ATTESTED.value

    ver_ok, ver_err = verify_tool_receipt(r2)
    assert ver_ok is True
    assert not ver_err

    factors, notes = extract_evidence_factors_from_receipt(r2)
    assert factors == set()
    assert any("ATTESTATION_NOT_VERIFIED" in note for note in notes)

    # 2. Attempting external_validation without external_validation_basis is blocked
    r2_no_ext = create_attested_tool_receipt(
        plugin_id="bionexus-gold",
        plugin_version="1.0.0-rc.3",
        tool_name="scrna.pseudobulk_de",
        request_payload={"dataset": "kang"},
        response_payload={"de_genes": ["IFNG"]},
        attestation={"attested_by": "bionexus-gold-provider"},
        metadata={"external_validation": True},
    )
    factors_no_ext, _ = extract_evidence_factors_from_receipt(r2_no_ext)
    assert "external_validation" not in factors_no_ext


@pytest.mark.parametrize("level", [-1, 3, 999, True, "2", None, {}, []])
def test_invalid_receipt_levels_never_fall_through_to_attested(level):
    from bionexus.tool_receipt import compute_receipt_hash, extract_evidence_factors_from_receipt

    receipt = create_tool_receipt(
        plugin_id="untrusted", plugin_version="1", tool_name="query",
        request_payload={}, response_payload={},
        metadata={"evidence_factors": ["external_validation", "regulatory_certification"]},
    )
    receipt["receipt_level"] = level
    receipt["receipt_hash"] = compute_receipt_hash(receipt)
    factors, notes = extract_evidence_factors_from_receipt(receipt)
    assert factors == set()
    assert any("Invalid receipt_level" in note for note in notes)


def test_rehashed_forged_signature_cannot_promote_through_log_or_evidence_model(tmp_path):
    from bionexus.evidence_model import extract_evidence_factors
    from bionexus.tool_receipt import (
        compute_receipt_hash,
        create_attested_tool_receipt,
        extract_evidence_factors_from_receipt_log,
    )

    receipt = create_attested_tool_receipt(
        plugin_id="untrusted", plugin_version="1", tool_name="query",
        request_payload={}, response_payload={},
        attestation={"signature": "forged", "role": "independent_assessor",
                     "public_key": "attacker-supplied", "regulatory_audit": True},
        metadata={"evidence_factors": ["external_validation", "regulatory_certification"],
                  "external_validation": True, "fda_cleared": True},
    )
    receipt["receipt_hash"] = compute_receipt_hash(receipt)
    assert verify_tool_receipt(receipt)[0]  # Integrity is distinct from trust.
    path = tmp_path / "receipts.jsonl"
    append_receipt_log(receipt, path)
    assert extract_evidence_factors_from_receipt_log(path)[0] == set()
    assert extract_evidence_factors(tool_receipts=[receipt], receipt_log_path=path) == []


def test_conflicting_receipt_tier_aliases_fail_closed():
    from bionexus.tool_receipt import compute_receipt_hash

    receipt = create_tool_receipt(plugin_id="p", plugin_version="1", tool_name="t",
                                  request_payload={}, response_payload={})
    receipt["level"] = 2
    receipt["receipt_hash"] = compute_receipt_hash(receipt)
    valid, errors = verify_tool_receipt(receipt)
    assert not valid
    assert any("Conflicting" in error for error in errors)
