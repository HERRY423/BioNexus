"""Executable controls for the packaged DE execution-receipt compatibility contract."""
from __future__ import annotations

import hashlib
import json
from importlib.resources import files

import pandas as pd

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
