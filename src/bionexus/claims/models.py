"""
Data models, enums, dataclasses, and JSON schema for BioNexus Scientific Claims (BNS-017).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from bionexus.evidence_model import ClaimClass


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
    STRUCTURAL_CONFORMATION = "structural_conformation"  # 3D folding, binding pocket, conformational state
    BIOACTIVE_BINDING = "bioactive_binding"  # Small-molecule target affinity, IC50/Kd inhibition



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
    negated: bool = False  # True if statement asserts absence of effect or disclaims proof
    negation_type: str = "NONE"  # "NONE" | "ABSENCE_OF_EVIDENCE" | "EVIDENCE_OF_ABSENCE"
    is_epistemic_disclaimer: bool = False  # True if stating inability to prove / absence of evidence
    is_negative_assertion: bool = False  # True if asserting non-existence of effect / evidence of absence
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
            "negation_type": self.negation_type,
            "is_epistemic_disclaimer": self.is_epistemic_disclaimer,
            "is_negative_assertion": self.is_negative_assertion,
            "metadata": self.metadata,
        }


@dataclass
class EvidenceProfile:
    """
    Caller-declared premises for conditional rule evaluation, not verified facts.
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
    plddt_score: Optional[float] = None  # AlphaFold/ESMFold mean pLDDT confidence (0-100)
    interdomain_pae: Optional[float] = None  # Inter-domain Predicted Aligned Error in Angstroms
    bioactivity_nm: Optional[float] = None  # Small-molecule IC50 / Ki / Kd in nanomolar
    dose_response_curve: bool = True  # True if measured via full concentration titration


    def validate(self) -> None:
        import math
        values = asdict(self)
        for name, value in values.items():
            if name in {"plddt_score", "interdomain_pae", "bioactivity_nm"}:
                if value is not None and (type(value) not in (int, float) or not math.isfinite(value) or value < 0):
                    raise ValueError(f"{name} must be a finite nonnegative number or null")
            elif name == "biological_replicates_count":
                if type(value) is not int or value < 0:
                    raise ValueError("biological_replicates_count must be a nonnegative integer")
            elif name == "confound_controls":
                if not isinstance(value, list) or any(not isinstance(x, str) for x in value):
                    raise ValueError("confound_controls must be a string list")
            elif name == "causal_identification_status":
                if value not in {"UNASSESSED", "BACKDOOR_SATISFIED", "UNBLOCKED_BACKDOOR", "COLLIDER_BIAS"}:
                    raise ValueError("Unknown causal_identification_status")
            elif type(value) is not bool:
                raise ValueError(f"{name} requires a boolean declaration")

    def to_dict(self) -> Dict[str, Any]:
        self.validate()
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
            "assessment_basis": "CONDITIONAL_ON_DECLARED_PREMISES",
            "scientific_facts_verified": False,
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
    has_claim_conflict: bool = False
    conflict_details: Optional[str] = None

    @property
    def evidence_contract(self) -> Dict[str, Any]:
        from bionexus.evidence_contract import conditional_contract
        return conditional_contract(self.is_fully_warranted, support="EXPERIMENTAL",
                                    scope="Conditional rule result or scoped disclaimer; no underlying scientific premise was verified.")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "evidence_contract": self.evidence_contract,
            "legacy_field_semantics": "is_fully_warranted, warranted_claim_class, evidence_ceiling and tier verdicts are conditional calculations, not verified facts.",
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
            "has_claim_conflict": self.has_claim_conflict,
            "conflict_details": self.conflict_details,
        }




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


