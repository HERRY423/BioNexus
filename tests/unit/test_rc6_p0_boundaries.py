"""Regression cases for post-rc6 P0 evidence boundaries (synthetic inputs only)."""

import hashlib
import json

import pandas as pd
import pytest

from bionexus.claim_semantics import (
    DeterministicClaimParser,
    DeterministicWarrantEngine,
    EvidenceProfile,
)
from bionexus.de_audit import CheckStatus, ExecutionRecord, audit_differential_expression


@pytest.fixture
def bound_inputs(tmp_path):
    frame = pd.DataFrame({"gene": ["NEG1"], "pvalue": [0.4], "padj": [0.8], "log2FoldChange": [-0.1]})
    path = tmp_path / "result.csv"
    frame.to_csv(path, index=False)
    samples = pd.DataFrame({"donor_id": [f"D{i}" for i in range(6)], "condition": ["C"] * 3 + ["T"] * 3})
    record = {
        "statistical_unit": "donor", "method": "pydeseq2", "fit_status": "CONVERGED",
        "design": "~ condition", "design_matrix_columns": ["Intercept", "condition[T.T]"],
        "n_donors": 6, "result_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "donor_ids": list(samples["donor_id"]),
    }
    return frame, path, samples, record


def binding(result):
    return next(c for c in result.checks if c.check_id == "analysis_execution_binding")


def test_complete_receipt_has_bounded_consistency_summary(bound_inputs):
    _, path, samples, record = bound_inputs
    result = audit_differential_expression(de_table=path, sample_metadata=samples, execution_record=record)
    assert result.passed
    assert binding(result).status == CheckStatus.ASSESSED
    assert "不证明真实模型执行" in binding(result).summary


def test_complete_fit_status_synonym_is_accepted(bound_inputs):
    _, path, samples, record = bound_inputs
    record["fit_status"] = "COMPLETE"
    result = audit_differential_expression(de_table=path, sample_metadata=samples, execution_record=record)
    assert result.passed
    assert binding(result).status == CheckStatus.ASSESSED


def test_legacy_receipt_derives_donors_only_from_hash_bound_metadata_file(bound_inputs, tmp_path):
    _, path, samples, record = bound_inputs
    metadata_path = tmp_path / "samples.csv"
    samples.to_csv(metadata_path, index=False)
    record.pop("donor_ids")
    record["sample_metadata_sha256"] = hashlib.sha256(metadata_path.read_bytes()).hexdigest()
    result = audit_differential_expression(
        de_table=path,
        sample_metadata=metadata_path,
        execution_record=record,
    )
    assert result.passed
    assert binding(result).status == CheckStatus.ASSESSED
    assert "sample_metadata_sha256" in binding(result).summary


def test_legacy_receipt_cannot_derive_donors_from_in_memory_metadata(bound_inputs, tmp_path):
    _, path, samples, record = bound_inputs
    metadata_path = tmp_path / "samples.csv"
    samples.to_csv(metadata_path, index=False)
    record.pop("donor_ids")
    record["sample_metadata_sha256"] = hashlib.sha256(metadata_path.read_bytes()).hexdigest()
    result = audit_differential_expression(de_table=path, sample_metadata=samples, execution_record=record)
    assert not result.passed
    assert binding(result).status == CheckStatus.MISSING_EVIDENCE


def test_legacy_receipt_metadata_hash_mismatch_is_blocked(bound_inputs, tmp_path):
    _, path, samples, record = bound_inputs
    metadata_path = tmp_path / "samples.csv"
    samples.to_csv(metadata_path, index=False)
    record.pop("donor_ids")
    record["sample_metadata_sha256"] = "f" * 64
    result = audit_differential_expression(
        de_table=path,
        sample_metadata=metadata_path,
        execution_record=record,
    )
    assert not result.passed
    assert result.overall_status == "BLOCKER_DETECTED"
    assert binding(result).status == CheckStatus.ISSUE_FOUND
    assert any(f.rule_id == "BFA-013e" for f in result.findings)


@pytest.mark.parametrize("bad_donor_ids", [[], "D0", [1], ["other"]])
def test_malformed_donor_ids_are_not_rescued_by_metadata_hash(bound_inputs, tmp_path, bad_donor_ids):
    _, path, samples, record = bound_inputs
    metadata_path = tmp_path / "samples.csv"
    samples.to_csv(metadata_path, index=False)
    record["donor_ids"] = bad_donor_ids
    record["sample_metadata_sha256"] = hashlib.sha256(metadata_path.read_bytes()).hexdigest()
    result = audit_differential_expression(
        de_table=path,
        sample_metadata=metadata_path,
        execution_record=record,
    )
    assert not result.passed
    assert binding(result).status == CheckStatus.ISSUE_FOUND


@pytest.mark.parametrize("field", ["statistical_unit", "method", "fit_status", "design", "design_matrix_columns", "n_donors", "donor_ids", "result_sha256"])
def test_each_missing_binding_field_prevents_pass(bound_inputs, field):
    _, path, samples, record = bound_inputs
    del record[field]
    result = audit_differential_expression(de_table=path, sample_metadata=samples, execution_record=record)
    assert not result.passed
    assert binding(result).status == CheckStatus.MISSING_EVIDENCE
    assert result.claim_boundary.overall_maturity != "ROBUST_POPULATION"


@pytest.mark.parametrize("updates", [
    {"fit_status": "PENDING"}, {"fit_status": "NOT_FAILED"},
    {"statistical_unit": "cell", "aggregation": "pseudobulk"},
    {"aggregation": "not_pseudobulk"}, {"aggregation": "cell"},
    {"method": "wilcoxon"}, {"cell_level_condition_test": "false"},
    {"cell_level_condition_test": 0}, {"n_donors": "6"}, {"n_donors": "junk"},
    {"n_donors": True}, {"n_donors": 6.5}, {"n_donors": -1},
    {"design_matrix_columns": [None]}, {"design_matrix_columns": "condition"},
    {"design_matrix_columns": ["Intercept", "condition[T.T]", "condition[T.T]"]},
    {"design_matrix_columns": ["Intercept", "batch[T.B]"]},
    {"design": "~ batch", "design_matrix_columns": ["Intercept", "batch[T.B]"]},
    {"design": "~ donor * condition"},
    {"result_sha256": "f" * 32}, {"result_sha256": "g" * 64},
    {"result_sha256": "f" * 65}, {"result_sha256": "0" * 64},
    {"donor_ids": ["other"] * 6}, {"donor_ids": ["other" + str(i) for i in range(6)]},
    {"donor_ids": "D0"}, {"donor_ids": []}, {"donor_ids": [1]},
    {"unit": "cell"}, {"formula": "~ batch"}, {"receipt_result_sha256": "a" * 64},
])
def test_malformed_or_contradictory_binding_cannot_pass(bound_inputs, updates):
    _, path, samples, record = bound_inputs
    record.update(updates)
    result = audit_differential_expression(de_table=path, sample_metadata=samples, execution_record=record)
    assert not result.passed
    assert binding(result).status != CheckStatus.ASSESSED


@pytest.mark.parametrize("payload", [[1], "donor", 1, True])
def test_non_object_json_receipt_is_parse_failed(bound_inputs, tmp_path, payload):
    _, path, samples, _ = bound_inputs
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(json.dumps(payload), encoding="utf-8")
    result = audit_differential_expression(de_table=path, sample_metadata=samples, execution_record=receipt_path)
    assert not result.passed
    assert binding(result).status == CheckStatus.PARSE_FAILED


def test_dataframe_hash_is_not_a_verified_file_digest(bound_inputs):
    frame, _, samples, record = bound_inputs
    result = audit_differential_expression(de_table=frame, sample_metadata=samples, execution_record=record)
    assert not result.passed
    assert binding(result).status == CheckStatus.MISSING_EVIDENCE


def test_duplicate_receipt_keys_are_rejected(bound_inputs, tmp_path):
    _, path, samples, record = bound_inputs
    receipt_path = tmp_path / "duplicate.json"
    text = json.dumps(record).replace('"fit_status": "CONVERGED"', '"fit_status": "FAILED", "fit_status": "CONVERGED"')
    receipt_path.write_text(text, encoding="utf-8")
    result = audit_differential_expression(de_table=path, sample_metadata=samples, execution_record=receipt_path)
    assert not result.passed
    assert binding(result).status == CheckStatus.PARSE_FAILED


def test_hash_cannot_bind_a_different_in_memory_result(bound_inputs):
    from bionexus.de_audit import DEAuditEngine

    frame, path, samples, record = bound_inputs
    engine = DEAuditEngine()
    findings, checks = [], []
    other = frame.copy()
    other.loc[0, "padj"] = 0.001
    execution = ExecutionRecord(source="test", method="pydeseq2", aggregation="donor_pseudobulk")
    assert not engine._verify_execution_binding(
        execution, record, path, other, samples,
        {"n_donors": 6, "donors": list(samples["donor_id"]), "condition_key": "condition"}, findings, checks,
    )
    assert checks[-1].status == CheckStatus.ISSUE_FOUND


def test_execution_record_object_cannot_manufacture_missing_receipt(bound_inputs):
    _, path, samples, _ = bound_inputs
    record = ExecutionRecord(source="test", method="pydeseq2", aggregation="donor_pseudobulk")
    result = audit_differential_expression(de_table=path, sample_metadata=samples, execution_record=record)
    assert not result.passed
    assert binding(result).status == CheckStatus.MISSING_EVIDENCE


@pytest.mark.parametrize("claim", [
    "NEG1 does not cause disease.", "NEG1 does not affect disease.",
    "NEG1 is not associated with disease.", "Treatment has no effect on NEG1.",
    "Treatment has zero effect on NEG1.", "There is no difference in NEG1.",
    "The treatments are equivalent for NEG1.", "The treatment is non-inferior for NEG1.",
    "Noninferiority was established for NEG1.", "药物不影响 NEG1。", "两组没有差异。",
    "药物无效应。", "治疗等效。", "治疗具有非劣效性。",
])
def test_absence_and_equivalence_are_not_ordinary_nonsignificance(bound_inputs, claim):
    _, path, samples, record = bound_inputs
    result = audit_differential_expression(de_table=path, sample_metadata=samples, execution_record=record, claim_text=claim)
    assert not result.passed
    assert any(f.rule_id == "BFA-008" for f in result.findings)
    ir = DeterministicClaimParser.parse(claim)
    verdict = DeterministicWarrantEngine.evaluate(ir, EvidenceProfile(observational_data=True, perturbation=True))
    assert not verdict.is_fully_warranted


@pytest.mark.parametrize("claim", [
    "NEG1 was not significant after FDR correction in the supplied result.",
    "No genes were significant in the supplied table.",
    "We cannot prove that NEG1 causes disease.",
    "For this completed analysis, these differential-expression results do not establish causality or clinical efficacy.",
    "Our reported conclusion is: These differential-expression results do not establish causality or clinical efficacy.",
])
def test_honest_negative_or_scoped_limitation_remains_usable(bound_inputs, claim):
    _, path, samples, record = bound_inputs
    result = audit_differential_expression(de_table=path, sample_metadata=samples, execution_record=record, claim_text=claim)
    assert result.passed


@pytest.mark.parametrize("claim", [
    "We cannot prove X causes Y; treatment has no effect.",
    "We cannot prove X causes Y. Z causes disease.",
    "We cannot prove X causes Y but Z causes disease.",
    "We cannot prove X causes Y and Z is clinically validated.",
    "We cannot prove X causes Y, Z causes disease.",
    "Z causes disease, we cannot prove X causes Y.",
    "本研究不能证明因果机制，但药物没有差异。",
])
def test_disclaimer_does_not_license_other_propositions(claim):
    ir = DeterministicClaimParser.parse(claim)
    assert not DeterministicWarrantEngine.evaluate(ir, EvidenceProfile(observational_data=True)).is_fully_warranted


@pytest.mark.parametrize("claim", [
    "For this completed analysis, treatment has no effect.",
    "Our reported conclusion is: these results do not establish causality, but treatment cures disease.",
])
def test_reporting_preamble_does_not_license_negative_or_compound_assertions(claim):
    ir = DeterministicClaimParser.parse(claim)
    assert not DeterministicWarrantEngine.evaluate(ir, EvidenceProfile(observational_data=True)).is_fully_warranted


def test_legacy_negated_bit_cannot_grant_warrant():
    ir = DeterministicClaimParser.parse("X causes disease.")
    ir.negated = True
    assert not DeterministicWarrantEngine.evaluate(ir, EvidenceProfile()).is_fully_warranted


def test_scoped_disclaimer_has_no_biological_evidence_ceiling():
    ir = DeterministicClaimParser.parse("We cannot prove that X causes disease.")
    verdict = DeterministicWarrantEngine.evaluate(ir, EvidenceProfile())
    assert verdict.is_fully_warranted
    assert verdict.evidence_ceiling == "UNASSESSED"
    assert verdict.warranted_claim_class == "descriptive"


@pytest.mark.parametrize("claim", ["The treatments are equivalent.", "Treatment has no effect."])
def test_text_checker_preserves_absence_rejection(claim):
    from bionexus.claim_checker import audit_prohibited_claims

    result = audit_prohibited_claims(claim)
    assert not result.passed
    assert result.violations


@pytest.mark.parametrize("claim", [
    "There was no significant effect on NEG1.", "NEG1 was not statistically significant.",
    "NEG1 was non-significant.", "NEG1 未见显著差异。",
])
@pytest.mark.parametrize("padj,expected", [(0.8, True), (0.001, False), (None, False)])
def test_nonsignificance_requires_an_actual_valid_negative_result(bound_inputs, claim, padj, expected):
    frame, path, samples, record = bound_inputs
    frame.loc[0, "padj"] = padj
    frame.to_csv(path, index=False)
    record["result_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    result = audit_differential_expression(de_table=path, sample_metadata=samples, execution_record=record, claim_text=claim)
    assert result.passed is expected
    if padj == 0.001:
        assert any(f.rule_id == "BFA-015b" for f in result.findings)
    if padj is None:
        assert any(c.check_id == "claim_fact_concordance" and c.status == CheckStatus.MISSING_EVIDENCE for c in result.checks)


@pytest.mark.parametrize("claim", [
    "No genes were significant after FDR correction in the supplied result.",
    "For this completed analysis, no genes were significant after FDR correction in the supplied result.",
    "Our reported conclusion is: No genes were significant after FDR correction in the supplied result.",
])
def test_reporting_preambles_do_not_hide_false_global_null(bound_inputs, claim):
    frame, path, samples, record = bound_inputs
    frame.loc[0, "padj"] = 0.001
    frame.to_csv(path, index=False)
    record["result_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    result = audit_differential_expression(
        de_table=path,
        sample_metadata=samples,
        execution_record=record,
        claim_text=claim,
    )
    assert not result.passed
    assert any(f.rule_id == "BFA-015c" for f in result.findings)


def test_global_negative_does_not_treat_missing_tests_as_nonsignificant(bound_inputs):
    frame, path, samples, record = bound_inputs
    frame.loc[0, "padj"] = float("nan")
    frame.to_csv(path, index=False)
    record["result_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    result = audit_differential_expression(de_table=path, sample_metadata=samples, execution_record=record, claim_text="No genes were significant.")
    assert not result.passed
    assert any(c.check_id == "claim_fact_concordance" and c.status == CheckStatus.MISSING_EVIDENCE for c in result.checks)
