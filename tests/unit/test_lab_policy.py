"""Tests for Lab Policy Profiles: Shadow / Advisory / Enforced enforcement modes.

Verifies the Task 5 contract:
- Execution invariants are enforced under every lab policy profile.
- Warrant constraints follow the lab's declared posture (shadow/advisory/enforced).
- Shadow mode records violations on the EvidenceCard without blocking or capping.
- Unknown policy names fall back to the default advisory profile.
"""

from unittest.mock import patch

from bionexus import (
    DEFAULT_LAB_POLICY,
    DISCOVERY_LAB,
    ENFORCED_LAB,
    SHADOW_AUDIT,
    EnforcementMode,
    get_lab_policy,
    route_scientific_intent,
)
from bionexus.capabilities import (
    CapabilityEvaluationResult,
    RefusalTrigger,
    get_capability,
)
from bionexus.contracts import DimensionGrade, EvidenceCard, ExecutionState
from bionexus.lab_policy import laxer, mode_rank, stricter
from bionexus.research_purpose import PurposeContext, ResearchPurpose
from bionexus.rule_classification import (
    CLASSIFICATION_BIOLOGICAL_REPLICATES,
    CLASSIFICATION_CLINICAL_DIAGNOSIS,
)

# ---------------------------------------------------------------------------
# Profile resolution & helpers
# ---------------------------------------------------------------------------


def test_policy_resolution_and_unknown_name_fallback():
    assert get_lab_policy(None) is DISCOVERY_LAB
    assert get_lab_policy("shadow_audit") is SHADOW_AUDIT
    assert get_lab_policy("discovery_lab") is DISCOVERY_LAB
    assert get_lab_policy("enforced_lab") is ENFORCED_LAB
    # Typo must never harden a pipeline into refusal: fall back to default.
    assert get_lab_policy("typo_lab") is DEFAULT_LAB_POLICY


def test_mode_ordering_helpers():
    assert mode_rank(EnforcementMode.SHADOW) < mode_rank(EnforcementMode.ADVISORY)
    assert mode_rank(EnforcementMode.ADVISORY) < mode_rank(EnforcementMode.ENFORCED)
    assert stricter(EnforcementMode.SHADOW, EnforcementMode.ENFORCED) is EnforcementMode.ENFORCED
    assert laxer(EnforcementMode.SHADOW, EnforcementMode.ENFORCED) is EnforcementMode.SHADOW


def test_effective_mode_for_semantics():
    # Invariants are ENFORCED under every profile.
    for policy in (SHADOW_AUDIT, DISCOVERY_LAB, ENFORCED_LAB):
        assert policy.effective_mode_for(CLASSIFICATION_CLINICAL_DIAGNOSIS) is EnforcementMode.ENFORCED
    # Warrants follow the lab posture.
    assert SHADOW_AUDIT.effective_mode_for(CLASSIFICATION_BIOLOGICAL_REPLICATES) is EnforcementMode.SHADOW
    assert DISCOVERY_LAB.effective_mode_for(CLASSIFICATION_BIOLOGICAL_REPLICATES) is EnforcementMode.ADVISORY
    assert ENFORCED_LAB.effective_mode_for(CLASSIFICATION_BIOLOGICAL_REPLICATES) is EnforcementMode.ENFORCED
    # Unknown classification falls back to the lab posture.
    assert DISCOVERY_LAB.effective_mode_for(None) is EnforcementMode.ADVISORY


def test_profile_serialization_round_trip():
    d = ENFORCED_LAB.to_dict()
    assert d["name"] == "enforced_lab"
    assert d["warrant_mode"] == "ENFORCED"
    assert d["require_override_justification"] is True
    assert d["auto_acknowledge_purposes"] == []


# ---------------------------------------------------------------------------
# End-to-end routing under the three profiles
# ---------------------------------------------------------------------------

_DE_META = {
    "n_cells": 5000,
    "has_condition": True,
    "conditions": ["ctrl", "treat"],
    "min_replicates_per_condition": 1,
    "is_normalized": False,
    "is_integer_like": True,
}
_DE_QUERY = "Run differential expression between conditions"


def test_shadow_policy_permits_and_records_warrant_violation():
    decision = route_scientific_intent(
        _DE_QUERY, data_metadata=_DE_META, research_purpose="screening", lab_policy="shadow_audit"
    )
    assert decision.status.value == "PERMITTED"
    card = decision.evidence_card_template
    assert card.details.get("shadow_mode") is True
    assert card.details.get("shadow_violations")
    assert card.details.get("lab_policy") == "shadow_audit"
    # Shadow posture never changes the science: the ceiling still applies.
    wa = card.details["warrant_assessment"]
    assert wa["evidence_ceiling"] == "FRAGILE"
    assert "population_level_inference" in wa["unsupported_claims"]
    assert card.evidence_ceiling == "FRAGILE"
    assert card.details["policy_decision"]["action"] == "ALLOW_WITH_ACK"


def test_discovery_policy_auto_acknowledges_screening_without_override():
    decision = route_scientific_intent(_DE_QUERY, data_metadata=_DE_META, research_purpose="screening")
    assert decision.status.value == "PERMITTED_WITH_LIMITS"
    pd = decision.evidence_card_template.details["policy_decision"]
    assert pd["action"] == "ALLOW_WITH_LIMITS"
    assert pd["friction_level"] == "record_only"
    assert pd["requires_user_action"] is False
    assert decision.evidence_card_template.details["low_friction_discovery"] is True
    assert decision.override_records == []


def test_warrant_assessment_is_identical_across_policies():
    """The theoretical core: policy decides the intervention, never the
    evidence value.  n=1 donor/condition must yield the SAME assessment
    (ceiling=FRAGILE, same unsupported claims) in shadow, advisory, and
    enforced labs."""
    assessments = {}
    actions = {}
    for pol in ("shadow_audit", "discovery_lab", "enforced_lab"):
        decision = route_scientific_intent(
            _DE_QUERY, data_metadata=_DE_META, research_purpose="screening", lab_policy=pol
        )
        details = decision.evidence_card_template.details
        assessments[pol] = details["warrant_assessment"]
        actions[pol] = details["policy_decision"]["action"]
    shadow, advisory, enforced = (
        assessments["shadow_audit"],
        assessments["discovery_lab"],
        assessments["enforced_lab"],
    )
    assert shadow == advisory == enforced
    assert shadow["evidence_ceiling"] == "FRAGILE"
    assert shadow["policy_independent"] is True
    # ...while the intervention differs.
    assert (actions["shadow_audit"], actions["discovery_lab"], actions["enforced_lab"]) == (
        "ALLOW_WITH_ACK",
        "ALLOW_WITH_LIMITS",
        "BLOCK",
    )


def test_discovery_policy_still_requires_override_for_confirmatory_gap():
    decision = route_scientific_intent(
        _DE_QUERY,
        data_metadata=_DE_META,
        research_purpose="confirmatory",
    )
    assert decision.status.value == "ABSTAIN"
    pd = decision.evidence_card_template.details["policy_decision"]
    assert pd["action"] == "REQUIRE_OVERRIDE"
    assert pd["friction_level"] == "documented_override"
    assert pd["requires_user_action"] is True


def test_advisory_policy_override_yields_permitted_with_limits():
    decision = route_scientific_intent(
        _DE_QUERY,
        data_metadata=_DE_META,
        research_purpose="screening",
        override_justification="Pilot screen; replicates pending.",
    )
    assert decision.status.value == "PERMITTED_WITH_LIMITS"
    assert decision.evidence_card_template.details.get("lab_policy") == "discovery_lab"
    assert decision.override_records


def test_enforced_policy_blocks_warrant_even_under_override():
    decision = route_scientific_intent(
        _DE_QUERY,
        data_metadata=_DE_META,
        research_purpose="screening",
        override_justification="Pilot screen; replicates pending.",
        lab_policy="enforced_lab",
    )
    assert decision.status.value == "ABSTAIN"
    assert decision.evidence_card_template.details["policy_decision"]["action"] == "BLOCK"


# ---------------------------------------------------------------------------
# Capability-layer classification under injected triggers
# ---------------------------------------------------------------------------


def _refused_base(cap_id: str, trigger: RefusalTrigger) -> CapabilityEvaluationResult:
    return CapabilityEvaluationResult(
        capability_id=cap_id,
        status="REFUSED",
        permitted=False,
        violations=[trigger.description],
        refusal_triggers=[trigger],
        remedies=[trigger.remedy],
        evidence_card=EvidenceCard(
            execution_state=ExecutionState.REFUSED.value,
            input_integrity=DimensionGrade.UNTESTED.value,
            assumption_validity=DimensionGrade.GRADE_C.value,
            statistical_support=DimensionGrade.UNTESTED.value,
            details={"contract_id": cap_id, "violations": [trigger.description]},
        ),
        conclusion_maturity="ABSTAIN",
    )


def test_invariant_trigger_blocks_under_every_policy():
    cap = get_capability("scrna.pseudobulk_de")
    trigger = RefusalTrigger(
        condition_id="model_substitution_attempt",
        description="Presenting proxy output as official foundation-model output.",
        remedy="Acknowledge the proxy.",
        violated_rule="Model attribution invariant",
    )
    base = _refused_base(cap.id, trigger)
    for pname in ("shadow_audit", "discovery_lab", "enforced_lab"):
        with patch.object(type(cap), "evaluate_viability", return_value=base):
            result = cap.evaluate_viability_with_purpose(
                purpose_context=PurposeContext(purpose=ResearchPurpose.EXPLORATORY),
                lab_policy=get_lab_policy(pname),
            )
            assert result.status == "REFUSED", (pname, result.status)
            assert result.permitted is False


def test_safety_invariant_escalates_in_every_lab():
    """INVARIANT_SAFETY rules demand human/regulatory review, not just a
    refusal — and no lab profile can downgrade that."""
    cap = get_capability("scrna.pseudobulk_de")
    trigger = RefusalTrigger(
        condition_id="clinical_diagnosis",
        description="Attempting clinical diagnosis without CLIA/CAP certification.",
        remedy="Attach RUO disclaimer.",
        violated_rule="Regulatory and clinical honesty invariant",
    )
    base = _refused_base(cap.id, trigger)
    for pname in ("shadow_audit", "discovery_lab", "enforced_lab"):
        with patch.object(type(cap), "evaluate_viability", return_value=base):
            result = cap.evaluate_viability_with_purpose(
                purpose_context=PurposeContext(purpose=ResearchPurpose.EXPLORATORY),
                lab_policy=get_lab_policy(pname),
            )
            assert result.status == "REFUSED", (pname, result.status)
            pd = result.policy_decision
            assert pd is not None
            assert pd["action"] == "ESCALATE", (pname, pd["action"])


def test_warrant_trigger_shadowed_but_not_forgotten():
    cap = get_capability("scrna.pseudobulk_de")
    trigger = RefusalTrigger(
        condition_id="missing_replicates",
        description="Found 1 replicate per condition, minimum required is 2.",
        remedy="Add replicates.",
        violated_rule="Biological replicate requirement",
    )
    base = _refused_base(cap.id, trigger)
    with patch.object(type(cap), "evaluate_viability", return_value=base):
        result = cap.evaluate_viability_with_purpose(
            purpose_context=PurposeContext(purpose=ResearchPurpose.SCREENING),
            lab_policy=SHADOW_AUDIT,
        )
        assert result.status == "PERMITTED" and result.permitted
        assert result.shadow_violations == [trigger.description]
        assert result.evidence_card.details["shadow_mode"] is True
        assert result.evidence_card.details["shadow_condition_ids"] == ["missing_replicates"]

    with patch.object(type(cap), "evaluate_viability", return_value=base):
        enforced = cap.evaluate_viability_with_purpose(
            purpose_context=PurposeContext(purpose=ResearchPurpose.SCREENING),
            lab_policy=ENFORCED_LAB,
        )
        assert enforced.status == "REFUSED" and not enforced.permitted


def test_evaluation_result_dict_exposes_policy_fields():
    cap = get_capability("scrna.pseudobulk_de")
    trigger = RefusalTrigger(
        condition_id="missing_replicates",
        description="Found 1 replicate per condition, minimum required is 2.",
        remedy="Add replicates.",
        violated_rule="Biological replicate requirement",
    )
    base = _refused_base(cap.id, trigger)
    with patch.object(type(cap), "evaluate_viability", return_value=base):
        result = cap.evaluate_viability_with_purpose(
            purpose_context=PurposeContext(purpose=ResearchPurpose.SCREENING),
            lab_policy=SHADOW_AUDIT,
        )
    d = result.to_dict()
    assert d["lab_policy"] == "shadow_audit"
    assert d["shadow_violations"] == [trigger.description]
