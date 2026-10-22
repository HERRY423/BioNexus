"""
Deterministic Warrant Evaluation Engine for BioNexus Scientific Claims (BNS-017).
"""

from __future__ import annotations

from typing import Dict, List, Optional

from bionexus.claims.models import (
    AssociationType,
    CausalStrength,
    ClaimRelationshipType,
    ClinicalActionability,
    Directionality,
    EvidenceProfile,
    GeneralizationScope,
    MechanismDepth,
    ScientificClaimIR,
    WarrantEvaluationResult,
    WarrantTierStatus,
    WarrantTierVerdict,
)
from bionexus.claims.parser import DeterministicClaimParser
from bionexus.contracts import ConclusionMaturity
from bionexus.evidence_model import ClaimClass


class DeterministicWarrantEngine:
    """
    Deterministic Warrant Engine.

    Evaluates a `ScientificClaimIR` against an `EvidenceProfile` using explicit
    epistemic rules and returns a multi-tier warrant assessment.
    """

    @classmethod
    def evaluate(
        cls,
        claim: ScientificClaimIR,
        evidence: Optional[EvidenceProfile] = None,
    ) -> WarrantEvaluationResult:
        """
        Evaluate claim IR against evidence facts and compute multi-tier warrant verdicts.
        """
        ev = evidence or EvidenceProfile()
        ev.validate()
        tier_verdicts: Dict[str, WarrantTierVerdict] = {}
        evidence_gaps: List[str] = []
        remedies: List[str] = []
        rule_violations: List[str] = []

        if claim.claim_class == ClaimClass.UNSPECIFIED:
            # Unsupported explicit classes cannot inherit a descriptive pass,
            # including through the negated-statement shortcut below.
            return WarrantEvaluationResult(
                claim_id=claim.claim_id,
                is_fully_warranted=False,
                requested_claim_class=claim.claim_class.value,
                warranted_claim_class=ClaimClass.UNSPECIFIED.value,
                evidence_ceiling=ConclusionMaturity.UNASSESSED.value,
                tier_verdicts={"claim_class": WarrantTierVerdict(
                    tier_name="claim_class", status=WarrantTierStatus.NOT_WARRANTED,
                    is_warranted=False, rationale="A supported claim class must be specified.",
                    missing_evidence=["supported_claim_class"],
                )},
                evidence_gaps=["supported_claim_class"],
                remedies=["Specify a supported claim class and re-evaluate."],
                rule_violations=["UNSPECIFIED_CLAIM_CLASS"],
                epistemic_summary="Claim class is unspecified or unsupported; warrant was not established.",
                has_claim_conflict=bool(claim.metadata.get("has_claim_conflict", False)),
                conflict_details=claim.metadata.get("conflict_details"),
            )

        # Warrant Policy for Negated Claims: strictly decouple Absence of Evidence vs Evidence of Absence.
        # "没有证据支持 X" (Absence of evidence / Epistemic disclaimer) acknowledges epistemic limitations
        # and is warranted as an honest disclaimer.
        # "有证据证明不存在 X" (Evidence of absence / Negative assertion) makes a biological claim that an
        # effect does not exist, which requires functional perturbation or controlled experimental evidence
        # and must NOT automatically be considered fully warranted.
        scoped_disclaimer = (
            claim.is_epistemic_disclaimer and not claim.is_negative_assertion
            and DeterministicClaimParser.is_scoped_disclaimer(claim.source_text)
        )
        if scoped_disclaimer:
            tier_verdicts["negated_qualification"] = WarrantTierVerdict(
                tier_name="negated_qualification",
                status=WarrantTierStatus.WARRANTED,
                is_warranted=True,
                rationale="Statement explicitly disclaims unwarranted causation or states inability to prove (Absence of Evidence != Evidence of Absence).",
            )
            tier_verdicts["epistemic_disclaimer"] = WarrantTierVerdict(
                tier_name="epistemic_disclaimer",
                status=WarrantTierStatus.WARRANTED,
                is_warranted=True,
                rationale="Statement acknowledges absence of evidence / inability to prove within epistemic boundaries.",
            )
            return WarrantEvaluationResult(
                claim_id=claim.claim_id,
                is_fully_warranted=True,
                requested_claim_class=claim.claim_class.value,
                warranted_claim_class=ClaimClass.DESCRIPTIVE.value,
                evidence_ceiling=ConclusionMaturity.UNASSESSED.value,
                tier_verdicts=tier_verdicts,
                evidence_gaps=[],
                remedies=[],
                rule_violations=[],
                epistemic_summary="Scoped epistemic disclaimer is permitted as a limitation; this does not establish a negative biological result or assess the underlying evidence.",
                has_claim_conflict=bool(claim.metadata.get("has_claim_conflict", False)),
                conflict_details=claim.metadata.get("conflict_details"),
            )

        if claim.negated and not claim.is_negative_assertion:
            tier_verdicts["negation_scope"] = WarrantTierVerdict(
                tier_name="negation_scope", status=WarrantTierStatus.NOT_ASSESSED,
                is_warranted=False,
                rationale="Negation alone or a limitation in compound prose does not warrant every proposition.",
                missing_evidence=["separately_scoped_claims"],
            )
            evidence_gaps.append("separately_scoped_claims")

        if claim.is_negative_assertion:
            # This profile has no endpoint/margin/CI/test receipt for absence,
            # equivalence or non-inferiority. A perturbation boolean cannot supply it.
            tier_verdicts["evidence_of_absence"] = WarrantTierVerdict(
                tier_name="evidence_of_absence", status=WarrantTierStatus.NOT_WARRANTED,
                is_warranted=False,
                rationale="No-effect, equivalence and non-inferiority assertions require claim-specific evidence; ordinary nonsignificance or perturbation metadata is insufficient.",
                missing_evidence=["claim_specific_absence_test_and_margin_review"],
            )
            evidence_gaps.append("claim_specific_absence_test_and_margin_review")
            rule_violations.append("EVIDENCE_OF_ABSENCE_OVERCLAIM: The supplied profile cannot verify an absence, equivalence or non-inferiority conclusion.")
            remedies.append("Report the observed estimate and uncertainty or the actual nonsignificant result. Submit the prespecified endpoint, margin, interval and appropriate test for scientific review before asserting equivalence or absence of a meaningful effect.")

        # ----------------------------------------------------------------------
        # Tier 1: Observational & Associational Warrant
        # ----------------------------------------------------------------------
        assoc_warranted = (
            ev.observational_data
            or ev.spatial_colocalization
            or ev.ligand_receptor_inference
            or ev.pseudobulk_aggregated
            or ev.cross_method_concordance
            or ev.biological_replicates_count > 0
        )
        tier_verdicts["association_claim"] = WarrantTierVerdict(
            tier_name="association_claim",
            status=WarrantTierStatus.WARRANTED if assoc_warranted else WarrantTierStatus.NOT_WARRANTED,
            is_warranted=assoc_warranted,
            rationale="Correlational/associational relationship is supported by observational or spatial data.",
            missing_evidence=[] if assoc_warranted else ["observational_data"],
        )

        # ----------------------------------------------------------------------
        # Tier 2: Population Generalization Warrant
        # ----------------------------------------------------------------------
        population_requested = (
            claim.generalization_scope == GeneralizationScope.POPULATION_GENERAL
            or claim.claim_class == ClaimClass.POPULATION_EFFECT
        )
        pop_warranted = True
        pop_gaps = []
        if population_requested:
            if ev.biological_replicates_count < 3 or not ev.pseudobulk_aggregated:
                pop_warranted = False
                pop_gaps.append("biological_replicates_gte_3_with_pseudobulk")
                evidence_gaps.append("missing_biological_replicates")
                remedies.append(
                    f"Population-level inference across '{claim.population_scope or 'cohort'}' requires n>=3 biological "
                    "replicates aggregated to sample pseudobulk before statistical testing (Love et al. 2014)."
                )

        tier_verdicts["population_claim"] = WarrantTierVerdict(
            tier_name="population_claim",
            status=(
                WarrantTierStatus.NOT_APPLICABLE
                if not population_requested
                else WarrantTierStatus.WARRANTED
                if pop_warranted
                else WarrantTierStatus.NOT_WARRANTED
            ),
            is_warranted=pop_warranted if population_requested else False,
            rationale="Population-level generalization supported by biological replicates and pseudobulk."
            if population_requested and pop_warranted
            else "Population-level generalization was not requested by this claim."
            if not population_requested
            else f"Population-level generalization across '{claim.population_scope or 'cohort'}' lacks n>=3 biological replicates.",
            missing_evidence=pop_gaps,
        )

        # ----------------------------------------------------------------------
        # Tier 3: Mechanistic Warrant
        # ----------------------------------------------------------------------
        # Mechanistic claims assert molecular/cellular cascades (e.g. CD8 T cells drive macrophage polarization).
        # Temporal ordering may strengthen a mechanism, but cannot substitute for
        # an intervention when issuing a positive mechanistic warrant.
        mech_warranted = True
        mech_gaps = []
        is_mechanistic_requested = (
            claim.claim_class == ClaimClass.MECHANISTIC
            or claim.mechanism_depth in (MechanismDepth.SIGNALING_CASCADE, MechanismDepth.PERTURBATIVE_FUNCTION)
            or claim.relationship in (ClaimRelationshipType.PHENOTYPE_DRIVER, ClaimRelationshipType.CELL_CELL_INTERACTION)
            and claim.direction != Directionality.UNDIRECTED
        )

        if is_mechanistic_requested:
            # A positive mechanistic warrant requires an actual functional
            # perturbation. Temporal kinetics alone remain supportive evidence.
            has_functional_proof = ev.perturbation
            if not has_functional_proof:
                mech_warranted = False
                mech_gaps.append("perturbation_functional_assay")
                if not ev.temporal_evidence:
                    mech_gaps.append("temporal_kinetics")
                evidence_gaps.append("missing_functional_perturbation")
                remedies.append(
                    f"Mechanistic claim '{claim.subject_entity.name} -> {claim.object_entity.name if claim.object_entity else 'phenotype'}' "
                    "requires experimental perturbation (CRISPR/knockdown/rescue); longitudinal time-series kinetics "
                    "may support but cannot replace the intervention. "
                    "Spatial colocalization and ligand-receptor co-expression establish spatial association, not directional mechanism."
                )

        tier_verdicts["mechanistic_claim"] = WarrantTierVerdict(
            tier_name="mechanistic_claim",
            status=(
                WarrantTierStatus.NOT_APPLICABLE
                if not is_mechanistic_requested
                else WarrantTierStatus.WARRANTED
                if mech_warranted
                else WarrantTierStatus.NOT_WARRANTED
            ),
            is_warranted=mech_warranted if is_mechanistic_requested else False,
            rationale="Mechanistic rule conditions satisfied if declared perturbation/kinetics are valid."
            if is_mechanistic_requested and mech_warranted
            else "A mechanistic claim was not requested."
            if not is_mechanistic_requested
            else "Mechanistic claim NOT warranted: observational co-occurrence cannot prove functional mechanism.",
            missing_evidence=mech_gaps,
        )

        # ----------------------------------------------------------------------
        # Tier 4: Causal Warrant
        # ----------------------------------------------------------------------
        causal_warranted = True
        causal_gaps = []
        is_causal_requested = (
            claim.causal_strength in (CausalStrength.COUNTERFACTUAL_CAUSAL, CausalStrength.MECHANISTIC_DRIVER)
            or claim.claim_class == ClaimClass.CAUSAL
        )

        if is_causal_requested:
            # Requires: Perturbation experiment OR formal Backdoor Criterion satisfied in Causal DAG
            has_causal_proof = ev.perturbation or ev.causal_identification_status == "BACKDOOR_SATISFIED"
            if not has_causal_proof:
                causal_warranted = False
                causal_gaps.extend(["experimental_perturbation", "scm_backdoor_satisfaction"])
                evidence_gaps.append("missing_causal_identification")
                rule_violations.append(
                    "CAUSAL_OVERCLAIM: Action verb asserting counterfactual causality without perturbation or DAG backdoor closure."
                )
                remedies.append(
                    "Downgrade claim phrasing from causal assertions ('drives', 'causes', 'induces') to correlational "
                    "observations ('is associated with', 'co-localizes with'), or conduct targeted functional perturbation."
                )

        tier_verdicts["causal_claim"] = WarrantTierVerdict(
            tier_name="causal_claim",
            status=(
                WarrantTierStatus.NOT_APPLICABLE
                if not is_causal_requested
                else WarrantTierStatus.WARRANTED
                if causal_warranted
                else WarrantTierStatus.NOT_WARRANTED
            ),
            is_warranted=causal_warranted if is_causal_requested else False,
            rationale="Causal rule conditions satisfied if declared perturbation or identification assumptions hold."
            if is_causal_requested and causal_warranted
            else "A causal claim was not requested."
            if not is_causal_requested
            else "Causal claim NOT warranted: observational data cannot rule out unobserved confounding.",
            missing_evidence=causal_gaps,
        )

        # ----------------------------------------------------------------------
        # Tier 5: Cell Identity Warrant
        # ----------------------------------------------------------------------
        identity_warranted = True
        identity_gaps = []
        identity_requested = (
            claim.relationship == ClaimRelationshipType.IDENTITY_ASSERTION
            or claim.claim_class == ClaimClass.CELL_IDENTITY
        )
        if identity_requested:
            has_identity_evidence = ev.reference_ground_truth or len(claim.qualifiers) > 0
            if not has_identity_evidence:
                identity_warranted = False
                identity_gaps.append("reference_atlas_mapping_or_qualifier")
                rule_violations.append(
                    "CELL_TYPE_HALLUCINATION: Unverified promotion of cluster to biological cell type without reference or candidate qualifier."
                )
                remedies.append(
                    "Keep cluster labels numeric (e.g. 'Cluster 0') or qualify marker assignments with explicit 'candidate' / 'putative' qualifiers."
                )

        tier_verdicts["cell_identity_claim"] = WarrantTierVerdict(
            tier_name="cell_identity_claim",
            status=(
                WarrantTierStatus.NOT_APPLICABLE
                if not identity_requested
                else WarrantTierStatus.WARRANTED
                if identity_warranted
                else WarrantTierStatus.NOT_WARRANTED
            ),
            is_warranted=identity_warranted if identity_requested else False,
            rationale="Identity grounded in reference ground truth or explicitly qualified as putative."
            if identity_requested and identity_warranted
            else "A cell-identity claim was not requested."
            if not identity_requested
            else "Cell identity assertion unverified without reference mapping.",
            missing_evidence=identity_gaps,
        )

        # ----------------------------------------------------------------------
        # Tier 6: Clinical & Regulatory Warrant
        # ----------------------------------------------------------------------
        clinical_warranted = True
        clinical_gaps = []
        clinical_requested = (
            claim.clinical_actionability in (
                ClinicalActionability.PRESCRIPTIVE_TREATMENT,
                ClinicalActionability.DIAGNOSTIC_ASSERTION,
            )
            or claim.claim_class == ClaimClass.CLINICAL_ACTIONABILITY
        )
        if clinical_requested:
            if not ev.regulatory_certification:
                clinical_warranted = False
                clinical_gaps.append("clia_cap_fda_certification")
                evidence_gaps.append("missing_regulatory_certification")
            if not ev.clinical_ground_truth:
                clinical_warranted = False
                clinical_gaps.append("clinical_ground_truth")
                evidence_gaps.append("missing_clinical_ground_truth")
            if not ev.independent_validation:
                clinical_warranted = False
                clinical_gaps.append("independent_validation")
                evidence_gaps.append("missing_independent_validation")
            if not clinical_warranted:
                rule_violations.append(
                    "REGULATORY_COMPLIANCE_OVERCLAIM: Diagnostic or treatment recommendation lacks regulatory "
                    "certification, intended-use clinical ground truth, or independent validation."
                )
                remedies.append(
                    "Include mandatory Research Use Only (RUO) disclaimer and restrict output to basic scientific exploration."
                )

        tier_verdicts["clinical_claim"] = WarrantTierVerdict(
            tier_name="clinical_claim",
            status=(
                WarrantTierStatus.NOT_APPLICABLE
                if not clinical_requested
                else WarrantTierStatus.WARRANTED
                if clinical_warranted
                else WarrantTierStatus.NOT_WARRANTED
            ),
            is_warranted=clinical_warranted if clinical_requested else False,
            rationale="Clinical rule conditions satisfied on declared certification, ground truth and validation; none authenticated here."
            if clinical_requested and clinical_warranted
            else "A clinical actionability claim was not requested."
            if not clinical_requested
            else "Clinical actionability is not warranted without certification, clinical ground truth, and independent validation.",
            missing_evidence=clinical_gaps,
        )

        # ----------------------------------------------------------------------
        # Tier 7: Macromolecular Structural Conformation Warrant
        # ----------------------------------------------------------------------
        struct_requested = claim.relationship == ClaimRelationshipType.STRUCTURAL_CONFORMATION
        struct_warranted = True
        struct_gaps = []
        if struct_requested:
            if ev.plddt_score is not None:
                if ev.plddt_score < 50.0:
                    struct_warranted = False
                    struct_gaps.append("plddt_gte_70_for_rigid_pocket")
                    rule_violations.append(
                        f"INTRINSIC_DISORDER_VIOLATION: Asserting rigid pocket/structure on region with pLDDT {ev.plddt_score:.1f} < 50."
                    )
                    remedies.append(
                        "AlphaFold/ESMFold pLDDT < 50 indicates intrinsic disorder (IDR); rigid pocket/docking claims are scientifically invalid."
                    )
                elif ev.plddt_score < 70.0:
                    struct_gaps.append("plddt_gte_70_for_confident_backbone")
                    remedies.append("pLDDT 50-70 represents low-confidence ribbon; cap claims at candidate screening (FRAGILE).")
            if ev.interdomain_pae is not None and ev.interdomain_pae > 15.0:
                struct_gaps.append("pae_lte_15_for_interdomain_orientation")
                remedies.append("Inter-domain PAE > 15 Å; relative domain orientation is unconstrained.")

        tier_verdicts["structural_conformation_claim"] = WarrantTierVerdict(
            tier_name="structural_conformation_claim",
            status=(
                WarrantTierStatus.NOT_APPLICABLE
                if not struct_requested
                else WarrantTierStatus.WARRANTED
                if struct_warranted
                else WarrantTierStatus.NOT_WARRANTED
            ),
            is_warranted=struct_warranted if struct_requested else False,
            rationale="Structure rule conditions satisfied on declared pLDDT metrics; physical structure not verified."
            if struct_requested and struct_warranted
            else "A structural conformation claim was not requested."
            if not struct_requested
            else "Structural conformation is unwarranted: low pLDDT indicates intrinsic disorder or unmodeled coordinates.",
            missing_evidence=struct_gaps,
        )

        # ----------------------------------------------------------------------
        # Tier 8: Small-Molecule Bioactivity & Target Binding Warrant
        # ----------------------------------------------------------------------
        bioact_requested = claim.relationship == ClaimRelationshipType.BIOACTIVE_BINDING
        bioact_warranted = True
        bioact_gaps = []
        if bioact_requested:
            if ev.bioactivity_nm is not None and ev.bioactivity_nm > 10000.0:
                bioact_warranted = False
                bioact_gaps.append("potency_lte_10000_nm")
                rule_violations.append(
                    f"NONSPECIFIC_BINDING_OVERCLAIM: Asserting targeted binding for compound with affinity {ev.bioactivity_nm:.1f} nM > 10 µM."
                )
                remedies.append("Binding activities > 10 µM represent weak non-specific binding; targeted claims are refused.")
            if not ev.dose_response_curve:
                bioact_gaps.append("concentration_response_titration")
                remedies.append("Single-concentration screening requires full multi-point concentration-response validation.")

        tier_verdicts["bioactive_binding_claim"] = WarrantTierVerdict(
            tier_name="bioactive_binding_claim",
            status=(
                WarrantTierStatus.NOT_APPLICABLE
                if not bioact_requested
                else WarrantTierStatus.WARRANTED
                if bioact_warranted
                else WarrantTierStatus.NOT_WARRANTED
            ),
            is_warranted=bioact_warranted if bioact_requested else False,
            rationale="Bioactivity rule conditions satisfied on declared affinity; activity not independently confirmed."
            if bioact_requested and bioact_warranted
            else "A bioactive target binding claim was not requested."
            if not bioact_requested
            else "Bioactivity claim unwarranted: affinity exceeds 10 µM medicinal chemistry threshold.",
            missing_evidence=bioact_gaps,
        )

        # ----------------------------------------------------------------------
        # Determine Maximum Warranted Claim Class & Ceiling
        # ----------------------------------------------------------------------
        applicable_tiers = [
            tier
            for tier in tier_verdicts.values()
            if tier.status != WarrantTierStatus.NOT_APPLICABLE
        ]
        all_tiers_ok = bool(applicable_tiers) and all(tier.is_warranted for tier in applicable_tiers)

        # Calculate maximum warranted claim class
        if not assoc_warranted:
            warranted_class = ClaimClass.DESCRIPTIVE
        elif not causal_warranted or not mech_warranted:
            if claim.association_type == AssociationType.SPATIAL_COLOCALIZATION:
                warranted_class = ClaimClass.SPATIAL_DEPENDENCY
            else:
                warranted_class = ClaimClass.ASSOCIATION
        elif not pop_warranted:
            warranted_class = ClaimClass.ASSOCIATION
        elif not identity_warranted:
            warranted_class = ClaimClass.DESCRIPTIVE
        elif not struct_warranted or not bioact_warranted:
            warranted_class = ClaimClass.DESCRIPTIVE
        else:
            warranted_class = claim.claim_class

        # Determine evidence ceiling
        if not assoc_warranted:
            evidence_ceiling = ConclusionMaturity.ABSTAIN.value
        elif any("INTRINSIC_DISORDER_VIOLATION" in v or "NONSPECIFIC_BINDING_OVERCLAIM" in v for v in rule_violations):
            evidence_ceiling = ConclusionMaturity.ABSTAIN.value
        elif struct_requested and ev.plddt_score is not None and ev.plddt_score < 70.0:
            evidence_ceiling = ConclusionMaturity.FRAGILE.value
        elif not all_tiers_ok:
            if len(rule_violations) > 0:
                evidence_ceiling = ConclusionMaturity.FRAGILE.value
            else:
                evidence_ceiling = ConclusionMaturity.SUPPORTED.value
        elif ev.independent_validation:
            evidence_ceiling = ConclusionMaturity.REPLICATED.value
        elif ev.perturbation and ev.biological_replicates_count >= 3:
            evidence_ceiling = ConclusionMaturity.ROBUST.value
        else:
            evidence_ceiling = ConclusionMaturity.SUPPORTED.value

        # Build epistemic summary
        warranted_list = [
            tier_name
            for tier_name, verdict in tier_verdicts.items()
            if verdict.status != WarrantTierStatus.NOT_APPLICABLE and verdict.is_warranted
        ]
        unwarranted_list = [
            tier_name
            for tier_name, verdict in tier_verdicts.items()
            if verdict.status != WarrantTierStatus.NOT_APPLICABLE and not verdict.is_warranted
        ]
        not_applicable_list = [
            tier_name
            for tier_name, verdict in tier_verdicts.items()
            if verdict.status == WarrantTierStatus.NOT_APPLICABLE
        ]
        summary = (
            f"Claim '{claim.claim_id}' Conditional Evaluation (declared premises, not verified facts): "
            f"Warranted tiers: [{', '.join(warranted_list)}]; "
            f"Unwarranted tiers: [{', '.join(unwarranted_list) or 'none'}]. "
            f"Not requested: [{', '.join(not_applicable_list) or 'none'}]. "
            f"Max warranted class: '{warranted_class.value}', ceiling: '{evidence_ceiling}'."
        )

        return WarrantEvaluationResult(
            claim_id=claim.claim_id,
            is_fully_warranted=all_tiers_ok,
            requested_claim_class=claim.claim_class.value,
            warranted_claim_class=warranted_class.value,
            evidence_ceiling=evidence_ceiling,
            tier_verdicts=tier_verdicts,
            evidence_gaps=sorted(set(evidence_gaps)),
            remedies=sorted(set(remedies)),
            rule_violations=rule_violations,
            epistemic_summary=summary,
            has_claim_conflict=bool(claim.metadata.get("has_claim_conflict", False)),
            conflict_details=claim.metadata.get("conflict_details"),
        )


