"""
Unit tests for the BioNexus Multi-Donor Differential Expression Evidence Audit Engine (de_audit.py).

Verifies the 5 essential pillars for laboratory adoption:
1. 哪个问题会影响当前结论 (Issues affecting conclusion)
2. 问题对应哪个样本、步骤或声明 (Sample, step, and claim mapping)
3. 最小修复是什么 (Minimal actionable fixes)
4. 当前可以陈述到什么范围 (Permissible claim scope & manuscript phrasing)
5. 哪些分歧需要负责人一次性裁决 (PI one-time decision items)
"""

import anndata as ad
import numpy as np
import pandas as pd
from scipy import sparse

from bionexus.cli import main as cli_main
from bionexus.de_audit import (
    CheckStatus,
    FindingCategory,
    FindingSeverity,
    audit_differential_expression,
)
from bionexus.de_audit_extract import extract_rank_genes_groups


def _create_mock_anndata(
    n_cells: int = 400,
    n_genes: int = 50,
    donors: list = None,
    conditions: list = None,
    cell_types: list = None,
    batches: list = None,
    is_raw_counts: bool = True,
) -> ad.AnnData:
    """Generate controlled AnnData object for audit testing."""
    donors = donors or ["D1", "D2", "D3", "D4"]
    conditions = conditions or ["Control", "Control", "Disease", "Disease"]
    cell_types = cell_types or ["Monocytes", "T_cells"]
    batches = batches or ["B1", "B2"]

    # Assign metadata to cells
    cell_donor = np.random.choice(donors, size=n_cells)
    # Map donor to condition
    donor_cond_map = {d: conditions[i % len(conditions)] for i, d in enumerate(donors)}
    cell_cond = [donor_cond_map[d] for d in cell_donor]
    cell_ct = np.random.choice(cell_types, size=n_cells)
    cell_batch = np.random.choice(batches, size=n_cells)

    obs = pd.DataFrame(
        {
            "donor_id": cell_donor,
            "condition": cell_cond,
            "cell_type": cell_ct,
            "batch": cell_batch,
        },
        index=[f"cell_{i}" for i in range(n_cells)],
    )

    if is_raw_counts:
        X = np.random.poisson(lam=3.0, size=(n_cells, n_genes)).astype(float)
    else:
        # Normalized continuous floats
        X = np.random.lognormal(mean=1.0, sigma=0.5, size=(n_cells, n_genes))

    adata = ad.AnnData(X=sparse.csr_matrix(X), obs=obs)
    if is_raw_counts:
        adata.layers["counts"] = adata.X.copy()
    return adata


def test_pseudoreplication_n_equals_1_detected():
    """Test that N=1 donor per group triggers a BLOCKER for pseudoreplication."""
    adata = _create_mock_anndata(
        donors=["D1", "D2"],
        conditions=["Control", "Disease"],  # 1 Control, 1 Disease
    )
    result = audit_differential_expression(adata=adata)

    assert not result.passed
    assert result.blocker_count >= 1
    replicate_finding = next(
        f for f in result.findings if f.category == FindingCategory.DONOR_REPLICATES
    )
    assert replicate_finding.severity == FindingSeverity.BLOCKER
    assert "BFA-001" in replicate_finding.rule_id
    assert "Control (N=1)" in replicate_finding.sample_or_donor
    assert "最小修复" in replicate_finding.minimal_fix or "必须" in replicate_finding.minimal_fix

    # Check that claim boundary is UNWARRANTED
    assert result.claim_boundary.overall_maturity == "UNWARRANTED"
    assert "严禁" in result.claim_boundary.prohibited_scope


def test_replicates_n_equals_2_triggers_high_impact_and_pi_decision():
    """Test that N=2 donors per group triggers HIGH_IMPACT and creates a PI decision."""
    adata = _create_mock_anndata(
        donors=["D1", "D2", "D3", "D4"],
        conditions=["Control", "Control", "Disease", "Disease"],  # N=2 per group
    )
    result = audit_differential_expression(adata=adata)

    assert result.overall_status == "NEEDS_REVISION"
    assert not result.passed
    assert result.high_impact_count >= 1
    replicate_finding = next(
        f for f in result.findings if f.category == FindingCategory.DONOR_REPLICATES
    )
    assert replicate_finding.severity == FindingSeverity.HIGH_IMPACT
    assert "BFA-001b" in replicate_finding.rule_id

    # Check PI decision generation
    pi_dec = next(d for d in result.pi_decisions if d.decision_id == "PI-DEC-01")
    assert "N=2" in pi_dec.title
    assert "探索性候选基因" in pi_dec.option_a
    assert pi_dec.recommended_option == "A"


def test_donor_imbalance_dominance_detected():
    """Test that single donor dominating > 70% of cells in a cluster is flagged."""
    # Force Donor D1 to dominate Monocytes
    adata = _create_mock_anndata(
        n_cells=300,
        donors=["D1", "D2", "D3", "D4", "D5", "D6"],
        conditions=["Control", "Control", "Control", "Disease", "Disease", "Disease"],
    )
    # Manually skew Monocytes to D1
    monocyte_idx = adata.obs["cell_type"] == "Monocytes"
    adata.obs.loc[monocyte_idx, "donor_id"] = "D1"

    result = audit_differential_expression(adata=adata)
    imb_finding = next(
        f for f in result.findings if f.category == FindingCategory.DONOR_IMBALANCE
    )
    assert imb_finding.severity == FindingSeverity.HIGH_IMPACT
    assert "BFA-007" in imb_finding.rule_id
    assert "D1" in imb_finding.sample_or_donor
    assert "Monocytes" in imb_finding.title

    # Check PI decision for imbalance
    imb_dec = next(d for d in result.pi_decisions if d.decision_id == "PI-DEC-02")
    assert "单一供体主导" in imb_dec.title


def test_complete_batch_confounding_detected():
    """Test that 100% confounding between condition and batch triggers a BLOCKER."""
    adata = _create_mock_anndata(
        donors=["D1", "D2", "D3", "D4", "D5", "D6"],
        conditions=["Control", "Control", "Control", "Disease", "Disease", "Disease"],
    )
    # Force all Control to Batch B1, all Disease to Batch B2
    control_mask = adata.obs["condition"] == "Control"
    adata.obs.loc[control_mask, "batch"] = "Batch_1"
    adata.obs.loc[~control_mask, "batch"] = "Batch_2"

    result = audit_differential_expression(adata=adata)
    assert not result.passed
    confound_finding = next(
        f for f in result.findings if f.category == FindingCategory.BATCH_CONFOUNDING
    )
    assert confound_finding.severity == FindingSeverity.BLOCKER
    assert "BFA-004" in confound_finding.rule_id
    assert "完全混杂" in confound_finding.title


def test_missing_raw_count_layer_detected():
    """Test that normalized float matrix without raw counts layer triggers BLOCKER."""
    adata = _create_mock_anndata(
        donors=["D1", "D2", "D3", "D4", "D5", "D6"],
        conditions=["Control", "Control", "Control", "Disease", "Disease", "Disease"],
        is_raw_counts=False,
    )

    result = audit_differential_expression(adata=adata)
    assert not result.passed
    matrix_finding = next(
        f for f in result.findings if f.category == FindingCategory.INPUT_COUNT_TYPE
    )
    assert matrix_finding.severity == FindingSeverity.BLOCKER
    assert "BFA-002" in matrix_finding.rule_id
    assert "counts" in matrix_finding.minimal_fix


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


def test_clean_design_without_de_results_is_needs_data():
    """A balanced 6-donor matrix is not a completed DE analysis."""
    adata = _create_mock_anndata(
        n_cells=600,
        donors=["D1", "D2", "D3", "D4", "D5", "D6"],
        conditions=["Control", "Control", "Control", "Disease", "Disease", "Disease"],
        batches=["B1", "B2"],
        is_raw_counts=True,
    )
    for i, d in enumerate(["D1", "D2", "D3", "D4", "D5", "D6"]):
        mask = adata.obs["donor_id"] == d
        adata.obs.loc[mask, "batch"] = "B1" if i % 2 == 0 else "B2"

    result = audit_differential_expression(adata=adata)
    assert result.overall_status == "NEEDS_DATA"
    assert not result.passed
    assert result.blocker_count == 0
    assert result.claim_boundary.overall_maturity == "NOT_ASSESSED"
    executed = result.claim_boundary.executed_methods_text.lower()
    assert "negative binomial" not in executed
    assert "wald" not in executed
    assert "pseudobulk aggregation" not in executed or "not confirmed" in executed
    assert "Squair et al." in result.claim_boundary.recommended_methods_text
    de_check = next(c for c in result.checks if c.check_id == "de_results")
    assert de_check.status == CheckStatus.MISSING_EVIDENCE


def test_summary_and_markdown_rendering():
    """Test that summary_text and to_markdown generate structured, readable outputs."""
    adata = _create_mock_anndata(
        donors=["D1", "D2"],
        conditions=["Control", "Disease"],
    )
    result = audit_differential_expression(adata=adata)

    text = result.summary_text(use_color=False)
    assert "BioNexus 证据审计：多供体单细胞差异表达" in text
    assert "1. 哪个问题会影响当前结论" in text
    assert "2. 问题对应哪个样本、步骤或声明" in text
    assert "3. 最小修复是什么" in text
    assert "4. 当前可以陈述到什么范围" in text

    md = result.to_markdown()
    assert "# BioNexus 证据审计报告：多供体单细胞差异表达" in md
    assert "## 1. 哪个问题会影响当前结论" in md
    assert "## 2. 问题对应哪个样本、步骤或声明" in md
    assert "## 3. 最小修复是什么" in md
    assert "## 4. 当前可以陈述到什么范围" in md


def test_cli_audit_de_invocation(tmp_path, monkeypatch):
    """Test CLI bionexus audit-de command execution end-to-end."""
    adata = _create_mock_anndata(
        donors=["D1", "D2", "D3", "D4", "D5", "D6"],
        conditions=["Control", "Control", "Control", "Disease", "Disease", "Disease"],
    )
    h5ad_path = tmp_path / "test.h5ad"
    adata.write_h5ad(h5ad_path)

    out_md = tmp_path / "report.md"
    monkeypatch.setattr(
        "sys.argv",
        ["bionexus", "audit-de", str(h5ad_path), "--out", str(out_md)],
    )

    exit_code = cli_main()
    assert exit_code == 1
    assert out_md.is_file()
    content = out_md.read_text(encoding="utf-8")
    assert "BioNexus 证据审计报告" in content
    assert "NEEDS_DATA" in content


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
    assert result.overall_status in {"NOT_ASSESSED", "NEEDS_DATA"}
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


def _official_rank_genes_groups_uns() -> dict:
    n = 2
    names = np.empty(n, dtype=[("stim", "O")])
    names["stim"] = np.array(["IFITM1", "STAT1"], dtype=object)
    pvals = np.empty(n, dtype=[("stim", "f8")])
    pvals["stim"] = np.array([0.001, 0.01])
    padj = np.empty(n, dtype=[("stim", "f8")])
    padj["stim"] = np.array([0.01, 0.03])
    lfc = np.empty(n, dtype=[("stim", "f8")])
    lfc["stim"] = np.array([2.0, 1.0])
    scores = np.empty(n, dtype=[("stim", "f8")])
    scores["stim"] = np.array([10.0, 5.0])
    return {
        "params": {
            "groupby": "stim",
            "method": "wilcoxon",
            "corr_method": "benjamini-hochberg",
        },
        "names": names,
        "scores": scores,
        "pvals": pvals,
        "pvals_adj": padj,
        "logfoldchanges": lfc,
    }


def test_scanpy_structured_array_preserves_identifiers_and_values():
    adata = _create_mock_anndata(n_cells=20, n_genes=4, donors=["D1", "D2"], conditions=["A", "B"])
    adata.uns["rank_genes_groups"] = _official_rank_genes_groups_uns()

    extracted = extract_rank_genes_groups(adata)
    assert extracted.error is None
    genes = list(extracted.frame["gene"])
    assert genes == ["IFITM1", "STAT1"]
    assert list(extracted.frame["pvalue"]) == [0.001, 0.01]
    assert list(extracted.frame["padj"]) == [0.01, 0.03]
    assert list(extracted.frame["log2fc"]) == [2.0, 1.0]

    result = audit_differential_expression(adata=adata)
    assert result.overall_status != "ROBUST_PASS"
    assert not result.passed
    de_check = next(c for c in result.checks if c.check_id == "de_results")
    assert de_check.status in {CheckStatus.ASSESSED, CheckStatus.ISSUE_FOUND}
    executed = result.claim_boundary.executed_methods_text.lower()
    assert "wilcoxon" in executed
    assert "were tested using negative binomial" not in executed
    assert "donor-level count-model testing was not recorded" in executed


def test_rank_genes_groups_parse_failure_is_reported():
    adata = _create_mock_anndata(
        n_cells=60,
        n_genes=3,
        donors=["D1", "D2", "D3", "D4", "D5", "D6"],
        conditions=["A", "A", "A", "B", "B", "B"],
    )
    for i, d in enumerate(["D1", "D2", "D3", "D4", "D5", "D6"]):
        adata.obs.loc[adata.obs["donor_id"] == d, "batch"] = "B1" if i % 2 == 0 else "B2"
    adata.uns["rank_genes_groups"] = {"params": {"method": "wilcoxon"}}
    result = audit_differential_expression(adata=adata)
    assert result.overall_status in {"NEEDS_DATA", "NEEDS_REVISION"}
    assert not result.passed
    parse = next(c for c in result.checks if c.check_id == "de_results")
    assert parse.status == CheckStatus.PARSE_FAILED
    assert any(f.rule_id == "BFA-PARSE" for f in result.findings)


def test_deseq2_schema_with_balanced_design_can_pass():
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
    result = audit_differential_expression(sample_metadata=samples, de_table=de_data)
    assert result.overall_status == "ROBUST_PASS"
    assert result.passed
    assert result.claim_boundary.overall_maturity == "ROBUST_POPULATION"
    executed = result.claim_boundary.executed_methods_text.lower()
    assert "basemean" in executed or "donor-level" in executed
    assert "wald" not in result.claim_boundary.executed_methods_text.lower() or "schema" in executed
