"""
Tests for the Evidence Model: Evidence Strength ≠ Intended Use Requirement.

Encodes the theoretical invariants of the third warrant-engine decoupling:

- Purpose decides the evidence REQUIREMENT, never the evidence VALUE.
- Strong evidence stays strong under an exploratory purpose.
- Weak evidence cannot be elevated by a clinical purpose.
- Verdicts compare evidence against the composed (purpose + claim) bar.
"""

from bionexus.contracts import ConclusionMaturity
from bionexus.evidence_model import (
    CLAIM_REQUIREMENTS,
    ClaimClass,
    ClaimContext,
    SufficiencyVerdict,
    assess_evidence,
    evaluate_sufficiency,
    use_requirement_for,
)
from bionexus.research_purpose import (
    PURPOSE_EVIDENCE_REQUIREMENT,
    PurposeContext,
    ResearchPurpose,
)

STRONG_FACTORS = [
    "sample_design",
    "confound_controls",
    "sensitivity_analysis",
    "backend_fidelity",
    "provenance",
]


class _Trigger:
    def __init__(self, condition_id):
        self.condition_id = condition_id
        self.description = condition_id
        self.provenance = None


# ── Evidence assessment is purpose-independent ────────────────────────────────


class TestEvidenceAssessmentIndependence:
    def test_purpose_does_not_change_evidence_value(self):
        """The same evidence facts yield the same assessment under every purpose."""
        assessments = [assess_evidence(satisfied_factors=STRONG_FACTORS) for _ in ResearchPurpose]
        first = assessments[0].to_dict()
        for a in assessments[1:]:
            assert a.to_dict() == first
        assert first["evidence_maturity"] == "ROBUST"
        assert first["purpose_independent"] is True
        assert first["policy_independent"] is True

    def test_strong_evidence_not_downgraded_by_exploratory_purpose(self):
        """10 donors, powered, controlled: ROBUST stays ROBUST for exploration."""
        evidence = assess_evidence(satisfied_factors=STRONG_FACTORS)
        assert evidence.evidence_maturity == "ROBUST"
        suff = evaluate_sufficiency(
            evidence=evidence,
            purpose_context=PurposeContext(purpose=ResearchPurpose.EXPLORATORY),
        )
        assert suff.verdict == SufficiencyVerdict.WARRANTED

    def test_weak_evidence_not_elevated_by_clinical_purpose(self):
        """Declaring a clinical purpose grants no evidence at all."""
        evidence = assess_evidence(satisfied_factors=[])
        assert evidence.evidence_maturity == "PRELIMINARY"
        suff = evaluate_sufficiency(
            evidence=evidence,
            purpose_context=PurposeContext(purpose=ResearchPurpose.CLINICAL),
        )
        assert suff.verdict == SufficiencyVerdict.NOT_SUFFICIENT_FOR_INTENDED_USE
        assert any("evidence_maturity" in g for g in suff.gaps)
        assert any("external_validation" in g for g in suff.gaps)
        assert any("regulatory_context" in g for g in suff.gaps)

    def test_violation_caps_evidence_despite_factors(self):
        """An active violation caps evidence at FRAGILE, factors notwithstanding."""
        evidence = assess_evidence(
            satisfied_factors=STRONG_FACTORS + ["replication", "external_validation"],
            warrant_triggers=[_Trigger("missing_replicates")],
        )
        assert evidence.evidence_maturity == "FRAGILE"
        assert "missing_replicates" in evidence.caps_applied

    def test_replicated_requires_replication_and_external_validation(self):
        evidence = assess_evidence(
            satisfied_factors=STRONG_FACTORS + ["replication", "external_validation"],
        )
        assert evidence.evidence_maturity == "REPLICATED"

    def test_robust_requires_integrity_factors(self):
        """ROBUST and above demand backend fidelity + provenance."""
        evidence = assess_evidence(
            satisfied_factors=["sample_design", "confound_controls", "sensitivity_analysis"],
        )
        assert evidence.evidence_maturity != "ROBUST"

    def test_undeclared_factors_default_to_preliminary(self):
        """A clean single run without declared factors is PRELIMINARY at best."""
        evidence = assess_evidence(satisfied_factors=[])
        assert evidence.evidence_maturity == "PRELIMINARY"


# ── The user's two canonical examples ─────────────────────────────────────────


class TestCanonicalExamples:
    def test_robust_population_effect_confirmatory_is_warranted(self):
        """Evidence ROBUST + population_effect claim + confirmatory -> WARRANTED."""
        evidence = assess_evidence(satisfied_factors=STRONG_FACTORS)
        assert evidence.evidence_maturity == "ROBUST"
        suff = evaluate_sufficiency(
            evidence=evidence,
            purpose_context=PurposeContext(purpose=ResearchPurpose.CONFIRMATORY),
            claim_context=ClaimContext(claim_class=ClaimClass.POPULATION_EFFECT),
        )
        assert suff.verdict == SufficiencyVerdict.WARRANTED
        assert suff.requirement.required_maturity == ConclusionMaturity.ROBUST

    def test_supported_evidence_is_not_sufficient_for_clinical_use(self):
        """Evidence SUPPORTED + clinical use -> NOT_SUFFICIENT_FOR_INTENDED_USE."""
        evidence = assess_evidence(satisfied_factors=["sample_design", "replication"])
        assert evidence.evidence_maturity == "SUPPORTED"
        suff = evaluate_sufficiency(
            evidence=evidence,
            purpose_context=PurposeContext(purpose=ResearchPurpose.CLINICAL),
        )
        assert suff.verdict == SufficiencyVerdict.NOT_SUFFICIENT_FOR_INTENDED_USE
        assert any("PRELIMINARY" not in g and "evidence_maturity" in g for g in suff.gaps)

    def test_unspecified_purpose_is_never_sufficient(self):
        """No declared intended use -> sufficiency undecided for any use."""
        evidence = assess_evidence(satisfied_factors=STRONG_FACTORS)
        suff = evaluate_sufficiency(evidence=evidence, purpose_context=PurposeContext())
        assert suff.verdict == SufficiencyVerdict.NOT_SUFFICIENT_FOR_INTENDED_USE
        assert "intended_use_undeclared" in suff.gaps

    def test_override_acknowledgement_downgrades_not_mutates(self):
        """A documented ack yields WARRANTED_WITH_LIMITS; the bar is unchanged."""
        evidence = assess_evidence(satisfied_factors=[])
        suff = evaluate_sufficiency(
            evidence=evidence,
            purpose_context=PurposeContext(purpose=ResearchPurpose.CONFIRMATORY),
            override_acknowledged=True,
        )
        assert suff.verdict == SufficiencyVerdict.WARRANTED_WITH_LIMITS
        assert suff.requirement.required_maturity == ConclusionMaturity.ROBUST


# ── Requirement composition ───────────────────────────────────────────────────


class TestUseRequirementComposition:
    def test_requirement_values_match_legacy_numbers(self):
        """The old 'ceiling' numbers are exactly the new requirement numbers."""
        assert PURPOSE_EVIDENCE_REQUIREMENT[ResearchPurpose.EXPLORATORY] == ConclusionMaturity.PRELIMINARY
        assert PURPOSE_EVIDENCE_REQUIREMENT[ResearchPurpose.CONFIRMATORY] == ConclusionMaturity.ROBUST
        assert PURPOSE_EVIDENCE_REQUIREMENT[ResearchPurpose.CLINICAL] == ConclusionMaturity.REPLICATED

    def test_claim_class_raises_the_bar(self):
        """A causal claim under an exploratory purpose still needs identification."""
        req = use_requirement_for(ResearchPurpose.EXPLORATORY, ClaimClass.CAUSAL)
        assert "causal_identification" in req.extra_requirements
        assert req.required_maturity == ConclusionMaturity.SUPPORTED

    def test_clinical_actionability_is_the_highest_claim_bar(self):
        req = use_requirement_for(ResearchPurpose.EXPLORATORY, ClaimClass.CLINICAL_ACTIONABILITY)
        assert req.required_maturity == ConclusionMaturity.REPLICATED
        assert "external_validation" in req.extra_requirements
        assert "regulatory_context" in req.extra_requirements

    def test_documented_extras_can_satisfy_conditions(self):
        """A documented causal identification strategy closes that gap."""
        evidence = assess_evidence(satisfied_factors=["sample_design", "replication"])
        suff = evaluate_sufficiency(
            evidence=evidence,
            purpose_context=PurposeContext(purpose=ResearchPurpose.CAUSAL),
            claim_context=ClaimContext(claim_class=ClaimClass.CAUSAL),
            documented_extras=["causal_identification"],
        )
        assert suff.verdict == SufficiencyVerdict.WARRANTED

    def test_all_claim_classes_have_requirements(self):
        assert len(CLAIM_REQUIREMENTS) == len(ClaimClass)
