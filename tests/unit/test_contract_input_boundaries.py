"""Older result inputs and unexecuted states cannot acquire scientific maturity."""
import pytest

from bionexus.contracts import EvidenceCard, synthesize_conclusion_maturity
from bionexus.rule_classification import RuleCategory, RuleClassification


@pytest.mark.parametrize("state", ["PERMITTED", "PERMITTED_WITH_LIMITS"])
@pytest.mark.parametrize("as_dict", [False, True])
def test_preflight_state_is_unassessed_even_with_strong_dimensions(state, as_dict):
    card = EvidenceCard(execution_state=state, statistical_support="A",
                        parameter_robustness="A", external_validation="A")
    assert synthesize_conclusion_maturity(card.to_dict() if as_dict else card) == "UNASSESSED"
    assert EvidenceCard(**card.to_dict()).synthesize_status() == "UNASSESSED"


@pytest.mark.parametrize("state", ["UNKNOWN_FUTURE_STATE", "", None, [], 7])
def test_explicit_invalid_execution_state_cannot_fall_back_to_legacy_success(state):
    assert synthesize_conclusion_maturity({"execution_state": state, "execution_fidelity": "A"}) == "ABSTAIN"


@pytest.mark.parametrize("fidelity,expected", [("A", "PRELIMINARY"), ("B", "FRAGILE"),
                                             ("REFUSED", "ABSTAIN"), ("FAIL", "ABSTAIN"),
                                             ("future-fidelity", "ABSTAIN")])
def test_legacy_fidelity_agrees_between_object_and_dictionary(fidelity, expected):
    assert synthesize_conclusion_maturity({"execution_fidelity": fidelity}) == expected
    assert EvidenceCard(execution_fidelity=fidelity).synthesize_status() == expected


@pytest.mark.parametrize("category", list(RuleCategory))
def test_default_rule_explanation_is_nonempty_text(category):
    rule = RuleClassification(category=category)
    assert isinstance(rule.rationale, str) and rule.rationale.strip()
    assert isinstance(rule.to_dict()["rationale"], str)
