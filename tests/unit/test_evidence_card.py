"""
Unit tests for the BioNexus Scientific Evidence Operating Layer (EvidenceCard 2.0).

Validates:
1. Layer 1: ExecutionState (EXECUTED | DEGRADED | REFUSED | FAILED).
2. Layer 2: DimensionGrade and distinction between UNTESTED, INSUFFICIENT, CONFLICTED, and GRADE_C.
3. Layer 3: ConclusionMaturity progression (ABSTAIN -> FRAGILE -> CONFLICTED -> PRELIMINARY -> SUPPORTED -> ROBUST -> REPLICATED).
4. EvidenceCard data structures, backward compatibility, and markdown rendering.
5. Diagnostic input integrity audits (raw counts vs log1p vs NaNs).
6. Spatial coordinates geometric audits.
7. Parameter stability & sensitivity audit (audit_parameter_stability).
8. Statistical significance power audit (audit_statistical_significance).
9. attach_meta and refuse contracts.
"""

import sys
from pathlib import Path

import numpy as np
import scipy.sparse as sp

# Ensure src is on sys.path
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SRC = _REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from bionexus.contracts import (
    CONFLICTED,
    GRADE_A,
    GRADE_B,
    GRADE_C,
    INSUFFICIENT,
    UNTESTED,
    ConclusionMaturity,
    ConclusionStatus,
    EvidenceCard,
    ExecutionState,
    attach_meta,
    refuse,
    synthesize_conclusion_maturity,
)
from bionexus.integrity import (
    audit_expression_matrix,
    audit_parameter_stability,
    audit_spatial_coordinates,
    audit_statistical_significance,
)


def test_evidence_card_defaults_and_serialization():
    """Verify EvidenceCard 2.0 default fields and dictionary conversion."""
    card = EvidenceCard()
    assert card.execution_state == ExecutionState.EXECUTED.value
    assert card.execution_fidelity == GRADE_A
    assert card.input_integrity == GRADE_A
    assert card.assumption_validity == GRADE_B
    assert card.statistical_support == GRADE_B
    assert card.parameter_robustness == UNTESTED
    assert card.cross_method_concordance == UNTESTED
    assert card.external_validation == UNTESTED

    d = card.to_dict()
    assert isinstance(d, dict)
    assert d["execution_state"] == "EXECUTED"
    assert d["execution_fidelity"] == "A"
    assert d["parameter_robustness"] == "UNTESTED"
    assert "details" in d

    md = card.to_markdown()
    assert "### BioNexus Evidence Card (v2.0)" in md
    assert "Layer 1: Execution State" in md
    assert "Layer 2: Evidence Dimensions" in md
    assert "Layer 3: Scientific Conclusion" in md


def test_layer1_execution_state_decoupling():
    """Verify execution state is decoupled from scientific conclusion."""
    # A method can be EXECUTED but yield FRAGILE scientific evidence due to degraded inputs
    card = EvidenceCard(
        execution_state=ExecutionState.EXECUTED.value,
        input_integrity=GRADE_C,
        statistical_support=GRADE_A,
    )
    assert card.execution_state == ExecutionState.EXECUTED.value
    assert synthesize_conclusion_maturity(card) == ConclusionMaturity.FRAGILE.value

    # A method can be DEGRADED (heuristic)
    degraded_card = EvidenceCard(
        execution_state=ExecutionState.DEGRADED.value,
        input_integrity=GRADE_A,
        statistical_support=GRADE_A,
    )
    assert synthesize_conclusion_maturity(degraded_card) == ConclusionMaturity.FRAGILE.value


def test_layer2_untested_vs_conflicted_distinction():
    """Verify UNTESTED is strictly distinguished from tested-and-fragile/conflicted."""
    # Single baseline run: untested dimensions do not cause FRAGILE or CONFLICTED
    card_untested = EvidenceCard(
        execution_state=ExecutionState.EXECUTED.value,
        input_integrity=GRADE_A,
        assumption_validity=GRADE_B,
        statistical_support=GRADE_B,
        parameter_robustness=UNTESTED,
        cross_method_concordance=UNTESTED,
        external_validation=UNTESTED,
    )
    # Untested results in PRELIMINARY baseline exploratory status
    assert synthesize_conclusion_maturity(card_untested) == ConclusionMaturity.PRELIMINARY.value

    # Tested and CONFLICTED triggers CONFLICTED
    card_conflicted = EvidenceCard(
        execution_state=ExecutionState.EXECUTED.value,
        input_integrity=GRADE_A,
        cross_method_concordance=CONFLICTED,
    )
    assert synthesize_conclusion_maturity(card_conflicted) == ConclusionMaturity.CONFLICTED.value

    # Tested and fragile parameters trigger FRAGILE
    card_fragile_param = EvidenceCard(
        execution_state=ExecutionState.EXECUTED.value,
        input_integrity=GRADE_A,
        parameter_robustness=GRADE_C,
    )
    assert synthesize_conclusion_maturity(card_fragile_param) == ConclusionMaturity.FRAGILE.value


def test_layer3_epistemic_maturity_progression():
    """Verify progression across the 7 conclusion maturity levels."""
    # 1. ABSTAIN
    card_refused = EvidenceCard(execution_state=ExecutionState.REFUSED.value)
    assert synthesize_conclusion_maturity(card_refused) == ConclusionMaturity.ABSTAIN.value

    # 2. FRAGILE
    card_fragile = EvidenceCard(
        execution_state=ExecutionState.EXECUTED.value,
        input_integrity=GRADE_A,
        statistical_support=INSUFFICIENT,
    )
    assert synthesize_conclusion_maturity(card_fragile) == ConclusionMaturity.FRAGILE.value

    # 3. CONFLICTED
    card_conf = EvidenceCard(
        execution_state=ExecutionState.EXECUTED.value,
        cross_method_concordance=CONFLICTED,
    )
    assert synthesize_conclusion_maturity(card_conf) == ConclusionMaturity.CONFLICTED.value

    # 4. PRELIMINARY (Standard single run)
    card_prelim = EvidenceCard(
        execution_state=ExecutionState.EXECUTED.value,
        input_integrity=GRADE_A,
        assumption_validity=GRADE_B,
        statistical_support=GRADE_B,
    )
    assert synthesize_conclusion_maturity(card_prelim) == ConclusionMaturity.PRELIMINARY.value

    # 5. SUPPORTED (Verified inputs, valid assumptions, strong statistics on current dataset)
    card_supp = EvidenceCard(
        execution_state=ExecutionState.EXECUTED.value,
        input_integrity=GRADE_A,
        assumption_validity=GRADE_A,
        statistical_support=GRADE_A,
    )
    assert synthesize_conclusion_maturity(card_supp) == ConclusionMaturity.SUPPORTED.value

    # 6. ROBUST (SUPPORTED + verified stable under parameter sweeps)
    card_robust = EvidenceCard(
        execution_state=ExecutionState.EXECUTED.value,
        input_integrity=GRADE_A,
        assumption_validity=GRADE_A,
        statistical_support=GRADE_A,
        parameter_robustness=GRADE_A,
    )
    assert synthesize_conclusion_maturity(card_robust) == ConclusionMaturity.ROBUST.value

    # 7. REPLICATED (ROBUST + verified against independent external truth sets)
    card_repl = EvidenceCard(
        execution_state=ExecutionState.EXECUTED.value,
        input_integrity=GRADE_A,
        assumption_validity=GRADE_A,
        statistical_support=GRADE_A,
        parameter_robustness=GRADE_A,
        external_validation=GRADE_A,
    )
    assert synthesize_conclusion_maturity(card_repl) == ConclusionMaturity.REPLICATED.value


def test_audit_parameter_stability():
    """Verify audit_parameter_stability evaluates parameter perturbation sweeps."""
    # Highly stable clustering across 3 resolutions (identical clusterings)
    c1 = np.array([0, 0, 0, 1, 1, 1, 2, 2])
    c2 = np.array([0, 0, 0, 1, 1, 1, 2, 2])
    c3 = np.array([1, 1, 1, 0, 0, 0, 2, 2])  # Relabeled same partition
    grade_stable, notes_stable, stats_stable = audit_parameter_stability([c1, c2, c3], metric="ari")
    assert grade_stable == GRADE_A
    assert stats_stable["mean_similarity"] > 0.99

    # Fragile random clusterings
    r1 = np.array([0, 1, 0, 1, 0, 1, 0, 1])
    r2 = np.array([1, 1, 0, 0, 1, 0, 0, 1])
    r3 = np.array([0, 0, 0, 1, 1, 1, 0, 0])
    grade_fragile, _, stats_fragile = audit_parameter_stability([r1, r2, r3], metric="ari")
    assert grade_fragile in (GRADE_B, GRADE_C)

    # Feature rank jaccard stability
    f1 = ["CD3D", "CD3E", "CD4", "IL7R", "TCF7"]
    f2 = ["CD3D", "CD3E", "CD4", "IL7R", "LEF1"]
    grade_jaccard, _, stats_j = audit_parameter_stability([f1, f2], metric="jaccard", tolerance_threshold=0.60)
    assert grade_jaccard == GRADE_A
    assert stats_j["mean_similarity"] >= 0.60


def test_audit_expression_matrix_raw_counts():
    """Verify integer count matrix is recognized as Grade A counts."""
    dense_counts = np.array([[0, 5, 12, 0], [3, 0, 1, 100], [0, 0, 0, 2]])
    grade, notes, stats = audit_expression_matrix(dense_counts, expected_type="counts")
    assert grade == GRADE_A
    assert stats["is_integer_like"] is True
    assert stats["has_nans"] is False
    assert stats["has_negs"] is False

    sparse_counts = sp.csr_matrix(dense_counts)
    s_grade, _, s_stats = audit_expression_matrix(sparse_counts, expected_type="counts")
    assert s_grade == GRADE_A
    assert s_stats["is_sparse"] is True


def test_audit_expression_matrix_detects_log_normalized():
    """Verify pre-log-normalized matrix is flagged when counts expected."""
    log_data = np.array([[0.0, 1.791, 2.564, 0.0], [1.386, 0.0, 0.693, 4.615], [0.0, 0.0, 0.0, 1.098]])
    grade, notes, stats = audit_expression_matrix(log_data, expected_type="counts")
    assert grade == GRADE_B
    assert stats["is_integer_like"] is False
    assert any("Continuous values detected" in n or "log-normalized" in n for n in notes)


def test_audit_expression_matrix_detects_nans_and_negatives():
    """Verify NaNs and negative values are caught and graded C."""
    neg_data = np.array([[1.0, -0.5], [2.0, 3.0]])
    grade_neg, notes_neg, _ = audit_expression_matrix(neg_data)
    assert grade_neg == GRADE_C
    assert any("negative values" in n for n in notes_neg)

    nan_data = np.array([[1.0, np.nan], [2.0, 3.0]])
    grade_nan, notes_nan, _ = audit_expression_matrix(nan_data)
    assert grade_nan == GRADE_C
    assert any("non-finite" in n for n in notes_nan)


def test_audit_spatial_coordinates_validation():
    """Verify spatial coordinate validation and degeneracy detection."""
    valid_coords = np.array(
        [
            [10.0, 20.0],
            [15.0, 25.0],
            [30.0, 40.0],
            [50.0, 60.0],
            [70.0, 80.0],
        ]
    )
    grade, notes, stats = audit_spatial_coordinates(valid_coords)
    assert grade == GRADE_A
    assert stats["n_points"] == 5
    assert stats["n_dimensions"] == 2

    degen_coords = np.zeros((10, 2))
    d_grade, d_notes, d_stats = audit_spatial_coordinates(degen_coords)
    assert d_grade == GRADE_C
    assert d_stats["zero_variance"] is True


def test_audit_statistical_significance():
    """Verify statistical significance power checks."""
    pvals = np.array([0.001, 0.02, 0.04, 0.20, 0.85])
    fdr_q = np.array([0.005, 0.03, 0.045, 0.30, 0.85])

    grade, notes, stats = audit_statistical_significance(pvals=pvals, fdr_q=fdr_q, alpha=0.05)
    assert grade == GRADE_A
    assert stats["n_significant"] == 3

    high_pvals = np.array([0.30, 0.50, 0.90])
    h_grade, _, h_stats = audit_statistical_significance(pvals=high_pvals, alpha=0.05)
    assert h_grade == GRADE_C
    assert h_stats["n_significant"] == 0


def test_attach_meta_evidence_card_enrichment():
    """Verify attach_meta enriches results with EvidenceCard 2.0 and conclusion_maturity."""
    raw = {"result": 42}
    enriched = attach_meta(
        raw,
        method="test_method",
        backend="test_backend",
        evidence_grade=GRADE_A,
    )
    assert enriched["evidence_grade"] == "A"
    assert enriched["execution_state"] == "EXECUTED"
    assert "evidence_card" in enriched
    assert enriched["evidence_card"]["execution_state"] == "EXECUTED"
    assert "conclusion_maturity" in enriched
    assert enriched["conclusion_maturity"] in (
        ConclusionMaturity.SUPPORTED.value,
        ConclusionMaturity.PRELIMINARY.value,
    )


def test_refuse_contract():
    """Verify refuse attaches ABSTAIN evidence card and conclusion status."""
    denied = refuse(
        method="clinical_claim",
        reason="Not authorized as medical device",
    )
    assert denied["refused"] is True
    assert denied["evidence_grade"] == "abstain"
    assert denied["execution_state"] == "REFUSED"
    assert denied["conclusion_maturity"] == ConclusionMaturity.ABSTAIN.value
    assert denied["conclusion_status"] == ConclusionStatus.ABSTAIN.value
    assert denied["evidence_card"]["execution_state"] == "REFUSED"
