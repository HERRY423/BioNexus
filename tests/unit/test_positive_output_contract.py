"""Synthetic contract acceptance; no real laboratory or external service calls."""
import argparse
import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest
from test_de_probability_gate import _audit
from test_rosalind_execution_gate import _evaluate, _results

from bionexus.claim_semantics import DeterministicClaimParser, DeterministicWarrantEngine, EvidenceProfile
from bionexus.contracts import EvidenceCard, attach_meta
from bionexus.de_bundle import verify_de_bundle
from bionexus.de_pilot import render_review, render_summary, summarize_reviews, write_bundle
from bionexus.evidence_contract import (
    SCHEMA,
    conditional_contract,
    contract_schema,
    contract_text,
    evidence_contract,
    interpret_positive_output,
    validate_evidence_contract,
)
from bionexus.evidence_model import assess_evidence
from bionexus.intent_router import route_scientific_intent
from bionexus.mcp.tools.governance import tool_bionexus_warrant_check
from bionexus.warrant import PolicyAction, PolicyDecision, WarrantAssessment


def _safe(c):
    assert validate_evidence_contract(c) == c
    assert c["scientific_facts_verified"] is False
    assert c["scientific_authorization"] == "NONE"
    assert c["independence"] == "UNKNOWN"


@pytest.mark.parametrize("profile,positive", [
    (EvidenceProfile(), False),
    (EvidenceProfile(observational_data=True), True),
    (EvidenceProfile(observational_data=True, independent_validation=True), True),
    (EvidenceProfile(observational_data=True, perturbation=True, biological_replicates_count=3), True),
])
def test_declared_conditions_remain_useful_but_never_verified(profile, positive):
    out = DeterministicWarrantEngine.evaluate(DeterministicClaimParser.parse("Gene A is associated with disease."), profile)
    c = out.to_dict()["evidence_contract"]
    _safe(c)
    assert c == out.evidence_contract
    assert c["outcome"] == ("POSITIVE" if positive else "RESTRICTED")
    assert c["analysis_execution"] == c["input_integrity"] == "UNKNOWN"
    assert c["premises"] == "DECLARED"
    assert all(t["scientific_facts_verified"] is False for t in out.to_dict()["tier_verdicts"].values())


@pytest.mark.parametrize("kwargs", [
    {"perturbation": "false"}, {"independent_validation": 1}, {"observational_data": []},
    {"biological_replicates_count": True}, {"biological_replicates_count": 3.5},
    {"causal_identification_status": "VERIFIED"}, {"plddt_score": float("nan")},
    {"bioactivity_nm": complex(1, 0)}, {"interdomain_pae": float("inf")},
])
def test_malformed_declarations_rejected(kwargs):
    with pytest.raises(ValueError):
        DeterministicWarrantEngine.evaluate(DeterministicClaimParser.parse("Gene A causes disease."), EvidenceProfile(**kwargs))


@pytest.mark.parametrize("positive", [True, False])
def test_shared_objects_consistently_qualify_positive_calculations(positive):
    card = EvidenceCard(execution_state="EXECUTED" if positive else "FAILED")
    wire = card.to_dict()
    _safe(wire["evidence_contract"])
    assert EvidenceCard(**json.loads(json.dumps(wire))).to_dict() == wire
    assert wire["evidence_contract"]["outcome"] == ("POSITIVE" if positive else "RESTRICTED")
    assert contract_text(wire["evidence_contract"]) in card.to_markdown()
    maturity = "SUPPORTED" if positive else "ABSTAIN"
    warrant = WarrantAssessment(maturity, maturity)
    policy = PolicyDecision(PolicyAction.ALLOW, "synthetic", warrant, "fixture")
    for obj in [warrant.to_dict(), policy.to_dict(),
                attach_meta({}, method="fixture", backend="fixture", evidence_card=card),
                assess_evidence(satisfied_factors=[]).to_dict()]:
        _safe(obj["evidence_contract"])
    assert policy.to_dict()["evidence_contract"] == warrant.evidence_contract
    assert policy.to_dict()["evidence_contract"]["outcome"] == ("POSITIVE" if positive else "RESTRICTED")


@pytest.mark.parametrize("field,value", [
    ("schema", "bionexus.evidence-state.v999"), ("outcome", "VERIFIED"),
    ("independence", "VERIFIED"), ("scientific_facts_verified", True),
    ("scientific_facts_verified", 0), ("scientific_authorization", "APPROVED"),
    ("positive_basis", "CHECKED_ARTIFACTS"), ("input_integrity", "CHECKED"),
    ("analysis_execution", "SUCCESS_REPORTED_AND_BOUND"), ("support_status", "UNACCEPTED"),
])
def test_unknown_or_escalated_contract_is_rejected(field, value):
    c = conditional_contract(True)
    c[field] = value
    with pytest.raises(ValueError):
        validate_evidence_contract(c)


def test_card_rejects_imported_artifact_authority():
    card = EvidenceCard().to_dict()
    card["evidence_contract"] = evidence_contract("ARTIFACT_REVIEW", positive=True, observations=["fake"], input_integrity="CHECKED")
    with pytest.raises(ValueError):
        EvidenceCard(**card)


@pytest.mark.parametrize("dimension", ["input_integrity", "assumption_validity", "statistical_support",
                                       "parameter_robustness", "cross_method_concordance", "external_validation"])
def test_unknown_grades_cannot_synthesize_a_positive(dimension):
    card = EvidenceCard(**{dimension: "FUTURE_UNSUPPORTED_GRADE"})
    assert card.synthesize_status() == "ABSTAIN"
    assert card.to_dict()["evidence_contract"]["outcome"] == "RESTRICTED"


@pytest.mark.parametrize("state,expected", [("FAILED", "ABSTAIN"), ("REFUSED", "ABSTAIN"),
                                          ("PERMITTED", "UNASSESSED")])
def test_explicit_nonexecution_overrides_a_positive_card(state, expected):
    out = attach_meta({}, method="fixture", backend="fixture", execution_state=state,
                      evidence_card=EvidenceCard(), conclusion_maturity="SUPPORTED")
    assert out["conclusion_maturity"] == expected
    assert out["declared_conclusion_maturity"] == "SUPPORTED"
    assert out["evidence_contract"]["outcome"] == "RESTRICTED"


def test_consumer_rejects_contract_contradicting_de_status():
    c = evidence_contract("ARTIFACT_REVIEW", positive=True, observations=["fixture"],
                          input_integrity="CHECKED", support="CANDIDATE_CORE")
    with pytest.raises(ValueError):
        interpret_positive_output({"evidence_contract": c, "passed": False, "overall_status": "NEEDS_DATA"},
                                  surface="cli:audit-de")


@pytest.mark.parametrize("values,positive", [
    ([.04, None], True), (["0.9", "1.0"], True), ([None, None], False),
    ([True, False], False), ([float("inf"), .1], False),
])
def test_de_python_json_report_and_bundle_agree(tmp_path, values, positive):
    result = _audit(tmp_path, values, values)
    wire = json.loads(json.dumps(result.to_dict()))
    c = wire["evidence_contract"]
    _safe(c)
    assert c["outcome"] == ("POSITIVE" if positive else "RESTRICTED")
    assert contract_text(c) in result.summary_text(False)
    assert contract_text(c) in result.to_markdown()
    assert contract_text(c) in render_review(wire, "fixture", True)
    bundle = write_bundle(result, tmp_path / "bundle", inputs={}, claim=None, synthetic=True)
    assert json.loads((bundle / "audit.json").read_text(encoding="utf-8"))["evidence_contract"] == c
    check = verify_de_bundle(bundle)
    assert check["status"] == "CONSISTENT"
    assert check["stored_audit_contract"] == c
    assert check["evidence_contract"]["positive_basis"] == "CONSISTENT_BYTES"
    _safe(check["evidence_contract"])
    (bundle / "audit.json").write_text("{}")
    invalid = verify_de_bundle(bundle)
    assert invalid["status"] == "INVALID"
    assert invalid["evidence_contract"]["outcome"] != "POSITIVE"


def test_bundle_unknown_contract_refuses_even_with_matching_hash(tmp_path):
    result = _audit(tmp_path, [.01], [.04])
    bundle = write_bundle(result, tmp_path / "bundle", inputs={}, claim=None, synthetic=True)
    data = result.to_dict()
    data["evidence_contract"]["schema"] = "unknown"
    raw = json.dumps(data).encode()
    (bundle / "audit.json").write_bytes(raw)
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    manifest["audit_sha256"] = manifest["immutable_artifacts"]["audit.json"] = hashlib.sha256(raw).hexdigest()
    (bundle / "manifest.json").write_text(json.dumps(manifest))
    assert verify_de_bundle(bundle)["status"] == "UNSUPPORTED_SCHEMA"


@pytest.mark.parametrize("mutation,expected", [("wrong_kind", "INVALID"), ("negative_status", "INVALID"),
                                               ("legacy_missing", "CONSISTENT")])
def test_bundle_contract_boundaries_with_recomputed_hashes(tmp_path, mutation, expected):
    result = _audit(tmp_path, [.01], [.04])
    bundle = write_bundle(result, tmp_path / "bundle", inputs={}, claim=None, synthetic=True)
    data = result.to_dict()
    if mutation == "wrong_kind":
        data["evidence_contract"] = conditional_contract(True)
    elif mutation == "negative_status":
        data.update(overall_status="NEEDS_DATA", passed=False)
    else:
        del data["evidence_contract"]
    raw = json.dumps(data).encode()
    (bundle / "audit.json").write_bytes(raw)
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    manifest["audit_sha256"] = manifest["immutable_artifacts"]["audit.json"] = hashlib.sha256(raw).hexdigest()
    (bundle / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    out = verify_de_bundle(bundle)
    assert out["status"] == expected
    if mutation == "legacy_missing":
        assert out["stored_audit_contract"]["support_status"] == "UNACCEPTED"
        assert out["evidence_contract"]["positive_basis"] == "CONSISTENT_BYTES"


@pytest.mark.parametrize("field", ["claim_maturity", "evidence_maturity", "conclusion_maturity", "conclusion_status"])
def test_consumer_rejects_primary_negative_maturities(field):
    payload = {"evidence_contract": conditional_contract(True), field: "ABSTAIN"}
    with pytest.raises(ValueError):
        interpret_positive_output(payload, surface="python:bionexus.warrant.WarrantAssessment")


def test_consumer_preserves_scoped_disclaimer_and_policy_separation():
    disclaimer = DeterministicWarrantEngine.evaluate(
        DeterministicClaimParser.parse("These data do not establish causality."), EvidenceProfile()).to_dict()
    assert disclaimer["is_fully_warranted"]
    assert disclaimer["evidence_ceiling"] == "UNASSESSED"
    assert interpret_positive_output(disclaimer,
        surface="python:bionexus.claim_semantics.DeterministicWarrantEngine.evaluate")["positive"]
    warrant = WarrantAssessment("SUPPORTED", "SUPPORTED")
    policy = PolicyDecision(PolicyAction.BLOCK, "fixture", warrant, "Separate operational restriction").to_dict()
    assert interpret_positive_output(policy, surface="python:bionexus.warrant.PolicyDecision")["positive"]
    policy["warrant"]["claim_maturity"] = "ABSTAIN"
    with pytest.raises(ValueError):
        interpret_positive_output(policy, surface="python:bionexus.warrant.PolicyDecision")


def test_consumer_rejects_negative_route():
    payload = {"evidence_contract": conditional_contract(True, support="EXPERIMENTAL"), "status": "ABSTAIN"}
    with pytest.raises(ValueError):
        interpret_positive_output(payload, surface="cli:route")


@pytest.mark.parametrize("status", ["SUCCESS", "FAILED", "PENDING", "UNKNOWN"])
def test_rosalind_bound_response_and_declared_review_are_separate(status):
    out = _evaluate(_results(status=status))
    c = out["evidence_contract"]
    _safe(c)
    assert c["support_status"] == "EXPERIMENTAL"
    assert c["human_review"] == "RECORDED_UNAUTHENTICATED"
    assert (c["outcome"] == "POSITIVE") == (status == "SUCCESS")
    assert c["analysis_execution"] == ("SUCCESS_REPORTED_AND_BOUND" if status == "SUCCESS" else "FAILED_OR_UNRESOLVED")


def test_duplicate_and_null_response_cannot_upgrade():
    results = _results()
    duplicate = _evaluate([results[0], results[0]])
    assert duplicate["evidence_contract"]["outcome"] != "POSITIVE"
    results[1].raw_result = None
    assert _evaluate(results)["evidence_contract"]["outcome"] != "POSITIVE"


def test_summary_unknown_is_not_a_lab_success():
    out = summarize_reviews([])
    _safe(out["evidence_contract"])
    assert out["evidence_contract"]["outcome"] == "RESTRICTED"
    assert contract_text(out["evidence_contract"]) in render_summary(out)


@pytest.mark.parametrize("complete", [False, True])
def test_summary_cli_and_python_preserve_negative_self_reports(tmp_path, capsys, complete):
    from test_de_pilot import _bundle, _complete

    from bionexus.cli import main
    path = _bundle(tmp_path)
    if complete:
        _complete(path)
    direct = summarize_reviews([path])
    assert main(["audit-de-summary", str(path), "--json"]) == 0
    wire = json.loads(capsys.readouterr().out)
    assert wire == direct
    assert wire["evidence_contract"]["outcome"] == ("POSITIVE" if complete else "RESTRICTED")
    assert wire["evidence_contract"]["human_review"] == ("RECORDED_UNAUTHENTICATED" if complete else "UNKNOWN")
    assert wire["mean_review_minutes_saved"] == (-5 if complete else None)
    assert wire["net_benefit"] == "NOT_ESTABLISHED"
    _safe(wire["evidence_contract"])
    assert main(["audit-de-summary", str(path)]) == 0
    assert contract_text(wire["evidence_contract"]) in capsys.readouterr().out


@pytest.mark.parametrize("positive", [True, False])
def test_de_cli_json_file_and_python_contracts_match(tmp_path, capsys, positive):
    import pandas as pd

    from bionexus.cli import main
    from bionexus.de_audit import audit_differential_expression
    table = tmp_path / "table.csv"
    metadata = tmp_path / "metadata.csv"
    receipt_file = tmp_path / "receipt.json"
    donors = [f"D{i}" for i in range(6)]
    pd.DataFrame({"gene": ["G"], "log2FoldChange": [0.0], "pvalue": [.9 if positive else None],
                  "padj": [.9 if positive else None]}).to_csv(table, index=False)
    pd.DataFrame({"donor_id": donors, "condition": ["C"] * 3 + ["T"] * 3}).to_csv(metadata, index=False)
    receipt_file.write_text(json.dumps({"statistical_unit": "donor", "method": "pydeseq2", "fit_status": "CONVERGED",
        "design": "~ condition", "design_matrix_columns": ["Intercept", "condition[T.T]"],
        "n_donors": 6, "donor_ids": donors, "result_sha256": hashlib.sha256(table.read_bytes()).hexdigest()}))
    direct = audit_differential_expression(de_table=table, sample_metadata=metadata, execution_record=receipt_file).to_dict()
    output = tmp_path / "audit-out.json"
    args = ["audit-de", "--de-table", str(table), "--sample-sheet", str(metadata), "--execution", str(receipt_file)]
    assert main([*args, "--json", "--out", str(output)]) == (0 if positive else 1)
    wire = json.loads(capsys.readouterr().out)
    assert wire["evidence_contract"] == direct["evidence_contract"]
    assert json.loads(output.read_text(encoding="utf-8"))["evidence_contract"] == wire["evidence_contract"]
    assert interpret_positive_output(wire, surface="cli:audit-de")["positive"] == positive
    assert main(args) == (0 if positive else 1)
    assert contract_text(wire["evidence_contract"]) in capsys.readouterr().out
    result = audit_differential_expression(de_table=table, sample_metadata=metadata, execution_record=receipt_file)
    bundle = write_bundle(result, tmp_path / "bundle", inputs={}, claim=None, synthetic=True)
    assert main(["audit-de-verify", str(bundle)]) == 0
    verification = json.loads(capsys.readouterr().out)
    assert verification == verify_de_bundle(bundle)
    assert interpret_positive_output(verification, surface="cli:audit-de-verify")["basis"] == "CONSISTENT_BYTES"
    (bundle / "REVIEW.md").write_text("changed")
    assert main(["audit-de-verify", str(bundle)]) == 1
    invalid = json.loads(capsys.readouterr().out)
    assert not interpret_positive_output(invalid, surface="cli:audit-de-verify")["positive"]


@pytest.mark.parametrize("payload,surface", [
    ({"passed": True}, "cli:audit-de"),
    ({"evidence_contract": conditional_contract(True)}, "cli:future-command"),
    ({"evidence_contract": conditional_contract(True)}, "cli:run"),
    ({"evidence_contract": conditional_contract(True)}, "cli:audit-de"),
    ({"evidence_contract": conditional_contract(True)}, "cli:warrant-claim"),
])
def test_consumer_rejects_legacy_flags_unknown_surfaces_and_borrowed_core_status(payload, surface):
    with pytest.raises(ValueError):
        interpret_positive_output(payload, surface=surface)


def test_surface_inventory_is_explicit_and_deduplicated():
    import bionexus
    inventory = json.loads((Path(bionexus.__file__).parent / "data/positive-output-surfaces.v1.json").read_text(encoding="utf-8"))
    surfaces = inventory["surfaces"]
    assert len(surfaces) == len({item["surface"] for item in surfaces})
    assert inventory["unknown_surface"] == "UNACCEPTED"
    for item in surfaces:
        if item["status"] != "UNACCEPTED":
            assert item["regression_tests"]
        else:
            with pytest.raises(ValueError):
                interpret_positive_output({"evidence_contract": conditional_contract(True)}, surface=item["surface"])


def test_router_and_mcp_never_authenticate_declared_conditions():
    for metadata in [{}, {"perturbation": True, "independent_validation": True, "num_donors": 6}]:
        direct = route_scientific_intent("Gene A causes disease.", data_metadata=metadata).to_dict()
        # This local coroutine has no awaits. Exercise its body without a host
        # event loop/socketpair; transport and native-host acceptance are separate.
        coro = tool_bionexus_warrant_check("Gene A causes disease.", data_metadata=metadata)
        with pytest.raises(StopIteration) as completed:
            coro.send(None)
        mcp = completed.value.value
        for obj in (direct, mcp):
            _safe(obj["evidence_contract"])
        assert direct["evidence_contract"] == mcp["evidence_contract"]
        if "claim_warrant_evaluation" in mcp:
            _safe(mcp["claim_warrant_evaluation"]["evidence_contract"])


def test_schema_resource_matches_runtime():
    import jsonschema

    import bionexus
    resource = Path(bionexus.__file__).parent / "data/evidence-state.v1.schema.json"
    schema = json.loads(resource.read_text(encoding="utf-8"))
    assert schema == contract_schema()
    jsonschema.validate(conditional_contract(True), schema)
    bad = deepcopy(conditional_contract(True))
    bad["independence"] = "VERIFIED"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


@pytest.mark.parametrize("positive", [True, False])
def test_cli_conditional_json_and_human_output(tmp_path, positive, capsys):
    from bionexus.commands.claims import handle_warrant_claim, register_warrant_claim_arguments
    profile = tmp_path / "evidence.json"
    profile.write_text(json.dumps({"observational_data": positive}))
    parser = argparse.ArgumentParser()
    register_warrant_claim_arguments(parser.add_subparsers())
    args = ["warrant-claim", "Gene A is associated with disease.", "--evidence-json", str(profile)]
    code = handle_warrant_claim(parser.parse_args([*args, "--json"]))
    assert code == (0 if positive else 1)
    c = json.loads(capsys.readouterr().out)["evidence_contract"]
    _safe(c)
    assert handle_warrant_claim(parser.parse_args(args)) == code
    human = capsys.readouterr().out
    assert contract_text(c) in human
    assert SCHEMA in human
