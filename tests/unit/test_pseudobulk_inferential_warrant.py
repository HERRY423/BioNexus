"""
Unit tests for Pseudobulk Inferential Warrant & Epistemic Boundary Engine.
"""

from __future__ import annotations

import pytest

from bionexus.claim_checker import audit_prohibited_claims
from bionexus.contracts import ConclusionMaturity
from bionexus.pseudobulk_warrant import (
    InferentialRegime,
    evaluate_pseudobulk_inferential_warrant,
)


def test_population_inference_regime():
    """N >= 3 biological replicates with raw integer counts permits population inference."""
    verdict = evaluate_pseudobulk_inferential_warrant(
        n_donors_per_group=4,
        min_cells_per_sample=50,
        is_raw_counts=True,
    )
    assert verdict.regime == InferentialRegime.POPULATION_INFERENCE
    assert verdict.permitted is True
    assert verdict.population_claims_allowed is True
    assert verdict.causal_claims_allowed is False
    assert verdict.maturity_ceiling in (ConclusionMaturity.SUPPORTED, ConclusionMaturity.ROBUST)


def test_descriptive_only_regime():
    """N = 2 replicates caps inference at PRELIMINARY descriptive claims."""
    verdict = evaluate_pseudobulk_inferential_warrant(
        n_donors_per_group=2,
        min_cells_per_sample=30,
        is_raw_counts=True,
    )
    assert verdict.regime == InferentialRegime.DESCRIPTIVE_ONLY
    assert verdict.permitted is True
    assert verdict.population_claims_allowed is False
    assert verdict.maturity_ceiling == ConclusionMaturity.PRELIMINARY
    assert len(verdict.warnings) > 0


def test_abstain_unreplicated_regime():
    """N = 1 (or zero donor metadata) strictly triggers ABSTAIN."""
    verdict_n1 = evaluate_pseudobulk_inferential_warrant(
        n_donors_per_group=1,
        is_raw_counts=True,
    )
    assert verdict_n1.regime == InferentialRegime.ABSTAIN_UNREPLICATED
    assert verdict_n1.permitted is False
    assert verdict_n1.maturity_ceiling == ConclusionMaturity.ABSTAIN

    verdict_no_meta = evaluate_pseudobulk_inferential_warrant(
        n_donors_per_group=5,
        has_donor_metadata=False,
        is_raw_counts=True,
    )
    assert verdict_no_meta.regime == InferentialRegime.ABSTAIN_UNREPLICATED
    assert verdict_no_meta.permitted is False


def test_abstain_non_integer_counts():
    """Normalized / log float inputs to count models strictly trigger ABSTAIN."""
    verdict = evaluate_pseudobulk_inferential_warrant(
        n_donors_per_group=4,
        is_raw_counts=False,
    )
    assert verdict.regime == InferentialRegime.ABSTAIN_INVALID_INPUT
    assert verdict.permitted is False
    assert verdict.maturity_ceiling == ConclusionMaturity.ABSTAIN


def test_abstain_confounded_design():
    """100% confounded batch/donor and condition strictly triggers ABSTAIN."""
    verdict = evaluate_pseudobulk_inferential_warrant(
        n_donors_per_group=4,
        is_confounded=True,
        is_raw_counts=True,
    )
    assert verdict.regime == InferentialRegime.ABSTAIN_CONFOUNDED
    assert verdict.permitted is False
    assert verdict.maturity_ceiling == ConclusionMaturity.ABSTAIN


def test_causal_language_interception():
    """Observational single-cell DE reports making causal claims are intercepted."""
    claim1 = "Marker p-values prove that treatment caused downregulation of gene X."
    audit1 = audit_prohibited_claims(claim1)
    assert audit1.passed is False
    assert any(v.violation_type.value == "CAUSAL_TREATMENT_DE_OVERCLAIM" for v in audit1.violations)

    claim2 = "Our pseudobulk analysis establishes a causal mechanism for lupus."
    audit2 = audit_prohibited_claims(claim2)
    assert audit2.passed is False

    compliant = "Pseudobulk DE identified differential expression associated with interferon stimulation (padj < 0.01)."
    audit_ok = audit_prohibited_claims(compliant)
    assert audit_ok.passed is True
