"""Known serious DE failure closure, including legitimate positive controls."""
import hashlib

import pandas as pd
import pytest

from bionexus.claim_semantics import DeterministicWarrantEngine
from bionexus.de_audit import CheckStatus, audit_differential_expression


@pytest.fixture
def audit(tmp_path):
    samples = pd.DataFrame({"donor_id": [f"D{i}" for i in range(6)], "condition": ["C"] * 3 + ["T"] * 3})
    def run(claim, genes=None, effects=None, adjusted=None):
        genes = ["POS1", "NEG1"] if genes is None else genes
        effects = [2.0, -1.0] if effects is None else effects
        adjusted = [0.001, 0.8] if adjusted is None else adjusted
        frame = pd.DataFrame({"gene": genes, "padj": adjusted, "pvalue": [0.0001, 0.4]})
        if effects != "missing":
            frame["log2FoldChange"] = effects
        path = tmp_path / "results.csv"
        frame.to_csv(path, index=False)
        receipt = {"statistical_unit": "donor", "method": "pydeseq2", "fit_status": "CONVERGED",
                   "design": "~ condition", "design_matrix_columns": ["Intercept", "condition[T.T]"],
                   "n_donors": 6, "donor_ids": list(samples["donor_id"]),
                   "result_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        return audit_differential_expression(de_table=path, sample_metadata=samples, execution_record=receipt, claim_text=claim)
    return run


@pytest.mark.parametrize("claim", [
    "POS1 is significant; NEG1 is significant.",
    "POS1 is significant. NEG1 is significant.",
    "POS1 is significant and NEG1 is significant.",
    "POS1 is upregulated; NEG1 is upregulated.",
    "POS1 is significant; MISSING1 is significant.",
    "POS1 is significant, MISSING1 is significant.",
    "NEG1 was significant.",
    "POS1 and NEG1 are significant.",
    "POS1 is not upregulated.",
    "NEG1 is not downregulated.",
    "NEG1 is not significant but is significant.",
    "POS1 is significant and MISSING1 also is significant.",
    "POS1 is significant, MISSING1 significant.",
    "POS1 is significant and MISSING1 downregulated.",
])
def test_false_second_or_ambiguous_assertion_cannot_pass(audit, claim):
    assert not audit(claim).passed


@pytest.mark.parametrize("claim", [
    "POS1 is significant; NEG1 was not significant.",
    "POS1 is upregulated. NEG1 is downregulated.",
    "POS1 is significant and NEG1 was not significant.",
    "POS1 is upregulated and significant in the supplied table.",
    "The supplied table contains a result for POS1.",
    "We cannot prove that POS1 causes disease.",
])
def test_supported_clauses_remain_usable(audit, claim):
    assert audit(claim).passed


@pytest.mark.parametrize("effects", ["missing", [None, -1], [float("inf"), -1], ["unknown", -1], [0, -1]])
def test_direction_needs_finite_nonzero_effect(audit, effects):
    assert not audit("POS1 is upregulated.", effects=effects).passed


def test_duplicate_gene_rows_are_ambiguous(audit):
    result = audit("POS1 is significant.", genes=["POS1", "POS1"])
    assert not result.passed
    assert any(c.check_id == "claim_fact_concordance" and c.status == CheckStatus.MISSING_EVIDENCE for c in result.checks)


def test_warrant_failure_is_explicit_and_fail_closed(audit, monkeypatch):
    def fail(*args, **kwargs):
        raise ValueError("injected evaluator failure")
    monkeypatch.setattr(DeterministicWarrantEngine, "evaluate", fail)
    result = audit("POS1 is significant.")
    assert not result.passed
    assert any(c.check_id == "claim_targeted_warrant" and c.status == CheckStatus.PARSE_FAILED for c in result.checks)


def test_population_transport_not_inferred_from_donor_count(audit):
    result = audit("POS1 is significantly upregulated in all humans.")
    assert not result.passed


def test_successful_consistency_audit_does_not_upgrade_evidence(audit):
    result = audit("POS1 is significant in the supplied table.")
    assert result.passed
    assert result.claim_boundary.overall_maturity == "EXPLORATORY_COHORT"
    assert result.to_dict()["scientific_authorization"] == "NONE"
    assert result.to_dict()["producer_authentication"] == "NOT_ESTABLISHED"
    assert result.to_dict()["analysis_execution_verification"] == "NOT_PERFORMED"
