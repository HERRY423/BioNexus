"""
Tests for the Evidence Model: Evidence Strength ≠ Intended Use Requirement.

Encodes the theoretical invariants of the third warrant-engine decoupling:

- Purpose decides the evidence REQUIREMENT, never the evidence VALUE.
- Strong evidence stays strong under an exploratory purpose.
- Weak evidence cannot be elevated by a clinical purpose.
- Verdicts compare evidence against the composed (purpose + claim) bar.
"""

from hypothesis import given
from hypothesis import strategies as st

from bionexus.contracts import ConclusionMaturity
from bionexus.evidence_model import (
    CLAIM_REQUIREMENTS,
    FACTOR_SUPPORT_LADDER,
    INTEGRITY_FACTORS,
    ClaimClass,
    ClaimContext,
    EvidenceFactor,
    SufficiencyVerdict,
    assess_evidence,
    evaluate_sufficiency,
    extract_evidence_factors,
    use_requirement_for,
)
from bionexus.research_purpose import (
    PURPOSE_EVIDENCE_REQUIREMENT,
    PurposeContext,
    ResearchPurpose,
)

STRONG_FACTORS = [
    "sample_design",
    "replication",
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
            claim_context=ClaimContext(claim_class=ClaimClass.DESCRIPTIVE),
        )
        assert suff.verdict == SufficiencyVerdict.WARRANTED

    def test_weak_evidence_not_elevated_by_clinical_purpose(self):
        """Declaring a clinical purpose grants no evidence at all."""
        evidence = assess_evidence(satisfied_factors=[])
        assert evidence.evidence_maturity == "PRELIMINARY"
        suff = evaluate_sufficiency(
            evidence=evidence,
            purpose_context=PurposeContext(purpose=ResearchPurpose.CLINICAL),
            claim_context=ClaimContext(claim_class=ClaimClass.CLINICAL_ACTIONABILITY),
        )
        assert suff.verdict == SufficiencyVerdict.NOT_SUFFICIENT_FOR_INTENDED_USE
        assert any("evidence_maturity" in g for g in suff.gaps)
        assert any("external_validation" in g for g in suff.gaps)
        assert any("regulatory_context" in g for g in suff.gaps)

    def test_violation_caps_evidence_despite_factors(self):
        """An active violation caps evidence at FRAGILE, factors notwithstanding."""
        evidence = assess_evidence(
            satisfied_factors=STRONG_FACTORS + ["external_validation"],
            warrant_triggers=[_Trigger("missing_replicates")],
        )
        assert evidence.evidence_maturity == "FRAGILE"
        assert "missing_replicates" in evidence.caps_applied

    def test_replicated_requires_replication_and_external_validation(self):
        evidence = assess_evidence(
            satisfied_factors=STRONG_FACTORS + ["external_validation"],
        )
        assert evidence.evidence_maturity == "REPLICATED"

    def test_robust_requires_integrity_factors(self):
        """ROBUST and above demand backend fidelity + provenance."""
        evidence = assess_evidence(
            satisfied_factors=["sample_design", "replication", "confound_controls", "sensitivity_analysis"],
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
            claim_context=ClaimContext(claim_class=ClaimClass.CLINICAL_ACTIONABILITY),
        )
        assert suff.verdict == SufficiencyVerdict.NOT_SUFFICIENT_FOR_INTENDED_USE
        assert any("PRELIMINARY" not in g and "evidence_maturity" in g for g in suff.gaps)

    def test_unspecified_purpose_is_never_sufficient(self):
        """No declared intended use -> sufficiency undecided for any use."""
        evidence = assess_evidence(satisfied_factors=STRONG_FACTORS)
        suff = evaluate_sufficiency(
            evidence=evidence,
            purpose_context=PurposeContext(),
            claim_context=ClaimContext(claim_class=ClaimClass.POPULATION_EFFECT),
        )
        assert suff.verdict == SufficiencyVerdict.NOT_SUFFICIENT_FOR_INTENDED_USE
        assert "intended_use_undeclared" in suff.gaps

    def test_override_acknowledgement_downgrades_not_mutates(self):
        """A documented ack yields WARRANTED_WITH_LIMITS; the bar is unchanged."""
        evidence = assess_evidence(satisfied_factors=[])
        suff = evaluate_sufficiency(
            evidence=evidence,
            purpose_context=PurposeContext(purpose=ResearchPurpose.CONFIRMATORY),
            claim_context=ClaimContext(claim_class=ClaimClass.POPULATION_EFFECT),
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
        """A causal claim under an exploratory purpose still needs identification and confound controls."""
        req = use_requirement_for(ResearchPurpose.EXPLORATORY, ClaimClass.CAUSAL)
        assert "causal_identification" in req.extra_requirements
        assert "confound_controls" in req.extra_requirements
        assert req.required_maturity == ConclusionMaturity.ROBUST

    def test_clinical_actionability_is_the_highest_claim_bar(self):
        req = use_requirement_for(ResearchPurpose.EXPLORATORY, ClaimClass.CLINICAL_ACTIONABILITY)
        assert req.required_maturity == ConclusionMaturity.REPLICATED
        assert "external_validation" in req.extra_requirements
        assert "regulatory_context" in req.extra_requirements

    def test_documented_extras_can_satisfy_conditions(self):
        """A documented causal identification strategy + verified confound controls closes that gap."""
        evidence = assess_evidence(satisfied_factors=STRONG_FACTORS)
        suff = evaluate_sufficiency(
            evidence=evidence,
            purpose_context=PurposeContext(purpose=ResearchPurpose.CAUSAL),
            claim_context=ClaimContext(claim_class=ClaimClass.CAUSAL),
            documented_extras=["causal_identification"],
        )
        assert suff.verdict == SufficiencyVerdict.WARRANTED

    def test_all_claim_classes_have_requirements(self):
        assert len(CLAIM_REQUIREMENTS) == len(ClaimClass)


# ── S1 & S2 Security & Safety Invariants Tests ───────────────────────────────


class TestPatientSafetyInvariantOverride:
    def test_clinical_purpose_override_is_denied_in_sufficiency(self):
        """Clinical purpose NEVER permits override: override_acknowledged cannot yield WARRANTED_WITH_LIMITS."""
        evidence = assess_evidence(satisfied_factors=[])
        suff = evaluate_sufficiency(
            evidence=evidence,
            purpose_context=PurposeContext(
                purpose=ResearchPurpose.CLINICAL,
                override_active=True,
                override_justification="Need to bypass clinical block",
            ),
            claim_context=ClaimContext(claim_class=ClaimClass.CLINICAL_ACTIONABILITY),
            override_acknowledged=True,
        )
        assert suff.verdict == SufficiencyVerdict.NOT_SUFFICIENT_FOR_INTENDED_USE
        assert suff.verdict != SufficiencyVerdict.WARRANTED_WITH_LIMITS
        assert any("evidence_maturity" in g for g in suff.gaps)

    def test_unspecified_purpose_override_is_denied_in_sufficiency(self):
        """Unspecified purpose NEVER permits override: must declare purpose first."""
        evidence = assess_evidence(satisfied_factors=[])
        suff = evaluate_sufficiency(
            evidence=evidence,
            purpose_context=PurposeContext(
                purpose=ResearchPurpose.UNSPECIFIED,
                override_active=True,
                override_justification="Trying to override unspecified",
            ),
            override_acknowledged=True,
        )
        assert suff.verdict == SufficiencyVerdict.NOT_SUFFICIENT_FOR_INTENDED_USE
        assert suff.verdict != SufficiencyVerdict.WARRANTED_WITH_LIMITS
        assert "intended_use_undeclared" in suff.gaps

    def test_purpose_context_post_init_enforces_overridable_purposes(self):
        """PurposeContext automatically deactivates override_active for clinical and unspecified purposes."""
        pctx_clinical = PurposeContext(purpose=ResearchPurpose.CLINICAL, override_active=True)
        assert pctx_clinical.override_active is False

        pctx_unspecified = PurposeContext(purpose=ResearchPurpose.UNSPECIFIED, override_active=True)
        assert pctx_unspecified.override_active is False

        pctx_confirmatory = PurposeContext(purpose=ResearchPurpose.CONFIRMATORY, override_active=True)
        assert pctx_confirmatory.override_active is True

        pctx_exploratory = PurposeContext(purpose=ResearchPurpose.EXPLORATORY, override_active=True)
        assert pctx_exploratory.override_active is True

        pctx_causal = PurposeContext(purpose=ResearchPurpose.CAUSAL, override_active=True)
        assert pctx_causal.override_active is True

        pctx_screening = PurposeContext(purpose=ResearchPurpose.SCREENING, override_active=True)
        assert pctx_screening.override_active is True

    def test_overridable_purposes_allow_override_in_sufficiency(self):
        """Exploratory, Screening, Confirmatory, Causal can receive WARRANTED_WITH_LIMITS on override."""
        evidence = assess_evidence(satisfied_factors=[])
        for purpose in (
            ResearchPurpose.EXPLORATORY,
            ResearchPurpose.SCREENING,
            ResearchPurpose.CONFIRMATORY,
            ResearchPurpose.CAUSAL,
        ):
            suff = evaluate_sufficiency(
                evidence=evidence,
                purpose_context=PurposeContext(purpose=purpose, override_active=True),
                claim_context=ClaimContext(claim_class=ClaimClass.POPULATION_EFFECT),
                override_acknowledged=True,
            )
            assert suff.verdict == SufficiencyVerdict.WARRANTED_WITH_LIMITS


class TestDocumentedExtrasSafety:
    def test_bare_regulatory_context_string_cannot_satisfy_clinical_requirement(self):
        """Bare string in documented_extras MUST NOT satisfy regulatory_context without verified factor."""
        evidence = assess_evidence(satisfied_factors=STRONG_FACTORS + ["external_validation"])
        assert evidence.evidence_maturity == "REPLICATED"
        suff = evaluate_sufficiency(
            evidence=evidence,
            purpose_context=PurposeContext(purpose=ResearchPurpose.CLINICAL),
            claim_context=ClaimContext(claim_class=ClaimClass.CLINICAL_ACTIONABILITY),
            documented_extras=["regulatory_context"],
        )
        assert suff.verdict == SufficiencyVerdict.NOT_SUFFICIENT_FOR_INTENDED_USE
        assert "missing_required_condition:regulatory_context" in suff.gaps

    def test_verified_regulatory_certification_factor_satisfies_regulatory_context(self):
        """Verified regulatory_certification factor satisfies regulatory_context."""
        evidence = assess_evidence(
            satisfied_factors=STRONG_FACTORS + ["external_validation", "regulatory_certification"]
        )
        assert evidence.evidence_maturity == "REPLICATED"
        suff = evaluate_sufficiency(
            evidence=evidence,
            purpose_context=PurposeContext(purpose=ResearchPurpose.CLINICAL),
            claim_context=ClaimContext(claim_class=ClaimClass.CLINICAL_ACTIONABILITY),
        )
        assert suff.verdict == SufficiencyVerdict.WARRANTED
        assert not suff.gaps

    def test_documented_extras_cannot_bypass_external_validation_factor(self):
        """Free-text documented_extras cannot bypass factor-backed conditions like external_validation."""
        evidence = assess_evidence(satisfied_factors=STRONG_FACTORS)
        # PREDICTIVE requires external_validation factor
        suff = evaluate_sufficiency(
            evidence=evidence,
            purpose_context=PurposeContext(purpose=ResearchPurpose.CONFIRMATORY),
            claim_context=ClaimContext(claim_class=ClaimClass.PREDICTIVE),
            documented_extras=["external_validation"],
        )
        assert suff.verdict == SufficiencyVerdict.NOT_SUFFICIENT_FOR_INTENDED_USE
        assert "missing_required_condition:external_validation" in suff.gaps


# ── H2 Cumulative Ladder Tests (P1 & P2 Invariant Probes) ─────────────────────


class TestFactorSupportLadderCumulative:
    def test_ladder_is_strictly_cumulative_and_nested(self):
        """Every level's required factors must be a strict superset of lower levels."""
        ladder_dict = {mat: reqs for mat, reqs in FACTOR_SUPPORT_LADDER}
        prelim = ladder_dict[ConclusionMaturity.PRELIMINARY]
        supp = ladder_dict[ConclusionMaturity.SUPPORTED]
        robust = ladder_dict[ConclusionMaturity.ROBUST]
        repl = ladder_dict[ConclusionMaturity.REPLICATED]

        assert prelim.issubset(supp)
        assert supp.issubset(robust)
        assert robust.issubset(repl)
        assert len(prelim) < len(supp) < len(robust) < len(repl)

    def test_p1_replicated_requires_all_prior_ladder_factors(self):
        """P1 probe: declaring only {replication, external_validation, backend_fidelity, provenance} CANNOT reach REPLICATED."""
        evidence = assess_evidence(
            satisfied_factors=["replication", "external_validation", "backend_fidelity", "provenance"]
        )
        # Missing sample_design, confound_controls, sensitivity_analysis
        assert evidence.evidence_maturity != "REPLICATED"

    def test_p2_robust_requires_replication(self):
        """P2 probe: declaring {sample_design, confound_controls, sensitivity_analysis, ...} WITHOUT replication CANNOT reach ROBUST."""
        evidence = assess_evidence(
            satisfied_factors=["sample_design", "confound_controls", "sensitivity_analysis", "backend_fidelity", "provenance"]
        )
        # Missing replication -> cannot even reach SUPPORTED, so cannot reach ROBUST
        assert evidence.evidence_maturity != "ROBUST"
        assert evidence.evidence_maturity != "SUPPORTED"
        assert evidence.evidence_maturity == "PRELIMINARY"

    def test_full_cumulative_factors_reach_replicated(self):
        """All cumulative factors satisfied reaches REPLICATED."""
        evidence = assess_evidence(satisfied_factors=STRONG_FACTORS + ["external_validation"])
        assert evidence.evidence_maturity == "REPLICATED"

    @given(
        st.sets(st.sampled_from(list(EvidenceFactor))),
        st.sets(st.sampled_from(list(EvidenceFactor))),
    )
    def test_hypothesis_factor_addition_monotonicity(self, s1, s2):
        """Hypothesis Property: adding evidence factors is strictly monotonic non-decreasing (A ⊆ B => rank(A) <= rank(B))."""
        rank_map = {
            "UNASSESSED": 0,
            "ABSTAIN": 1,
            "FRAGILE": 2,
            "CONFLICTED": 3,
            "PRELIMINARY": 4,
            "SUPPORTED": 5,
            "ROBUST": 6,
            "REPLICATED": 7,
        }
        set_a = s1
        set_b = s1 | s2  # set_a is strict subset or equal to set_b

        ev_a = assess_evidence(satisfied_factors=list(set_a))
        ev_b = assess_evidence(satisfied_factors=list(set_b))

        rank_a = rank_map.get(ev_a.evidence_maturity, 0)
        rank_b = rank_map.get(ev_b.evidence_maturity, 0)
        assert rank_a <= rank_b

    @given(st.sets(st.sampled_from(list(EvidenceFactor))))
    def test_hypothesis_ladder_nesting_and_soundness(self, factors):
        """Hypothesis Property: satisfying higher ladder tiers guarantees attaining at least that maturity rank."""
        ladder_dict = {mat: reqs for mat, reqs in FACTOR_SUPPORT_LADDER}
        prelim = ladder_dict[ConclusionMaturity.PRELIMINARY]
        supp = ladder_dict[ConclusionMaturity.SUPPORTED]
        robust = ladder_dict[ConclusionMaturity.ROBUST]
        repl = ladder_dict[ConclusionMaturity.REPLICATED]

        rank_map = {
            "UNASSESSED": 0,
            "ABSTAIN": 1,
            "FRAGILE": 2,
            "CONFLICTED": 3,
            "PRELIMINARY": 4,
            "SUPPORTED": 5,
            "ROBUST": 6,
            "REPLICATED": 7,
        }
        ev = assess_evidence(satisfied_factors=list(factors))
        actual_rank = rank_map[ev.evidence_maturity]

        if (repl | INTEGRITY_FACTORS).issubset(factors):
            assert actual_rank >= rank_map["REPLICATED"]
        elif (robust | INTEGRITY_FACTORS).issubset(factors):
            assert actual_rank >= rank_map["ROBUST"]
        elif supp.issubset(factors):
            assert actual_rank >= rank_map["SUPPORTED"]
        elif prelim.issubset(factors):
            assert actual_rank >= rank_map["PRELIMINARY"]

    @given(
        st.sets(st.sampled_from(list(EvidenceFactor))),
        st.lists(st.text(min_size=1, max_size=20), min_size=1, max_size=5),
    )
    def test_hypothesis_violation_monotonicity(self, factors, triggers):
        """Hypothesis Property: adding active violation triggers is monotonic non-increasing (never raises evidence maturity)."""
        rank_map = {
            "UNASSESSED": 0,
            "ABSTAIN": 1,
            "FRAGILE": 2,
            "CONFLICTED": 3,
            "PRELIMINARY": 4,
            "SUPPORTED": 5,
            "ROBUST": 6,
            "REPLICATED": 7,
        }
        ev_clean = assess_evidence(satisfied_factors=list(factors))
        ev_violated = assess_evidence(satisfied_factors=list(factors), warrant_triggers=triggers)

        rank_clean = rank_map[ev_clean.evidence_maturity]
        rank_violated = rank_map[ev_violated.evidence_maturity]
        assert rank_violated <= rank_clean


# ── H3 Claim Class Fail-Closed Symmetry Tests (P6 Probe) ──────────────────────


class TestClaimClassFailClosedSymmetry:
    def test_claim_class_unspecified_enum_exists(self):
        assert ClaimClass.UNSPECIFIED.value == "unspecified"

    def test_omitted_claim_context_fails_closed_with_gap(self):
        """P6 probe: omitting claim_context defaults to UNSPECIFIED and fails closed with claim_class_undeclared."""
        evidence = assess_evidence(satisfied_factors=STRONG_FACTORS)
        suff = evaluate_sufficiency(
            evidence=evidence,
            purpose_context=PurposeContext(purpose=ResearchPurpose.EXPLORATORY),
            # claim_context omitted
        )
        assert suff.verdict == SufficiencyVerdict.NOT_SUFFICIENT_FOR_INTENDED_USE
        assert "claim_class_undeclared" in suff.gaps

    def test_explicit_descriptive_claim_passes(self):
        """Explicitly declaring ClaimClass.DESCRIPTIVE allows exploratory descriptive sufficiency."""
        evidence = assess_evidence(satisfied_factors=STRONG_FACTORS)
        suff = evaluate_sufficiency(
            evidence=evidence,
            purpose_context=PurposeContext(purpose=ResearchPurpose.EXPLORATORY),
            claim_context=ClaimContext(claim_class=ClaimClass.DESCRIPTIVE),
        )
        assert suff.verdict == SufficiencyVerdict.WARRANTED
        assert "claim_class_undeclared" not in suff.gaps


# ── H1 Evidence Factor Extraction & Wiring Tests ──────────────────────────────


class TestEvidenceFactorExtraction:
    def test_extract_from_replicates_and_metadata(self):
        meta = {
            "min_replicates_per_condition": 3,
            "confound_controls": True,
            "sensitivity_analysis": True,
            "external_validation": True,
        }
        factors = extract_evidence_factors(meta, backend_fidelity=True, has_provenance=True)
        assert "sample_design" in factors
        assert "replication" in factors
        assert "confound_controls" in factors
        assert "sensitivity_analysis" in factors
        assert "external_validation" in factors
        assert "backend_fidelity" in factors
        assert "provenance" in factors

    def test_extract_from_explicit_factors_merging(self):
        meta = {"min_replicates_per_condition": 2}
        factors = extract_evidence_factors(
            meta,
            explicit_factors=["confound_controls", EvidenceFactor.SENSITIVITY_ANALYSIS],
            backend_fidelity=True,
            has_provenance=True,
        )
        assert "sample_design" in factors
        assert "replication" in factors
        assert "confound_controls" in factors
        assert "sensitivity_analysis" in factors


# ── M1 CONFLICTED Signal Preservation Tests (P7 Probe) ────────────────────────


class TestM1ConflictedSignalPreservation:
    def test_conflicted_base_maturity_preserved_across_violations(self):
        """P7 probe: base=CONFLICTED with active warrant triggers MUST NOT be rewritten to FRAGILE."""
        evidence = assess_evidence(
            base_maturity=ConclusionMaturity.CONFLICTED,
            warrant_triggers=[_Trigger("missing_replicates")],
        )
        assert evidence.evidence_maturity == "CONFLICTED"
        assert "missing_replicates" in evidence.caps_applied
        assert "Active violations" in evidence.rationale

    def test_conflicted_string_base_maturity_preserved(self):
        """Passing string 'CONFLICTED' preserves CONFLICTED evidence maturity."""
        evidence = assess_evidence(
            base_maturity="CONFLICTED",
            invariant_triggers=[_Trigger("unnormalized_distribution")],
        )
        assert evidence.evidence_maturity == "CONFLICTED"
        assert "unnormalized_distribution" in evidence.caps_applied


# ── M2 Causal Claim Confound Controls Tests (P11 Probe) ───────────────────────


class TestM2CausalRequirementConfoundControls:
    def test_causal_claim_missing_confound_controls_fails_sufficiency(self):
        """P11 probe: CAUSAL claim without confound_controls cannot be WARRANTED."""
        evidence = assess_evidence(
            satisfied_factors=["sample_design", "replication", "backend_fidelity", "provenance"]
        )
        suff = evaluate_sufficiency(
            evidence=evidence,
            purpose_context=PurposeContext(purpose=ResearchPurpose.CAUSAL),
            claim_context=ClaimContext(claim_class=ClaimClass.CAUSAL),
            documented_extras=["causal_identification"],
        )
        assert suff.verdict == SufficiencyVerdict.NOT_SUFFICIENT_FOR_INTENDED_USE
        assert "missing_required_condition:confound_controls" in suff.gaps

    def test_causal_claim_with_both_identification_and_confounds_warranted(self):
        """CAUSAL claim with verified confound_controls and causal_identification is WARRANTED."""
        evidence = assess_evidence(satisfied_factors=STRONG_FACTORS)
        assert evidence.evidence_maturity == "ROBUST"
        suff = evaluate_sufficiency(
            evidence=evidence,
            purpose_context=PurposeContext(purpose=ResearchPurpose.CAUSAL),
            claim_context=ClaimContext(claim_class=ClaimClass.CAUSAL),
            documented_extras=["causal_identification"],
        )
        assert suff.verdict == SufficiencyVerdict.WARRANTED
        assert not suff.gaps


# ── L1 Malformed Trigger Handling Tests (P8 Probe) ────────────────────────────


class TestL1MalformedTriggerHandling:
    def test_malformed_trigger_does_not_pseudo_cap_evidence(self):
        """P8 probe: triggers with missing condition_id or empty string must not cap evidence to FRAGILE."""
        class _MalformedTrigger:
            pass

        class _EmptyCidTrigger:
            condition_id = ""

        evidence = assess_evidence(
            satisfied_factors=STRONG_FACTORS,
            warrant_triggers=[_MalformedTrigger(), _EmptyCidTrigger(), ""],
        )
        assert evidence.evidence_maturity == "ROBUST"
        assert not evidence.caps_applied
        assert "Active violations" not in evidence.rationale


# ── L2 Safe Parsing Robustness Tests (P9 / P10 Probes) ────────────────────────


class TestL2SafeParsingRobustness:
    def test_misspelled_factor_does_not_crash(self):
        """P9 probe: misspelled or unknown factor strings are safely ignored rather than crashing."""
        evidence = assess_evidence(
            satisfied_factors=["replciation", "non_existent_factor_xyz"]
        )
        assert evidence.evidence_maturity == "PRELIMINARY"
        assert not evidence.satisfied_factors

    def test_invalid_base_maturity_does_not_crash(self):
        """P10 probe: unrecognized base_maturity string does not crash and falls back safely."""
        evidence = assess_evidence(
            base_maturity="INVALID_MATURITY_STRING_12345",
            satisfied_factors=STRONG_FACTORS,
        )
        assert evidence.evidence_maturity == "ROBUST"


# ── Fail-Closed Default UseRequirement Tests ──────────────────────────────────


class TestFailClosedDefaultUseRequirement:
    def test_unknown_purpose_fails_closed_at_replicated(self):
        """Unrecognized research purpose demands REPLICATED rather than failing open at FRAGILE."""
        req = use_requirement_for("UNKNOWN_FUTURE_PURPOSE", ClaimClass.DESCRIPTIVE)
        assert req.required_maturity == ConclusionMaturity.REPLICATED

    def test_unknown_claim_class_fails_closed_at_replicated(self):
        """Unrecognized claim class demands REPLICATED rather than failing open."""
        req = use_requirement_for(ResearchPurpose.EXPLORATORY, "UNKNOWN_FUTURE_CLAIM")
        assert req.required_maturity == ConclusionMaturity.REPLICATED



