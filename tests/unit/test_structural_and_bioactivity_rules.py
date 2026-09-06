"""
Tests for Macromolecular Structural Confidence and Small-Molecule Bioactivity Rules.
"""

from pathlib import Path

from bionexus.bctk.dimensions.cross_host import evaluate_cross_host
from bionexus.bctk.spec import DimensionStatus
from bionexus.claim_semantics import (
    ClaimRelationshipType,
    ConclusionMaturity,
    DeterministicWarrantEngine,
    EvidenceProfile,
    ScientificClaimIR,
    ScientificEntity,
)
from bionexus.statistical_rules import (
    BioactivityRegime,
    StructureConfidenceRegime,
    assess_bioactivity_affinity,
    assess_protein_structure_confidence,
)


class TestStructuralConfidenceRules:
    """Test AlphaFold/ESMFold pLDDT and PAE epistemic rules."""

    def test_plddt_disordered_fails_closed(self):
        res = assess_protein_structure_confidence(mean_plddt=42.0, min_plddt=28.0)
        assert res.regime == StructureConfidenceRegime.VERY_LOW_DISORDERED
        assert res.sufficient_for_rigid_pocket is False
        assert any("intrinsic disorder" in w.lower() for w in res.warnings)
        assert any("abstain" in r.lower() for r in res.remedies)

    def test_plddt_low_confidence_boundary(self):
        res = assess_protein_structure_confidence(mean_plddt=62.5, min_plddt=54.0)
        assert res.regime == StructureConfidenceRegime.LOW
        assert res.sufficient_for_rigid_pocket is False
        assert any("exploratory" in w.lower() for w in res.warnings)

    def test_plddt_high_confidence(self):
        res = assess_protein_structure_confidence(mean_plddt=94.0, min_plddt=88.0)
        assert res.regime == StructureConfidenceRegime.VERY_HIGH
        assert res.sufficient_for_rigid_pocket is True
        assert len(res.warnings) == 0

    def test_interdomain_pae_warning(self):
        res = assess_protein_structure_confidence(mean_plddt=82.0, interdomain_pae=22.4)
        assert res.regime == StructureConfidenceRegime.CONFIDENT
        assert any("predicted aligned error" in w.lower() or "pae" in w.lower() for w in res.warnings)


class TestBioactivityRules:
    """Test small-molecule affinity and potency tiering rules."""

    def test_potent_nanomolar_lead(self):
        res = assess_bioactivity_affinity(value_nm=45.0, metric_name="IC50", has_dose_response=True)
        assert res.regime == BioactivityRegime.POTENT
        assert res.sufficient_for_lead_claim is True
        assert len(res.warnings) == 0

    def test_micromolar_inactive_refusal(self):
        res = assess_bioactivity_affinity(value_nm=25000.0, metric_name="Kd")
        assert res.regime == BioactivityRegime.INACTIVE_OR_NONSPECIFIC
        assert res.sufficient_for_lead_claim is False
        assert any("exceeds 10,000 nm" in w.lower() for w in res.warnings)

    def test_single_dose_screening_caveat(self):
        res = assess_bioactivity_affinity(value_nm=80.0, has_dose_response=False)
        assert res.regime == BioactivityRegime.POTENT
        assert res.sufficient_for_lead_claim is False
        assert any("single-concentration" in w.lower() for w in res.warnings)


class TestWarrantEngineSemanticIntegration:
    """Test DeterministicWarrantEngine handling of structure and bioactivity."""

    def test_structural_claim_disordered_refusal(self):
        claim = ScientificClaimIR(
            claim_id="claim-str-001",
            source_text="Target pocket forms a rigid hydrophobic binding site.",
            subject_entity=ScientificEntity(name="ProteinA", entity_type="protein"),
            relationship=ClaimRelationshipType.STRUCTURAL_CONFORMATION,
        )
        ev = EvidenceProfile(
            observational_data=True,
            plddt_score=36.5,
        )
        res = DeterministicWarrantEngine.evaluate(claim, ev)
        assert res.is_fully_warranted is False
        assert res.evidence_ceiling == ConclusionMaturity.ABSTAIN.value
        assert any("INTRINSIC_DISORDER_VIOLATION" in v for v in res.rule_violations)

    def test_bioactivity_weak_affinity_refusal(self):
        claim = ScientificClaimIR(
            claim_id="claim-bio-001",
            source_text="Compound BNS-999 is a potent inhibitor of EGFR.",
            subject_entity=ScientificEntity(name="BNS-999", entity_type="small_molecule"),
            relationship=ClaimRelationshipType.BIOACTIVE_BINDING,
        )
        ev = EvidenceProfile(
            observational_data=True,
            bioactivity_nm=35000.0,
        )
        res = DeterministicWarrantEngine.evaluate(claim, ev)
        assert res.is_fully_warranted is False
        assert res.evidence_ceiling == ConclusionMaturity.ABSTAIN.value
        assert any("NONSPECIFIC_BINDING_OVERCLAIM" in v for v in res.rule_violations)


class TestBCTKCrossHostEvaluator:
    """Test BCTK Cross-Host Consistency evaluator with generated comparison report."""

    def test_evaluate_cross_host_headless_comparison_is_not_assessed(self):
        from bionexus.bctk.targets import TargetDescriptor, TargetType
        target = TargetDescriptor(name="bionexus", target_type=TargetType.PLUGIN, root_path=Path("."))
        result = evaluate_cross_host(target)
        assert result.status == DimensionStatus.NOT_ASSESSED
        assert result.score_percentage == 0.0
        rule_ids = {r.rule_id for r in result.rule_evaluations}
        assert rule_ids == {"BCTK-HST-001", "BCTK-HST-002", "BCTK-HST-003"}
