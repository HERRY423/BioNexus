"""Bounded disclaimer scope regressions; these do not establish general language understanding."""

from __future__ import annotations

import pytest

from bionexus.claim_semantics import (
    DeterministicClaimParser,
    DeterministicWarrantEngine,
    EvidenceProfile,
    detect_assertive_causal_language,
)


@pytest.mark.parametrize("connector", ["since", "since then", "since 2020", "because", "but", "however", "yet", "and", "therefore", "thus", "although", "whereas", ";"])
def test_disclaimer_cannot_cover_following_independent_causal_assertion(connector):
    text = f"We cannot prove A causes B {connector} C drives macrophage polarization"
    claim = DeterministicClaimParser.parse(text)
    result = DeterministicWarrantEngine.evaluate(claim, EvidenceProfile(observational_data=True, perturbation=False))
    assert claim.is_epistemic_disclaimer is True
    assert DeterministicClaimParser.is_scoped_disclaimer(text) is False
    assert detect_assertive_causal_language(text) == "drives"
    assert result.is_fully_warranted is False
    assert "epistemic_disclaimer" not in result.tier_verdicts


@pytest.mark.parametrize("text", [
    "We cannot prove A causes B.",
    "Our findings cannot prove that IFITM1 drives disease pathogenesis.",
    "There is no evidence that A drives macrophage polarization.",
    "We cannot prove A causes B since we cannot establish C drives D.",
    "We cannot prove A causes B because we cannot establish C drives D.",
    "We cannot prove A causes B but we cannot establish C drives D either.",
    "Evidence gathered since 2020 cannot prove A causes B.",
    "Evidence gathered since then cannot prove A causes B.",
])
def test_pure_scoped_disclaimers_remain_permitted(text):
    claim = DeterministicClaimParser.parse(text)
    result = DeterministicWarrantEngine.evaluate(claim, EvidenceProfile())
    assert DeterministicClaimParser.is_scoped_disclaimer(text) is True
    assert detect_assertive_causal_language(text) is None
    assert result.is_fully_warranted is True
    assert result.tier_verdicts["epistemic_disclaimer"].is_warranted is True
    assert result.evidence_ceiling == "UNASSESSED"


@pytest.mark.parametrize("connector", ["since", "because", "but"])
def test_local_negation_in_second_clause_is_not_reported_as_positive_causation(connector):
    text = f"We cannot prove A causes B {connector} C does not drive macrophage polarization"
    claim = DeterministicClaimParser.parse(text)
    result = DeterministicWarrantEngine.evaluate(claim, EvidenceProfile(observational_data=True))
    assert detect_assertive_causal_language(text) is None
    # A negative biological assertion still requires its own evidence; it is
    # distinct from falsely interpreting "does not drive" as positive causation.
    assert claim.is_negative_assertion is True
    assert result.is_fully_warranted is False


@pytest.mark.parametrize("connector", ["but", "since then", "since 2020"])
def test_negative_first_clause_does_not_hide_positive_second_clause(connector):
    text = f"A does not drive B {connector} C drives macrophage polarization"
    assert detect_assertive_causal_language(text) == "drives"
