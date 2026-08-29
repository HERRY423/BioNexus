"""Unit tests for BioNexus ChatGPT Rosalind Adapter (BNS-022 / BNS-019)."""

from __future__ import annotations

import json
import pytest

from bionexus.rosalind_adapter import (
    evaluate_rosalind_warrant,
    export_openai_tool_definitions,
    intake_chatgpt_tool_call,
)
from bionexus.tool_receipt import verify_tool_receipt


def test_export_openai_tool_definitions():
    """Verify tool definition generation matches OpenAI function schema."""
    tools = export_openai_tool_definitions()
    assert isinstance(tools, list)
    assert len(tools) >= 5

    names = {t["function"]["name"] for t in tools}
    assert "bionexus_warrant_check" in names
    assert "search_uniprot" in names
    assert "search_pdb" in names
    assert "run_pseudobulk_de" in names

    # Verify JSON schema structure
    for t in tools:
        assert t["type"] == "function"
        fn = t["function"]
        assert "name" in fn
        assert "description" in fn
        assert "parameters" in fn
        assert fn["parameters"]["type"] == "object"
        assert "properties" in fn["parameters"]


def test_intake_chatgpt_tool_call_creates_envelope_and_receipt():
    """Intake of ChatGPT tool execution generates valid envelope and receipt."""
    res = intake_chatgpt_tool_call(
        tool_name="search_uniprot",
        arguments={"query": "P04637", "reviewed": True},
        raw_result={
            "primaryAccession": "P04637",
            "uniProtkbId": "P53_HUMAN",
            "organism": {"scientificName": "Homo sapiens"},
            "genes": [{"geneName": {"value": "TP53"}}],
        },
        source_database="UniProtKB",
        source_accession="P04637",
    )

    assert res.tool_name == "search_uniprot"
    assert res.envelope.family == "database"
    assert res.is_warranted is True
    assert len(res.warnings) == 0

    # Verify generated receipt
    valid, errors = verify_tool_receipt(
        res.receipt,
        expected_request=res.arguments,
        expected_response=res.raw_result,
        expected_plugin_id="chatgpt-rosalind",
        expected_tool_name="search_uniprot",
    )
    assert valid is True
    assert len(errors) == 0


def test_evaluate_rosalind_warrant_enforces_epistemic_ceilings():
    """Multi-envelope claims are evaluated against cross-family warrant standards."""
    # 1. Single database envelope attempting to claim SUPPORTED
    res1 = intake_chatgpt_tool_call(
        tool_name="search_uniprot",
        arguments={"query": "P04637"},
        raw_result={"entry": "P53_HUMAN"},
    )
    eval1 = evaluate_rosalind_warrant(
        claim_id="CLM-001",
        target_claim="TP53 causes oncogenic transformation.",
        tool_results=[res1],
        stated_maturity="SUPPORTED",
    )
    # Single modality cannot claim SUPPORTED -> downgraded to PRELIMINARY
    assert eval1["warranted_maturity"] == "PRELIMINARY"
    assert eval1["is_warranted"] is False
    assert any("Single-modality" in r for r in eval1["downgrade_reasons"])

    # 2. Multi-modality (Database + Analysis)
    res2 = intake_chatgpt_tool_call(
        tool_name="run_pseudobulk_de",
        arguments={"dataset_id": "kang2018_pbmc_ifnb", "contrast_column": "stim"},
        raw_result={"log2FoldChange": 2.4, "padj": 1e-12},
    )
    eval2 = evaluate_rosalind_warrant(
        claim_id="CLM-002",
        target_claim="TP53 is differentially expressed in stimulated lymphocytes.",
        tool_results=[res1, res2],
        stated_maturity="SUPPORTED",
    )
    assert eval2["warranted_maturity"] == "SUPPORTED"
    assert eval2["is_warranted"] is True
    assert len(eval2["receipts"]) == 2
