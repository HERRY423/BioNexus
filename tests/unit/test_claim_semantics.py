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
    AssociationType,
    CausalStrength,
    ClaimRelationshipType,
    ClinicalActionability,
    DeterministicClaimParser,
    DeterministicWarrantEngine,
    Directionality,
    EvidenceProfile,
    GeneralizationScope,
    MechanismDepth,
    ScientificClaimIR,
    WarrantTierStatus,
)
from bionexus.claim_checker import audit_claim_semantics, audit_prohibited_claims
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
