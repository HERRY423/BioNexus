"""Executable controls for the packaged DE execution-receipt compatibility contract."""
from __future__ import annotations

import hashlib
import json
from importlib.resources import files

import pandas as pd
import pytest

from bionexus.de_audit import (
    DE_EXECUTION_RECEIPT_COMPATIBILITY_SCHEMA,
    DE_SUCCESS_FIT_STATUSES,
    CheckStatus,
    audit_differential_expression,
)


def contract() -> dict:
    resource = files("bionexus.data").joinpath("de_execution_receipt_compatibility_v1.json")
    return json.loads(resource.read_text(encoding="utf-8"))


def inputs(tmp_path):
    samples = pd.DataFrame({"donor": [f"D{i}" for i in range(6)], "condition": ["C"] * 3 + ["T"] * 3})
    metadata = tmp_path / "metadata.csv"
    samples.to_csv(metadata, index=False)
    result = tmp_path / "de.csv"
    pd.DataFrame({
        "gene": ["POS1", "NEG1"],
        "log2FoldChange": [2.0, 0.1],
        "pvalue": [1e-12, 0.5],
        "padj": [1e-10, 0.8],
    }).to_csv(result, index=False)
    receipt = {
        "statistical_unit": "donor",
        "method": "pydeseq2",
        "fit_status": "COMPLETED",
        "design": "~ condition",
        "design_matrix_columns": ["Intercept", "condition[T.T]"],
        "n_donors": 6,
        "donor_ids": list(samples["donor"]),
        "result_sha256": hashlib.sha256(result.read_bytes()).hexdigest(),
    }
    return samples, metadata, result, receipt


def binding(result):
    return next(check for check in result.checks if check.check_id == "analysis_execution_binding")


def test_packaged_contract_matches_runtime_status_vocabulary():
    spec = contract()
    assert spec["schema"] == DE_EXECUTION_RECEIPT_COMPATIBILITY_SCHEMA
    assert set(spec["fit_status"]["accepted_success_values"]) == DE_SUCCESS_FIT_STATUSES
    assert spec["metadata_hash_failure"] == {"rule_id": "BFA-013e", "severity": "BLOCKER"}
    assert spec["evidence_ceiling"]["scientific_authorization"] == "NONE"


def test_legitimate_explicit_and_legacy_positive_controls_pass(tmp_path):
    samples, metadata, result_path, receipt = inputs(tmp_path)
    receipt["fit_status"] = "COMPLETE"
    explicit = audit_differential_expression(
        de_table=result_path, sample_metadata=samples, execution_record=receipt,
        donor_col="donor", condition_col="condition",
        claim_text="POS1 is upregulated and significant after FDR correction in the supplied result.",
    )
    assert explicit.passed

    receipt.pop("donor_ids")
    receipt["sample_metadata_sha256"] = hashlib.sha256(metadata.read_bytes()).hexdigest()
    legacy = audit_differential_expression(
        de_table=result_path, sample_metadata=metadata, execution_record=receipt,
        donor_col="donor", condition_col="condition",
        claim_text="NEG1 was not significant after FDR correction in the supplied result.",
    )
    assert legacy.passed
    assert "sample_metadata_sha256" in binding(legacy).summary


def test_in_memory_metadata_cannot_substitute_for_legacy_source_bytes(tmp_path):
    samples, metadata, result_path, receipt = inputs(tmp_path)
    receipt.pop("donor_ids")
    receipt["sample_metadata_sha256"] = hashlib.sha256(metadata.read_bytes()).hexdigest()
    result = audit_differential_expression(
        de_table=result_path, sample_metadata=samples, execution_record=receipt,
        donor_col="donor", condition_col="condition",
    )
    assert not result.passed
    assert binding(result).status == CheckStatus.MISSING_EVIDENCE


def test_malformed_or_mismatched_metadata_hash_is_a_blocker(tmp_path):
    _, metadata, result_path, receipt = inputs(tmp_path)
    receipt.pop("donor_ids")
    for bad_hash in ("0" * 64, "not-a-digest", "f" * 64):
        receipt["sample_metadata_sha256"] = bad_hash
        result = audit_differential_expression(
            de_table=result_path, sample_metadata=metadata, execution_record=receipt,
            donor_col="donor", condition_col="condition",
        )
        assert not result.passed
        assert result.overall_status == "BLOCKER_DETECTED"
        assert any(finding.rule_id == "BFA-013e" for finding in result.findings)


def test_reporting_preamble_preserves_limitation_and_exposes_false_null(tmp_path):
    samples, _, result_path, receipt = inputs(tmp_path)
    limitation = audit_differential_expression(
        de_table=result_path, sample_metadata=samples, execution_record=receipt,
        donor_col="donor", condition_col="condition",
        claim_text="For this completed analysis, these results do not establish causality or clinical efficacy.",
    )
    assert limitation.passed

    false_null = audit_differential_expression(
        de_table=result_path, sample_metadata=samples, execution_record=receipt,
        donor_col="donor", condition_col="condition",
        claim_text="For this completed analysis, no genes were significant after FDR correction in the supplied result.",
    )
    assert not false_null.passed
    assert any(finding.rule_id == "BFA-015c" for finding in false_null.findings)


@pytest.mark.parametrize(("method", "design", "columns", "id_col"), [
    ("DESeq2", "~ donor + condition", ["(Intercept)", "donorD1", "donorD2", "conditionT"], None),
    ("edgeR", "~ donor + condition", ["Intercept", "donor[T.D1]", "donor[T.D2]", "condition[T.T]"], None),
    ("limma-voom", "~ donor + condition", ["(Intercept)", "donorD1", "donorD2", "conditionT"], None),
    ("variancePartition::dream", "~ condition + (1 | donor)", ["(Intercept)", "conditionT"], None),
    ("NEBULA", "~ condition", ["Intercept", "condition[T.T]"], "donor"),
])
def test_donor_aware_receipts_bind_paired_contrasts(tmp_path, method, design, columns, id_col):
    samples, _, result_path, receipt = inputs(tmp_path)
    samples["donor"] = ["D0", "D1", "D2"] * 2
    receipt.update(method=method, design=design, design_matrix_columns=columns,
                   n_donors=3, donor_ids=["D0", "D1", "D2"], evidence_factors=["replication"])
    if id_col:
        receipt.update(id_col=id_col, statistical_unit="cell")
    result = audit_differential_expression(de_table=result_path, sample_metadata=samples, execution_record=receipt)
    assert binding(result).status == CheckStatus.ASSESSED
    assert result.execution_record.is_donor_aware
    assert result.execution_record.declared_factors == ["replication"]
    assert "condition" in result.execution_record.design_factors
    assert "donor" in result.execution_record.design_factors + result.execution_record.random_effects
    assert not any(f.rule_id in {"BFA-001", "BFA-001d"} for f in result.findings)


@pytest.mark.parametrize(("method", "design"), [
    ("dream", "~ condition"), ("dream", "~ condition + (1 | batch)"),
    ("pydeseq2", "~ condition + (1 | donor)"), ("unrecognized-model", "~ condition"),
])
def test_method_names_or_incompatible_designs_do_not_bind(tmp_path, method, design):
    samples, _, result_path, receipt = inputs(tmp_path)
    receipt.update(method=method, design=design)
    result = audit_differential_expression(de_table=result_path, sample_metadata=samples, execution_record=receipt)
    assert binding(result).status != CheckStatus.ASSESSED
    assert not result.passed
    assert result.execution_record.design_factors == []


def test_paired_contrast_without_donor_effect_gets_high_impact(tmp_path):
    samples, _, result_path, receipt = inputs(tmp_path)
    samples["donor"] = ["D0", "D1", "D2"] * 2
    receipt.update(n_donors=3, donor_ids=["D0", "D1", "D2"])
    result = audit_differential_expression(de_table=result_path, sample_metadata=samples, execution_record=receipt)
    issue = next(f for f in result.findings if f.rule_id == "BFA-001d")
    assert issue.severity.value == "HIGH_IMPACT"
    assert issue.evidence_data["paired_donors"] == ["D0", "D1", "D2"]

def test_one_numeric_column_does_not_verify_a_categorical_donor_block(tmp_path):
    samples, _, result_path, receipt = inputs(tmp_path)
    samples["donor"] = ["D0", "D1", "D2"] * 2
    receipt.update(n_donors=3, donor_ids=["D0", "D1", "D2"], design="~ donor + condition",
                   design_matrix_columns=["Intercept", "donor", "condition[T.T]"])
    result = audit_differential_expression(de_table=result_path, sample_metadata=samples, execution_record=receipt)
    assert binding(result).status == CheckStatus.ISSUE_FOUND
    assert not result.passed


def test_selected_cell_type_receipt_uses_only_eligible_donors(tmp_path):
    samples, _, result_path, receipt = inputs(tmp_path)
    rows = []
    for donor, condition in samples.itertuples(index=False, name=None):
        rows.extend([(donor, condition, "T")] * (3 if donor == "D0" else 22))
        rows.extend([(donor, condition, "B")] * 22)
    obs = pd.DataFrame(rows, columns=["donor", "condition", "cell_type"])
    receipt.update(n_donors=5, donor_ids=[f"D{i}" for i in range(1, 6)])
    result = audit_differential_expression(de_table=result_path, sample_metadata=obs, execution_record=receipt,
                                           cell_type="T", case="T", reference="C")
    assert binding(result).status == CheckStatus.ASSESSED
    receipt.update(n_donors=6, donor_ids=samples["donor"].tolist())
    other = audit_differential_expression(de_table=result_path, sample_metadata=obs, execution_record=receipt,
                                          cell_type="T", case="T", reference="C")
    assert binding(other).status == CheckStatus.ISSUE_FOUND
