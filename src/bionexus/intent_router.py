"""
BioNexus Scientific Intent & Invariant Router.

Evolves static skill discovery into a validated 6-stage Scientific Intent Pipeline:
1. Scientific Query/Prompt -> Extract Analytical Intent
2. Data Semantics Inspection (Raw counts vs Normalized floats, Spatial coords, Survival events)
3. Scientific Preconditions Verification (Biological replication, Non-degenerate geometry)
4. Capability Contract Matching (Canonical Capability vs Heuristic)
5. Backend Lifecycle Probe (Installed vs Missing vs Incompatible)
6. Deterministic Routing Decision
   (PERMITTED | NEEDS_DATA | ABSTAIN | DEGRADED_ADVISORY | EXPERIMENTAL_CAPABILITY_REQUIRES_OPT_IN)

Enforces what is scientifically legal and protects Host Agents from executing invalid analyses.

Gate order is normative: Scientific validity -> Execution fidelity -> Availability.
Backend readiness is bound to the Capability (canonical vs frontier track), never
to a skill's default/legacy classification (BNS-010 runtime isolation).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from bionexus.abi import detect_forbidden_claims_in_query
from bionexus.capabilities import (
    ALL_CAPABILITIES,
    FRONTIER_CAPABILITIES,
    CapabilityContract,
    find_capabilities_by_intent,
)
from bionexus.contracts import (
    EvidenceCard,
    ExecutionState,
)
from bionexus.integrity import audit_expression_matrix
from bionexus.research_purpose import (
    PurposeContext,
    ResearchPurpose,
    infer_research_purpose,
    purpose_from_string,
)
from bionexus.researcher_override import OverrideRecord, create_override_record


class RoutingStatus(str, Enum):
    """Status of the scientific routing decision."""

    PERMITTED = "PERMITTED"  # Analysis is scientifically valid, preconditions met, backend ready
    PERMITTED_WITH_LIMITS = "PERMITTED_WITH_LIMITS"  # Permitted with documented soft-limit overrides and evidence ceiling
    NEEDS_DATA = "NEEDS_DATA"  # Valid intent, but essential metadata or input artifacts are missing
    ABSTAIN = "ABSTAIN"  # Refused: Mathematically/biologically impossible or violates scientific invariants
    DEGRADED_ADVISORY = "DEGRADED_ADVISORY"  # Permitted with explicit notice of Grade C heuristic degradation
    EXPERIMENTAL_CAPABILITY_REQUIRES_OPT_IN = "EXPERIMENTAL_CAPABILITY_REQUIRES_OPT_IN"  # Frontier capability blocked until explicit opt-in (BNS-010)


@dataclass
class ScientificIntentRequest:
    """Input request describing the user's analytical goal and available data."""

    query: str
    intent_keywords: List[str] = field(default_factory=list)
    data_path: Optional[str] = None
    data_metadata: Dict[str, Any] = field(default_factory=dict)
    allow_degraded: bool = False
    # Purpose-aware fields
    research_purpose: Optional[str] = None  # exploratory | screening | confirmatory | causal | clinical
    override_justification: str = ""  # researcher override reason (empty = no override)


@dataclass
class RoutingDecision:
    """The authoritative decision and guidance emitted by the BioNexus Scientific Router."""

    status: RoutingStatus
    matched_capability: Optional[CapabilityContract]
    target_skill: Optional[str]
    recommended_script: Optional[str]
    recommended_command: Optional[str]
    rationale: str
    violations: List[str] = field(default_factory=list)
    remedies: List[str] = field(default_factory=list)
    missing_data_requests: List[str] = field(default_factory=list)
    evidence_card_template: Optional[EvidenceCard] = None
    # Purpose-aware fields
    purpose_context: Optional[PurposeContext] = None
    residual_limitations: List[str] = field(default_factory=list)
    blocked_claims: List[str] = field(default_factory=list)
    override_records: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert decision to dictionary."""
        d = {
            "status": self.status.value,
            "matched_capability_id": self.matched_capability.id if self.matched_capability else None,
            "target_skill": self.target_skill,
            "recommended_script": self.recommended_script,
            "recommended_command": self.recommended_command,
            "rationale": self.rationale,
            "violations": self.violations,
            "remedies": self.remedies,
            "missing_data_requests": self.missing_data_requests,
            "evidence_card_template": self.evidence_card_template.to_dict() if self.evidence_card_template else None,
        }
        if self.purpose_context:
            d["purpose_context"] = self.purpose_context.to_dict()
            d["residual_limitations"] = self.residual_limitations
            d["blocked_claims"] = self.blocked_claims
            d["override_records"] = self.override_records
        return d


# ==============================================================================
# Scientific Intent Pattern Matcher
# ==============================================================================

_INTENT_PATTERNS: List[Tuple[List[str], str]] = [
    # 1. Single-cell condition differential expression
    (
        [
            r"compare.*(?:condition|treatment|treated|group|tumor|control|disease|replicate|sample)",
            r"condition.*(?:de|differential expression)",
            r"pseudobulk.*(?:de|differential expression)",
            r"differentially expressed",
            r"differential expression",
            r"treated.*vs.*control",
            r"disease.*vs.*healthy",
            r"pydeseq2",
            r"deseq2",
            r"negative binomial.*glm",
            r"glm.*pseudobulk",
            r"rank_genes_groups.*(?:drug|treatment|vehicle|cause)",
        ],
        "scrna.pseudobulk_de",
    ),
    # 2. Single-cell clustering & exploratory markers
    (
        [
            r"cluster.*(?:cell|single cell|scrna|\d+)",
            r"clusters \d+",
            r"guess.*cell.*type",
            r"cell.*type.*cluster",
            r"leiden.*clustering",
            r"marker.*(?:gene|identification)",
            r"umap.*(?:visualization|embedding)",
            r"dimension.*reduction",
            r"preprocess.*(?:single cell|scrna)",
        ],
        "scrna.exploratory_clustering",
    ),
    # 3. Spatial transcriptomics Moran's I SVGs
    (
        [
            r"spatial.*(?:transcriptomics|variable gene|svg|autocorrelation|spot|graph)",
            r"moran.*(?:i|spatial)",
            r"visium.*analysis",
            r"slide-seq.*analysis",
        ],
        "spatial.morans_svg",
    ),
    # 4. Clinical Cohort Survival analysis
    (
        [
            r"survival.*(?:analysis|curve|estimation|cohort)",
            r"kaplan[- ]meier",
            r"log[- ]rank.*test",
            r"prognostic.*biomarker",
            r"patient.*stratification",
        ],
        "survival.kaplan_meier",
    ),
    # 5. scvi-tools generative representation
    (
        [
            r"scvi.*(?:tools|model|training)",
            r"train.*(?:scvi|scanvi|totalvi)",
            r"deep generative.*single cell",
            r"latent.*embedding.*scvi",
        ],
        "scvi.probabilistic_vae",
    ),
    # 6. Allotrope instrument standardization
    (
        [
            r"allotrope.*(?:conversion|format|asm)",
            r"standardize.*instrument",
            r"plate reader.*(?:parser|csv|export)",
            r"chromatography.*asm",
            r"21 cfr part 11.*(?:audit|csv)",
            r"audit log.*csv",
        ],
        "allotrope.format_conversion",
    ),
    # 7. Nextflow pipeline launch
    (
        [
            r"nextflow.*(?:pipeline|samplesheet|launch)",
            r"nf-core.*(?:samplesheet|rnaseq|scrnaseq)",
            r"cluster.*config.*nextflow",
        ],
        "nextflow.pipeline_launch",
    ),
    # 8. ACMG variant tiering
    (
        [
            r"acmg.*(?:classification|criteria|tiering)",
            r"variant.*(?:pathogenicity|interpretation|brca|tp53|c\.)",
            r"patient variant",
            r"(?:brca\d+|tp53).*(?:variant|mutation|pathogenicity|c\.|p\.|acmg)",
            r"pathogenicity.*scoring",
            r"pathology report.*variant",
        ],
        "variant.acmg_classification",
    ),
    # 9. Cell annotation evidence assessment (BNS-013 flagship capability B)
    (
        [
            r"annotation.*(?:evidence|support|valid|quality|audit)",
            r"(?:cell[- ]type|label).*(?:evidence|support|verdict|confidence|warrant)",
            r"open[- ]set.*(?:annotation|label)",
            r"how (?:much|well) (?:is |are )?(?:the )?label",
            r"label.*(?:supported|tentative|abstain)",
        ],
        "scrna.annotation_evidence",
    ),
    # 10. Spatial inference validity / alternative-explanation testing (flagship capability C)
    (
        [
            r"spatial.*(?:inference|conclusion|interpretation).*(?:valid|hold|survive|alternative|robust|fragile)",
            r"alternative explanation.*(?:spatial|neighborhood|enrich)",
            r"(?:observation|finding|enrich).*(?:toward|toward membrane).*(?:valid|hold)",
            r"segmentation.*leak",
            r"neighborhood.*radius.*sensitiv",
            r"permutation null.*spatial",
            r"spatial.*(?:finding|conclusion).*(?:control|confound)",
        ],
        "spatial.inference_validity",
    ),
    # 11. HPC & Cloud Batch cluster dispatch
    (
        [
            r"slurm.*(?:job|script|sbatch|submit|queue|cluster|partition)",
            r"pbs.*(?:job|script|qsub)",
            r"lsf.*(?:job|script|bsub)",
            r"kubernetes.*(?:batch|job|manifest|k8s)",
            r"aws batch.*(?:job|submit)",
            r"gcp batch.*(?:job|submit)",
            r"hpc.*(?:cluster|submit|dispatch|job|diagnostic)",
            r"cluster.*(?:submit|dispatch|probe|sbatch)",
            r"diagnose.*(?:oom|exit code|job failure|137)",
        ],
        "cluster.hpc_dispatch",
    ),
    # 12. Large-scale matrix memory estimation & out-of-core audit
    (
        [
            r"memory.*(?:estimate|estimation|requirement|overhead|capacity)",
            r"out[- ]of[- ]core.*(?:streaming|matrix|scanpy|zarr|analysis)",
            r"zarr.*(?:storage|streaming|chunk|audit)",
            r"large.*(?:dataset|matrix|scale|million cells)",
            r"oom.*(?:prevention|protection|guard)",
            r"how much ram.*(?:cells|genes|matrix)",
        ],
        "bigdata.out_of_core_audit",
    ),
    # 13. Tangram spatial deconvolution and cell-to-space mapping
    (
        [
            r"tangram.*(?:mapping|deconvolution|spatial|cell to space|project)",
            r"(?:spatial|spot).*(?:deconvolution|deconvolve|cell type proportion)",
            r"cell.*(?:to.*space|projection.*spatial|map.*spatial)",
            r"visium.*(?:deconvolution|cell type.*predict|spot composition)",
        ],
        "spatial.tangram_deconvolution",
    ),
    # 14. Geneformer official foundation model
    (
        [
            r"\bgeneformer\b",
            r"in silico.*(?:knockout|deletion|perturbation|overexpression)",
            r"geneformer.*(?:embedding|inference|checkpoint)",
        ],
        "scfm.geneformer_canonical",
    ),
    # 15. scGPT official foundation model
    (
        [
            r"\bscgpt\b",
            r"generative single[- ]cell.*(?:model|transformer|representation)",
        ],
        "scfm.scgpt_canonical",
    ),
    # 16. Single-cell Rank-Value SVD Embedding Proxy (Grade C Experimental)
    (
        [
            r"rank[- ]value.*(?:encoding|svd|proxy|representation)",
            r"rank.*(?:proxy|embedding proxy)",
            r"scfm.*(?:proxy|heuristic)",
        ],
        "scfm.rank_proxy_embedding",
    ),
    # 16. Dry-wet closed loop perturbation to spatial niche
    (
        [
            r"(?:dry[- ]wet|closed[- ]loop).*(?:perturbation|niche|spatial|gears|nicheformer)",
            r"(?:perturbation|knockout).*(?:to.*spatial|spatial.*niche|microenvironment.*distribution)",
            r"gears.*(?:and|with|to).*nicheformer",
            r"nicheformer.*(?:and|with|to).*gears",
        ],
        "closed_loop.perturbation_to_niche",
    ),
    # 17. GEARS combinatorial genetic perturbation
    (
        [
            r"\bgears\b",
            r"combinatorial.*(?:knockout|perturbation|gene knockout)",
            r"graph[- ]enhanced.*(?:perturbation|gene perturbation)",
        ],
        "perturbation.gears_prediction",
    ),
    # 18. NicheFormer spatial microenvironment forecasting
    (
        [
            r"\bnicheformer\b",
            r"spatial.*(?:niche.*forecast|niche.*prediction|microenvironment.*forecast)",
            r"niche.*(?:remodeling|composition.*prediction|spatial distribution)",
        ],
        "spatial.nicheformer_forecasting",
    ),
]

# Coordinate provenance values that are never silent substitutes for physical
# tissue coordinates (BNS-II-006 / BN-F009).
_EMBEDDING_COORDINATE_TYPES = ("umap_embedding", "pca_embedding", "embedding", "umap", "tsne")


def extract_scientific_capability(
    query: str, explicit_intents: Optional[List[str]] = None
) -> Optional[CapabilityContract]:
    """Identify the most specific matching canonical capability contract."""
    # 1. Check explicit intents first
    if explicit_intents:
        for intent in explicit_intents:
            matches = find_capabilities_by_intent(intent)
            if matches:
                return matches[0]

    # 2. Check query string patterns
    query_lower = query.lower()
    for patterns, cap_id in _INTENT_PATTERNS:
        for pat in patterns:
            if re.search(pat, query_lower):
                if cap_id in ALL_CAPABILITIES:
                    return ALL_CAPABILITIES[cap_id]

    return None


# ==============================================================================
# The Scientific Invariant Router
# ==============================================================================


def _screen_metadata_traps(cap: CapabilityContract, meta: Dict[str, Any]) -> Optional[RoutingDecision]:
    """
    Stage 3.5: deterministic screening of BioFailureBench-detectable traps.

    These are metadata-visible scientific traps that MUST be caught before any
    compute (BNS-013 firewall, BN-F004/F006/F008/F009): identifier-namespace
    mismatches, perfect condition confounding, cross-database contradictions,
    embedding-substituted spatial coordinates, and evidence-free annotation
    requests. Returns None when no trap fires.
    """
    cap_id = cap.id

    # BN-F004: identifier namespace mismatch on cross-source joins
    id_ns = meta.get("identifier_namespace")
    ref_ns = meta.get("reference_namespace")
    if id_ns and ref_ns and str(id_ns).lower() != str(ref_ns).lower():
        return RoutingDecision(
            status=RoutingStatus.ABSTAIN,
            matched_capability=cap,
            target_skill=cap.skill_name,
            recommended_script=None,
            recommended_command=None,
            rationale=(
                "Identifier namespace mismatch: joining data keyed on "
                f"'{id_ns}' against a reference keyed on '{ref_ns}' corrupts every downstream result."
            ),
            violations=[
                f"Identifier namespace mismatch (BN-F004): input identifiers are '{id_ns}' while the "
                f"reference/knowledge source is keyed on '{ref_ns}'. Silent cross-namespace joins are never acceptable."
            ],
            remedies=[
                "Provide an explicit identifier mapping table (e.g. org.Hs.eg.db / mygene.info / Ensembl release map) "
                "and record it in provenance, or re-key both sources onto the same namespace before joining."
            ],
            evidence_card_template=EvidenceCard(
                execution_state=ExecutionState.REFUSED.value,
                details={"failure_mode": "BN-F004", "identifier_namespace": id_ns, "reference_namespace": ref_ns},
            ),
        )

    # BN-F008: cross-database contradiction between knowledge sources
    if meta.get("cross_database_contradiction"):
        return RoutingDecision(
            status=RoutingStatus.ABSTAIN,
            matched_capability=cap,
            target_skill=cap.skill_name,
            recommended_script=None,
            recommended_command=None,
            rationale=(
                "Cross-database contradiction: independent knowledge sources disagree about the same entity; "
                "the conclusion is CONFLICTED, not resolved."
            ),
            violations=[
                "Cross-database contradiction (BN-F008): independent knowledge sources disagree about the target "
                "entity (e.g. conflicting classifications or mappings across releases). The conflict MUST be surfaced, "
                "never silently resolved by source preference order."
            ],
            remedies=[
                "Mark the conclusion maturity CONFLICTED, surface both sources with identifiers and access dates, "
                "and seek expert review before any downstream claim."
            ],
            evidence_card_template=EvidenceCard(
                execution_state=ExecutionState.REFUSED.value,
                details={"failure_mode": "BN-F008"},
            ),
        )

    # BN-F006: perfect confounding between condition and a donor/batch variable
    confounded_with = meta.get("condition_confounded_with")
    if confounded_with:
        return RoutingDecision(
            status=RoutingStatus.ABSTAIN,
            matched_capability=cap,
            target_skill=cap.skill_name,
            recommended_script=None,
            recommended_command=None,
            rationale=(
                f"Condition is perfectly confounded with '{confounded_with}': the design cannot separate the "
                "treatment effect from the confounding variable."
            ),
            violations=[
                f"Perfect confounding (invalid model assumption, BN-F006): condition is 1:1 with '{confounded_with}', "
                "so population-level condition effects are unidentifiable in this design."
            ],
            remedies=[
                f"Add biological replicates that decouple condition from '{confounded_with}', restrict claims to "
                "exploratory within-stratum comparisons, or perform and report an explicit sensitivity analysis."
            ],
            evidence_card_template=EvidenceCard(
                execution_state=ExecutionState.REFUSED.value,
                details={"failure_mode": "BN-F006", "confounded_with": confounded_with},
            ),
        )

    # BN-F009: embedding coordinates substituted for physical tissue coordinates
    coordinate_type = meta.get("coordinate_type")
    requires_coords = cap_id in ("spatial.morans_svg", "spatial.inference_validity")
    if requires_coords and coordinate_type and str(coordinate_type).lower() in _EMBEDDING_COORDINATE_TYPES:
        return RoutingDecision(
            status=RoutingStatus.ABSTAIN,
            matched_capability=cap,
            target_skill=cap.skill_name,
            recommended_script=None,
            recommended_command=None,
            rationale=(
                f"Spatial coordinates are a '{coordinate_type}' embedding, not physical tissue coordinates; "
                "substituting an embedding silently invalidates spatial statistics."
            ),
            violations=[
                f"Spatial coordinate substitution (BN-F009): obsm coordinates are a '{coordinate_type}' embedding. "
                "A UMAP/PCA embedding MUST NOT be silently used in place of physical tissue coordinates."
            ],
            remedies=[
                "Provide physical coordinates in obsm['spatial'], or record an explicit spatial justification for the "
                "embedding and cap the conclusion maturity at FRAGILE (BNS-II-006)."
            ],
            evidence_card_template=EvidenceCard(
                execution_state=ExecutionState.REFUSED.value,
                details={"failure_mode": "BN-F009", "coordinate_type": coordinate_type},
            ),
        )

    # BN-F003: annotation requested with no evidence source at all
    if cap_id == "scrna.annotation_evidence" and meta.get("annotation_evidence_available") is False:
        return RoutingDecision(
            status=RoutingStatus.ABSTAIN,
            matched_capability=cap,
            target_skill=cap.skill_name,
            recommended_script=None,
            recommended_command=None,
            rationale="No annotation evidence source is available; identity labels cannot be assessed or asserted.",
            violations=[
                "Unsupported annotation (BN-F003): no reference mapping, marker panel, or negative-marker set is "
                "available. Labels must stay numeric/putative; identity claims are blocked."
            ],
            remedies=[
                "Attach a reference atlas mapping, a curated marker panel with negative markers, or a cross-method "
                "annotation before asserting any cell-type identity."
            ],
            evidence_card_template=EvidenceCard(
                execution_state=ExecutionState.REFUSED.value,
                details={"failure_mode": "BN-F003"},
            ),
        )

    # BN-F003: open-set population forced into known-label assignment
    if cap_id == "scrna.annotation_evidence" and meta.get("open_set_detected"):
        return RoutingDecision(
            status=RoutingStatus.ABSTAIN,
            matched_capability=cap,
            target_skill=cap.skill_name,
            recommended_script=None,
            recommended_command=None,
            rationale="Open-set population detected: a novel/unknown population cannot be assigned a known label.",
            violations=[
                "Open-set annotation (BN-F003): an unknown population lies outside the reference universe; assigning "
                "the nearest known label would be annotation without evidence."
            ],
            remedies=[
                "Report the population as 'unknown / novel' (ABSTAIN verdict) and collect orthogonal evidence "
                "(sorted bulk profiles, spatial markers, citation-supported panels) before naming it."
            ],
            evidence_card_template=EvidenceCard(
                execution_state=ExecutionState.REFUSED.value,
                details={"failure_mode": "BN-F003", "open_set": True},
            ),
        )

    # Spatial validity assessment with zero controls: request the data (BNS-005)
    if cap_id == "spatial.inference_validity" and meta.get("alternative_explanations_tested") is False:
        return RoutingDecision(
            status=RoutingStatus.NEEDS_DATA,
            matched_capability=cap,
            target_skill=cap.skill_name,
            recommended_script=None,
            recommended_command=None,
            rationale=(
                "Validity assessment of a spatial conclusion requires alternative-explanation controls; "
                "none were provided."
            ),
            missing_data_requests=[
                "Provide alternative-explanation control results (cell size, transcript density, segmentation "
                "uncertainty, local cell density, spot composition, batch/FOV, permutation null)."
            ],
            remedies=[
                "Run at least the core confound controls before asking whether the spatial conclusion holds."
            ],
        )

    return None


def route_scientific_intent(
    query: str,
    *,
    intent_keywords: Optional[List[str]] = None,
    data_path: Optional[str | Path] = None,
    data_metadata: Optional[Dict[str, Any]] = None,
    allow_degraded: bool = False,
    allow_frontier: bool = False,
    research_purpose: Optional[str] = None,
    override_justification: str = "",
) -> RoutingDecision:
    """
    Evaluate scientific intent and determine execution validity.

    Pipeline:
    1. Match query -> CapabilityContract
    2. Frontier execution-isolation gate (BNS-010): frontier capabilities are
       unreachable unless the caller explicitly opts in (`allow_frontier=True`)
    3. Inspect data semantics -> Extract metadata
    4. Evaluate scientific preconditions & refusal triggers (purpose-aware)
    5. Deterministic capability-bound backend gate
    6. Return authoritative RoutingDecision with evidence ceiling and override records

    ``allow_frontier`` defaults to False: stable/frontier isolation is enforced
    at runtime, not only in the registry.

    ``research_purpose`` modulates the evidence ceiling: the same data design
    can carry different epistemic weight under exploratory vs confirmatory vs
    clinical intent.  When omitted, the purpose is inferred from the query.

    ``override_justification`` activates the explicit researcher override
    mechanism: soft blocks can be bypassed with full documentation of what
    limitations remain and what claims are still not warranted.
    """
    meta = dict(data_metadata or {})
    intents = list(intent_keywords or [])

    # 0. Build PurposeContext (explicit or inferred from query).
    if research_purpose:
        pctx = PurposeContext(
            purpose=purpose_from_string(research_purpose),
            explicitly_declared=True,
            override_active=bool(override_justification),
            override_justification=override_justification,
        )
    else:
        inferred = infer_research_purpose(query)
        pctx = PurposeContext(
            purpose=inferred,
            explicitly_declared=False,
            override_active=bool(override_justification),
            override_justification=override_justification,
        )

    # 1. Match Capability Contract
    cap = extract_scientific_capability(query, intents)
    if cap is None:
        return RoutingDecision(
            status=RoutingStatus.NEEDS_DATA,
            matched_capability=None,
            target_skill="start",
            recommended_script=None,
            recommended_command="bionexus doctor",
            rationale="No specific scientific analytical intent could be resolved from query. Defaulting to session orientation.",
            missing_data_requests=[
                "Clarify specific scientific analytical intent (e.g. differential expression, clustering, survival analysis, spatial transcriptomics)."
            ],
        )

    skill_name = cap.skill_name
    is_frontier = cap.id in FRONTIER_CAPABILITIES

    # 1.5 Frontier Execution-Isolation Gate (BNS-010).
    # Registry segregation is nominal; this gate makes it an execution-time fact:
    # no frontier capability is reachable without explicit caller opt-in.
    if is_frontier and not allow_frontier:
        return RoutingDecision(
            status=RoutingStatus.EXPERIMENTAL_CAPABILITY_REQUIRES_OPT_IN,
            matched_capability=cap,
            target_skill=skill_name,
            recommended_script=None,
            recommended_command=None,
            rationale=(
                f"Frontier capability detected: '{cap.id}' ({cap.display_name}) is an experimental "
                "capability segregated from the stable canonical core. Execution requires explicit opt-in."
            ),
            violations=[
                f"Frontier capability '{cap.id}' requested without experimental opt-in "
                "(allow_frontier=False; BNS-010 runtime isolation)."
            ],
            remedies=[
                "Rerun with --allow-frontier (CLI) or allow_frontier=True (Python API) to execute "
                "this experimental capability with its PRELIMINARY evidence ceiling."
            ],
            evidence_card_template=EvidenceCard(
                execution_state=ExecutionState.REFUSED.value,
                details={"contract_id": cap.id, "refusal_triggers": ["frontier_opt_in_required"]},
            ),
        )

    # 1.6 Forbidden-Claim Intent Screening (BNS-AD-009, BNS-CC-012)
    # The request itself asks this capability to assert a claim on its
    # forbidden_claims list (e.g. causal cell-cell communication from Moran's I).
    claim_hits = detect_forbidden_claims_in_query(cap.id, query)
    if claim_hits:
        violations = [
            f"Forbidden claim '{h['claim_id']}' requested from capability '{cap.id}': {h['description']}"
            for h in claim_hits
        ]
        remedies = [
            f"Reformulate within the capability's warranted claims: {cap.display_name} cannot support '{h['claim_id']}' without additional orthogonal evidence. {h['remedy']}"
            for h in claim_hits
        ]
        return RoutingDecision(
            status=RoutingStatus.ABSTAIN,
            matched_capability=cap,
            target_skill=skill_name,
            recommended_script=None,
            recommended_command=None,
            rationale=(
                f"Request violates the forbidden-claims contract of capability '{cap.id}' "
                "(Biological Capability ABI). The method's evidence cannot warrant the requested claim."
            ),
            violations=violations,
            remedies=remedies,
            evidence_card_template=EvidenceCard(
                execution_state=ExecutionState.REFUSED.value,
                details={
                    "contract_id": cap.id,
                    "refusal_triggers": [f"forbidden_claim:{h['claim_id']}" for h in claim_hits],
                    "violations": violations,
                },
            ),
        )

    # 2. Inspect Data Semantics from data_path if provided
    if data_path:
        p = Path(data_path)
        if p.exists() and p.suffix == ".h5ad":
            try:
                import anndata as ad

                adata = ad.read_h5ad(p, backed="r")
                grade, notes, stats = audit_expression_matrix(adata.X, expected_type="counts")
                meta["is_integer_like"] = stats.get("is_integer_like", False)
                meta["is_normalized"] = not stats.get("is_integer_like", False)
                meta["has_spatial"] = "spatial" in adata.obsm
                if "spatial" in adata.obsm:
                    meta["n_spatial_spots"] = adata.obsm["spatial"].shape[0]
            except Exception:
                pass

    # 3. Check for Essential Missing Metadata (NEEDS_DATA state)
    if cap.id == "scrna.pseudobulk_de":
        if (
            "min_replicates_per_condition" not in meta
            and not meta.get("is_normalized")
            and meta.get("is_integer_like", True)
        ):
            # Check if user query mentions replicates or if we need to request them
            if not re.search(r"\b(replicate|rep|n=\d+)\b", query.lower()):
                # If replicates were neither stated nor found in meta
                return RoutingDecision(
                    status=RoutingStatus.NEEDS_DATA,
                    matched_capability=cap,
                    target_skill=skill_name,
                    recommended_script="skills/single-cell-rna-qc/scripts/scrna_pseudobulk.py",
                    recommended_command="python skills/single-cell-rna-qc/scripts/scrna_pseudobulk.py --help",
                    rationale="Condition differential expression requires biological replicate groupings to avoid single-cell pseudoreplication.",
                    missing_data_requests=[
                        "Please provide biological replicate identifiers in `adata.obs` (e.g. `sample_id`, `donor_id`, `batch`) and the experimental condition factor (`condition`).",
                    ],
                    remedies=[
                        "Condition DE is valid only when biological replicates (n >= 2 per condition) are available."
                    ],
                )

    # 3.5 Deterministic trap screening (BN-F004/F006/F008/F009 + flagship gates)
    trap_decision = _screen_metadata_traps(cap, meta)
    if trap_decision is not None:
        return trap_decision

    # 4. Scientific Validity + Availability Evaluation (purpose-aware).
    # `evaluate_viability_with_purpose` classifies refusals as hard BLOCK or
    # soft PERMITTED_WITH_LIMITS, applies evidence ceiling, and creates
    # override records when the researcher has invoked an override.
    eval_result = cap.evaluate_viability_with_purpose(
        input_metadata=meta,
        purpose_context=pctx,
    )

    script_map = {
        "scrna.pseudobulk_de": "skills/single-cell-rna-qc/scripts/scrna_deseq.py",
        "scrna.exploratory_clustering": "skills/single-cell-rna-qc/scripts/scrna_pipeline.py",
        "spatial.morans_svg": "skills/spatial-transcriptomics/scripts/spatial_pipeline.py",
        "survival.kaplan_meier": "skills/clinical-cohort-analysis/scripts/survival_analyzer.py",
        "scvi.probabilistic_vae": "skills/scvi-tools/scripts/scvi_smoke.py",
        "allotrope.format_conversion": "skills/instrument-data-to-allotrope/scripts/allotrope_converter.py",
        "nextflow.pipeline_launch": "skills/nextflow-development/scripts/nfcore_launch.py",
        "variant.acmg_classification": "skills/variant-interpretation/scripts/acmg_classifier.py",
    }
    rec_script = script_map.get(cap.id)

    if eval_result.status == "PERMITTED_WITH_LIMITS":
        # Soft blocks overridden: execution permitted with documented limits.
        rationale = (
            f"Analysis under capability '{cap.id}' is permitted with limits via "
            f"researcher override (purpose={pctx.purpose.value}). "
            f"Evidence ceiling capped at {eval_result.evidence_ceiling}."
        )
        return RoutingDecision(
            status=RoutingStatus.PERMITTED_WITH_LIMITS,
            matched_capability=cap,
            target_skill=skill_name,
            recommended_script=rec_script,
            recommended_command=f"python {rec_script} --help" if rec_script else None,
            rationale=rationale,
            violations=[],
            remedies=eval_result.remedies,
            evidence_card_template=eval_result.evidence_card,
            purpose_context=pctx,
            residual_limitations=eval_result.residual_limitations,
            blocked_claims=eval_result.blocked_claims,
            override_records=eval_result.override_records,
        )

    if not eval_result.permitted:
        backend_missing = eval_result.backend_available is False
        # The single backend violation (if any) is appended last; everything
        # before it is a scientific-validity violation.
        scientific_violations = (
            eval_result.violations[:-1] if backend_missing else list(eval_result.violations)
        )

        if scientific_violations or not backend_missing:
            # Fatal Scientific Refusal (ABSTAIN): validity failures never degrade.
            return RoutingDecision(
                status=RoutingStatus.ABSTAIN,
                matched_capability=cap,
                target_skill=skill_name,
                recommended_script=None,
                recommended_command=None,
                rationale=f"Analysis is scientifically invalid or prohibited by BioNexus capability contract '{cap.id}'.",
                violations=eval_result.violations,
                remedies=eval_result.remedies,
                evidence_card_template=eval_result.evidence_card,
                purpose_context=pctx,
            )

        # Availability-only refusal: the deterministic capability-bound backend gate.
        # Backend correctness binds to the Capability (track), never to the skill.
        install_hint = f"pip install bionexus-reliability[{cap.backend.extra or 'all'}]"
        if is_frontier and allow_degraded:
            # FRONTIER + opt-in + backend absent + explicit fallback -> DEGRADED
            return RoutingDecision(
                status=RoutingStatus.DEGRADED_ADVISORY,
                matched_capability=cap,
                target_skill=skill_name,
                recommended_script=rec_script,
                recommended_command=install_hint,
                rationale=(
                    f"Frontier capability '{cap.id}': canonical backend '{cap.backend.canonical_name}' "
                    "is not installed. Executing via Grade C heuristic fallback under explicit opt-in; "
                    "output is experimental and must never be presented as the canonical backend's result."
                ),
                violations=eval_result.violations,
                remedies=eval_result.remedies,
                evidence_card_template=EvidenceCard(
                    execution_state=ExecutionState.DEGRADED.value,
                    details={"missing_backend": cap.backend.canonical_name, "frontier": True},
                ),
            )

        # CANONICAL + backend missing -> REFUSE (strict).
        # FRONTIER + opt-in + backend absent + no fallback consent -> REFUSE too.
        return RoutingDecision(
            status=RoutingStatus.ABSTAIN,
            matched_capability=cap,
            target_skill=skill_name,
            recommended_script=None,
            recommended_command=install_hint,
            rationale=(
                f"Canonical backend '{cap.backend.canonical_name}' required by capability '{cap.id}' "
                "is not available. Backend readiness binds to the capability: no silent substitution, "
                "no skill-based exceptions."
            ),
            violations=eval_result.violations,
            remedies=eval_result.remedies,
            evidence_card_template=EvidenceCard(
                execution_state=ExecutionState.REFUSED.value,
                details={"missing_backend": cap.backend.canonical_name},
            ),
        )

    # 5. PERMITTED (Fully scientifically valid execution path)
    rationale = f"Scientific preconditions, input semantics, and backend for '{cap.id}' are fully satisfied."
    if is_frontier:
        rationale += (
            " FRONTIER/EXPERIMENTAL capability executed under explicit opt-in: conclusions are "
            "capped at PRELIMINARY without external validation (BNS-CC-013)."
        )
    rationale += f" Purpose: {pctx.purpose.value}; evidence ceiling: {pctx.evidence_ceiling.value}."
    return RoutingDecision(
        status=RoutingStatus.PERMITTED,
        matched_capability=cap,
        target_skill=skill_name,
        recommended_script=rec_script,
        recommended_command=f"python {rec_script} --help" if rec_script else None,
        rationale=rationale,
        evidence_card_template=eval_result.evidence_card,
        purpose_context=pctx,
    )
