"""
Unit tests for BioNexus Scientific Claim Semantics & Deterministic Warrant Engine (BNS-017).

Validates:
1. Deterministic extraction of natural-language claims into typed ScientificClaimIR.
2. Multi-tier epistemic evaluation (association, mechanistic, causal, population, clinical, cell identity).
3. The exact flagship scenario: "CXCL13+ CD8 T cells drive macrophage polarization in NSCLC"
   with spatial colocalization + ligand-receptor inference only -> association WARRANTED,
   mechanistic NOT WARRANTED, causal NOT WARRANTED.
4. Epistemic honesty of negated claims ("cannot prove", "does not cause").
5. Cell-type identity qualification invariants.
6. CLI commands: 'parse-claim' and 'warrant-claim'.
"""

import json
import sys
from pathlib import Path

# Ensure src is on sys.path
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SRC = _REPO_ROOT / "src"
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from bionexus.claim_semantics import (
    CausalStrength,
    ClaimRelationshipType,
    ClinicalActionability,
    DeterministicClaimParser,
    DeterministicWarrantEngine,
    Directionality,
    EvidenceProfile,
    GeneralizationScope,
    MechanismDepth,
    WarrantTierStatus,
    enforce_governing_status,
)
from bionexus.cli import main as cli_main
from bionexus.contracts import ConclusionMaturity
from bionexus.evidence_model import ClaimClass
from bionexus.ledger import ClaimLedger, ClaimRecord, EvidenceRef


def test_flagship_claim_parsing():
    """Test deterministic parsing of the flagship causal-mechanistic claim."""
    claim_text = "CXCL13+ CD8 T cells drive macrophage polarization in NSCLC."
    ir = DeterministicClaimParser.parse(claim_text, claim_id="CLAIM-FLAGSHIP-001")

    assert ir.claim_id == "CLAIM-FLAGSHIP-001"
    assert ir.source_text == claim_text
    assert "CXCL13+ CD8 T cells" in ir.subject_entity.name
    assert "CXCL13+" in ir.subject_entity.features
    assert "CD8" in ir.subject_entity.features or "CD8+" in ir.subject_entity.features
    assert ir.object_entity is not None
    assert "macrophage polarization" in ir.object_entity.name
    assert ir.direction == Directionality.DIRECTED_FORWARD
    assert ir.relationship in (ClaimRelationshipType.PHENOTYPE_DRIVER, ClaimRelationshipType.CELL_CELL_INTERACTION)
    assert ir.population_scope == "NSCLC"
    assert ir.generalization_scope == GeneralizationScope.POPULATION_GENERAL
    assert ir.causal_strength == CausalStrength.COUNTERFACTUAL_CAUSAL
    assert ir.mechanism_depth == MechanismDepth.SIGNALING_CASCADE
    assert ir.claim_class == ClaimClass.MECHANISTIC
    assert ir.negated is False


def test_flagship_warrant_engine_evaluation():
    """
    Test the normative scenario:
    Claim: CXCL13+ CD8 T cells drive macrophage polarization in NSCLC.
    Evidence available:
      - spatial colocalization: True
      - ligand-receptor inference: True
      - perturbation: False
      - temporal evidence: False
      - biological replicates: 1 (no pseudobulk)
    Expected Verdict:
      - association claim:       WARRANTED
      - mechanistic claim:       NOT WARRANTED (Gap: perturbation / temporal kinetics)
      - causal claim:            NOT WARRANTED (Gap: perturbation / causal identification)
      - population claim:        NOT WARRANTED (Gap: n>=3 biological replicates)
    """
    claim_text = "CXCL13+ CD8 T cells drive macrophage polarization in NSCLC."
    ir = DeterministicClaimParser.parse(claim_text)

    # Observational evidence profile (spatial + LR only)
    obs_profile = EvidenceProfile(
        spatial_colocalization=True,
        ligand_receptor_inference=True,
        perturbation=False,
        temporal_evidence=False,
        biological_replicates_count=1,
        pseudobulk_aggregated=False,
    )

    verdict = DeterministicWarrantEngine.evaluate(ir, obs_profile)

    assert verdict.is_fully_warranted is False
    assert verdict.requested_claim_class == ClaimClass.MECHANISTIC.value
    assert verdict.warranted_claim_class in (ClaimClass.SPATIAL_DEPENDENCY.value, ClaimClass.ASSOCIATION.value)

    # Tier checks
    assert verdict.tier_verdicts["association_claim"].status == WarrantTierStatus.WARRANTED
    assert verdict.tier_verdicts["association_claim"].is_warranted is True

    assert verdict.tier_verdicts["mechanistic_claim"].status == WarrantTierStatus.NOT_WARRANTED
    assert verdict.tier_verdicts["mechanistic_claim"].is_warranted is False
    assert "perturbation_functional_assay" in verdict.tier_verdicts["mechanistic_claim"].missing_evidence

    assert verdict.tier_verdicts["causal_claim"].status == WarrantTierStatus.NOT_WARRANTED
    assert verdict.tier_verdicts["causal_claim"].is_warranted is False

    assert verdict.tier_verdicts["population_claim"].status == WarrantTierStatus.NOT_WARRANTED
    assert verdict.tier_verdicts["population_claim"].is_warranted is False

    # Gap checks
    assert "missing_functional_perturbation" in verdict.evidence_gaps
    assert "missing_causal_identification" in verdict.evidence_gaps
    assert "missing_biological_replicates" in verdict.evidence_gaps
    assert len(verdict.remedies) > 0


def test_warrant_upgrade_with_functional_perturbation():
    """Verify that adding functional perturbation and replicates warrants the claim."""
    claim_text = "CXCL13+ CD8 T cells drive macrophage polarization in NSCLC."
    ir = DeterministicClaimParser.parse(claim_text)

    # Complete empirical evidence profile
    full_profile = EvidenceProfile(
        spatial_colocalization=True,
        ligand_receptor_inference=True,
        perturbation=True,  # CRISPR knockout functional proof
        temporal_evidence=True,  # Time series kinetics
        biological_replicates_count=5,
        pseudobulk_aggregated=True,
        independent_validation=True,
    )

    verdict = DeterministicWarrantEngine.evaluate(ir, full_profile)

    assert verdict.is_fully_warranted is True
    assert verdict.warranted_claim_class == ClaimClass.MECHANISTIC.value
    assert verdict.evidence_ceiling == ConclusionMaturity.REPLICATED.value
    assert verdict.tier_verdicts["association_claim"].is_warranted is True
    assert verdict.tier_verdicts["mechanistic_claim"].is_warranted is True
    assert verdict.tier_verdicts["causal_claim"].is_warranted is True
    assert verdict.tier_verdicts["population_claim"].is_warranted is True
    assert len(verdict.evidence_gaps) == 0


def test_claim_syntax_is_not_evidence_and_unrequested_tiers_are_not_warranted():
    """Association syntax must not mint evidence or imply higher-tier warrant."""
    ir = DeterministicClaimParser.parse("TP53 is associated with DNA damage response.")

    verdict = DeterministicWarrantEngine.evaluate(ir, EvidenceProfile())

    assert verdict.tier_verdicts["association_claim"].status == WarrantTierStatus.NOT_WARRANTED
    assert verdict.evidence_ceiling == ConclusionMaturity.ABSTAIN.value
    assert verdict.warranted_claim_class == ClaimClass.DESCRIPTIVE.value
    for tier_name in (
        "population_claim",
        "mechanistic_claim",
        "causal_claim",
        "cell_identity_claim",
        "clinical_claim",
    ):
        tier = verdict.tier_verdicts[tier_name]
        assert tier.status == WarrantTierStatus.NOT_APPLICABLE
        assert tier.is_warranted is False


def test_negated_claim_epistemic_honesty():
    """Verify that statements expressing negative findings or limitations are warranted."""
    negated_claim = "Marker p-values from rank_genes_groups cannot prove drug treatment caused 200 DEGs."
    ir = DeterministicClaimParser.parse(negated_claim)

    assert ir.negated is True
    verdict = DeterministicWarrantEngine.evaluate(ir, EvidenceProfile())

    assert verdict.is_fully_warranted is True
    assert verdict.tier_verdicts["negated_qualification"].status == WarrantTierStatus.WARRANTED


def test_cell_identity_qualifiers():
    """Verify cell identity assertions without reference are unverified unless qualified."""
    # Unverified without qualifier
    unverified_claim = "Cluster 0 is CD4+ T cell."
    ir_unverified = DeterministicClaimParser.parse(unverified_claim)
    verdict_unverified = DeterministicWarrantEngine.evaluate(ir_unverified, EvidenceProfile())

    assert verdict_unverified.tier_verdicts["cell_identity_claim"].status == WarrantTierStatus.NOT_WARRANTED
    assert any("CELL_TYPE_HALLUCINATION" in v for v in verdict_unverified.rule_violations)

    # Qualified as candidate / exploratory
    qualified_claim = "Cluster 0 represents candidate T-cell markers (exploratory)."
    ir_qualified = DeterministicClaimParser.parse(qualified_claim)
    verdict_qualified = DeterministicWarrantEngine.evaluate(ir_qualified, EvidenceProfile())

    assert verdict_qualified.tier_verdicts["cell_identity_claim"].status == WarrantTierStatus.WARRANTED


def test_clinical_actionability_firewall():
    """Verify clinical diagnosis claims on research pipelines are prohibited."""
    clinical_claim = "This gene expression signature provides definitive clinical diagnosis for patients."
    ir = DeterministicClaimParser.parse(clinical_claim)

    assert ir.clinical_actionability == ClinicalActionability.DIAGNOSTIC_ASSERTION
    verdict = DeterministicWarrantEngine.evaluate(ir, EvidenceProfile(regulatory_certification=False))

    assert verdict.tier_verdicts["clinical_claim"].status == WarrantTierStatus.NOT_WARRANTED
    assert any("REGULATORY_COMPLIANCE_OVERCLAIM" in v for v in verdict.rule_violations)


def test_clinical_warrant_requires_ground_truth_and_independent_validation():
    """Regulatory configuration alone must never authorize a clinical claim."""
    ir = DeterministicClaimParser.parse(
        "This gene expression signature provides definitive clinical diagnosis for patients."
    )

    incomplete = DeterministicWarrantEngine.evaluate(
        ir,
        EvidenceProfile(
            regulatory_certification=True,
            clinical_ground_truth=False,
            independent_validation=False,
        ),
    )

    tier = incomplete.tier_verdicts["clinical_claim"]
    assert tier.status == WarrantTierStatus.NOT_WARRANTED
    assert tier.is_warranted is False
    assert set(tier.missing_evidence) == {"clinical_ground_truth", "independent_validation"}
    assert "missing_clinical_ground_truth" in incomplete.evidence_gaps
    assert "missing_independent_validation" in incomplete.evidence_gaps

    complete = DeterministicWarrantEngine.evaluate(
        ir,
        EvidenceProfile(
            regulatory_certification=True,
            clinical_ground_truth=True,
            independent_validation=True,
        ),
    )
    assert complete.tier_verdicts["clinical_claim"].status == WarrantTierStatus.WARRANTED


def test_temporal_evidence_cannot_replace_mechanistic_perturbation():
    """A temporal series may support but cannot independently warrant mechanism."""
    ir = DeterministicClaimParser.parse("CXCL13+ CD8 T cells drive macrophage polarization in NSCLC.")
    verdict = DeterministicWarrantEngine.evaluate(
        ir,
        EvidenceProfile(
            observational_data=True,
            temporal_evidence=True,
            perturbation=False,
            biological_replicates_count=4,
            pseudobulk_aggregated=True,
        ),
    )

    tier = verdict.tier_verdicts["mechanistic_claim"]
    assert tier.status == WarrantTierStatus.NOT_WARRANTED
    assert "perturbation_functional_assay" in tier.missing_evidence
    assert "temporal_kinetics" not in tier.missing_evidence


def test_non_authorizing_governing_status_removes_positive_tier_authority():
    """Tier-only consumers must not see WARRANTED under NEEDS_DATA/ABSTAIN."""
    ir = DeterministicClaimParser.parse("TP53 is associated with DNA damage response.")
    verdict = DeterministicWarrantEngine.evaluate(ir, EvidenceProfile(observational_data=True))

    enforce_governing_status(verdict, "NEEDS_DATA")

    assert verdict.governing_status == "NEEDS_DATA"
    assert verdict.is_fully_warranted is False
    assert verdict.evidence_ceiling == ConclusionMaturity.ABSTAIN.value
    assert verdict.tier_verdicts["association_claim"].status == WarrantTierStatus.NOT_ASSESSED
    assert verdict.tier_verdicts["association_claim"].is_warranted is False
    assert all(tier.status != WarrantTierStatus.WARRANTED for tier in verdict.tier_verdicts.values())


def test_ledger_semantic_claim_resolution():
    """Verify ClaimLedger evaluates structured claims via DeterministicWarrantEngine."""
    ledger = ClaimLedger()

    # Add evidence refs
    ev_spatial = EvidenceRef(ref_id="SPATIAL-01", kind="spatial_colocalization", maturity=ConclusionMaturity.SUPPORTED.value)
    ev_lr = EvidenceRef(ref_id="LR-01", kind="ligand_receptor", maturity=ConclusionMaturity.SUPPORTED.value)
    ledger.add_evidence(ev_spatial)
    ledger.add_evidence(ev_lr)

    # Add claim with spatial and LR evidence only
    claim = ClaimRecord(
        claim_id="CLAIM-001",
        statement="CXCL13+ CD8 T cells drive macrophage polarization in NSCLC.",
        supported_by=["SPATIAL-01", "LR-01"],
    )
    ledger.add_claim(claim, resolve=True)

    # Check that warrant evaluation was computed
    assert claim.warrant_evaluation is not None
    assert claim.structured_claim is not None
    assert claim.warrant_evaluation["is_fully_warranted"] is False
    assert "missing_functional_perturbation" in claim.warrant_evaluation["evidence_gaps"]


def test_cli_parse_claim_and_warrant_claim(capsys):
    """Verify CLI subcommands parse-claim and warrant-claim."""
    # Test parse-claim
    rc = cli_main(["parse-claim", "CXCL13+ CD8 T cells drive macrophage polarization in NSCLC."])
    assert rc == 0
    captured = capsys.readouterr()
    assert "Scientific Claim IR" in captured.out
    assert "CXCL13+ CD8 T cells" in captured.out
    assert "macrophage polarization" in captured.out
    assert "directed_forward" in captured.out

    # Test parse-claim with --json
    rc_json = cli_main(["parse-claim", "CXCL13+ CD8 T cells drive macrophage polarization in NSCLC.", "--json"])
    assert rc_json == 0
    captured_json = capsys.readouterr()
    data = json.loads(captured_json.out)
    assert data["relationship"] in ("phenotype_driver", "cell_cell_interaction")
    assert data["direction"] == "directed_forward"

    # Test warrant-claim without perturbation (fails / exits 1)
    rc_warrant_fail = cli_main(["warrant-claim", "CXCL13+ CD8 T cells drive macrophage polarization in NSCLC.", "--spatial", "--ligand-receptor"])
    assert rc_warrant_fail == 1
    captured_w = capsys.readouterr()
    assert "NOT FULLY WARRANTED" in captured_w.out
    assert "missing_functional_perturbation" in captured_w.out

    # Test warrant-claim with perturbation and replicates (passes / exits 0)
    rc_warrant_pass = cli_main([
        "warrant-claim",
        "CXCL13+ CD8 T cells drive macrophage polarization in NSCLC.",
        "--spatial",
        "--ligand-receptor",
        "--perturbation",
        "--replicates", "4",
    ])
    assert rc_warrant_pass == 0
    captured_pass = capsys.readouterr()
    assert "[WARRANTED]" in captured_pass.out


def test_scientific_claim_ir_json_schema():
    """Verify standard JSON-Schema generation for structured LLM decoding."""
    from bionexus.claim_semantics import get_scientific_claim_ir_schema

    schema = get_scientific_claim_ir_schema()
    assert schema["type"] == "object"
    assert "properties" in schema
    assert "claim_id" in schema["properties"]
    assert "relationship" in schema["properties"]
    assert "causal_strength" in schema["properties"]
    assert "claim_class" in schema["properties"]
    assert "required" in schema
    assert "relationship" in schema["required"]
    assert "direction" in schema["required"]


def test_compound_claim_decomposition():
    """Verify decomposition of complex compound scientific statements into atomic IRs."""
    from bionexus.claim_semantics import decompose_compound_claim

    compound_text = (
        "CD274 is upregulated in exhausted CD8+ T cells; "
        "which drives T-cell exhaustion and thereby promotes tumor progression."
    )
    atomic_claims = decompose_compound_claim(compound_text)
    assert len(atomic_claims) >= 2
    assert atomic_claims[0].claim_id == "atomic_claim_01"
    assert any("CD274" in c.subject_entity.name or "CD274" in c.source_text for c in atomic_claims)
    assert any("decomposed_clause" in q for q in atomic_claims[0].qualifiers)


def test_counterfactual_warrant_advice():
    """Verify counterfactual evidence remediation recommendations for scientists."""
    from bionexus.claim_semantics import (
        DeterministicClaimParser,
        DeterministicWarrantEngine,
        EvidenceProfile,
        generate_counterfactual_warrant_advice,
    )

    claim_text = "CXCL13+ CD8 T cells drive macrophage polarization in NSCLC."
    ir = DeterministicClaimParser.parse(claim_text)

    # Observational evidence facts (n=1 replicate, no perturbation)
    facts = EvidenceProfile(
        spatial_colocalization=True,
        ligand_receptor_inference=True,
        perturbation=False,
        biological_replicates_count=1,
        pseudobulk_aggregated=False,
    )
    evaluation = DeterministicWarrantEngine.evaluate(ir, facts)

    advice = generate_counterfactual_warrant_advice(ir, facts, evaluation)
    assert len(advice) >= 2

    # Check for population claim advice
    pop_advice = next((a for a in advice if a["target_tier"] == "population_claim"), None)
    assert pop_advice is not None
    assert "biological_replicates_count" in pop_advice["missing_facts"]
    assert "Squair et al. 2021" in pop_advice["actionable_remediation"]

    # Check for causal claim advice
    causal_advice = next((a for a in advice if a["target_tier"] == "causal_claim"), None)
    assert causal_advice is not None
    assert "perturbation" in causal_advice["missing_facts"]
    assert "CRISPR" in causal_advice["actionable_remediation"]


def test_chinese_scientific_claim_parsing_and_warrants():
    """Verify Chinese scientific claim parsing and warrant boundary checks without silent downgrades."""
    # T1: Population effect claim in Chinese
    t1_text = "CID4535 证明了 TNBC 患者普遍存在 IFN 边界机制。"
    t1_ir = DeterministicClaimParser.parse(
        t1_text,
        explicit_claim_class="population_effect",
        data_metadata={"claim_class": "population_effect", "eligible_sections": 1},
    )
    assert t1_ir.claim_class == ClaimClass.POPULATION_EFFECT
    assert t1_ir.generalization_scope == GeneralizationScope.POPULATION_GENERAL

    t1_profile = EvidenceProfile(
        spatial_colocalization=True,
        biological_replicates_count=1,
        pseudobulk_aggregated=False,
    )
    t1_verdict = DeterministicWarrantEngine.evaluate(t1_ir, t1_profile)
    # Population claim tier MUST be evaluated, NOT skipped as NOT_APPLICABLE
    assert t1_verdict.tier_verdicts["population_claim"].status == WarrantTierStatus.NOT_WARRANTED
    assert t1_verdict.tier_verdicts["population_claim"].is_warranted is False
    assert "biological_replicates_gte_3_with_pseudobulk" in t1_verdict.tier_verdicts["population_claim"].missing_evidence

    # C5: Causal claim in Chinese
    c5_text = "CXCL9/10–CXCR3 因果驱动 T 细胞向肿瘤边界募集。"
    c5_ir = DeterministicClaimParser.parse(
        c5_text,
        explicit_claim_class="causal",
        data_metadata={"claim_class": "causal"},
    )
    assert c5_ir.claim_class in (ClaimClass.CAUSAL, ClaimClass.MECHANISTIC)
    assert c5_ir.causal_strength in (CausalStrength.COUNTERFACTUAL_CAUSAL, CausalStrength.MECHANISTIC_DRIVER)

    c5_profile = EvidenceProfile(
        spatial_colocalization=True,
        perturbation=False,
    )
    c5_verdict = DeterministicWarrantEngine.evaluate(c5_ir, c5_profile)
    assert c5_verdict.tier_verdicts["causal_claim"].status == WarrantTierStatus.NOT_WARRANTED
    assert c5_verdict.tier_verdicts["causal_claim"].is_warranted is False

    # C6: Clinical prediction claim in Chinese
    c6_text = "该边界特征能够预测免疫治疗反应。"
    c6_ir = DeterministicClaimParser.parse(
        c6_text,
        explicit_claim_class="clinical",
        data_metadata={"claim_class": "clinical"},
    )
    assert c6_ir.claim_class == ClaimClass.CLINICAL_ACTIONABILITY
    assert c6_ir.clinical_actionability != ClinicalActionability.NONE

    c6_profile = EvidenceProfile(regulatory_certification=False, clinical_ground_truth=False)
    c6_verdict = DeterministicWarrantEngine.evaluate(c6_ir, c6_profile)
    assert c6_verdict.tier_verdicts["clinical_claim"].status == WarrantTierStatus.NOT_WARRANTED
    assert c6_verdict.tier_verdicts["clinical_claim"].is_warranted is False


def test_explicit_claim_class_conflict_preservation():
    """Verify that explicit claim class is preserved and conflicts are recorded instead of silently defaulting."""
    # Text looks descriptive or correlational, but explicit metadata requests population_effect
    ir = DeterministicClaimParser.parse(
        "Observation in slice 1",
        explicit_claim_class="population_effect",
    )
    assert ir.claim_class == ClaimClass.POPULATION_EFFECT
    assert ir.metadata.get("has_claim_conflict") is True
    assert "differs from text-inferred" in ir.metadata.get("conflict_details", "")

    verdict = DeterministicWarrantEngine.evaluate(ir, EvidenceProfile())
    assert verdict.has_claim_conflict is True
    assert verdict.conflict_details is not None
    assert verdict.requested_claim_class == ClaimClass.POPULATION_EFFECT.value

