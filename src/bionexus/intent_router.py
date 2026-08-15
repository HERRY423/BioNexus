"""
BioNexus Scientific Intent & Invariant Router.

Evolves static skill discovery into a validated 6-stage Scientific Intent Pipeline:
1. Scientific Query/Prompt -> Extract Analytical Intent
2. Data Semantics Inspection (Raw counts vs Normalized floats, Spatial coords, Survival events)
3. Scientific Preconditions Verification (Biological replication, Non-degenerate geometry)
4. Capability Contract Matching (Canonical Capability vs Heuristic)
5. Backend Lifecycle Probe (Installed vs Missing vs Incompatible)
6. Deterministic Routing Decision (PERMITTED | NEEDS_DATA | ABSTAIN | DEGRADED_ADVISORY)

Enforces what is scientifically legal and protects Host Agents from executing invalid analyses.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from bionexus.agent_routing import is_default_skill
from bionexus.backends import probe
from bionexus.capabilities import (
    CANONICAL_CAPABILITIES,
    CapabilityContract,
    find_capabilities_by_intent,
)
from bionexus.contracts import (
    EvidenceCard,
    ExecutionState,
)
from bionexus.integrity import audit_expression_matrix


class RoutingStatus(str, Enum):
    """Status of the scientific routing decision."""

    PERMITTED = "PERMITTED"  # Analysis is scientifically valid, preconditions met, backend ready
    NEEDS_DATA = "NEEDS_DATA"  # Valid intent, but essential metadata or input artifacts are missing
    ABSTAIN = "ABSTAIN"  # Refused: Mathematically/biologically impossible or violates scientific invariants
    DEGRADED_ADVISORY = "DEGRADED_ADVISORY"  # Permitted with explicit notice of Grade C heuristic degradation


@dataclass
class ScientificIntentRequest:
    """Input request describing the user's analytical goal and available data."""

    query: str
    intent_keywords: List[str] = field(default_factory=list)
    data_path: Optional[str] = None
    data_metadata: Dict[str, Any] = field(default_factory=dict)
    allow_degraded: bool = False


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

    def to_dict(self) -> Dict[str, Any]:
        """Convert decision to dictionary."""
        return {
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


# ==============================================================================
# Scientific Intent Pattern Matcher
# ==============================================================================

_INTENT_PATTERNS: List[Tuple[List[str], str]] = [
    # 1. Single-cell condition differential expression
    (
        [
            r"compare.*(?:condition|treatment|treated|group|tumor|control|disease|replicate)",
            r"condition.*(?:de|differential expression)",
            r"pseudobulk.*(?:de|differential expression)",
            r"treated.*vs.*control",
            r"disease.*vs.*healthy",
            r"differential expression between (?:conditions|groups)",
        ],
        "scrna.pseudobulk_de",
    ),
    # 2. Single-cell clustering & exploratory markers
    (
        [
            r"cluster.*(?:cell|single cell|scrna)",
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
            r"spatial.*(?:transcriptomics|variable gene|svg|autocorrelation)",
            r"moran.*(?:i|spatial)",
            r"visium.*analysis",
            r"slide-seq.*analysis",
        ],
        "spatial.morans_svg",
    ),
    # 4. Clinical Cohort Survival analysis
    (
        [
            r"survival.*(?:analysis|curve|estimation)",
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
            r"plate reader.*parser",
            r"chromatography.*asm",
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
            r"variant.*(?:pathogenicity|interpretation)",
            r"pathogenicity.*scoring",
        ],
        "variant.acmg_classification",
    ),
]


def extract_scientific_capability(query: str, explicit_intents: Optional[List[str]] = None) -> Optional[CapabilityContract]:
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
                if cap_id in CANONICAL_CAPABILITIES:
                    return CANONICAL_CAPABILITIES[cap_id]

    return None


# ==============================================================================
# The Scientific Invariant Router
# ==============================================================================

def route_scientific_intent(
    query: str,
    *,
    intent_keywords: Optional[List[str]] = None,
    data_path: Optional[str | Path] = None,
    data_metadata: Optional[Dict[str, Any]] = None,
    allow_degraded: bool = False,
) -> RoutingDecision:
    """
    Evaluate scientific intent and determine execution validity.

    Pipeline:
    1. Match query -> CapabilityContract
    2. Inspect data semantics -> Extract metadata
    3. Evaluate scientific preconditions & refusal triggers
    4. Check backend status
    5. Return authoritative RoutingDecision
    """
    meta = dict(data_metadata or {})
    intents = list(intent_keywords or [])

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
            missing_data_requests=["Clarify specific scientific analytical intent (e.g. differential expression, clustering, survival analysis, spatial transcriptomics)."],
        )

    skill_name = cap.skill_name
    is_default = is_default_skill(skill_name)

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
        if "min_replicates_per_condition" not in meta:
            # Check if user query mentions replicates or if we need to request them
            if not re.search(r"\b(replicate|rep|n=\d+)\b", query.lower()) and "min_replicates_per_condition" not in meta:
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
                    remedies=["Condition DE is valid only when biological replicates (n >= 2 per condition) are available."],
                )

    # 4. Check Scientific Preconditions & Refusal Triggers
    eval_result = cap.evaluate_viability(input_metadata=meta)

    if not eval_result.permitted:
        # Check if this is a backend missing issue on a legacy skill that user allows degrading
        if not is_default and allow_degraded:
            return RoutingDecision(
                status=RoutingStatus.DEGRADED_ADVISORY,
                matched_capability=cap,
                target_skill=skill_name,
                recommended_script=None,
                recommended_command=None,
                rationale=f"Executing via Grade C heuristic fallback for '{skill_name}'. Results are preliminary/degraded.",
                violations=eval_result.violations,
                remedies=eval_result.remedies,
                evidence_card_template=eval_result.evidence_card,
            )

        # Fatal Scientific Refusal (ABSTAIN)
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
        )

    # 5. Check Gold Backend Presence
    backend_import = cap.backend.import_name
    if backend_import and backend_import != "none":
        b_status = probe(backend_import)
        if not b_status.available:
            return RoutingDecision(
                status=RoutingStatus.ABSTAIN,
                matched_capability=cap,
                target_skill=skill_name,
                recommended_script=None,
                recommended_command=f"pip install bionexus[{cap.backend.extra or 'all'}]",
                rationale=f"Required gold-standard backend '{cap.backend.canonical_name}' is missing ({b_status.lifecycle_state}).",
                violations=[f"Backend '{cap.backend.canonical_name}' is not installed."],
                remedies=[f"Install required backend via `pip install bionexus[{cap.backend.extra}]` or `pip install {cap.backend.import_name}`."],
                evidence_card_template=EvidenceCard(
                    execution_state=ExecutionState.REFUSED.value,
                    details={"missing_backend": cap.backend.canonical_name},
                ),
            )

    # 6. PERMITTED (Fully scientifically valid execution path)
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

    return RoutingDecision(
        status=RoutingStatus.PERMITTED,
        matched_capability=cap,
        target_skill=skill_name,
        recommended_script=rec_script,
        recommended_command=f"python {rec_script} --help" if rec_script else None,
        rationale=f"Scientific preconditions, input semantics, and backend for '{cap.id}' are fully satisfied.",
        evidence_card_template=eval_result.evidence_card,
    )
