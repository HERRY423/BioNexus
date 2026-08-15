"""
Unit tests for the BioNexus Scientific Evidence Operating Layer.

Validates:
1. EvidenceCard data structures and markdown rendering.
2. ConclusionStatus multi-dimensional synthesis.
3. Diagnostic input integrity audits (raw counts vs log1p vs NaNs).
4. Spatial coordinates geometric audits.
5. attach_meta and refuse contracts.
6. Prevention of unearned Grade A when input semantics are distorted.
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

from bio_research.contracts import (
    ABSTAIN,
    GRADE_A,
    GRADE_B,
    GRADE_C,
    ConclusionStatus,
    EvidenceCard,
    attach_meta,
    refuse,
    synthesize_conclusion_status,
)
from bio_research.integrity import (
    audit_expression_matrix,
    audit_spatial_coordinates,
    audit_statistical_significance,
)


def test_evidence_card_defaults_and_serialization():
    """Verify EvidenceCard default fields and dictionary conversion."""
    card = EvidenceCard()
    assert card.execution_fidelity == GRADE_A
    assert card.input_integrity == GRADE_A
    assert card.assumption_validity == GRADE_B
    assert card.statistical_support == GRADE_B
    assert card.parameter_robustness == "UNTESTED"
    assert card.cross_method_concordance == "UNTESTED"
    assert card.external_validation == "UNTESTED"

    d = card.to_dict()
    assert isinstance(d, dict)
    assert d["execution_fidelity"] == "A"
    assert "details" in d

    md = card.to_markdown()
    assert "### BioNexus Evidence Card" in md
    assert "Execution Fidelity" in md


def test_conclusion_status_synthesis_supported():
    """Verify all-A dimensions synthesize to SUPPORTED."""
    card = EvidenceCard(
        execution_fidelity=GRADE_A,
        input_integrity=GRADE_A,
        assumption_validity=GRADE_A,
        statistical_support=GRADE_A,
        parameter_robustness=GRADE_A,
        cross_method_concordance=GRADE_A,
        external_validation=GRADE_A,
    )
    status = synthesize_conclusion_status(card)
    assert status == ConclusionStatus.SUPPORTED.value


def test_conclusion_status_synthesis_tentative():
    """Verify standard execution with default assumptions synthesizes to TENTATIVE."""
    card = EvidenceCard(
        execution_fidelity=GRADE_A,
        input_integrity=GRADE_A,
        assumption_validity=GRADE_B,
        statistical_support=GRADE_B,
    )
    status = synthesize_conclusion_status(card)
    assert status == ConclusionStatus.TENTATIVE.value


def test_conclusion_status_synthesis_fragile():
    """Verify degraded input or assumption violation synthesizes to FRAGILE."""
    # Degraded input
    card_degraded_input = EvidenceCard(
        execution_fidelity=GRADE_A,
        input_integrity=GRADE_C,
        assumption_validity=GRADE_B,
        statistical_support=GRADE_A,
    )
    assert synthesize_conclusion_status(card_degraded_input) == ConclusionStatus.FRAGILE.value

    # Marginal statistical support
    card_weak_stats = EvidenceCard(
        execution_fidelity=GRADE_A,
        input_integrity=GRADE_A,
        assumption_validity=GRADE_A,
        statistical_support=GRADE_C,
    )
    assert synthesize_conclusion_status(card_weak_stats) == ConclusionStatus.FRAGILE.value


def test_conclusion_status_synthesis_conflicted():
    """Verify cross-method discordance synthesizes to CONFLICTED."""
    card = EvidenceCard(
        execution_fidelity=GRADE_A,
        input_integrity=GRADE_A,
        cross_method_concordance=GRADE_C,
    )
    assert synthesize_conclusion_status(card) == ConclusionStatus.CONFLICTED.value


def test_conclusion_status_synthesis_abstain():
    """Verify refusal or missing backend synthesizes to ABSTAIN."""
    card = EvidenceCard(
        execution_fidelity=ABSTAIN,
        input_integrity=ABSTAIN,
    )
    assert synthesize_conclusion_status(card) == ConclusionStatus.ABSTAIN.value
    assert synthesize_conclusion_status(card, abstain=True) == ConclusionStatus.ABSTAIN.value


def test_audit_expression_matrix_raw_counts():
    """Verify integer count matrix is recognized as Grade A counts."""
    # Dense raw counts
    dense_counts = np.array([
        [0, 5, 12, 0],
        [3, 0, 1, 100],
        [0, 0, 0, 2]
    ])
    grade, notes, stats = audit_expression_matrix(dense_counts, expected_type="counts")
    assert grade == GRADE_A
    assert stats["is_integer_like"] is True
    assert stats["has_nans"] is False
    assert stats["has_negs"] is False

    # Sparse raw counts
    sparse_counts = sp.csr_matrix(dense_counts)
    s_grade, _, s_stats = audit_expression_matrix(sparse_counts, expected_type="counts")
    assert s_grade == GRADE_A
    assert s_stats["is_sparse"] is True


def test_audit_expression_matrix_detects_log_normalized():
    """Verify pre-log-normalized matrix is flagged when counts expected."""
    # Simulated log1p(x) floats
    log_data = np.array([
        [0.0, 1.791, 2.564, 0.0],
        [1.386, 0.0, 0.693, 4.615],
        [0.0, 0.0, 0.0, 1.098]
    ])
    grade, notes, stats = audit_expression_matrix(log_data, expected_type="counts")
    assert grade == GRADE_B
    assert stats["is_integer_like"] is False
    assert any("Continuous values detected" in n or "log-normalized" in n for n in notes)


def test_audit_expression_matrix_detects_nans_and_negatives():
    """Verify NaNs and negative values are caught and graded C."""
    # Negative values
    neg_data = np.array([[1.0, -0.5], [2.0, 3.0]])
    grade_neg, notes_neg, _ = audit_expression_matrix(neg_data)
    assert grade_neg == GRADE_C
    assert any("negative values" in n for n in notes_neg)

    # NaNs
    nan_data = np.array([[1.0, np.nan], [2.0, 3.0]])
    grade_nan, notes_nan, _ = audit_expression_matrix(nan_data)
    assert grade_nan == GRADE_C
    assert any("non-finite" in n for n in notes_nan)


def test_audit_spatial_coordinates_validation():
    """Verify spatial coordinate validation and degeneracy detection."""
    # Valid 2D
    valid_coords = np.array([
        [10.0, 20.0],
        [15.0, 25.0],
        [30.0, 40.0],
        [50.0, 60.0],
        [70.0, 80.0],
    ])
    grade, notes, stats = audit_spatial_coordinates(valid_coords)
    assert grade == GRADE_A
    assert stats["n_points"] == 5
    assert stats["n_dimensions"] == 2

    # Degenerate zero variance (all spots at single point)
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

    # All non-significant
    high_pvals = np.array([0.30, 0.50, 0.90])
    h_grade, _, h_stats = audit_statistical_significance(pvals=high_pvals, alpha=0.05)
    assert h_grade == GRADE_C
    assert h_stats["n_significant"] == 0


def test_attach_meta_evidence_card_enrichment():
    """Verify attach_meta enriches results with EvidenceCard and conclusion_status."""
    raw = {"result": 42}
    enriched = attach_meta(
        raw,
        method="test_method",
        backend="test_backend",
        evidence_grade=GRADE_A,
    )
    assert enriched["evidence_grade"] == "A"
    assert "evidence_card" in enriched
    assert enriched["evidence_card"]["execution_fidelity"] == "A"
    assert "conclusion_status" in enriched
    assert enriched["conclusion_status"] in (
        ConclusionStatus.SUPPORTED.value,
        ConclusionStatus.TENTATIVE.value
    )


def test_refuse_contract():
    """Verify refuse attaches ABSTAIN evidence card and conclusion status."""
    denied = refuse(
        method="clinical_claim",
        reason="Not authorized as medical device",
    )
    assert denied["refused"] is True
    assert denied["evidence_grade"] == "abstain"
    assert denied["conclusion_status"] == ConclusionStatus.ABSTAIN.value
    assert denied["evidence_card"]["execution_fidelity"] == "abstain"
