"""Synthetic adapter trust-boundary regression cases; no upstream tool calls."""
from dataclasses import replace

import pytest

from bionexus.ecosystem_claim import EvidenceAdjudication
from bionexus.rosalind_adapter import evaluate_rosalind_warrant, intake_chatgpt_tool_call


def _results(status="SUCCESS", response=None):
    database = intake_chatgpt_tool_call(
        tool_name="search_uniprot", arguments={"query": "synthetic"},
        raw_result={"entry": "synthetic", "organism": {"taxonId": 9606}},
        source_database="synthetic", source_accession="synthetic",
        metadata={"database_release": "fixture", "identifier_namespace": "fixture"})
    analysis = intake_chatgpt_tool_call(
        tool_name="run_pseudobulk_de", arguments={"dataset_id": "synthetic"},
        raw_result=response if response is not None else {"padj": .04},
        execution_status=status,
        metadata={"parameters_sha256": "0" * 64, "execution_receipt_sha256": "1" * 64})
    return [database, analysis]


def _evaluate(results, **kwargs):
    return evaluate_rosalind_warrant(
        claim_id="synthetic", target_claim="A gene is differentially expressed.",
        tool_results=results, adjudications=kwargs.pop("adjudications", ["supports"] * len(results)),
        adjudicator_id=kwargs.pop("adjudicator_id", "declared_fixture_reviewer"), **kwargs)


@pytest.mark.parametrize("status", ["FAILED", "ERROR", "ABSTAIN", "REJECTED", "", "UNKNOWN"])
def test_non_success_receipts_cannot_upgrade(status):
    results = _results(status=status)
    output = _evaluate(results)
    assert not output["claim_warranted"]
    assert output["warranted_maturity"] != "SUPPORTED"
    assert output["declared_adjudications"][1]["relationship"] == "supports"
    assert output["claim_packet"]["adjudications"][1]["relationship"] == "context"
    assert output["receipts"][1]["execution_status"] == status


@pytest.mark.parametrize("response", [{"error": "fit failed"}, {"errors": ["fit failed"]},
                                     {"isError": True}, {"success": False}, {"status": "FAILED"},
                                     {"status": "TIMEOUT"}, {"status": "CANCELLED"},
                                     {"status": " timed out "}, {"status": "PENDING"},
                                     {"execution_status": "FAILED"}, {"execution_status": None}])
def test_explicit_error_overrides_default_success(response):
    results = _results(response=response)
    output = _evaluate(results)
    assert not output["claim_warranted"]
    assert results[1].raw_result == response
    assert not output["execution_checks"][1]["eligible_for_support"]


@pytest.mark.parametrize("mutation", ["receipt", "request", "response", "envelope", "source_context", "tool"])
def test_rechecks_content_after_intake(mutation):
    results = _results()
    result = results[1]
    if mutation == "receipt":
        result.receipt["receipt_hash"] = "0" * 64
    elif mutation == "request":
        result.arguments["dataset_id"] = "different"
    elif mutation == "response":
        result.raw_result = {"padj": .9}
    elif mutation == "envelope":
        result.envelope.payload["padj"] = .9
    elif mutation == "source_context":
        result.envelope.source_context["response_sha256"] = "0" * 64
    elif mutation == "tool":
        result.tool_name = "other"
    assert not _evaluate(results)["claim_warranted"]


def test_no_invented_reviewer_or_decision_owner():
    output = _evaluate(_results(), adjudicator_id=None)
    assert not output["claim_warranted"]
    assert output["claim_packet"]["decision_owner"] == ""
    assert output["declared_adjudications"][0]["adjudicator_id"] == ""


@pytest.mark.parametrize("adjudications", [["supports"], ["supports"] * 3])
def test_no_silent_truncation(adjudications):
    with pytest.raises(ValueError, match="Exactly one"):
        _evaluate(_results(), adjudications=adjudications)


def test_structured_adjudication_cannot_bypass_failure():
    results = _results(status="FAILED")
    adjudications = [EvidenceAdjudication(
        evidence_id=result.envelope.evidence_id, relationship="supports", maturity="SUPPORTED",
        rationale="Synthetic declared support", adjudicator_id="fixture", adjudication_receipt_sha256="2" * 64)
        for result in results]
    output = _evaluate(results, adjudications=adjudications)
    assert not output["claim_warranted"]
    assert adjudications[1].relationship == "supports"


def test_valid_declared_support_still_works():
    assert _evaluate(_results())["claim_warranted"]
    assert _evaluate(_results(status="success"))["claim_warranted"]


def test_failure_retained_as_context_does_not_taint_other_successful_support():
    results = _results()
    failure = _results(status="FAILED")[1]
    failure.envelope = replace(failure.envelope, evidence_id="distinct-failure")
    output = _evaluate(results + [failure], adjudications=["supports", "supports", "context"])
    assert output["claim_warranted"]
    assert not output["execution_checks"][2]["eligible_for_support"]
