"""DE table adjustment diagnostics and independent, donor-level sign checks."""
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from scipy import sparse

from bionexus.de.engine import DEAuditEngine
from bionexus.de.models import CheckStatus, FindingSeverity
from bionexus.de.rules.matrix_rules import _audit_lfc_concordance
from bionexus.de.rules.table_rules import _audit_de_table


def table_findings(table, **kw):
    findings, checks = [], []
    _audit_de_table(table, findings, [], checks, **kw)
    return {finding.rule_id: finding for finding in findings}, checks


def test_zero_significant_genes_does_not_match_a_row_number():
    table = pd.DataFrame({"pvalue": [.01, .04], "padj": [.15, .20]})
    findings, _ = table_findings(table, claim_text="0 significant genes after FDR correction.")
    assert "BFA-003b" not in findings


def test_copied_and_below_raw_probabilities_require_review():
    raw = np.linspace(.001, .99, 50)
    findings, checks = table_findings(pd.DataFrame({"pvalue": raw, "padj": raw}))
    assert findings["BFA-003d"].severity is FindingSeverity.HIGH_IMPACT
    assert checks[-1].status is CheckStatus.ISSUE_FOUND
    adjusted = raw.copy()
    adjusted[1] = raw[1] / 2
    findings, _ = table_findings(pd.DataFrame({"pvalue": raw, "padj": adjusted}))
    assert findings["BFA-003d"].evidence_data["adjusted_below_raw"] == 1


def test_adjustment_diagnostic_requires_distinct_paired_values_and_accounts_for_method():
    raw = np.linspace(.001, .99, 50)
    for adjusted in (np.ones(50), np.r_[raw[:-1], np.nan]):
        assert "BFA-003d" not in table_findings(pd.DataFrame({"pvalue": raw, "padj": adjusted}))[0]
    for value in (0, .5, 1):
        assert "BFA-003d" not in table_findings(pd.DataFrame({"pvalue": [value]*50, "padj": [value]*50}))[0]
    assert "BFA-003d" not in table_findings(pd.DataFrame({"pvalue": raw, "qval": raw / 2}),
                                             adjustment_method="storey")[0]
    assert "BFA-003d" not in table_findings(pd.DataFrame({"pvals_adj": raw}))[0]
    tiny = np.linspace(1e-30, 1e-25, 50)
    assert "BFA-003d" not in table_findings(pd.DataFrame({"pvalue": tiny, "padj": 2*tiny}))[0]


def test_global_null_shortcut_respects_gene_mentions_and_structured_contract():
    genes = [f"G{i}" for i in range(120)]
    table = pd.DataFrame({"gene": genes, "pvalue": .01, "padj": .5})
    for text in ("G1 不显著，但 G2、G3 显著上调。", "校正后无显著基因，包括G3。",
                 "No genes were significant after FDR correction. TP53 merits validation."):
        finding = table_findings(table, claim_text=text)[0]["BFA-003b"]
        assert "selection-history" in finding.minimal_fix and "0.10" not in finding.minimal_fix
    text = "No genes were significant after FDR correction."
    assert "BFA-003b" not in table_findings(table, claim_text=text)[0]
    assert "BFA-003b" in table_findings(table, claim_text=text, structured_claims=[
        {"gene": "G2", "direction": "up"}])[0]
    table.loc[1, "padj"] = np.nan
    assert "BFA-003b" in table_findings(table, claim_text=text)[0]


@pytest.fixture
def two_types():
    genes = [f"G{i}" for i in range(20)]
    rows, counts = [], []
    for ct in ("T", "B"):
        for group in ("case", "ref"):
            high_first = (ct == "T") == (group == "case")
            for idx in (1, 2):
                for _ in range(2):
                    rows.append((ct, group, f"{group}_{idx}"))
                    counts.append(([20] * 10 + [2] * 10) if high_first else ([2] * 10 + [20] * 10))
    obs = pd.DataFrame(rows, columns=["cell_type", "condition", "donor"])
    table = pd.DataFrame({"gene": genes, "log2_fold_change": [1] * 10 + [-1] * 10,
                          "cell_type": "T", "numerator": "case", "denominator": "ref"})
    return SimpleNamespace(obs=obs, var_names=pd.Index(genes), X=np.array(counts)), table


def audit_pair(adata, de_df, **kw):
    findings, checks = [], []
    summary = _audit_lfc_concordance(adata, de_df, findings, checks, d_col="donor", c_col="condition",
                                     ct_col="cell_type", **kw)
    return summary, [f for f in findings if f.rule_id == "BFA-016"], checks[-1]


@pytest.mark.parametrize("matrix_format", [np.asarray, sparse.csr_matrix, sparse.csc_matrix])
def test_donor_sign_agreement_uses_only_requested_cells_and_contrast(two_types, matrix_format):
    adata, table = two_types
    adata.X = matrix_format(adata.X)
    wrong_type = table.assign(cell_type="B", log2_fold_change=-table.log2_fold_change)
    wrong_case = table.assign(numerator="ref", denominator="case", log2_fold_change=-table.log2_fold_change)
    multi = pd.concat([wrong_type, wrong_case, table])
    assert audit_pair(adata, multi)[0]["status"] == "NOT_ESTIMABLE"
    result, findings, check = audit_pair(adata, multi, case="case", cell_type="T")
    assert result["sign_agreement"] == 1 and result["donors_per_group"] == {"case": 2, "ref": 2}
    assert result["denominator"] == "ref" and check.status is CheckStatus.ASSESSED and not findings
    signs = -table.log2_fold_change
    result, findings, check = audit_pair(adata, table.assign(log2_fold_change=signs))
    assert result["sign_agreement"] == 0 and findings[0].severity is FindingSeverity.HIGH_IMPACT
    assert len(result["discordant_genes"]) == 20
    signs.iloc[:10] *= -1
    assert audit_pair(adata, table.assign(log2_fold_change=signs))[1][0].severity is FindingSeverity.ADVISORY


def test_raw_axis_and_zero_library_are_handled_before_normalization(two_types):
    adata, table = two_types
    # AnnData.raw can have a different number of genes and a different order.
    adata.raw = SimpleNamespace(X=adata.X, var_names=adata.var_names)
    adata.X = adata.X[:, :1]
    adata.var_names = ["filtered_feature"]
    assert audit_pair(adata, table)[0]["count_source"] == "adata.raw.X"
    adata.raw.X[:2] = 0
    result, findings, check = audit_pair(adata, table)
    assert result["zero_libraries"] == [{"condition": "case", "donor": "case_1"}]
    assert result["status"] == "NOT_ESTIMABLE" and check.status is CheckStatus.MISSING_EVIDENCE
    assert not findings


def test_direction_check_abstains_on_missing_overlap_and_ambiguous_ids(two_types):
    adata, table = two_types
    for invalid in (table.assign(gene="duplicate"), table.assign(gene=[f"Z{i}" for i in range(20)]),
                    table.assign(log2_fold_change=0), table.assign(log2_fold_change=np.inf)):
        assert audit_pair(adata, invalid)[0]["status"] == "NOT_ESTIMABLE"
    assert audit_pair(adata, table, min_cells_per_donor=3)[0]["status"] == "NOT_ESTIMABLE"
    tiny, findings, check = audit_pair(adata, table.iloc[:1].assign(log2_fold_change=-1))
    assert tiny["n_genes"] == 1 and not findings and check.status is CheckStatus.MISSING_EVIDENCE
    adata.X[:] = 1
    assert audit_pair(adata, table)[0]["status"] == "NOT_ESTIMABLE"


def test_scanpy_group_requires_same_ordered_condition_comparison(two_types):
    adata, table = two_types
    scanpy_table = table.drop(columns=["cell_type", "numerator", "denominator"]).assign(cluster="case")
    result, _, _ = audit_pair(adata, scanpy_table, cell_type="T", rgg_params={"groupby": "condition"})
    assert result["sign_agreement"] == 1 and result["denominator"] == "ref"
    adata.obs.loc[15, "condition"] = "other"
    result, _, _ = audit_pair(adata, scanpy_table, cell_type="T", ref="ref", rgg_params={"groupby": "condition"})
    assert result["status"] == "NOT_ESTIMABLE"
    assert audit_pair(adata, scanpy_table, rgg_params={"groupby": "cell_type"})[0]["status"] == "NOT_ESTIMABLE"


def test_audit_engine_reports_reversed_direction_from_tagged_table(two_types):
    adata, table = two_types
    table = table.assign(log2_fold_change=-table.log2_fold_change)
    audit = DEAuditEngine(config={"min_cells_per_donor": 2}).audit(adata=adata, de_table=table)
    assert audit.cohort_summary["lfc_concordance"]["sign_agreement"] == 0
    finding = next(f for f in audit.findings if f.rule_id == "BFA-016")
    assert finding.severity is FindingSeverity.HIGH_IMPACT
