"""
BioNexus Scientific Claim Semantics & Deterministic Warrant Engine (BNS-017).

Transforms unstructured natural-language scientific statements into a strictly
typed Scientific Claim Intermediate Representation (ScientificClaimIR) and
evaluates them against evidence ledgers using deterministic epistemic rules.

Implementation honesty note (corrects an earlier misleading claim): this parser
IS a deterministic lexical-semantic layer — curated verb/concept lexicons
compiled to word-boundary regexes, with negation scoping, hedge detection, and
light morphological handling. It does NOT avoid pattern matching; it avoids
unconstrained LLM judges (non-deterministic, irreproducible). The design trade
is recall for determinism and auditability: identical text always yields an
identical IR, and every lexicon below is a reviewable registry constant with
documented precision/recall limits (see INV-009/INV-010 in
review/SCIENTIFIC_RULE_CATALOG.json).
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

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
    NOT_ASSESSED = "NOT_ASSESSED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


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

    observational_data: bool = False  # At least one admissible claim-supporting evidence node
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
    clinical_ground_truth: bool = False  # Verified clinical endpoint/diagnosis bound to the intended use
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
    governing_status: Optional[str] = None

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
            "governing_status": self.governing_status,
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

    # Causal & Mechanistic Action Verbs (word-boundary compiled below)
    _CAUSAL_VERBS_FORWARD = [
        r"\bdrives?\b",
        r"\bcauses?\b",
        r"\binduces?\b",
        r"\btriggers?\b",
        r"\bpromotes?\b",
        r"\bactivates?\b",
        r"\brepresses?\b",
        r"\bsuppress(?:es)?\b",
        r"\binhibits?\b",
        r"\bmodulates?\b",
        r"\bregulates?\b",
        r"\bup-?regulates?\b",
        r"\bdown-?regulates?\b",
        r"\benhances?\b",
        r"\battenuates?\b",
        r"\bconfers?\b",
        r"\baccelerates?\b",
        r"\bimpairs?\b",
        r"\babrogates?\b",
        r"\bleads?\s+to\b",
        r"\bresults?\s+in\b",
        r"\bpolarizes?\b",
        r"\bprograms?\b",
        r"\bcontrols?\b",
        r"\bmediates?\b",
    ]

    _CAUSAL_VERBS_PASSIVE = [
        r"\b(?:is|are|was|were)\s+driven\s+by\b",
        r"\b(?:is|are|was|were)\s+caused\s+by\b",
        r"\b(?:is|are|was|were)\s+induced\s+by\b",
        r"\b(?:is|are|was|were)\s+triggered\s+by\b",
        r"\b(?:is|are|was|were)\s+regulated\s+by\b",
        r"\b(?:is|are|was|were)\s+mediated\s+by\b",
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

    # Word-boundary qualifier matcher: fixes substring false hedges such as
    # "unlikely" matching "likely".
    _QUALIFIER_RE = re.compile(r"\b(?:" + "|".join(_QUALIFIERS) + r")\b", re.IGNORECASE)

    # Modal/verbal hedge window: a causal verb preceded within the same clause
    # by an epistemic modal is hypothesized, not asserted.
    _HEDGE_MODAL_RE = re.compile(
        r"\b(?:may|might|could|appears?\s+to|seems?\s+to|is\s+thought\s+to|"
        r"are\s+thought\s+to|putatively|presumably)\b",
        re.IGNORECASE,
    )
    _HEDGE_WINDOW_CHARS = 64

    # Negation Markers
    _NEGATION_PATTERNS = [
        r"\bcannot\s+(?:prove|demonstrate|establish|confirm|conclude)\b",
        r"\bcan\s+not\s+(?:prove|demonstrate|establish|confirm|conclude)\b",
        r"\bdoes\s+not\s+(?:prove|cause|drive|induce|imply|show|affect|alter|correlate|associate|change)\b",
        r"\bdo\s+not\s+(?:prove|cause|drive|induce|imply|show|affect|alter|correlate|associate|change)\b",
        r"\bdid\s+not\s+(?:prove|cause|drive|induce|affect|change|alter|show)\b",
        r"\bnever\s+(?:prove|cause|drive|induce)\b",
        r"\bnot\s+(?:proven|established|sufficient|causal)\b",
        r"\b(?:is|are)\s+not\s+(?:associated|correlated|linked)\s+with\b",
        r"\bunable\s+to\s+(?:prove|establish|conclude)\b",
        r"\bno\s+evidence\s+(?:for|of|that)\b",
        r"\bfails?\s+to\s+(?:show|induce|cause|drive|demonstrate|reveal)\b",
        r"\bnot\s+sufficient\s+to\s+(?:prove|establish|infer|conclude|claim)\b",
        r"\bwithout\s+evidence\s+(?:of|for)\b",
    ]

    # Population & Context Scopes
    _POPULATION_PATTERNS = [
        r"\bin\s+([A-Z0-9_-]+(?:\s+[A-Z0-9_-]+)?)\b",  # in NSCLC, in PBMC
        r"\bacross\s+([A-Z0-9_-]+(?:\s+[A-Z0-9_-]+)?)\b",
        r"\bin\s+(human|mouse|murine|patient|tumor|tme|cancer|normal|healthy)\s*([a-zA-Z0-9_-]*)",
    ]

    # Generic words that must never become a population scope ("in this study").
    _POPULATION_STOPWORDS = {
        "this", "study", "our", "the", "these", "those", "their", "its",
        "vitro", "vivo", "silico", "each", "both", "same", "other",
        "sample", "samples", "dataset", "data", "analysis", "model", "cohort",
    }

    @classmethod
    def parse(cls, text: str, claim_id: Optional[str] = None) -> ScientificClaimIR:
        """
        Parse a single natural-language claim into a structured ScientificClaimIR.
        """
        clean_text = text.strip()
        cid = claim_id or f"CLAIM-{abs(hash(clean_text)) % 1000000:06d}"

        # 1. Negation detection
        negated = any(re.search(pat, clean_text, re.IGNORECASE) for pat in cls._NEGATION_PATTERNS)

        # 2. Qualifiers / Hedges extraction (word-boundary exact)
        text_lower = clean_text.lower()
        qualifiers = [q for q in cls._QUALIFIER_RE.findall(clean_text)]

        # 3. Population Scope extraction (stopword-guarded)
        population_scope = ""
        for pat in cls._POPULATION_PATTERNS:
            match = re.search(pat, clean_text, re.IGNORECASE)
            if not match:
                continue
            candidate = re.sub(r"^(?:in|across)\s+", "", match.group(0), flags=re.IGNORECASE).strip()
            first_token = candidate.split()[0].lower() if candidate.split() else ""
            if candidate and first_token not in cls._POPULATION_STOPWORDS:
                population_scope = candidate
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

            def _hedged(verb_start: int) -> bool:
                """Hypothesized vs asserted: any word-boundary epistemic qualifier,
                or an epistemic modal immediately preceding the causal verb."""
                if cls._QUALIFIER_RE.search(clean_text):
                    return True
                window_start = max(0, verb_start - cls._HEDGE_WINDOW_CHARS)
                return bool(cls._HEDGE_MODAL_RE.search(clean_text[window_start:verb_start]))

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

                causal_strength = (
                    CausalStrength.HYPOTHESIZED_CAUSAL if _hedged(start) else CausalStrength.COUNTERFACTUAL_CAUSAL
                )

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
                causal_strength = (
                    CausalStrength.HYPOTHESIZED_CAUSAL if _hedged(start) else CausalStrength.COUNTERFACTUAL_CAUSAL
                )
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

        # Negation suppression: a statement that explicitly disclaims causation
        # ("X does not drive Y", "cannot prove X caused Y") is a disclaimer or
        # negative finding, not an assertive causal claim — downgrade any causal
        # classification so downstream ledgers never record it as positive
        # mechanistic support. The warrant engine additionally short-circuits
        # negated claims as honest disclaimers.
        if negated and causal_strength in (
            CausalStrength.COUNTERFACTUAL_CAUSAL,
            CausalStrength.HYPOTHESIZED_CAUSAL,
            CausalStrength.MECHANISTIC_DRIVER,
        ):
            causal_strength = CausalStrength.NONE
            rel_type = ClaimRelationshipType.CORRELATION
            claim_class = ClaimClass.DESCRIPTIVE
            mech_depth = MechanismDepth.BLACK_BOX

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
# 2b. Assertive Causal-Language Detector (shared with BNS-013 verify)
# ==============================================================================

_ASSERTIVE_CAUSAL_RE = re.compile(
    r"\b(?:drives?|driven|causes?|caused|induces?|induced|triggers?|triggered|"
    r"proves?|proven|proving|mechanism of action|is causal|confers?)\b",
    re.IGNORECASE,
)

# A negation cue within the preceding window (same sentence, <=48 chars) scopes
# the causal term into a disclaimer: "does not drive", "cannot prove ... caused".
_NEGATION_CUE_RE = re.compile(
    r"\b(?:not|no|never|cannot|can't|without|fails? to|unable to|"
    r"neither)\b[^.;]{0,48}$",
    re.IGNORECASE,
)


def detect_assertive_causal_language(text: str) -> Optional[str]:
    """
    Return the first ASSERTIVE causal-language hit in `text`, or None.

    Hits preceded by a negation cue (e.g. "does not drive", "cannot prove ...
    caused", "no evidence that X induces Y") are disclaimers, not assertions,
    and are skipped. This is the single shared detector behind `bionexus verify`
    so the firewall never flags honest negative findings as overclaims.
    Heuristic by design: documented precision/recall limits (INV-009).
    """
    for match in _ASSERTIVE_CAUSAL_RE.finditer(text):
        window = text[max(0, match.start() - 48):match.start()]
        if _NEGATION_CUE_RE.search(window):
            continue
        return match.group(0)
    return None


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

        population_requested = claim.generalization_scope == GeneralizationScope.POPULATION_GENERAL
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
            else f"Population-level generalization across '{claim.population_scope}' lacks n>=3 biological replicates.",
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
            rationale="Mechanistic cascade verified by functional perturbation/kinetics."
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
            rationale="Causal identifiability verified via perturbation or structural causal DAG."
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
        clinical_requested = claim.clinical_actionability in (
            ClinicalActionability.PRESCRIPTIVE_TREATMENT,
            ClinicalActionability.DIAGNOSTIC_ASSERTION,
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
            rationale="Clinical certification, intended-use ground truth, and independent validation verified."
            if clinical_requested and clinical_warranted
            else "A clinical actionability claim was not requested."
            if not clinical_requested
            else "Clinical actionability is not warranted without certification, clinical ground truth, and independent validation.",
            missing_evidence=clinical_gaps,
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
        else:
            warranted_class = claim.claim_class

        # Determine evidence ceiling
        if not assoc_warranted:
            evidence_ceiling = ConclusionMaturity.ABSTAIN.value
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
            f"Claim '{claim.claim_id}' Epistemic Evaluation: "
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
        )


_NON_AUTHORIZING_GOVERNING_STATUSES = {
    "ABSTAIN",
    "NEEDS_DATA",
    "EXPERIMENTAL_CAPABILITY_REQUIRES_OPT_IN",
}


def enforce_governing_status(
    evaluation: WarrantEvaluationResult,
    governing_status: str,
) -> WarrantEvaluationResult:
    """Make a non-authorizing top-level route fail closed inside tier verdicts.

    Some consumers read only ``tier_verdicts``. Therefore a top-level refusal
    cannot coexist with a positive tier that those consumers could mistake for
    authorization. Existing negative and not-applicable tiers are preserved;
    positive tiers become explicitly ``NOT_ASSESSED`` because the governing
    preconditions prevented an authorizing assessment.
    """

    normalized = str(getattr(governing_status, "value", governing_status)).upper()
    evaluation.governing_status = normalized
    if normalized not in _NON_AUTHORIZING_GOVERNING_STATUSES:
        return evaluation

    for verdict in evaluation.tier_verdicts.values():
        if verdict.status in (
            WarrantTierStatus.WARRANTED,
            WarrantTierStatus.WARRANTED_WITH_LIMITS,
        ):
            verdict.status = WarrantTierStatus.NOT_ASSESSED
            verdict.is_warranted = False
            verdict.rationale = (
                f"Not authoritatively assessed because the governing route returned {normalized}. "
                "Resolve the top-level refusal or missing-data state before using this tier."
            )
            if "governing_route_authorization" not in verdict.missing_evidence:
                verdict.missing_evidence.append("governing_route_authorization")

    evaluation.is_fully_warranted = False
    evaluation.warranted_claim_class = ClaimClass.DESCRIPTIVE.value
    evaluation.evidence_ceiling = ConclusionMaturity.ABSTAIN.value
    gap = f"governing_status_{normalized.lower()}"
    if gap not in evaluation.evidence_gaps:
        evaluation.evidence_gaps.append(gap)
        evaluation.evidence_gaps.sort()
    evaluation.epistemic_summary = (
        f"Claim '{evaluation.claim_id}' is not scientifically authorized: governing status {normalized}. "
        "Positive tier verdicts were replaced with NOT_ASSESSED; existing negative and not-applicable verdicts remain visible."
    )
    return evaluation


# ==============================================================================
# 4. Cognitive Evolution: JSON-Schema, Decomposition, & Counterfactuals
# ==============================================================================


def get_scientific_claim_ir_schema() -> Dict[str, Any]:
    """Generate language-agnostic JSON-Schema for ScientificClaimIR.

    Enables LLM constrained decoding (Structured Outputs) to guarantee 100% valid
    deterministic semantic compilation from scientific literature or agent transcripts.
    """
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "ScientificClaimIR",
        "type": "object",
        "description": "Typed intermediate representation of a biological claim (BNS-017).",
        "properties": {
            "claim_id": {"type": "string", "description": "Unique identifier for the claim."},
            "raw_text": {"type": "string", "description": "Original raw natural language statement."},
            "subject_entity": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "entity_type": {"type": "string"},
                    "features": {"type": "array", "items": {"type": "string"}},
                    "raw_span": {"type": "string"},
                },
                "required": ["name"],
            },
            "object_entity": {
                "type": ["object", "null"],
                "properties": {
                    "name": {"type": "string"},
                    "entity_type": {"type": "string"},
                    "features": {"type": "array", "items": {"type": "string"}},
                    "raw_span": {"type": "string"},
                },
            },
            "relationship": {
                "type": "string",
                "enum": [r.value for r in ClaimRelationshipType],
            },
            "direction": {
                "type": "string",
                "enum": [d.value for d in Directionality],
            },
            "association_type": {
                "type": "string",
                "enum": [a.value for a in AssociationType],
            },
            "causal_strength": {
                "type": "string",
                "enum": [c.value for c in CausalStrength],
            },
            "generalization_scope": {
                "type": "string",
                "enum": [g.value for g in GeneralizationScope],
            },
            "mechanism_depth": {
                "type": "string",
                "enum": [m.value for m in MechanismDepth],
            },
            "clinical_actionability": {
                "type": "string",
                "enum": [cl.value for cl in ClinicalActionability],
            },
            "claim_class": {
                "type": "string",
                "enum": [cc.value for cc in ClaimClass],
            },
            "qualifiers": {
                "type": "array",
                "items": {"type": "string"},
            },
            "negation": {"type": "boolean"},
            "population_scope": {"type": "string"},
            "evidence_ledger_ref": {"type": ["string", "null"]},
        },
        "required": [
            "claim_id",
            "raw_text",
            "subject_entity",
            "relationship",
            "direction",
            "association_type",
            "causal_strength",
            "generalization_scope",
            "mechanism_depth",
            "clinical_actionability",
            "claim_class",
        ],
    }


def decompose_compound_claim(text: str) -> List[ScientificClaimIR]:
    """Decompose complex compound scientific prose into atomic ScientificClaimIR records.

    Splits multi-clause sentences linked by causal/mechanistic connectives (e.g.
    'which drives', 'and thereby induces', 'leading to', ';') and parses each
    atomic proposition while preserving relational context.
    """
    if not text or not text.strip():
        return []

    split_pattern = re.compile(
        r"(?:;|\bwhich\s+(?:in\s+turn\s+)?(?:drives|causes|induces|promotes|suppresses|mediates|suggests|indicates|leads\s+to)\b|"
        r"\band\s+thereby\b|\band\s+consequently\b|\band\s+therefore\b|\bmoreover,\s+|\bfurthermore,\s+)",
        re.IGNORECASE,
    )

    raw_clauses = split_pattern.split(text)
    clauses = [c.strip() for c in raw_clauses if c.strip() and len(c.strip()) > 3]

    if not clauses:
        clauses = [text.strip()]

    decomposed: List[ScientificClaimIR] = []

    for i, clause in enumerate(clauses):
        claim_id = f"atomic_claim_{i+1:02d}"
        atomic_ir = DeterministicClaimParser.parse(clause, claim_id=claim_id)
        if len(clauses) > 1:
            atomic_ir.qualifiers.append(f"decomposed_clause_{i+1}_of_{len(clauses)}")
            if i > 0:
                atomic_ir.qualifiers.append(f"upstream_clause:atomic_claim_{i:02d}")
        decomposed.append(atomic_ir)

    return decomposed


def generate_counterfactual_warrant_advice(
    claim: ScientificClaimIR,
    facts: EvidenceProfile,
    evaluation: WarrantEvaluationResult,
) -> List[Dict[str, Any]]:
    """Compute minimal counterfactual evidence delta required to upgrade warrant standing.

    Tells scientists and agents precisely what wet-lab experiments or analytical
    adjustments will promote a FRAGILE/NOT_WARRANTED claim to SUPPORTED or ROBUST.
    """
    advice: List[Dict[str, Any]] = []

    # 1. Check unwarranted tiers
    for tier_name, verdict in evaluation.tier_verdicts.items():
        if not verdict.is_warranted:
            if tier_name == "population_claim":
                advice.append({
                    "target_tier": tier_name,
                    "target_status": WarrantTierStatus.WARRANTED.value,
                    "target_ceiling": ConclusionMaturity.SUPPORTED.value,
                    "missing_facts": {
                        "biological_replicates_count": ">= 3 (currently %d)" % facts.biological_replicates_count,
                        "pseudobulk_aggregated": "True (currently %s)" % str(facts.pseudobulk_aggregated),
                    },
                    "actionable_remediation": (
                        "Collect at least %d additional biological replicate donor(s) and aggregate single-cell counts "
                        "into sample-level pseudobulk before statistical testing (Squair et al. 2021)."
                        % max(1, 3 - facts.biological_replicates_count)
                    ),
                })
            elif tier_name == "causal_claim":
                advice.append({
                    "target_tier": tier_name,
                    "target_status": WarrantTierStatus.WARRANTED.value,
                    "target_ceiling": ConclusionMaturity.ROBUST.value,
                    "missing_facts": {
                        "perturbation": "True (currently False)",
                        "causal_identification_status": "'BACKDOOR_SATISFIED' or 'FRONTDOOR_SATISFIED'",
                    },
                    "actionable_remediation": (
                        "Perform targeted genetic perturbation (CRISPR KO / knockdown) or construct a structural causal DAG "
                        "satisfying Backdoor or Frontdoor criterion to justify counterfactual causal language."
                    ),
                })
            elif tier_name == "mechanistic_claim":
                advice.append({
                    "target_tier": tier_name,
                    "target_status": WarrantTierStatus.WARRANTED.value,
                    "target_ceiling": ConclusionMaturity.SUPPORTED.value,
                    "missing_facts": {
                        "perturbation": "True",
                        "temporal_evidence": "True",
                    },
                    "actionable_remediation": (
                        "Provide functional rescue/inhibition assay data or longitudinal time-series kinetics to prove "
                        "intermediate directional signaling."
                    ),
                })
            elif tier_name == "cell_identity_claim":
                advice.append({
                    "target_tier": tier_name,
                    "target_status": WarrantTierStatus.WARRANTED.value,
                    "target_ceiling": ConclusionMaturity.SUPPORTED.value,
                    "missing_facts": {
                        "reference_ground_truth": "True",
                        "qualifiers": "Include 'putative' or 'candidate'",
                    },
                    "actionable_remediation": (
                        "Map against an established reference atlas (e.g. Azimuth/CellTypist) with CITE-seq/FACS sorting, "
                        "or prepend 'candidate' / 'putative' to marker-inferred labels."
                    ),
                })
            elif tier_name == "clinical_claim":
                advice.append({
                    "target_tier": tier_name,
                    "target_status": WarrantTierStatus.PROHIBITED.value,
                    "target_ceiling": ConclusionMaturity.ABSTAIN.value,
                    "missing_facts": {
                        "regulatory_certification": "CLIA/CAP or FDA approved device",
                    },
                    "actionable_remediation": (
                        "Clinical actionability is strictly prohibited on Research Use Only (RUO) software. "
                        "Restructure claim as exploratory basic biomarker discovery."
                    ),
                })

    # 2. If all tiers are warranted, advise on reaching higher maturity (ROBUST / REPLICATED)
    if evaluation.is_fully_warranted:
        if evaluation.evidence_ceiling == ConclusionMaturity.SUPPORTED.value:
            if not facts.independent_validation:
                advice.append({
                    "target_tier": "overall_maturity",
                    "target_status": WarrantTierStatus.WARRANTED.value,
                    "target_ceiling": ConclusionMaturity.REPLICATED.value,
                    "missing_facts": {
                        "independent_validation": "True (currently False)",
                    },
                    "actionable_remediation": (
                        "Validate top candidates in an independent held-out patient cohort to upgrade evidence standing "
                        "from SUPPORTED to REPLICATED."
                    ),
                })
            if not facts.perturbation:
                advice.append({
                    "target_tier": "overall_maturity",
                    "target_status": WarrantTierStatus.WARRANTED.value,
                    "target_ceiling": ConclusionMaturity.ROBUST.value,
                    "missing_facts": {
                        "perturbation": "True (currently False)",
                        "biological_replicates_count": ">= 3",
                    },
                    "actionable_remediation": (
                        "Couple observational findings with functional in vitro perturbation across >=3 biological replicates "
                        "to upgrade to ROBUST evidence."
                    ),
                })

    return advice
