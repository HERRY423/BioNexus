"""
Tests for Patient Safety Invariants and Documented Extras Verification (S1 and S2).

Verifies:
- S1: Clinical and Unspecified purpose NEVER permit override on the execution or sufficiency path (P3/P4).
- S2: Free-text documented_extras cannot satisfy non-documentable/unverified conditions like regulatory_context (P5).
"""

from bionexus.capabilities import ALL_CAPABILITIES
from bionexus.evidence_model import (
    ClaimClass,
    ClaimContext,
    SufficiencyVerdict,
)
from bionexus.intent_router import route_scientific_intent
from bionexus.research_purpose import (
    PurposeContext,
    ResearchPurpose,
)


class TestSafetyInvariantsS1AndS2:
    def test_e2e_clinical_purpose_override_bypass_blocked(self):
        """End-to-end reproduction of S1:

        Zero evidence factors, PRELIMINARY evidence, CLINICAL purpose,
        CLINICAL_ACTIONABILITY claim + override_active=True / override_justification.
        Must return NOT_SUFFICIENT_FOR_INTENDED_USE, NOT WARRANTED_WITH_LIMITS.
        """
        cap = ALL_CAPABILITIES["scrna.pseudobulk_de"]
        pctx = PurposeContext(
            purpose=ResearchPurpose.CLINICAL,
            explicitly_declared=True,
            override_active=True,
            override_justification="Attempting to override clinical purpose",
        )
        # PurposeContext __post_init__ must force override_active to False
        assert pctx.override_active is False

        claim = ClaimContext(claim_class=ClaimClass.CLINICAL_ACTIONABILITY)
        result = cap.evaluate_viability_with_purpose(
            input_metadata={
                "is_integer_like": True,
                "is_normalized": False,
                "min_replicates_per_condition": 3,
                "conditions": 2,
            },
            purpose_context=pctx,
            claim_context=claim,
        )

        assert result.sufficiency["verdict"] == SufficiencyVerdict.NOT_SUFFICIENT_FOR_INTENDED_USE.value
        assert result.sufficiency["verdict"] != SufficiencyVerdict.WARRANTED_WITH_LIMITS.value
        assert any("evidence_maturity" in g for g in result.sufficiency["gaps"])
        assert any("regulatory_context" in g for g in result.sufficiency["gaps"])

    def test_e2e_unspecified_purpose_override_bypass_blocked_p3_p4(self):
        """Probes P3/P4: Unspecified purpose with override_active=True must fail closed."""
        cap = ALL_CAPABILITIES["scrna.pseudobulk_de"]
        pctx = PurposeContext(
            purpose=ResearchPurpose.UNSPECIFIED,
            explicitly_declared=False,
            override_active=True,
            override_justification="Attempting override on unspecified purpose",
        )
        assert pctx.override_active is False

        result = cap.evaluate_viability_with_purpose(
            input_metadata={
                "is_integer_like": True,
                "is_normalized": False,
                "min_replicates_per_condition": 3,
                "conditions": 2,
            },
            purpose_context=pctx,
        )

        assert result.sufficiency["verdict"] == SufficiencyVerdict.NOT_SUFFICIENT_FOR_INTENDED_USE.value
        assert "intended_use_undeclared" in result.sufficiency["gaps"]

    def test_e2e_p5_replicated_evidence_with_bare_regulatory_context_string_blocked(self):
        """Probe P5:

        REPLICATED evidence + documented_extras=["regulatory_context"] must NOT
        produce a WARRANTED clinical actionability verdict without verified regulatory factors.
        """
        cap = ALL_CAPABILITIES["scrna.pseudobulk_de"]
        pctx = PurposeContext(
            purpose=ResearchPurpose.CLINICAL,
            explicitly_declared=True,
        )
        claim = ClaimContext(claim_class=ClaimClass.CLINICAL_ACTIONABILITY)

        # Supply REPLICATED factors (replication, external_validation, sample_design, etc.)
        # but do NOT supply verified regulatory_certification / regulatory_context factor
        replicated_factors = [
            "sample_design",
            "replication",
            "external_validation",
            "confound_controls",
            "sensitivity_analysis",
            "backend_fidelity",
            "provenance",
        ]

        result = cap.evaluate_viability_with_purpose(
            input_metadata={
                "is_integer_like": True,
                "is_normalized": False,
                "min_replicates_per_condition": 3,
                "conditions": 2,
            },
            purpose_context=pctx,
            claim_context=claim,
            evidence_factors=replicated_factors,
            documented_extras=["regulatory_context"],
        )

        assert result.evidence_assessment["evidence_maturity"] == "REPLICATED"
        assert result.sufficiency["verdict"] == SufficiencyVerdict.NOT_SUFFICIENT_FOR_INTENDED_USE.value
        assert "missing_required_condition:regulatory_context" in result.sufficiency["gaps"]

    def test_e2e_verified_regulatory_certification_factor_yields_warranted(self):
        """When genuine regulatory_certification factor is supplied with REPLICATED evidence,

        clinical actionability is WARRANTED.
        """
        cap = ALL_CAPABILITIES["scrna.pseudobulk_de"]
        pctx = PurposeContext(
            purpose=ResearchPurpose.CLINICAL,
            explicitly_declared=True,
        )
        claim = ClaimContext(claim_class=ClaimClass.CLINICAL_ACTIONABILITY)

        verified_factors = [
            "sample_design",
            "replication",
            "external_validation",
            "confound_controls",
            "sensitivity_analysis",
            "backend_fidelity",
            "provenance",
            "regulatory_certification",
        ]

        result = cap.evaluate_viability_with_purpose(
            input_metadata={
                "is_integer_like": True,
                "is_normalized": False,
                "min_replicates_per_condition": 3,
                "conditions": 2,
            },
            purpose_context=pctx,
            claim_context=claim,
            evidence_factors=verified_factors,
        )

        assert result.evidence_assessment["evidence_maturity"] == "REPLICATED"
        assert result.sufficiency["verdict"] == SufficiencyVerdict.WARRANTED.value
        assert not result.sufficiency["gaps"]

    def test_intent_router_clinical_override_justification_cannot_activate_override(self):
        """intent_router must not activate override_active for clinical purpose."""
        decision = route_scientific_intent(
            "clinical diagnostic patient treatment decision",
            research_purpose="clinical",
            override_justification="Doctor wants to force this analysis",
        )
        assert decision.purpose_context.purpose == ResearchPurpose.CLINICAL
        assert decision.purpose_context.override_active is False

    def test_intent_router_unspecified_override_justification_cannot_activate_override(self):
        """intent_router must not activate override_active for unspecified purpose."""
        decision = route_scientific_intent(
            "Run something on my expression data",
            override_justification="Trying to force unspecified analysis",
        )
        assert decision.purpose_context.purpose == ResearchPurpose.UNSPECIFIED
        assert decision.purpose_context.override_active is False

    def test_intent_router_exploratory_override_justification_activates_override(self):
        """intent_router properly activates override_active for exploratory purpose."""
        decision = route_scientific_intent(
            "explore cluster markers in single cell",
            research_purpose="exploratory",
            override_justification="Pilot study with single replicate",
        )
        assert decision.purpose_context.purpose == ResearchPurpose.EXPLORATORY
        assert decision.purpose_context.override_active is True

    def test_e2e_h1_router_wiring_elevates_evidence_from_preliminary(self):
        """H1: Router and capability wiring allows empirical evidence to reach ROBUST and clear confirmatory bar."""
        decision = route_scientific_intent(
            "pseudobulk differential expression",
            data_metadata={
                "min_replicates_per_condition": 3,
                "conditions": 2,
                "is_integer_like": True,
                "is_normalized": False,
                "confound_controls": True,
                "sensitivity_analysis": True,
            },
            research_purpose="confirmatory",
            claim_context=ClaimClass.POPULATION_EFFECT,
        )
        assert decision.status.value == "PERMITTED"
        card = decision.evidence_card_template
        assert card is not None
        assert card.details["evidence_assessment"]["evidence_maturity"] == "ROBUST"
        assert "sample_design" in card.details["evidence_assessment"]["satisfied_factors"]
        assert "replication" in card.details["evidence_assessment"]["satisfied_factors"]
        assert "confound_controls" in card.details["evidence_assessment"]["satisfied_factors"]
        assert "sensitivity_analysis" in card.details["evidence_assessment"]["satisfied_factors"]
        assert card.details["sufficiency"]["verdict"] == SufficiencyVerdict.WARRANTED.value

    def test_e2e_h2_p1_and_p2_probes_via_capability(self):
        """H2: Probes P1 (no shortcut to REPLICATED) and P2 (no shortcut to ROBUST without replication)."""
        cap = ALL_CAPABILITIES["scrna.pseudobulk_de"]
        pctx = PurposeContext(purpose=ResearchPurpose.CONFIRMATORY)

        # P1 probe: Missing sample_design, confound_controls, sensitivity_analysis
        res_p1 = cap.evaluate_viability_with_purpose(
            input_metadata={"is_integer_like": True, "is_normalized": False, "conditions": 2},
            purpose_context=pctx,
            claim_context=ClaimContext(claim_class=ClaimClass.CLINICAL_ACTIONABILITY),
            evidence_factors=["replication", "external_validation", "backend_fidelity", "provenance"],
        )
        assert res_p1.evidence_assessment["evidence_maturity"] != "REPLICATED"

        # P2 probe: Missing replication
        res_p2 = cap.evaluate_viability_with_purpose(
            input_metadata={"is_integer_like": True, "is_normalized": False, "conditions": 2},
            purpose_context=pctx,
            claim_context=ClaimContext(claim_class=ClaimClass.POPULATION_EFFECT),
            evidence_factors=["sample_design", "confound_controls", "sensitivity_analysis", "backend_fidelity", "provenance"],
        )
        assert res_p2.evidence_assessment["evidence_maturity"] != "ROBUST"
        assert res_p2.evidence_assessment["evidence_maturity"] != "SUPPORTED"
        assert res_p2.evidence_assessment["evidence_maturity"] == "PRELIMINARY"

    def test_e2e_h3_p6_probe_omitted_claim_class_fails_closed(self):
        """H3: Probe P6 - omitting claim_context must fail closed with claim_class_undeclared gap."""
        cap = ALL_CAPABILITIES["scrna.pseudobulk_de"]
        pctx = PurposeContext(purpose=ResearchPurpose.EXPLORATORY)

        # P6 probe: Omitted claim class + exploratory + zero factors
        res_omitted = cap.evaluate_viability_with_purpose(
            input_metadata={"is_integer_like": True, "is_normalized": False, "min_replicates_per_condition": 3, "conditions": 2},
            purpose_context=pctx,
            # claim_context omitted
        )
        assert res_omitted.sufficiency["verdict"] == SufficiencyVerdict.NOT_SUFFICIENT_FOR_INTENDED_USE.value
        assert "claim_class_undeclared" in res_omitted.sufficiency["gaps"]

        # Explicit claim class descriptive passes
        res_declared = cap.evaluate_viability_with_purpose(
            input_metadata={"is_integer_like": True, "is_normalized": False, "min_replicates_per_condition": 3, "conditions": 2},
            purpose_context=pctx,
            claim_context=ClaimContext(claim_class=ClaimClass.DESCRIPTIVE),
        )
        assert res_declared.sufficiency["verdict"] == SufficiencyVerdict.WARRANTED.value
        assert "claim_class_undeclared" not in res_declared.sufficiency["gaps"]

