"""Connector Profile Registry and Scientific Contracts for BioNexus (BNS-025 / BNS-019).

Decouples BioNexus Core from connector transport/marketplace mechanics.
Defines declarative scientific output contracts across two decoupled dimensions:
    ScientificDomain × EvidenceProductionMode
Specifies required provenance context, epistemic maturity ceilings, prohibited claims,
and non-evidence communication safeguards.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple, Union

import yaml

from bionexus.contracts import _MATURITY_RANK, ConclusionMaturity
from bionexus.ecosystem_intake import ExternalEvidenceEnvelope
from bionexus.epistemic_lineage import EpistemicLineage, OriginType

DEFAULT_PROFILES_DIR = (
    Path(__file__).resolve().parents[2]
    / "standards"
    / "connector-profiles"
    / "profiles"
)


class ScientificDomain(str, Enum):
    """Scientific knowledge domain under BNS-025."""

    LITERATURE = "literature"
    CHEMISTRY = "chemistry"
    GENOMICS = "genomics"
    FUNCTIONAL_GENOMICS = "functional_genomics"
    TRANSCRIPTOMICS = "transcriptomics"
    PATHOLOGY = "pathology"
    CLINICAL = "clinical"
    REGULATORY = "regulatory"
    LAB_RECORD = "lab_record"
    STRUCTURE = "structure"
    COMMUNICATION = "communication"


class EvidenceProductionMode(str, Enum):
    """Epistemic mode of evidence generation under BNS-025."""

    RETRIEVAL = "retrieval"
    OBSERVATION = "observation"
    EXPERIMENT = "experiment"
    STATISTICAL_ANALYSIS = "statistical_analysis"
    COMPUTATIONAL_INFERENCE = "computational_inference"
    MODEL_PREDICTION = "model_prediction"
    GENERATIVE_MODEL = "generative_model"
    WORKFLOW_EXECUTION = "workflow_execution"
    HUMAN_ANNOTATION = "human_annotation"
    SYNTHESIS = "synthesis"


@dataclass(frozen=True)
class ConnectorProfile:
    """Scientific contract for connector output (BNS-025 / BNS-019)."""

    connector: str
    tool: str
    production_mode: Union[str, EvidenceProductionMode]
    domain: Union[str, ScientificDomain]
    required_context: Tuple[str, ...] = ()
    default_evidence_role: str = "supporting"
    maximum_default_claim: str = "preliminary"
    forbidden_claims: Tuple[str, ...] = ()
    semantic_profile: Dict[str, Any] = field(default_factory=dict)
    independence: Any = None
    epistemic_lineage_mapping: Dict[str, Any] = field(default_factory=dict)
    scientific_object_type: str = "unspecified"
    allows_scientific_evidence: bool = True
    allowed_claim_types: Tuple[str, ...] = ("descriptive", "associative")

    @property
    def connector_id(self) -> str:
        return self.connector

    @property
    def tool_name(self) -> str:
        return self.tool

    @property
    def default_max_claim_maturity(self) -> str:
        norm = str(self.maximum_default_claim).upper()
        if norm in _MATURITY_RANK:
            return norm
        if norm in ("PATHWAY_ASSOCIATION", "REPORTED_ASSOCIATION", "ASSOCIATIVE", "PRELIMINARY"):
            return ConclusionMaturity.PRELIMINARY.value
        if norm in ("ROBUST_CORRELATION", "SUPPORTED"):
            return ConclusionMaturity.SUPPORTED.value
        return ConclusionMaturity.PRELIMINARY.value

    @property
    def prohibited_claims(self) -> Tuple[str, ...]:
        return self.forbidden_claims

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ConnectorProfile":
        d = dict(data)
        req_ctx = tuple(d.get("required_context", ()))
        forbidden = tuple(d.get("forbidden_claims", ()))
        sem_prof = dict(d.get("semantic_profile") or {})
        lineage_map = dict(d.get("epistemic_lineage_mapping") or {})

        return cls(
            connector=str(d.get("connector", "")),
            tool=str(d.get("tool", "")),
            production_mode=str(d.get("production_mode", "")),
            domain=str(d.get("domain", "")),
            required_context=req_ctx,
            default_evidence_role=str(d.get("default_evidence_role", "supporting")),
            maximum_default_claim=str(d.get("maximum_default_claim", "")),
            forbidden_claims=forbidden,
            semantic_profile=sem_prof,
            independence=d.get("independence"),
            epistemic_lineage_mapping=lineage_map,
            scientific_object_type=str(d.get("scientific_object_type", "unspecified")),
            allows_scientific_evidence=bool(d.get("allows_scientific_evidence", True)),
            allowed_claim_types=tuple(d.get("allowed_claim_types", ("descriptive", "associative"))),
        )

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "connector": self.connector,
            "tool": self.tool,
            "production_mode": self.production_mode.value if isinstance(self.production_mode, Enum) else str(self.production_mode),
            "domain": self.domain.value if isinstance(self.domain, Enum) else str(self.domain),
            "required_context": list(self.required_context),
            "default_evidence_role": self.default_evidence_role,
            "maximum_default_claim": self.maximum_default_claim,
            "forbidden_claims": list(self.forbidden_claims),
            "semantic_profile": dict(self.semantic_profile),
        }
        if self.independence is not None:
            d["independence"] = self.independence
        if self.epistemic_lineage_mapping:
            d["epistemic_lineage_mapping"] = dict(self.epistemic_lineage_mapping)
        return d


@dataclass(frozen=True)
class ProfileAuditResult:
    valid: bool
    status: str
    errors: Tuple[str, ...]
    warnings: Tuple[str, ...]
    profile: ConnectorProfile
    derived_lineage: Optional[Dict[str, Any]] = None
    derived_semantic_profile: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["errors"] = list(self.errors)
        d["warnings"] = list(self.warnings)
        return d


# In-memory registry of canonical profiles
_CANONICAL_PROFILES: Dict[str, ConnectorProfile] = {}


def register_connector_profile(profile: ConnectorProfile) -> None:
    """Register a ConnectorProfile in the active in-memory catalog."""
    key = f"{profile.connector}:{profile.tool}"
    _CANONICAL_PROFILES[key] = profile
    if profile.connector not in _CANONICAL_PROFILES:
        _CANONICAL_PROFILES[profile.connector] = profile
    if profile.tool not in _CANONICAL_PROFILES:
        _CANONICAL_PROFILES[profile.tool] = profile


def _init_canonical_catalog() -> None:
    """Initialize canonical tool profiles for major scientific connectors (BNS-025)."""
    canonical_list = [
        ConnectorProfile(
            connector="pubmed",
            tool="search_pubmed",
            domain=ScientificDomain.LITERATURE,
            production_mode=EvidenceProductionMode.RETRIEVAL,
            scientific_object_type="published_abstract_record",
            required_context=("query", "pmid", "publication_status"),
            default_evidence_role="supporting",
            maximum_default_claim="preliminary",
            forbidden_claims=("consensus_proven", "causality", "independent_experimental_replication"),
            semantic_profile={"claim.type": "associative", "evidence.type": ["primary_literature"]},
        ),
        ConnectorProfile(
            connector="consensus",
            tool="synthesize_literature",
            domain=ScientificDomain.LITERATURE,
            production_mode=EvidenceProductionMode.SYNTHESIS,
            scientific_object_type="synthesized_evidence_summary",
            required_context=("query", "source_count", "synthesis_model"),
            default_evidence_role="supporting",
            maximum_default_claim="preliminary",
            forbidden_claims=("independent_experimental_replication", "causality", "clinical_guideline_standard"),
            semantic_profile={"claim.type": "associative", "evidence.type": ["systematic_review"]},
        ),
        ConnectorProfile(
            connector="chembl",
            tool="query_chembl",
            domain=ScientificDomain.CHEMISTRY,
            production_mode=EvidenceProductionMode.EXPERIMENT,
            scientific_object_type="bioactivity_measurement",
            required_context=("target_id", "molecule_chembl_id", "assay_id", "standard_type", "standard_value"),
            default_evidence_role="supporting",
            maximum_default_claim="supported",
            forbidden_claims=("in_vivo_efficacy", "clinical_safety"),
            semantic_profile={"claim.type": "bioactivity", "evidence.type": ["in_vitro_assay"]},
        ),
        ConnectorProfile(
            connector="enrichr",
            tool="enrich_gene_set",
            domain=ScientificDomain.FUNCTIONAL_GENOMICS,
            production_mode=EvidenceProductionMode.COMPUTATIONAL_INFERENCE,
            scientific_object_type="pathway_enrichment_table",
            required_context=("gene_list", "library_name", "adjusted_p_value"),
            default_evidence_role="supporting",
            maximum_default_claim="preliminary",
            forbidden_claims=("causal_mechanism", "pathway_activation_proven", "clinical_actionability"),
            semantic_profile={"claim.type": "associative", "evidence.type": ["computational_inference"]},
        ),
        ConnectorProfile(
            connector="owkin",
            tool="analyze_cohort_histology",
            domain=ScientificDomain.PATHOLOGY,
            production_mode=EvidenceProductionMode.STATISTICAL_ANALYSIS,
            scientific_object_type="spatial_histology_biomarker_score",
            required_context=("cohort_id", "slide_count", "model_version", "hazard_ratio"),
            default_evidence_role="supporting",
            maximum_default_claim="supported",
            forbidden_claims=("mechanistic_causality", "cross_cohort_generalization_without_replication"),
            semantic_profile={"claim.type": "prognostic", "evidence.type": ["cohort_histology"]},
        ),
        ConnectorProfile(
            connector="synthesize_bio",
            tool="predict_perturbation_expression",
            domain=ScientificDomain.TRANSCRIPTOMICS,
            production_mode=EvidenceProductionMode.MODEL_PREDICTION,
            scientific_object_type="in_silico_perturbation_response",
            required_context=("target_gene", "cell_type", "model_checkpoint", "confidence_interval"),
            default_evidence_role="supporting",
            maximum_default_claim="preliminary",
            forbidden_claims=("in_vivo_validation", "established_mechanism", "independent_replication"),
            semantic_profile={"claim.type": "predictive", "evidence.type": ["in_silico_model"]},
        ),
        ConnectorProfile(
            connector="eden",
            tool="generate_small_molecule_candidates",
            domain=ScientificDomain.CHEMISTRY,
            production_mode=EvidenceProductionMode.GENERATIVE_MODEL,
            scientific_object_type="generative_chemical_structure",
            required_context=("target_pocket", "generation_seed", "docking_score"),
            default_evidence_role="supporting",
            maximum_default_claim="preliminary",
            forbidden_claims=("synthesizability_guarantee", "in_vivo_potency"),
            semantic_profile={"claim.type": "candidate_structure", "evidence.type": ["generative_design"]},
        ),
        ConnectorProfile(
            connector="inductive_bio",
            tool="predict_admet_properties",
            domain=ScientificDomain.CHEMISTRY,
            production_mode=EvidenceProductionMode.MODEL_PREDICTION,
            scientific_object_type="predicted_admet_profile",
            required_context=("smiles", "property_endpoint", "model_version", "uncertainty_score"),
            default_evidence_role="supporting",
            maximum_default_claim="preliminary",
            forbidden_claims=("clinical_pharmacokinetics", "regulatory_toxicology_clearance"),
            semantic_profile={"claim.type": "predictive", "evidence.type": ["qsar_model"]},
        ),
        ConnectorProfile(
            connector="latchbio",
            tool="run_workflow_execution",
            domain=ScientificDomain.GENOMICS,
            production_mode=EvidenceProductionMode.WORKFLOW_EXECUTION,
            scientific_object_type="reproducible_pipeline_output",
            required_context=("workflow_id", "execution_digest", "container_sha256"),
            default_evidence_role="supporting",
            maximum_default_claim="preliminary",
            forbidden_claims=("biological_validation",),
            semantic_profile={"claim.type": "computational_result", "evidence.type": ["workflow_execution"]},
        ),
        ConnectorProfile(
            connector="scispot",
            tool="query_electronic_lab_record",
            domain=ScientificDomain.LAB_RECORD,
            production_mode=EvidenceProductionMode.OBSERVATION,
            scientific_object_type="eln_experimental_record",
            required_context=("notebook_id", "entry_id", "operator_id", "timestamp"),
            default_evidence_role="supporting",
            maximum_default_claim="preliminary",
            forbidden_claims=("multi_site_reproducibility",),
            semantic_profile={"claim.type": "observational", "evidence.type": ["eln_record"]},
        ),
        ConnectorProfile(
            connector="revvity",
            tool="read_plate_reader_data",
            domain=ScientificDomain.LAB_RECORD,
            production_mode=EvidenceProductionMode.OBSERVATION,
            scientific_object_type="raw_instrument_signal",
            required_context=("instrument_serial", "run_id", "channel", "blank_subtraction"),
            default_evidence_role="supporting",
            maximum_default_claim="preliminary",
            forbidden_claims=("causality",),
            semantic_profile={"claim.type": "observational", "evidence.type": ["instrument_data"]},
        ),
        ConnectorProfile(
            connector="dalea",
            tool="annotate_scientific_literature",
            domain=ScientificDomain.LAB_RECORD,
            production_mode=EvidenceProductionMode.HUMAN_ANNOTATION,
            scientific_object_type="curated_expert_annotation",
            required_context=("annotator_id", "ontology_version", "guideline_adherence"),
            default_evidence_role="supporting",
            maximum_default_claim="preliminary",
            forbidden_claims=("independent_experimental_replication",),
            semantic_profile={"claim.type": "annotative", "evidence.type": ["human_curation"]},
        ),
        ConnectorProfile(
            connector="cortellis",
            tool="lookup_regulatory_intelligence",
            domain=ScientificDomain.REGULATORY,
            production_mode=EvidenceProductionMode.RETRIEVAL,
            scientific_object_type="regulatory_approval_status",
            required_context=("drug_id", "jurisdiction", "approval_date"),
            default_evidence_role="supporting",
            maximum_default_claim="preliminary",
            forbidden_claims=("mechanistic_efficacy",),
            semantic_profile={"claim.type": "regulatory", "evidence.type": ["regulatory_filing"]},
        ),
        ConnectorProfile(
            connector="biorender",
            tool="export_scientific_diagram",
            domain=ScientificDomain.COMMUNICATION,
            production_mode=EvidenceProductionMode.GENERATIVE_MODEL,
            scientific_object_type="visual_communication_asset",
            required_context=("canvas_id", "asset_export_format"),
            default_evidence_role="context_only",
            maximum_default_claim="UNASSESSED",
            forbidden_claims=("scientific_evidence", "experimental_finding", "causal_mechanism"),
            allows_scientific_evidence=False,
            semantic_profile={"claim.type": "illustration", "evidence.type": ["diagram"]},
        ),
        # ChatGPT Rosalind standard tools
        ConnectorProfile(
            connector="chatgpt-rosalind",
            tool="search_uniprot",
            domain=ScientificDomain.GENOMICS,
            production_mode=EvidenceProductionMode.RETRIEVAL,
            scientific_object_type="curated_protein_record",
            required_context=("query", "source_name", "record_ids"),
            default_evidence_role="supporting",
            maximum_default_claim="preliminary",
            forbidden_claims=("independent_experimental_validation", "causality"),
            semantic_profile={"claim.type": "descriptive", "evidence.type": ["curated_database"]},
        ),
        ConnectorProfile(
            connector="chatgpt-rosalind",
            tool="search_pdb",
            domain=ScientificDomain.STRUCTURE,
            production_mode=EvidenceProductionMode.OBSERVATION,
            scientific_object_type="experimental_macromolecular_structure",
            required_context=("pdb_id", "structure_source", "resolution"),
            default_evidence_role="supporting",
            maximum_default_claim="supported",
            forbidden_claims=("in_vivo_binding",),
            semantic_profile={"claim.type": "structural", "evidence.type": ["xray_or_cryoem"]},
        ),
        ConnectorProfile(
            connector="chatgpt-rosalind",
            tool="search_alphafold",
            domain=ScientificDomain.STRUCTURE,
            production_mode=EvidenceProductionMode.MODEL_PREDICTION,
            scientific_object_type="predicted_3d_coordinates",
            required_context=("uniprot_id", "plddt", "structure_version"),
            default_evidence_role="supporting",
            maximum_default_claim="preliminary",
            forbidden_claims=("experimental_structure_ground_truth", "dynamic_conformation_proof"),
            semantic_profile={"claim.type": "structural_prediction", "evidence.type": ["alphafold_prediction"]},
        ),
        ConnectorProfile(
            connector="chatgpt-rosalind",
            tool="run_pseudobulk_de",
            domain=ScientificDomain.TRANSCRIPTOMICS,
            production_mode=EvidenceProductionMode.STATISTICAL_ANALYSIS,
            scientific_object_type="differential_expression_summary",
            required_context=("dataset_id", "contrast_column", "log2FoldChange", "padj"),
            default_evidence_role="supporting",
            maximum_default_claim="supported",
            forbidden_claims=("direct_causality_without_knockout",),
            semantic_profile={"claim.type": "associative", "evidence.type": ["pseudobulk_de"]},
        ),
    ]
    for p in canonical_list:
        register_connector_profile(p)


_init_canonical_catalog()


def load_connector_profile(path_or_name: str | Path) -> ConnectorProfile:
    """Load a Connector Profile from a filepath or canonical profile name."""
    p = Path(path_or_name)
    if not p.is_file():
        candidate = DEFAULT_PROFILES_DIR / f"{path_or_name}.yaml"
        if candidate.is_file():
            p = candidate
        else:
            candidate_json = DEFAULT_PROFILES_DIR / f"{path_or_name}.json"
            if candidate_json.is_file():
                p = candidate_json
            else:
                # Check canonical in-memory catalog
                name_str = str(path_or_name)
                if name_str in _CANONICAL_PROFILES:
                    return _CANONICAL_PROFILES[name_str]
                raise FileNotFoundError(f"Connector profile not found: {path_or_name}")

    text = p.read_text(encoding="utf-8")
    if p.suffix in (".yaml", ".yml"):
        data = yaml.safe_load(text)
    else:
        data = json.loads(text)

    if not isinstance(data, dict):
        raise ValueError(f"Profile file {p} must contain a dictionary")

    return ConnectorProfile.from_dict(data)


def list_connector_profiles(
    profiles_dir: Optional[Path] = None,
) -> Dict[str, ConnectorProfile]:
    """Scan and list all community connector profiles in the registry."""
    root = profiles_dir or DEFAULT_PROFILES_DIR
    profiles: Dict[str, ConnectorProfile] = dict(_CANONICAL_PROFILES)

    if root.is_dir():
        for item in sorted(root.glob("*.yaml")) + sorted(root.glob("*.yml")) + sorted(root.glob("*.json")):
            try:
                prof = load_connector_profile(item)
                key = f"{prof.connector}:{prof.tool}"
                profiles[key] = prof
                if prof.connector not in profiles:
                    profiles[prof.connector] = prof
            except Exception:
                continue

    return profiles


def get_connector_profile(
    connector_id: str,
    tool_name: Optional[str] = None,
) -> Optional[ConnectorProfile]:
    """Retrieve a connector profile by connector ID and optional tool name."""
    if tool_name:
        key = f"{connector_id}:{tool_name}"
        if key in _CANONICAL_PROFILES:
            return _CANONICAL_PROFILES[key]

    if connector_id in _CANONICAL_PROFILES:
        return _CANONICAL_PROFILES[connector_id]

    if tool_name and tool_name in _CANONICAL_PROFILES:
        return _CANONICAL_PROFILES[tool_name]

    # Try loading from filesystem
    try:
        return load_connector_profile(connector_id)
    except FileNotFoundError:
        return None


def audit_envelope_against_profile(
    envelope: ExternalEvidenceEnvelope,
    profile: ConnectorProfile,
    asserted_claim: Optional[str] = None,
) -> ProfileAuditResult:
    """Audit an ExternalEvidenceEnvelope against a declarative ConnectorProfile."""
    errors: List[str] = []
    warnings: List[str] = []

    # 1. Verify required context fields
    for req in profile.required_context:
        if req not in envelope.source_context:
            errors.append(f"Missing required context field: {req!r} for connector {profile.connector!r}")

    # 2. Check for forbidden claim violations
    if asserted_claim:
        claim_lower = asserted_claim.lower().replace(" ", "_").replace("-", "_")
        for forbidden in profile.forbidden_claims:
            forb_clean = forbidden.lower().replace(" ", "_").replace("-", "_")
            if forb_clean in claim_lower:
                errors.append(
                    f"Forbidden claim violation: {asserted_claim!r} asserts forbidden class {forbidden!r} "
                    f"for connector {profile.connector!r} (maximum allowed: {profile.maximum_default_claim!r})"
                )

    # 3. Derive or validate Epistemic Lineage according to profile
    lineage_map = profile.epistemic_lineage_mapping
    ctx = envelope.source_context
    origin_id = None
    if lineage_map.get("origin_id_field") and lineage_map["origin_id_field"] in ctx:
        val = ctx[lineage_map["origin_id_field"]]
        origin_id = str(val[0]) if isinstance(val, (list, tuple)) and val else str(val)

    origin_type = lineage_map.get("origin_type") or OriginType.UNKNOWN.value
    dataset_id = None
    if lineage_map.get("dataset_identity_field") and lineage_map["dataset_identity_field"] in ctx:
        val = ctx[lineage_map["dataset_identity_field"]]
        dataset_id = str(val)

    assay_id = None
    if lineage_map.get("assay_identity_field") and lineage_map["assay_identity_field"] in ctx:
        val = ctx[lineage_map["assay_identity_field"]]
        assay_id = str(val[0]) if isinstance(val, (list, tuple)) and val else str(val)

    derived_lineage = EpistemicLineage(
        origin_id=origin_id,
        origin_type=origin_type,
        dataset_identity=dataset_id,
        assay_identity=assay_id,
    ).to_dict()

    derived_semantics = dict(profile.semantic_profile)

    status = "VALID" if not errors else "INVALID"
    return ProfileAuditResult(
        valid=not errors,
        status=status,
        errors=tuple(errors),
        warnings=tuple(warnings),
        profile=profile,
        derived_lineage=derived_lineage if derived_lineage else None,
        derived_semantic_profile=derived_semantics,
    )


def audit_connector_claim(
    profile: ConnectorProfile,
    target_claim_statement: str,
    claimed_maturity: str,
    claim_class: Optional[str] = None,
) -> Tuple[bool, str, List[str]]:
    """Audit a proposed scientific claim against a ConnectorProfile.

    Returns:
        (is_warranted, adjusted_maturity, reasons)
    """
    reasons: List[str] = []
    adjusted_maturity = claimed_maturity

    # 1. Non-evidence tools cannot warrant scientific claims
    if not profile.allows_scientific_evidence:
        reasons.append(
            f"Connector '{profile.connector_id}' produces communication artifacts only "
            f"and is strictly prohibited from serving as scientific evidence."
        )
        return False, ConclusionMaturity.UNASSESSED.value, reasons

    # 2. Check claim class compatibility if provided
    if claim_class and claim_class not in profile.allowed_claim_types:
        reasons.append(
            f"Claim class '{claim_class}' is not in allowed claim types "
            f"{profile.allowed_claim_types} for capability {profile.tool_name}."
        )
        adjusted_maturity = ConclusionMaturity.FRAGILE.value

    # 3. Check prohibited inferences via substring or regex matching
    statement_lower = target_claim_statement.lower()
    for prohibited in profile.prohibited_claims:
        p_lower = prohibited.lower().replace("_", " ")
        patterns = [p_lower]
        if p_lower == "causality" or p_lower == "mechanistic causality":
            patterns.extend(["causal", "cause", "causes", "caused", "causing"])
        elif p_lower == "consensus" or p_lower == "consensus proven":
            patterns.extend(["general agreement", "established consensus"])
        elif p_lower == "in vivo validation":
            patterns.extend(["in vivo", "animal model", "mouse model"])

        if any(pat in statement_lower for pat in patterns):
            reasons.append(
                f"Claim statement touches prohibited inference '{prohibited}' for "
                f"{profile.domain} × {profile.production_mode} capability."
            )
            if _MATURITY_RANK.get(adjusted_maturity, 0) > _MATURITY_RANK.get("FRAGILE", 0):
                adjusted_maturity = "FRAGILE"

    # 4. Enforce epistemic maturity ceiling
    max_rank = _MATURITY_RANK.get(profile.default_max_claim_maturity, 0)
    current_rank = _MATURITY_RANK.get(adjusted_maturity, 0)
    if current_rank > max_rank:
        adjusted_maturity = profile.default_max_claim_maturity
        reasons.append(
            f"Claimed maturity '{claimed_maturity}' exceeds connector '{profile.connector_id}' "
            f"epistemic ceiling '{profile.default_max_claim_maturity}'."
        )

    is_warranted = bool(adjusted_maturity == claimed_maturity and not any("prohibited" in r for r in reasons))
    return is_warranted, adjusted_maturity, reasons
