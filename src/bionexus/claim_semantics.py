"""
BioNexus Scientific Claim Semantics & Deterministic Warrant Engine (BNS-017).

Transforms unstructured natural-language scientific statements into a strictly
typed Scientific Claim Intermediate Representation (ScientificClaimIR) and
evaluates them against evidence ledgers using deterministic epistemic rules.

Avoids both:
1. Brittle regex/keyword heuristics (high false-positive / false-negative rates).
2. Unconstrained LLM judges (non-deterministic, irreproducible, hallucination-prone).
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple, Union

from bionexus.contracts import ConclusionMaturity
from bionexus.evidence_model import ClaimClass


# ==============================================================================
# 1. Semantic IR Enums & Data Structures
# ==============================================================================


class ClaimRelationshipType(str, Enum):
    """Semantic relationship expressed in the scientific claim."""

    CORRELATION = "correlation"  # Co-expression, statistical association
    DIFFERENTIAL_ABUNDANCE = "differential_abundance"  # Up/down regulation across conditions
    CELL_CELL_INTERACTION = "cell_cell_interaction"  # Colocalization, ligand-receptor signaling
    REGULATORY_EFFECT = "regulatory_effect"  # TF binding, transcription modulation, epigenetic
    PHENOTYPE_DRIVER = "phenotype_driver"  # Differentiation, polarization, tumorigenesis, exhaustion
    THERAPEUTIC_RESPONSE = "therapeutic_response"  # Drug sensitivity, resistance, survival benefit
    IDENTITY_ASSERTION = "identity_assertion"  # Cell-type identity, cluster assignment
    DIAGNOSTIC_ASSERTION = "diagnostic_assertion"  # Clinical diagnosis, patient disease call
    MODEL_FIDELITY = "model_fidelity"  # Claim about computational model / algorithm backend


class Directionality(str, Enum):
    """Direction of influence between subject and object."""

    DIRECTED_FORWARD = "directed_forward"  # Subject -> Object (e.g. A drives B)
    DIRECTED_REVERSE = "directed_reverse"  # Object -> Subject (e.g. B is driven by A)
    BIDIRECTIONAL = "bidirectional"  # A <-> B (reciprocal, feedback loop)
    UNDIRECTED = "undirected"  # A and B correlated without direction


class AssociationType(str, Enum):
    """Nature of empirical observation supporting the relationship."""

    OBSERVATIONAL_CORRELATION = "observational_correlation"
    SPATIAL_COLOCALIZATION = "spatial_colocalization"
    LIGAND_RECEPTOR_INFERENCE = "ligand_receptor_inference"
    DIFFERENTIAL_EXPRESSION = "differential_expression"
    TEMPORAL_COVARIANCE = "temporal_covariance"
    SURVIVAL_HAZARD = "survival_hazard"
    UNKNOWN = "unknown"


class CausalStrength(str, Enum):
    """Epistemic strength of the asserted causal claim."""

    NONE = "none"  # Pure descriptive / summary
    ASSOCIATIONAL = "associational"  # Correlational / observational association
    HYPOTHESIZED_CAUSAL = "hypothesized_causal"  # Qualified/putative causal hypothesis ("may drive")
    COUNTERFACTUAL_CAUSAL = "counterfactual_causal"  # Direct causal assertion ("causes", "induces", "drives")
    MECHANISTIC_DRIVER = "mechanistic_driver"  # Multi-step molecular/cellular mechanistic causality


class GeneralizationScope(str, Enum):
    """Scope of generalizability asserted by the claim."""

    SAMPLE_SPECIFIC = "sample_specific"  # Within this specific sample/run
    STRATUM_SPECIFIC = "stratum_specific"  # Within a specific cluster / subtype
    COHORT_SPECIFIC = "cohort_specific"  # Across the analyzed cohort
    POPULATION_GENERAL = "population_general"  # Universal disease or species population ("in NSCLC", "in humans")


class MechanismDepth(str, Enum):
    """Depth of mechanistic detail asserted."""

    BLACK_BOX = "black_box"  # Input-output correlation without intermediate mechanism
    PATHWAY_ENRICHMENT = "pathway_enrichment"  # Pathway or gene set co-enrichment
    SIGNALING_CASCADE = "signaling_cascade"  # Specific ligand-receptor-downstream cascade
    MOLECULAR_BINDING = "molecular_binding"  # Physical binding / docking / PPI
    PERTURBATIVE_FUNCTION = "perturbative_function"  # Functional rescue/knockout perturbation proof


class ClinicalActionability(str, Enum):
    """Level of clinical or translational assertion."""

    NONE = "none"  # Basic biological research
    EXPLORATORY_BIOMARKER = "exploratory_biomarker"  # Candidate prognostic/diagnostic biomarker
    PRESCRIPTIVE_TREATMENT = "prescriptive_treatment"  # Direct treatment recommendation / dosage
    DIAGNOSTIC_ASSERTION = "diagnostic_assertion"  # Definitive patient diagnostic confirmation


class WarrantTierStatus(str, Enum):
    """Warrant status for a specific epistemic tier."""

    WARRANTED = "WARRANTED"
    WARRANTED_WITH_LIMITS = "WARRANTED_WITH_LIMITS"
    NOT_WARRANTED = "NOT_WARRANTED"
    PROHIBITED = "PROHIBITED"


@dataclass
class ScientificEntity:
    """A biological entity (cell type, gene, protein, disease, phenotype, condition)."""

    name: str
    entity_type: str = "biological_entity"  # "cell_type", "gene", "protein", "phenotype", "disease", "condition"
    features: List[str] = field(default_factory=list)  # e.g. ["CXCL13+", "CD8+"]
    raw_span: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ScientificClaimIR:
    """
    Structured Scientific Claim Intermediate Representation (IR).

    A canonical, normalized decomposition of a scientific claim statement
    into typed epistemic dimensions.
    """

    claim_id: str
    source_text: str
    subject_entity: ScientificEntity
    object_entity: Optional[ScientificEntity] = None
    relationship: ClaimRelationshipType = ClaimRelationshipType.CORRELATION
    direction: Directionality = Directionality.UNDIRECTED
    comparison: Optional[str] = None  # e.g. "treatment vs control"
    population_scope: str = ""  # e.g. "NSCLC", "human PBMC"
    generalization_scope: GeneralizationScope = GeneralizationScope.COHORT_SPECIFIC
    association_type: AssociationType = AssociationType.OBSERVATIONAL_CORRELATION
    causal_strength: CausalStrength = CausalStrength.ASSOCIATIONAL
    mechanism_depth: MechanismDepth = MechanismDepth.BLACK_BOX
    clinical_actionability: ClinicalActionability = ClinicalActionability.NONE
    claim_class: ClaimClass = ClaimClass.ASSOCIATION
    qualifiers: List[str] = field(default_factory=list)  # ["putative", "candidate", "exploratory"]
    negated: bool = False  # True if statement asserts absence of effect ("cannot prove", "does not cause")
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "source_text": self.source_text,
            "subject_entity": self.subject_entity.to_dict(),
            "object_entity": self.object_entity.to_dict() if self.object_entity else None,
            "relationship": self.relationship.value,
            "direction": self.direction.value,
            "comparison": self.comparison,
            "population_scope": self.population_scope,
            "generalization_scope": self.generalization_scope.value,
            "association_type": self.association_type.value,
            "causal_strength": self.causal_strength.value,
            "mechanism_depth": self.mechanism_depth.value,
            "clinical_actionability": self.clinical_actionability.value,
            "claim_class": self.claim_class.value,
            "qualifiers": self.qualifiers,
            "negated": self.negated,
            "metadata": self.metadata,
        }


@dataclass
class EvidenceProfile:
    """
    Empirical evidence facts available to support or constrain a claim.
    """

    spatial_colocalization: bool = False
    ligand_receptor_inference: bool = False
    perturbation: bool = False  # Knockout, knockdown, CRISPR, drug assay
    temporal_evidence: bool = False  # Time-series kinetics, longitudinal
    independent_validation: bool = False  # Orthogonal cohort, external dataset
    biological_replicates_count: int = 0  # Number of distinct biological donors/samples
    pseudobulk_aggregated: bool = False  # Sample-level aggregation performed
    confound_controls: List[str] = field(default_factory=list)  # ["donor", "batch", "cell_cycle"]
    causal_identification_status: str = "UNASSESSED"  # "BACKDOOR_SATISFIED" | "UNBLOCKED_BACKDOOR" | "COLLIDER_BIAS"
    reference_ground_truth: bool = False  # Verified cell atlas / reference panel
    regulatory_certification: bool = False  # CLIA/CAP / FDA Part 11 certified
    ruo_disclaimer_present: bool = False  # Research Use Only disclaimer
    cross_method_concordance: bool = False  # Agreement across alternative tools

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class WarrantTierVerdict:
    """Verdict for one specific epistemic tier."""

    tier_name: str
    status: WarrantTierStatus
    is_warranted: bool
    rationale: str
    missing_evidence: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tier_name": self.tier_name,
            "status": self.status.value,
            "is_warranted": self.is_warranted,
            "rationale": self.rationale,
            "missing_evidence": self.missing_evidence,
        }


@dataclass
class WarrantEvaluationResult:
    """
    Comprehensive multi-tier verdict emitted by the Deterministic Warrant Engine.
    """

    claim_id: str
    is_fully_warranted: bool
    requested_claim_class: str
    warranted_claim_class: str
    evidence_ceiling: str  # ConclusionMaturity string
    tier_verdicts: Dict[str, WarrantTierVerdict] = field(default_factory=dict)
    evidence_gaps: List[str] = field(default_factory=list)
    remedies: List[str] = field(default_factory=list)
    rule_violations: List[str] = field(default_factory=list)
    epistemic_summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "is_fully_warranted": self.is_fully_warranted,
            "requested_claim_class": self.requested_claim_class,
            "warranted_claim_class": self.warranted_claim_class,
            "evidence_ceiling": self.evidence_ceiling,
            "tier_verdicts": {k: v.to_dict() for k, v in self.tier_verdicts.items()},
            "evidence_gaps": self.evidence_gaps,
            "remedies": self.remedies,
            "rule_violations": self.rule_violations,
            "epistemic_summary": self.epistemic_summary,
        }


# ==============================================================================
# 2. Deterministic Claim Parser
# ==============================================================================


class DeterministicClaimParser:
    """
    Deterministic scientific claim parser.

    Transforms raw statements into canonical `ScientificClaimIR` representations
    without relying on stochastic LLM calls.
    """

    # Causal & Mechanistic Action Verbs
    _CAUSAL_VERBS_FORWARD = [
        r"\bdrives?\b",
        r"\bcauses?\b",
        r"\binduces?\b",
        r"\btriggers?\b",
        r"\bpromotes?\b",
        r"\bactivates?\b",
        r"\brepresses?\b",
        r"\binhibits?\b",
        r"\bmodulates?\b",
        r"\bregulates?\b",
        r"\bleads?\s+to\b",
        r"\bresults?\s+in\b",
        r"\bpolarizes?\b",
        r"\bprograms?\b",
        r"\bcontrols?\b",
        r"\bmediates?\b",
    ]

    _CAUSAL_VERBS_PASSIVE = [
        r"\bis\s+driven\s+by\b",
        r"\bis\s+caused\s+by\b",
        r"\bis\s+induced\s+by\b",
        r"\bis\s+triggered\s+by\b",
        r"\bis\s+regulated\s+by\b",
        r"\bis\s+mediated\s+by\b",
        r"\bdepends?\s+on\b",
    ]

    # Associational & Correlational Verbs
    _ASSOCIATIONAL_VERBS = [
        r"\bcorrelates?\s+with\b",
        r"\bassociates?\s+with\b",
        r"\bis\s+associated\s+with\b",
        r"\bco-?occurs?\s+with\b",
        r"\bco-?localizes?\s+with\b",
        r"\bco-?expressed\s+with\b",
        r"\bexhibits?\b",
        r"\bshows?\b",
        r"\bdisplays?\b",
    ]

    # Identity / Cluster Assignment Verbs
    _IDENTITY_VERBS = [
        r"\bcluster\s*\d+\s*(?:is|represents|corresponds\s*to|identified\s*as|assigned\s*as|defines)\b",
        r"\bcluster\s*\d+\s*:\s*",
        r"\bidentified\s+as\b",
        r"\brepresents?\b",
    ]

    # Clinical / Regulatory Action Verbs
    _CLINICAL_VERBS = [
        r"\bdiagnos(?:es|ed|is|tic)\b",
        r"\btreat(?:s|ed|ment)\s+recommendation\b",
        r"\bpatient\s+(?:treatment|therapy|prescription)\b",
        r"\b21\s*cfr\s*part\s*11\b",
        r"\bclia\b",
        r"\bcap\s+accredited\b",
    ]

    # Epistemic Hedges & Qualifiers
    _QUALIFIERS = [
        "candidate",
        "putative",
        "unverified",
        "hypothesized",
        "exploratory",
        "suggests",
        "suggesting",
        "potential",
        "preliminary",
        "indicates",
        "possibly",
        "likely",
    ]

    # Negation Markers
    _NEGATION_PATTERNS = [
        r"\bcannot\s+(?:prove|demonstrate|establish|confirm|conclude)\b",
        r"\bcan\s+not\s+(?:prove|demonstrate|establish|confirm|conclude)\b",
        r"\bdoes\s+not\s+(?:prove|cause|drive|induce|imply|show)\b",
        r"\bdo\s+not\s+(?:prove|cause|drive|induce|imply|show)\b",
        r"\bnever\s+(?:prove|cause|drive|induce)\b",
        r"\bnot\s+(?:proven|established|sufficient|causal)\b",
        r"\bunable\s+to\s+(?:prove|establish|conclude)\b",
        r"\bno\s+evidence\s+for\b",
        r"\bfails?\s+to\s+show\b",
    ]

    # Population & Context Scopes
    _POPULATION_PATTERNS = [
        r"\bin\s+([A-Z0-9_-]+(?:\s+[A-Z0-9_-]+)?)\b",  # in NSCLC, in PBMC
        r"\bacross\s+([A-Z0-9_-]+(?:\s+patients|\s+samples|\s+cohorts)?)\b",
        r"\bin\s+(human|mouse|murine|patient|tumor|tme|cancer|normal|healthy)\s*([a-zA-Z0-9_-]*)",
    ]

    @classmethod
    def parse(cls, text: str, claim_id: Optional[str] = None) -> ScientificClaimIR:
        """
        Parse a single natural-language claim into a structured ScientificClaimIR.
        """
        clean_text = text.strip()
        cid = claim_id or f"CLAIM-{abs(hash(clean_text)) % 1000000:06d}"

        # 1. Negation detection
        negated = any(re.search(pat, clean_text, re.IGNORECASE) for pat in cls._NEGATION_PATTERNS)

        # 2. Qualifiers / Hedges extraction
        text_lower = clean_text.lower()
        qualifiers = [q for q in cls._QUALIFIERS if q in text_lower]

        # 3. Population Scope extraction
        population_scope = ""
        for pat in cls._POPULATION_PATTERNS:
            match = re.search(pat, clean_text, re.IGNORECASE)
            if match:
                population_scope = match.group(0).replace("in ", "").replace("across ", "").strip()
                break

        # 4. Generalization scope
        if population_scope and any(
            p in population_scope.lower()
            for p in ("nsclc", "human", "cancer", "tumor", "patient", "disease", "cohort")
        ):
            gen_scope = GeneralizationScope.POPULATION_GENERAL
        elif "cluster" in text_lower:
            gen_scope = GeneralizationScope.STRATUM_SPECIFIC
        elif "sample" in text_lower:
            gen_scope = GeneralizationScope.SAMPLE_SPECIFIC
        else:
            gen_scope = GeneralizationScope.COHORT_SPECIFIC

        # 5. Clinical Actionability
        clinical_act = ClinicalActionability.NONE
        if any(re.search(pat, clean_text, re.IGNORECASE) for pat in cls._CLINICAL_VERBS):
            if "diagnos" in text_lower:
                clinical_act = ClinicalActionability.DIAGNOSTIC_ASSERTION
            elif "treat" in text_lower or "prescrib" in text_lower:
                clinical_act = ClinicalActionability.PRESCRIPTIVE_TREATMENT
            elif "biomarker" in text_lower:
                clinical_act = ClinicalActionability.EXPLORATORY_BIOMARKER

        # 6. Entity & Predicate Extraction
        subject_name = "Subject"
        object_name = None
        direction = Directionality.UNDIRECTED
        rel_type = ClaimRelationshipType.CORRELATION
        causal_strength = CausalStrength.ASSOCIATIONAL
        mech_depth = MechanismDepth.BLACK_BOX
        assoc_type = AssociationType.OBSERVATIONAL_CORRELATION
        claim_class = ClaimClass.ASSOCIATION

        # Check for Cell Identity claim
        if any(re.search(pat, clean_text, re.IGNORECASE) for pat in cls._IDENTITY_VERBS):
            rel_type = ClaimRelationshipType.IDENTITY_ASSERTION
            claim_class = ClaimClass.CELL_IDENTITY
            causal_strength = CausalStrength.NONE
            # Extract cluster and cell type
            m = re.search(r"\b(cluster\s*\d+)\b.*?(?:is|represents|corresponds\s*to|:)\s*(?:a|an|the)?\s*([a-zA-Z0-9_\+\-\s]+)", clean_text, re.IGNORECASE)
            if m:
                subject_name = m.group(1).strip()
                object_name = m.group(2).split(".")[0].split(",")[0].strip()

        # Check for Causal / Forward Action Claim (e.g. "A drives B in C")
        else:
            forward_verb_match = None
            for verb_pat in cls._CAUSAL_VERBS_FORWARD:
                m = re.search(verb_pat, clean_text, re.IGNORECASE)
                if m:
                    forward_verb_match = m
                    break

            passive_verb_match = None
            for verb_pat in cls._CAUSAL_VERBS_PASSIVE:
                m = re.search(verb_pat, clean_text, re.IGNORECASE)
                if m:
                    passive_verb_match = m
                    break

            assoc_verb_match = None
            for verb_pat in cls._ASSOCIATIONAL_VERBS:
                m = re.search(verb_pat, clean_text, re.IGNORECASE)
                if m:
                    assoc_verb_match = m
                    break

            if forward_verb_match:
                start, end = forward_verb_match.span()
                raw_subj = clean_text[:start].strip()
                raw_obj = clean_text[end:].strip()
                # Clean subject and object
                if population_scope:
                    raw_obj = re.sub(rf"\b(?:in|across)\s+{re.escape(population_scope)}\b.*", "", raw_obj, flags=re.IGNORECASE).strip()
                raw_obj = raw_obj.rstrip(". ,;")

                subject_name = raw_subj or "Entity A"
                object_name = raw_obj or "Entity B"
                direction = Directionality.DIRECTED_FORWARD

                if qualifiers:
                    causal_strength = CausalStrength.HYPOTHESIZED_CAUSAL
                else:
                    causal_strength = CausalStrength.COUNTERFACTUAL_CAUSAL

                # Discern relationship type & depth
                if any(w in text_lower for w in ("polariz", "differentiat", "fate", "exhaustion", "activation")):
                    rel_type = ClaimRelationshipType.PHENOTYPE_DRIVER
                    mech_depth = MechanismDepth.SIGNALING_CASCADE
                    claim_class = ClaimClass.MECHANISTIC
                elif any(w in text_lower for w in ("express", "degs", "transcript", "down-regulat", "up-regulat")):
                    rel_type = ClaimRelationshipType.REGULATORY_EFFECT
                    mech_depth = MechanismDepth.PATHWAY_ENRICHMENT
                    claim_class = ClaimClass.CAUSAL
                elif any(w in text_lower for w in ("cell", "t cell", "macrophage", "monocyte", "b cell")):
                    rel_type = ClaimRelationshipType.CELL_CELL_INTERACTION
                    mech_depth = MechanismDepth.SIGNALING_CASCADE
                    claim_class = ClaimClass.MECHANISTIC
                else:
                    rel_type = ClaimRelationshipType.REGULATORY_EFFECT
                    claim_class = ClaimClass.CAUSAL

            elif passive_verb_match:
                start, end = passive_verb_match.span()
                raw_obj = clean_text[:start].strip()
                raw_subj = clean_text[end:].strip()
                if population_scope:
                    raw_subj = re.sub(rf"\b(?:in|across)\s+{re.escape(population_scope)}\b.*", "", raw_subj, flags=re.IGNORECASE).strip()

                subject_name = raw_subj or "Entity A"
                object_name = raw_obj or "Entity B"
                direction = Directionality.DIRECTED_FORWARD
                causal_strength = CausalStrength.HYPOTHESIZED_CAUSAL if qualifiers else CausalStrength.COUNTERFACTUAL_CAUSAL
                rel_type = ClaimRelationshipType.REGULATORY_EFFECT
                claim_class = ClaimClass.CAUSAL

            elif assoc_verb_match:
                start, end = assoc_verb_match.span()
                subject_name = clean_text[:start].strip()
                raw_obj = clean_text[end:].strip()
                if population_scope:
                    raw_obj = re.sub(rf"\b(?:in|across)\s+{re.escape(population_scope)}\b.*", "", raw_obj, flags=re.IGNORECASE).strip()
                object_name = raw_obj.rstrip(". ,;")
                direction = Directionality.UNDIRECTED
                causal_strength = CausalStrength.ASSOCIATIONAL
                rel_type = ClaimRelationshipType.CORRELATION
                claim_class = ClaimClass.ASSOCIATION

            else:
                # Default fallback extraction
                subject_name = clean_text
                object_name = None
                direction = Directionality.UNDIRECTED
                causal_strength = CausalStrength.ASSOCIATIONAL
                rel_type = ClaimRelationshipType.CORRELATION
                claim_class = ClaimClass.DESCRIPTIVE

        # Association type fine-tuning
        if "spatial" in text_lower or "colocaliz" in text_lower or "moran" in text_lower or "niche" in text_lower:
            assoc_type = AssociationType.SPATIAL_COLOCALIZATION
            if claim_class == ClaimClass.ASSOCIATION:
                claim_class = ClaimClass.SPATIAL_DEPENDENCY
        elif "ligand" in text_lower or "receptor" in text_lower or "cellchat" in text_lower or "cellphone" in text_lower:
            assoc_type = AssociationType.LIGAND_RECEPTOR_INFERENCE
        elif "deg" in text_lower or "differential" in text_lower or "deseq" in text_lower:
            assoc_type = AssociationType.DIFFERENTIAL_EXPRESSION
            if gen_scope == GeneralizationScope.POPULATION_GENERAL:
                claim_class = ClaimClass.POPULATION_EFFECT
        elif "hazard" in text_lower or "survival" in text_lower or "kaplan" in text_lower:
            assoc_type = AssociationType.SURVIVAL_HAZARD

        # Model substitution check
        if any(m in text_lower for m in ("esm-2", "alphafold", "protbert")) and any(
            h in text_lower for h in ("blosum", "heuristic", "substitution matrix")
        ):
            rel_type = ClaimRelationshipType.MODEL_FIDELITY

        # Subject entity features
        features = []
        token_matches = re.findall(r"\b([A-Za-z0-9_]+[\+\-]?)", subject_name)
        for tok in token_matches:
            if tok.endswith(("+", "-")) or any(m in tok.upper() for m in ("CD8", "CD4", "CD3", "CD19", "CD20", "CD14", "CD56", "CD68", "CXCL13", "FOXP3", "PD1", "CTLA4")):
                if tok not in features and tok.lower() not in ("cells", "t", "b"):
                    features.append(tok)

        subj_entity = ScientificEntity(
            name=subject_name,
            entity_type="cell_population" if "cell" in subject_name.lower() else "biological_entity",
            features=features,
            raw_span=subject_name,
        )

        obj_entity = None
        if object_name:
            obj_features = []
            obj_token_matches = re.findall(r"\b([A-Za-z0-9_]+[\+\-]?)", object_name)
            for tok in obj_token_matches:
                if tok.endswith(("+", "-")) or any(m in tok.upper() for m in ("CD8", "CD4", "CD3", "CD19", "CD20", "CD14", "CD56", "CD68", "CXCL13", "FOXP3", "PD1", "CTLA4")):
                    if tok not in obj_features and tok.lower() not in ("cells", "t", "b"):
                        obj_features.append(tok)

            obj_entity = ScientificEntity(
                name=object_name,
                entity_type="phenotype" if "polariz" in object_name.lower() or "differentiat" in object_name.lower() else "biological_entity",
                features=obj_features,
                raw_span=object_name,
            )

        return ScientificClaimIR(
            claim_id=cid,
            source_text=clean_text,
            subject_entity=subj_entity,
            object_entity=obj_entity,
            relationship=rel_type,
            direction=direction,
            population_scope=population_scope,
            generalization_scope=gen_scope,
            association_type=assoc_type,
            causal_strength=causal_strength,
            mechanism_depth=mech_depth,
            clinical_actionability=clinical_act,
            claim_class=claim_class,
            qualifiers=qualifiers,
            negated=negated,
        )


# ==============================================================================
# 3. Deterministic Warrant Engine
# ==============================================================================


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
        tier_verdicts: Dict[str, WarrantTierVerdict] = {}
        evidence_gaps: List[str] = []
        remedies: List[str] = []
        rule_violations: List[str] = []

        # If claim is explicitly negated (e.g. "cannot prove drug caused DEGs"),
        # it is epistemically honest and immediately warranted!
        if claim.negated:
            tier_verdicts["negated_qualification"] = WarrantTierVerdict(
                tier_name="negated_qualification",
                status=WarrantTierStatus.WARRANTED,
                is_warranted=True,
                rationale="Statement explicitly disclaims unwarranted causation or states inability to prove.",
            )
            return WarrantEvaluationResult(
                claim_id=claim.claim_id,
                is_fully_warranted=True,
                requested_claim_class=claim.claim_class.value,
                warranted_claim_class=claim.claim_class.value,
                evidence_ceiling=ConclusionMaturity.ROBUST.value,
                tier_verdicts=tier_verdicts,
                evidence_gaps=[],
                remedies=[],
                rule_violations=[],
                epistemic_summary="Claim is a scientifically honest disclaimer or negative finding.",
            )

        # ----------------------------------------------------------------------
        # Tier 1: Observational & Associational Warrant
        # ----------------------------------------------------------------------
        assoc_warranted = (
            ev.spatial_colocalization
            or ev.ligand_receptor_inference
            or ev.pseudobulk_aggregated
            or ev.cross_method_concordance
            or ev.biological_replicates_count > 0
            or claim.association_type == AssociationType.OBSERVATIONAL_CORRELATION
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
        pop_warranted = True
        pop_gaps = []
        if claim.generalization_scope == GeneralizationScope.POPULATION_GENERAL:
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
            status=WarrantTierStatus.WARRANTED if pop_warranted else WarrantTierStatus.NOT_WARRANTED,
            is_warranted=pop_warranted,
            rationale="Population-level generalization supported by biological replicates and pseudobulk."
            if pop_warranted
            else f"Population-level generalization across '{claim.population_scope}' lacks n>=3 biological replicates.",
            missing_evidence=pop_gaps,
        )

        # ----------------------------------------------------------------------
        # Tier 3: Mechanistic Warrant
        # ----------------------------------------------------------------------
        # Mechanistic claims assert molecular/cellular cascades (e.g. CD8 T cells drive macrophage polarization)
        mech_warranted = True
        mech_gaps = []
        is_mechanistic_requested = (
            claim.claim_class == ClaimClass.MECHANISTIC
            or claim.mechanism_depth in (MechanismDepth.SIGNALING_CASCADE, MechanismDepth.PERTURBATIVE_FUNCTION)
            or claim.relationship in (ClaimRelationshipType.PHENOTYPE_DRIVER, ClaimRelationshipType.CELL_CELL_INTERACTION)
            and claim.direction != Directionality.UNDIRECTED
        )

        if is_mechanistic_requested:
            # Requires: (Spatial + L-R + (Perturbation OR Temporal)) OR (Ground Truth Reference + Perturbation)
            has_functional_proof = ev.perturbation or ev.temporal_evidence
            if not has_functional_proof:
                mech_warranted = False
                mech_gaps.extend(["perturbation_functional_assay", "temporal_kinetics"])
                evidence_gaps.append("missing_functional_perturbation")
                remedies.append(
                    f"Mechanistic claim '{claim.subject_entity.name} -> {claim.object_entity.name if claim.object_entity else 'phenotype'}' "
                    "requires experimental perturbation (CRISPR/knockdown/rescue) or longitudinal time-series kinetics. "
                    "Spatial colocalization and ligand-receptor co-expression establish spatial association, not directional mechanism."
                )

        tier_verdicts["mechanistic_claim"] = WarrantTierVerdict(
            tier_name="mechanistic_claim",
            status=WarrantTierStatus.WARRANTED if mech_warranted else WarrantTierStatus.NOT_WARRANTED,
            is_warranted=mech_warranted,
            rationale="Mechanistic cascade verified by functional perturbation/kinetics."
            if mech_warranted
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
                    f"CAUSAL_OVERCLAIM: Action verb asserting counterfactual causality without perturbation or DAG backdoor closure."
                )
                remedies.append(
                    "Downgrade claim phrasing from causal assertions ('drives', 'causes', 'induces') to correlational "
                    "observations ('is associated with', 'co-localizes with'), or conduct targeted functional perturbation."
                )

        tier_verdicts["causal_claim"] = WarrantTierVerdict(
            tier_name="causal_claim",
            status=WarrantTierStatus.WARRANTED if causal_warranted else WarrantTierStatus.NOT_WARRANTED,
            is_warranted=causal_warranted,
            rationale="Causal identifiability verified via perturbation or structural causal DAG."
            if causal_warranted
            else "Causal claim NOT warranted: observational data cannot rule out unobserved confounding.",
            missing_evidence=causal_gaps,
        )

        # ----------------------------------------------------------------------
        # Tier 5: Cell Identity Warrant
        # ----------------------------------------------------------------------
        identity_warranted = True
        identity_gaps = []
        if claim.relationship == ClaimRelationshipType.IDENTITY_ASSERTION or claim.claim_class == ClaimClass.CELL_IDENTITY:
            has_identity_evidence = ev.reference_ground_truth or len(claim.qualifiers) > 0
            if not has_identity_evidence:
                identity_warranted = False
                identity_gaps.append("reference_atlas_mapping_or_qualifier")
                rule_violations.append(
                    f"CELL_TYPE_HALLUCINATION: Unverified promotion of cluster to biological cell type without reference or candidate qualifier."
                )
                remedies.append(
                    "Keep cluster labels numeric (e.g. 'Cluster 0') or qualify marker assignments with explicit 'candidate' / 'putative' qualifiers."
                )

        tier_verdicts["cell_identity_claim"] = WarrantTierVerdict(
            tier_name="cell_identity_claim",
            status=WarrantTierStatus.WARRANTED if identity_warranted else WarrantTierStatus.NOT_WARRANTED,
            is_warranted=identity_warranted,
            rationale="Identity grounded in reference ground truth or explicitly qualified as putative."
            if identity_warranted
            else "Cell identity assertion unverified without reference mapping.",
            missing_evidence=identity_gaps,
        )

        # ----------------------------------------------------------------------
        # Tier 6: Clinical & Regulatory Warrant
        # ----------------------------------------------------------------------
        clinical_warranted = True
        clinical_gaps = []
        if claim.clinical_actionability in (ClinicalActionability.PRESCRIPTIVE_TREATMENT, ClinicalActionability.DIAGNOSTIC_ASSERTION):
            if not ev.regulatory_certification:
                clinical_warranted = False
                clinical_gaps.append("clia_cap_fda_certification")
                rule_violations.append(
                    "REGULATORY_COMPLIANCE_OVERCLAIM: Diagnostic or treatment recommendation emitted on research-use-only platform."
                )
                remedies.append(
                    "Include mandatory Research Use Only (RUO) disclaimer and restrict output to basic scientific exploration."
                )

        tier_verdicts["clinical_claim"] = WarrantTierVerdict(
            tier_name="clinical_claim",
            status=WarrantTierStatus.WARRANTED if clinical_warranted else WarrantTierStatus.NOT_WARRANTED,
            is_warranted=clinical_warranted,
            rationale="Clinical certification verified."
            if clinical_warranted
            else "Clinical actionability prohibited on research-grade pipeline.",
            missing_evidence=clinical_gaps,
        )

        # ----------------------------------------------------------------------
        # Determine Maximum Warranted Claim Class & Ceiling
        # ----------------------------------------------------------------------
        all_tiers_ok = all(t.is_warranted for t in tier_verdicts.values())

        # Calculate maximum warranted claim class
        if not causal_warranted or not mech_warranted:
            if claim.association_type == AssociationType.SPATIAL_COLOCALIZATION:
                warranted_class = ClaimClass.SPATIAL_DEPENDENCY
            else:
                warranted_class = ClaimClass.ASSOCIATION
        elif not pop_warranted:
            warranted_class = ClaimClass.ASSOCIATION
        elif not identity_warranted:
            warranted_class = ClaimClass.DESCRIPTIVE
        else:
            warranted_class = claim.claim_class

        # Determine evidence ceiling
        if not all_tiers_ok:
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
        warranted_list = [t for t, v in tier_verdicts.items() if v.is_warranted]
        unwarranted_list = [t for t, v in tier_verdicts.items() if not v.is_warranted]
        summary = (
            f"Claim '{claim.claim_id}' Epistemic Evaluation: "
            f"Warranted tiers: [{', '.join(warranted_list)}]; "
            f"Unwarranted tiers: [{', '.join(unwarranted_list) or 'none'}]. "
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
        )
