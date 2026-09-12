"""
Unit tests for the BioNexus Multi-Donor Differential Expression Evidence Audit Engine (de_audit.py).
Pure core DataFrame & metadata tests with NO AnnData / SciPy dependencies,
ensuring clean test collection in core CI matrix environments.
"""

import hashlib

import numpy as np
import pandas as pd

from bionexus.de_audit import (
    CheckStatus,
    FindingCategory,
    FindingSeverity,
    audit_differential_expression,
)


def _bound_result(tmp_path, frame):
    """Synthetic receipt verifies byte/metadata consistency, never real execution."""
    path = tmp_path / "results.csv"
    frame.to_csv(path, index=False)
    return path, {
        "statistical_unit": "donor", "method": "pydeseq2",
        "fit_status": "CONVERGED", "design": "~ condition",
        "design_matrix_columns": ["Intercept", "condition[T.T]"],
        "n_donors": 6, "result_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "donor_ids": [f"D{i}" for i in range(1, 7)],
    }


def _assert_not_executed_methods(result) -> None:
    executed = (result.claim_boundary.executed_methods_text or "").lower()
    for banned in ("negative binomial", "wald test", "empirical bayes", "were tested using"):
        assert banned not in executed


def test_no_input_is_not_assessed():
    result = audit_differential_expression()
    assert result.overall_status == "NOT_ASSESSED"
    assert not result.passed
    _assert_not_executed_methods(result)
    assert result.claim_boundary.overall_maturity == "NOT_ASSESSED"
    statuses = {c.check_id: c.status for c in result.checks}
    assert statuses["donor_replicates"] == CheckStatus.MISSING_EVIDENCE
    assert statuses["de_results"] == CheckStatus.MISSING_EVIDENCE


def test_empty_de_table_is_needs_data():
    result = audit_differential_expression(de_table=pd.DataFrame())
    assert result.overall_status == "NEEDS_DATA"
    assert not result.passed
    _assert_not_executed_methods(result)


def test_single_row_pvalue_padj_table_is_needs_data():
    de_data = pd.DataFrame({"pvalue": [0.02], "padj": [0.04]})
    result = audit_differential_expression(de_table=de_data)
    assert result.overall_status == "NEEDS_DATA"
    assert not result.passed
    _assert_not_executed_methods(result)
    fdr = next(c for c in result.checks if c.check_id == "fdr_and_testing")
    assert fdr.status == CheckStatus.ASSESSED
    donor = next(c for c in result.checks if c.check_id == "donor_replicates")
    assert donor.status == CheckStatus.MISSING_EVIDENCE


def test_claim_text_only_is_not_a_pass():
    result = audit_differential_expression(claim_text="IFITM1 is a population biomarker")
    assert result.overall_status in {"NOT_ASSESSED", "NEEDS_DATA", "NEEDS_REVISION"}
    assert not result.passed
    _assert_not_executed_methods(result)


def test_sample_sheet_only_does_not_claim_nb_glm():
    samples = pd.DataFrame(
        {
            "donor_id": [f"D{i}" for i in range(1, 7)],
            "condition": ["A", "A", "A", "B", "B", "B"],
        }
    )
    result = audit_differential_expression(sample_metadata=samples)
    assert result.overall_status == "NEEDS_DATA"
    assert not result.passed
    assert result.claim_boundary.overall_maturity != "ROBUST_POPULATION"
    executed = result.claim_boundary.executed_methods_text.lower()
    assert "negative binomial" not in executed
    assert "wald" not in executed
    assert "benjamini-hochberg" not in executed
    donor = next(c for c in result.checks if c.check_id == "donor_replicates")
    assert donor.status == CheckStatus.ASSESSED
    de_check = next(c for c in result.checks if c.check_id == "de_results")
    assert de_check.status == CheckStatus.MISSING_EVIDENCE


def test_de_table_missing_fdr():
    """Test that DE table missing adjusted p-values triggers HIGH_IMPACT."""
    de_data = pd.DataFrame(
        {
            "gene": [f"Gene_{i}" for i in range(50)],
            "log2fc": np.random.normal(0, 1, 50),
            "pvalue": np.random.uniform(0.001, 0.5, 50),
        }
    )
    result = audit_differential_expression(de_table=de_data)
    fdr_finding = next(
        f for f in result.findings if f.category == FindingCategory.FDR_AND_TESTING
    )
    assert fdr_finding.severity == FindingSeverity.HIGH_IMPACT
    assert "BFA-003" in fdr_finding.rule_id
    assert "multipletests" in fdr_finding.minimal_fix


def test_de_table_pseudoreplication_tiny_pvalues():
    """Test that DE table containing extreme tiny p-values (< 1e-100) triggers pseudoreplication warning."""
    de_data = pd.DataFrame(
        {
            "gene": [f"Gene_{i}" for i in range(100)],
            "log2fc": np.random.normal(0, 1, 100),
            "pvalue": [1e-150] * 15 + list(np.random.uniform(0.001, 0.5, 85)),
            "padj": [1e-148] * 15 + list(np.random.uniform(0.01, 0.6, 85)),
        }
    )
    result = audit_differential_expression(de_table=de_data)
    tiny_p_finding = next(
        f for f in result.findings if f.rule_id == "BFA-001c"
    )
    assert tiny_p_finding.severity == FindingSeverity.HIGH_IMPACT
    assert result.overall_status == "NEEDS_REVISION"
    assert not result.passed


def test_de_table_invalid_probability_range():
    """Test that negative p-values or padj > 1 trigger BFA-003c (statistical invalidity)."""
    de_data = pd.DataFrame(
        {
            "gene": ["Gene_A", "Gene_B", "Gene_C"],
            "baseMean": [100.0, 50.0, 30.0],
            "log2FoldChange": [1.2, -0.5, 0.8],
            "pvalue": [-0.05, 0.01, 0.02],
            "padj": [-0.10, 0.05, 1.25],
        }
    )
    samples = pd.DataFrame(
        {
            "donor_id": [f"D{i}" for i in range(1, 7)],
            "condition": ["Control", "Control", "Control", "Disease", "Disease", "Disease"],
        }
    )
    result = audit_differential_expression(
        sample_metadata=samples,
        de_table=de_data,
        execution_record={"statistical_unit": "donor", "method": "pydeseq2"},
    )
    assert not result.passed
    assert result.overall_status == "NEEDS_REVISION"
    finding_3c = next(f for f in result.findings if f.rule_id == "BFA-003c")
    assert finding_3c.severity == FindingSeverity.HIGH_IMPACT
    assert "超出有效概率区间" in finding_3c.title


def test_de_table_honest_null_result_not_flagged_as_p_hacking():
    """Test that honest reporting of negative/null FDR result does NOT trigger BFA-003b."""
    # 150 raw p < 0.05, but 0 padj < 0.05
    de_data = pd.DataFrame(
        {
            "gene": [f"Gene_{i}" for i in range(200)],
            "baseMean": [100.0] * 200,
            "log2FoldChange": np.random.normal(0, 0.2, 200),
            "pvalue": [0.01] * 120 + [0.3] * 80,
            "padj": [0.15] * 200,  # none < 0.05
        }
    )
    # Honest user claim explicitly declaring no significant genes
    result = audit_differential_expression(
        de_table=de_data,
        claim_text="In our cohort, no genes were significant after FDR multiple testing correction.",
    )
    assert not any(f.rule_id == "BFA-003b" for f in result.findings)


def test_de_table_format_recognized_requires_execution_binding_for_pass():
    """Format recognition (baseMean column) alone must NOT grant ROBUST_PASS without execution record."""
    samples = pd.DataFrame(
        {
            "donor_id": [f"D{i}" for i in range(1, 7)],
            "condition": ["Control", "Control", "Control", "Disease", "Disease", "Disease"],
        }
    )
    de_data = pd.DataFrame(
        {
            "gene": ["IFITM1", "STAT1"],
            "baseMean": [120.0, 80.0],
            "log2FoldChange": [1.5, -0.8],
            "lfcSE": [0.2, 0.3],
            "stat": [7.5, -2.6],
            "pvalue": [1e-8, 0.01],
            "padj": [1e-6, 0.04],
        }
    )
    # Without execution_record, Level 2 Fact Verification fails -> NEEDS_DATA
    result = audit_differential_expression(sample_metadata=samples, de_table=de_data)
    assert result.overall_status == "NEEDS_DATA"
    assert not result.passed
    binding_check = next(c for c in result.checks if c.check_id == "analysis_execution_binding")
    assert binding_check.status == CheckStatus.MISSING_EVIDENCE


def test_deseq2_with_verified_execution_record_achieves_pass(tmp_path):
    """When both balanced design and verified donor execution record are supplied, audit passes."""
    samples = pd.DataFrame(
        {
            "donor_id": [f"D{i}" for i in range(1, 7)],
            "condition": ["Control", "Control", "Control", "Disease", "Disease", "Disease"],
        }
    )
    de_data = pd.DataFrame(
        {
            "gene": ["IFITM1", "STAT1"],
            "baseMean": [120.0, 80.0],
            "log2FoldChange": [1.5, -0.8],
            "lfcSE": [0.2, 0.3],
            "stat": [7.5, -2.6],
            "pvalue": [1e-8, 0.01],
            "padj": [1e-6, 0.04],
        }
    )
    result_path, receipt = _bound_result(tmp_path, de_data)
    result = audit_differential_expression(
        sample_metadata=samples,
        de_table=result_path,
        execution_record=receipt,
    )
    assert result.overall_status == "ROBUST_PASS"
    assert result.passed
    assert result.claim_boundary.overall_maturity == "ROBUST_POPULATION"
    binding_check = next(c for c in result.checks if c.check_id == "analysis_execution_binding")
    assert binding_check.status == CheckStatus.ASSESSED


def test_targeted_claim_exceeding_evidence_yields_bfa008():
    """Claiming causal cure or biomarker from observational DE emits BFA-008 and requires revision."""
    samples = pd.DataFrame(
        {
            "donor_id": [f"D{i}" for i in range(1, 7)],
            "condition": ["Control", "Control", "Control", "Disease", "Disease", "Disease"],
        }
    )
    de_data = pd.DataFrame(
        {
            "gene": ["IFITM1", "STAT1"],
            "baseMean": [120.0, 80.0],
            "log2FoldChange": [1.5, -0.8],
            "lfcSE": [0.2, 0.3],
            "stat": [7.5, -2.6],
            "pvalue": [1e-8, 0.01],
            "padj": [1e-6, 0.04],
        }
    )
    # Unwarranted causal assertion
    claim = "IFITM1 causes disease pathogenesis and serves as a proven curative therapeutic target."
    result = audit_differential_expression(
        sample_metadata=samples,
        de_table=de_data,
        execution_record={"statistical_unit": "donor", "method": "pydeseq2"},
        claim_text=claim,
    )
    assert not result.passed
    assert result.overall_status == "NEEDS_REVISION"
    bfa008 = next(f for f in result.findings if f.rule_id == "BFA-008")
    assert bfa008.severity == FindingSeverity.HIGH_IMPACT
    assert "超出证据边界" in bfa008.title
    assert "严禁" in result.claim_boundary.prohibited_scope


def test_failed_fit_status_blocks_and_issues_bfa013b():
    """Execution record with fit_status=FAILED must trigger BFA-013b and fail closed."""
    samples = pd.DataFrame({"donor_id": [f"D{i}" for i in range(1, 7)], "condition": ["C"]*3 + ["T"]*3})
    de_data = pd.DataFrame({"gene": ["G1"], "pvalue": [0.01], "padj": [0.04]})
    result = audit_differential_expression(
        sample_metadata=samples,
        de_table=de_data,
        execution_record={"statistical_unit": "donor", "method": "pydeseq2", "fit_status": "FAILED"},
    )
    assert not result.passed
    assert result.overall_status == "BLOCKER_DETECTED"
    binding = next(c for c in result.checks if c.check_id == "analysis_execution_binding")
    assert binding.status == CheckStatus.ISSUE_FOUND
    assert any(f.rule_id == "BFA-013b" and f.severity == FindingSeverity.BLOCKER for f in result.findings)


def test_tampered_zero_hash_blocks_and_issues_bfa013a():
    """Execution record with all-zeros hash must trigger BFA-013a as tampered receipt."""
    samples = pd.DataFrame({"donor_id": [f"D{i}" for i in range(1, 7)], "condition": ["C"]*3 + ["T"]*3})
    de_data = pd.DataFrame({"gene": ["G1"], "pvalue": [0.01], "padj": [0.04]})
    result = audit_differential_expression(
        sample_metadata=samples,
        de_table=de_data,
        execution_record={"statistical_unit": "donor", "method": "pydeseq2", "result_sha256": "0"*64},
    )
    assert not result.passed
    assert result.overall_status == "BLOCKER_DETECTED"
    binding = next(c for c in result.checks if c.check_id == "analysis_execution_binding")
    assert binding.status == CheckStatus.ISSUE_FOUND
    assert any(f.rule_id == "BFA-013a" and f.severity == FindingSeverity.BLOCKER for f in result.findings)


def test_mismatched_result_hash_from_disk_blocks_and_issues_bfa013a(tmp_path):
    """Execution record with hash mismatch against real CSV file must trigger BFA-013a."""
    samples = pd.DataFrame({"donor_id": [f"D{i}" for i in range(1, 7)], "condition": ["C"]*3 + ["T"]*3})
    csv_file = tmp_path / "de_results.csv"
    csv_file.write_text("gene,pvalue,padj\nG1,0.01,0.04\n", encoding="utf-8")
    result = audit_differential_expression(
        sample_metadata=samples,
        de_table=csv_file,
        execution_record={"statistical_unit": "donor", "method": "pydeseq2", "result_sha256": "f"*64},
    )
    assert not result.passed
    assert result.overall_status == "BLOCKER_DETECTED"
    binding = next(c for c in result.checks if c.check_id == "analysis_execution_binding")
    assert binding.status == CheckStatus.ISSUE_FOUND
    assert any(f.rule_id == "BFA-013a" and f.severity == FindingSeverity.BLOCKER for f in result.findings)


def test_formula_matrix_columns_conflict_blocks_and_issues_bfa013c():
    """Design formula (~ condition) conflicting with matrix columns (donor[...]) triggers BFA-013c."""
    samples = pd.DataFrame({"donor_id": [f"D{i}" for i in range(1, 7)], "condition": ["C"]*3 + ["T"]*3})
    de_data = pd.DataFrame({"gene": ["G1"], "pvalue": [0.01], "padj": [0.04]})
    result = audit_differential_expression(
        sample_metadata=samples,
        de_table=de_data,
        execution_record={
            "statistical_unit": "donor",
            "method": "pydeseq2",
            "design": "~ condition",
            "design_matrix_columns": ["Intercept", "donor[T.1015]", "condition[T.treated]"],
        },
    )
    assert not result.passed
    assert result.overall_status == "BLOCKER_DETECTED"
    binding = next(c for c in result.checks if c.check_id == "analysis_execution_binding")
    assert binding.status == CheckStatus.ISSUE_FOUND
    assert any(f.rule_id == "BFA-013c" and f.severity == FindingSeverity.BLOCKER for f in result.findings)


def test_donor_count_mismatch_blocks_and_issues_bfa013d():
    """Execution record recording 12 donors while sample_metadata has 6 triggers BFA-013d."""
    samples = pd.DataFrame({"donor_id": [f"D{i}" for i in range(1, 7)], "condition": ["C"]*3 + ["T"]*3})
    de_data = pd.DataFrame({"gene": ["G1"], "pvalue": [0.01], "padj": [0.04]})
    result = audit_differential_expression(
        sample_metadata=samples,
        de_table=de_data,
        execution_record={
            "statistical_unit": "donor",
            "method": "pydeseq2",
            "n_donors": 12,
        },
    )
    assert not result.passed
    assert result.overall_status == "BLOCKER_DETECTED"
    binding = next(c for c in result.checks if c.check_id == "analysis_execution_binding")
    assert binding.status == CheckStatus.ISSUE_FOUND
    assert any(f.rule_id == "BFA-013d" and f.severity == FindingSeverity.BLOCKER for f in result.findings)


def test_negative_pvalues_trigger_bfa003c_and_refuse_pass():
    """Negative p-values must trigger BFA-003c and block ROBUST_PASS."""
    samples = pd.DataFrame({"donor_id": [f"D{i}" for i in range(1, 7)], "condition": ["C"]*3 + ["T"]*3})
    de_data = pd.DataFrame({"gene": ["G1"], "pvalue": [-0.1], "padj": [-0.2]})
    result = audit_differential_expression(
        sample_metadata=samples,
        de_table=de_data,
        execution_record={"statistical_unit": "donor", "method": "pydeseq2"},
    )
    assert not result.passed
    assert any(f.rule_id == "BFA-003c" for f in result.findings)


def test_tiny_pvalues_with_verified_donor_execution_not_blocked(tmp_path):
    """P1: 18 genes with p < 1e-100 in verified donor execution must not be blocked by BFA-001c."""
    samples = pd.DataFrame({"donor_id": [f"D{i}" for i in range(1, 7)], "condition": ["C"]*3 + ["T"]*3})
    # Create 18 genes with p < 1e-100 (non-zero)
    genes = [f"G{i}" for i in range(20)]
    pvals = [1e-120] * 18 + [0.01, 0.02]
    padjs = [1e-118] * 18 + [0.02, 0.03]
    lfcs = [2.0] * 20
    de_data = pd.DataFrame({"gene": genes, "pvalue": pvals, "padj": padjs, "log2FoldChange": lfcs})
    result_path, receipt = _bound_result(tmp_path, de_data)
    result = audit_differential_expression(
        sample_metadata=samples,
        de_table=result_path,
        execution_record=receipt,
    )
    assert result.passed is True
    assert result.overall_status == "ROBUST_PASS"
    # BFA-001c finding should be present as ADVISORY, not HIGH_IMPACT
    tiny_f = next((f for f in result.findings if f.rule_id == "BFA-001c"), None)
    if tiny_f:
        assert tiny_f.severity == FindingSeverity.ADVISORY


def test_claim_absent_gene_triggers_bfa014():
    """P1: Claim asserting an absent gene must trigger BFA-014 and be rejected."""
    samples = pd.DataFrame({"donor_id": [f"D{i}" for i in range(1, 7)], "condition": ["C"]*3 + ["T"]*3})
    de_data = pd.DataFrame({"gene": ["IL1RN"], "pvalue": [1e-10], "padj": [1e-9], "log2FoldChange": [2.5]})
    result = audit_differential_expression(
        sample_metadata=samples,
        de_table=de_data,
        execution_record={"statistical_unit": "donor", "method": "pydeseq2"},
        claim_text="BN_NOT_IN_INPUT_20260908 is significantly upregulated after FDR correction in the supplied result.",
    )
    assert not result.passed
    assert result.overall_status == "NEEDS_REVISION"
    assert any(f.rule_id == "BFA-014" for f in result.findings)


def test_claim_wrong_direction_triggers_bfa015d():
    """P1: Claim asserting downregulated when actual log2FC > 0 must trigger BFA-015d."""
    samples = pd.DataFrame({"donor_id": [f"D{i}" for i in range(1, 7)], "condition": ["C"]*3 + ["T"]*3})
    de_data = pd.DataFrame({"gene": ["IL1RN"], "pvalue": [1e-10], "padj": [1e-9], "log2FoldChange": [2.5]})
    result = audit_differential_expression(
        sample_metadata=samples,
        de_table=de_data,
        execution_record={"statistical_unit": "donor", "method": "pydeseq2"},
        claim_text="IL1RN is significantly downregulated after FDR correction in the supplied treated-versus-control result.",
    )
    assert not result.passed
    assert result.overall_status == "NEEDS_REVISION"
    assert any(f.rule_id == "BFA-015d" for f in result.findings)


def test_claim_false_significance_triggers_bfa015a():
    """P1: Claim asserting significant when actual padj >= 0.05 must trigger BFA-015a."""
    samples = pd.DataFrame({"donor_id": [f"D{i}" for i in range(1, 7)], "condition": ["C"]*3 + ["T"]*3})
    de_data = pd.DataFrame({"gene": ["NEG1"], "pvalue": [0.4], "padj": [0.8], "log2FoldChange": [-0.1]})
    result = audit_differential_expression(
        sample_metadata=samples,
        de_table=de_data,
        execution_record={"statistical_unit": "donor", "method": "pydeseq2"},
        claim_text="NEG1 is significant after FDR correction in the supplied result.",
    )
    assert not result.passed
    assert result.overall_status == "NEEDS_REVISION"
    assert any(f.rule_id == "BFA-015a" for f in result.findings)


def test_claim_false_negative_triggers_bfa015b():
    """P1: Claim asserting not significant when actual padj < 0.05 must trigger BFA-015b."""
    samples = pd.DataFrame({"donor_id": [f"D{i}" for i in range(1, 7)], "condition": ["C"]*3 + ["T"]*3})
    de_data = pd.DataFrame({"gene": ["IL1RN"], "pvalue": [1e-10], "padj": [1e-9], "log2FoldChange": [2.5]})
    result = audit_differential_expression(
        sample_metadata=samples,
        de_table=de_data,
        execution_record={"statistical_unit": "donor", "method": "pydeseq2"},
        claim_text="IL1RN was not significant after FDR correction in the supplied result.",
    )
    assert not result.passed
    assert result.overall_status == "NEEDS_REVISION"
    assert any(f.rule_id == "BFA-015b" for f in result.findings)


def test_claim_false_global_null_triggers_bfa015c():
    """P1: Claim asserting no genes significant when table has DEGs must trigger BFA-015c."""
    samples = pd.DataFrame({"donor_id": [f"D{i}" for i in range(1, 7)], "condition": ["C"]*3 + ["T"]*3})
    de_data = pd.DataFrame({"gene": ["IL1RN"], "pvalue": [1e-10], "padj": [1e-9], "log2FoldChange": [2.5]})
    result = audit_differential_expression(
        sample_metadata=samples,
        de_table=de_data,
        execution_record={"statistical_unit": "donor", "method": "pydeseq2"},
        claim_text="No genes were significant after FDR correction in the supplied result.",
    )
    assert not result.passed
    assert result.overall_status == "NEEDS_REVISION"
    assert any(f.rule_id == "BFA-015c" for f in result.findings)


def test_valid_claims_concordant_with_table_achieve_robust_pass(tmp_path):
    """P1: Valid claims concordant with table (positive, negative, presence) achieve ROBUST_PASS."""
    samples = pd.DataFrame({"donor_id": [f"D{i}" for i in range(1, 7)], "condition": ["C"]*3 + ["T"]*3})
    de_data = pd.DataFrame({
        "gene": ["IL1RN", "NEG1"],
        "pvalue": [1e-10, 0.4],
        "padj": [1e-9, 0.8],
        "log2FoldChange": [2.5, -0.1],
    })
    # Valid positive claim
    result_path, receipt = _bound_result(tmp_path, de_data)
    r1 = audit_differential_expression(
        sample_metadata=samples,
        de_table=result_path,
        execution_record=receipt,
        claim_text="IL1RN is upregulated and significant after FDR correction in the supplied treated-versus-control result.",
    )
    assert r1.passed is True
    assert r1.overall_status == "ROBUST_PASS"

    # Valid negative claim
    r2 = audit_differential_expression(
        sample_metadata=samples,
        de_table=result_path,
        execution_record=receipt,
        claim_text="NEG1 was not significant after FDR correction in the supplied result.",
    )
    assert r2.passed is True
    assert r2.overall_status == "ROBUST_PASS"

    # Valid table presence claim
    r3 = audit_differential_expression(
        sample_metadata=samples,
        de_table=result_path,
        execution_record=receipt,
        claim_text="The supplied differential-expression table contains a result for IL1RN.",
    )
    assert r3.passed is True
    assert r3.overall_status == "ROBUST_PASS"


def test_unwarranted_negative_causal_assertion_rejected():
    """Negative causal assertion ('does not cause') without perturbation must NOT bypass warrant via negation."""
    samples = pd.DataFrame({"donor_id": [f"D{i}" for i in range(1, 7)], "condition": ["C"]*3 + ["T"]*3})
    de_data = pd.DataFrame({
        "gene": ["IFITM1", "STAT1"],
        "baseMean": [100.0, 80.0],
        "log2FoldChange": [1.5, -0.8],
        "pvalue": [1e-4, 0.01],
        "padj": [1e-3, 0.04],
    })
    # Negative causal assertion: asserting evidence of absence without perturbation
    claim = "IFITM1 does not cause disease pathogenesis in the treated cohort."
    result = audit_differential_expression(
        sample_metadata=samples,
        de_table=de_data,
        execution_record={"statistical_unit": "donor", "method": "pydeseq2"},
        claim_text=claim,
    )
    assert result.passed is False
    assert result.overall_status == "NEEDS_REVISION"
    # Must trigger BFA-008 for exceeding evidence ceiling (absence of evidence != evidence of absence)
    bfa008 = next((f for f in result.findings if f.rule_id == "BFA-008"), None)
    assert bfa008 is not None
    assert "超出证据边界" in bfa008.title
    check_targeted = next(c for c in result.checks if c.check_id == "claim_targeted_warrant")
    assert check_targeted.status == CheckStatus.ISSUE_FOUND


def test_epistemic_disclaimer_honest_warrant_accepted(tmp_path):
    """Epistemic disclaimer ('cannot prove') acknowledging absence of evidence is warranted and passes."""
    samples = pd.DataFrame({"donor_id": [f"D{i}" for i in range(1, 7)], "condition": ["C"]*3 + ["T"]*3})
    de_data = pd.DataFrame({
        "gene": ["IFITM1", "STAT1"],
        "baseMean": [100.0, 80.0],
        "log2FoldChange": [1.5, -0.8],
        "pvalue": [1e-4, 0.01],
        "padj": [1e-3, 0.04],
    })
    # Honest epistemic disclaimer stating inability to prove
    claim = "In our cohort, marker p-values cannot prove IFITM1 causes disease pathogenesis."
    result_path, receipt = _bound_result(tmp_path, de_data)
    result = audit_differential_expression(
        sample_metadata=samples,
        de_table=result_path,
        execution_record=receipt,
        claim_text=claim,
    )
    assert result.passed is True
    assert result.overall_status == "ROBUST_PASS"
    assert not any(f.rule_id == "BFA-008" for f in result.findings)
    check_targeted = next(c for c in result.checks if c.check_id == "claim_targeted_warrant")
    assert check_targeted.status == CheckStatus.ASSESSED


def test_extreme_p_diagnostic_signal_wording():
    """Verify BFA-001c explicitly defines extreme P as diagnostic signal, not methodological invalidity."""
    de_data = pd.DataFrame({
        "gene": [f"G_{i}" for i in range(50)],
        "pvalue": [1e-150] * 15 + [0.01] * 35,
        "padj": [1e-148] * 15 + [0.04] * 35,
    })
    result = audit_differential_expression(de_table=de_data)
    f = next(f for f in result.findings if f.rule_id == "BFA-001c")
    assert "诊断信号" in f.title
    assert "diagnostic signal" in f.impact_on_conclusion
    assert "methodological invalidity" in f.impact_on_conclusion
    assert "非方法学无效" in f.impact_on_conclusion
