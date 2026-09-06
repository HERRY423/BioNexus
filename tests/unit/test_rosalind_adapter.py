"""Unit tests for BioNexus ChatGPT Rosalind Adapter (BNS-022 / BNS-025 / BNS-019)."""

from __future__ import annotations

from bionexus.rosalind_adapter import (
    evaluate_rosalind_warrant,
    export_openai_tool_definitions,
    intake_chatgpt_tool_call,
)
from bionexus.tool_receipt import ToolReceiptLevel, verify_tool_receipt


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


def test_intake_missing_source_context_stays_incomplete_no_synthetic_fallbacks():
    """P0-1 Fix: Missing upstream information remains INCOMPLETE; no synthetic guessing."""
    res = intake_chatgpt_tool_call(
        tool_name="search_uniprot",
        arguments={"query": "P04637"},
        raw_result={"entry": "P53_HUMAN"},
        source_database="UniProtKB",
        source_accession="P04637",
        # database_release and identifier_namespace are intentionally NOT provided
    )

    # Must NOT guess database_release="2026_01" or organism_taxon="9606"
    assert res.intake_status == "INCOMPLETE"
    assert "database_release" in res.audit.missing_context
    assert "identifier_namespace" in res.audit.missing_context
    # Intake validity != claim warranted
    assert res.is_warranted is False


def test_intake_complete_context_creates_envelope_and_level1_receipt():
    """Complete context produces VALID intake and a Level 1 Host-Observed Receipt."""
    res = intake_chatgpt_tool_call(
        tool_name="search_uniprot",
        arguments={"query": "P04637", "reviewed": True},
        raw_result={
            "primaryAccession": "P04637",
            "uniProtkbId": "P53_HUMAN",
            "organism": {"scientificName": "Homo sapiens", "taxonId": 9606},
            "genes": [{"geneName": {"value": "TP53"}}],
        },
        source_database="UniProtKB",
        source_accession="P04637",
        metadata={
            "database_release": "2026_01",
            "identifier_namespace": "uniprot.accession",
        },
    )

    assert res.tool_name == "search_uniprot"
    assert res.envelope.family == "database"
    assert res.intake_status == "VALID"
    assert len(res.warnings) == 0

    # Receipt is Level 1 Host-Observed (BNS-025)
    assert res.receipt["receipt_level"] == ToolReceiptLevel.LEVEL_1_HOST_OBSERVED.value
    assert "host_context" in res.receipt
    assert res.receipt["host_context"]["host"] == "chatgpt-rosalind"

    # Verify cryptographic integrity
    valid, errors = verify_tool_receipt(
        res.receipt,
        expected_request=res.arguments,
        expected_response=res.raw_result,
        expected_plugin_id="chatgpt-rosalind",
        expected_tool_name="search_uniprot",
    )
    assert valid is True
    assert len(errors) == 0


def test_evaluate_rosalind_warrant_separates_three_epistemic_states():
    """BNS-025: INTAKE_VALID != EVIDENCE_SUPPORTS_CLAIM != CLAIM_WARRANTED."""
    # Complete database evidence
    res1 = intake_chatgpt_tool_call(
        tool_name="search_uniprot",
        arguments={"query": "P04637"},
        raw_result={"entry": "P53_HUMAN", "organism": {"taxonId": 9606}},
        source_database="UniProtKB",
        source_accession="P04637",
        metadata={
            "database_release": "2026_01",
            "identifier_namespace": "uniprot.accession",
        },
    )
    assert res1.intake_status == "VALID"

    # Complete analysis evidence
    res2 = intake_chatgpt_tool_call(
        tool_name="run_pseudobulk_de",
        arguments={"dataset_id": "kang2018_pbmc_ifnb", "contrast_column": "stim"},
        raw_result={"log2FoldChange": 2.4, "padj": 1e-12},
        metadata={
            "parameters_sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
            "execution_receipt_sha256": "fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210",
        },
    )
    assert res2.intake_status == "VALID"

    # 1. Unadjudicated call: adjudications=None -> context-only, CANNOT claim SUPPORTED
    eval_unadj = evaluate_rosalind_warrant(
        claim_id="CLM-UNADJ",
        target_claim="TP53 is differentially expressed in stimulated lymphocytes.",
        tool_results=[res1, res2],
        stated_maturity="SUPPORTED",
    )
    assert eval_unadj["intake_valid"] is True
    assert eval_unadj["evidence_supports_claim"] is False
    assert eval_unadj["claim_warranted"] is False
    assert eval_unadj["warranted_maturity"] == "UNASSESSED"
    assert any("No evidence envelope has been explicitly adjudicated" in r for r in eval_unadj["downgrade_reasons"])

    # 2. Single-modality with explicit supports: capped at PRELIMINARY
    eval_single = evaluate_rosalind_warrant(
        claim_id="CLM-SINGLE",
        target_claim="TP53 is associated with cellular response.",
        tool_results=[res1],
        adjudications=["supports"],
        stated_maturity="SUPPORTED",
        adjudicator_id="dr_reviewer",
    )
    assert eval_single["intake_valid"] is True
    assert eval_single["evidence_supports_claim"] is True
    assert eval_single["claim_warranted"] is False  # Cannot claim SUPPORTED from single modality
    assert eval_single["warranted_maturity"] == "PRELIMINARY"
    assert any("Single-modality" in r for r in eval_single["downgrade_reasons"])

    # 3. Multi-modality with explicit supports and complete context: WARRANTED
    eval_multi = evaluate_rosalind_warrant(
        claim_id="CLM-MULTI",
        target_claim="TP53 is differentially expressed in stimulated lymphocytes.",
        tool_results=[res1, res2],
        adjudications=["supports", "supports"],
        stated_maturity="SUPPORTED",
        adjudicator_id="dr_reviewer",
    )
    assert eval_multi["intake_valid"] is True
    assert eval_multi["evidence_supports_claim"] is True
    assert eval_multi["claim_warranted"] is True
    assert eval_multi["warranted_maturity"] == "SUPPORTED"
    assert eval_multi["is_warranted"] is True


def test_evaluate_rosalind_warrant_enforces_connector_profile_prohibitions():
    """Connector profile prohibited claims (e.g. causality from database) trigger downgrade."""
    res1 = intake_chatgpt_tool_call(
        tool_name="search_uniprot",
        arguments={"query": "P04637"},
        raw_result={"entry": "P53_HUMAN", "organism": {"taxonId": 9606}},
        source_database="UniProtKB",
        source_accession="P04637",
        metadata={
            "database_release": "2026_01",
            "identifier_namespace": "uniprot.accession",
        },
    )
    # search_uniprot profile prohibits 'causality'
    eval_causal = evaluate_rosalind_warrant(
        claim_id="CLM-CAUSAL",
        target_claim="TP53 directly causes tumorigenesis in all patients.",
        tool_results=[res1],
        adjudications=["supports"],
        stated_maturity="PRELIMINARY",
    )
    assert any("prohibited inference" in r for r in eval_causal["downgrade_reasons"])
