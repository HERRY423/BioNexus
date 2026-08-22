"""
BioNexus Semantic Nomination Layer (deterministic, offline, auditable).

Dual-layer routing contract (BNS-013 / BNS-001):

1. **Pattern layer** (existing): curated regex patterns -> capability. Exact,
   highest confidence.
2. **Semantic nomination layer** (this module): a deterministic lexical-semantic
   scorer expands domain synonyms and scores every capability contract. It may
   only *nominate* a capability; it can never adjudicate.
3. **Host nomination channel**: an agent host (Biomni, Claude, Codex) may pass
   its own ``nominated_capability`` from its reasoning. This is treated exactly
   like a semantic nomination: validated against the registry, never trusted.

Adjudication invariants (non-negotiable):

- Pure function of the query string and registry state: same input -> same
  decision, no network, no model inference, no temperature.
- A nomination is accepted ONLY if the capability exists in the canonical
  registry AND passes the minimum-score + margin thresholds below.
- Ambiguity fails closed to ``None`` (router then emits NEEDS_DATA), never to
  the highest-scoring guess.
- Every acceptance records its routing layer so decisions stay auditable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Domain synonym table: canonical concept -> surface variants (lowercase).
# Curated; extending it is a reviewed registry change, not runtime behavior.
# ---------------------------------------------------------------------------

_CONCEPT_SYNONYMS: Dict[str, Tuple[str, ...]] = {
    # pseudobulk DE concept family
    "differential_expression": (
        "differential expression", "differentially expressed", "de analysis",
        "deseq2", "pydeseq2", "edger", "condition effect", "treatment effect",
        "bulk-level", "pseudobulk",
    ),
    "condition_comparison": (
        "vs", "versus", "between conditions", "across conditions",
        "treated control", "case control", "stimulated", "perturbed",
    ),
    # clustering / exploratory family
    "clustering": (
        "cluster", "clusters", "clustering", "leiden", "louvain",
        "communities", "populations", "unsupervised groups",
    ),
    "marker_genes": ("marker genes", "markers", "signature genes", "canonical markers"),
    "dimensionality": ("umap", "tsne", "pca", "embedding", "manifold", "latent space"),
    # spatial family
    "spatial": (
        "spatial", "space", "tissue coordinates", "visium", "slide-seq", "slide seq",
        "merfish", "cosmx", "xenium", "spots", "spot", "tissue positions",
        "histological", "in situ", "stereoseq",
    ),
    "spatial_statistics": (
        "moran", "morans i", "autocorrelation", "spatially variable", "svg",
        "spatial graph", "neighborhood enrichment", "ripley", "co-occurrence",
    ),
    "validity_assessment": (
        "alternative explanation", "conclusion valid", "does the conclusion hold",
        "conclusion survive", "robust to", "confound control", "permutation null",
        "sensitivity of the conclusion", "invalidated",
    ),
    # survival family
    "survival": (
        "survival", "kaplan meier", "kaplan-meier", "log-rank", "logrank",
        "cox", "hazard", "prognosis", "prognostic", "overall survival",
        "progression-free", "time-to-event",
    ),
    # generative models
    "generative_model": (
        "scvi", "scvi-tools", "scanvi", "totalvi", "variational",
        "deep generative", "vae", "latent embedding",
    ),
    # variant family
    "variant": (
        "variant", "variants", "mutation", "snv", "indel", "cnv",
        "pathogenicity", "acmg", "clinvar", "hgvs",
    ),
    # annotation evidence
    "annotation": (
        "annotate", "annotation", "cell type label", "cell-type", "identity labels",
        "reference mapping", "label transfer",
    ),
    # pipelines / infra
    "pipeline": ("nextflow", "nf-core", "nfcore", "pipeline", "samplesheet", "workflow launch"),
    "instrument": ("allotrope", "plate reader", "chromatography", "instrument export", "asm json"),
    "hpc": ("slurm", "sbatch", "pbs", "qsub", "lsf", "bsub", "kubernetes", "aws batch", "hpc"),
    "memory": ("memory", "ram", "out-of-core", "oom", "zarr chunking", "large matrix"),
    # foundation models / perturbation
    "foundation_model": ("geneformer", "scgpt", "scbert", "foundation model", "pretrained scfm"),
    "perturbation_generic": (
        "knockout", "perturbation", "perturb-seq", "perturb seq", "overexpression",
        "in silico deletion",
    ),
    "combinatorial_perturbation": (
        "gears", "combinatorial knockout", "combinatorial perturbation",
        "graph-enhanced perturbation",
    ),
    "niche": ("niche", "microenvironment", "tumor microenvironment", "spatial niche"),
}

# Pre-compiled lowercase variant index: variant string -> concept name.
_VARIANT_INDEX: Dict[str, str] = {}
for _concept, _variants in _CONCEPT_SYNONYMS.items():
    for _v in _variants:
        _VARIANT_INDEX[_v] = _concept

# Capability -> weighted concept profile. Weights express how strongly each
# concept evidences the capability; they are registry-reviewed constants.
_CAPABILITY_CONCEPTS: Dict[str, Dict[str, float]] = {
    "scrna.pseudobulk_de": {
        "differential_expression": 3.0, "condition_comparison": 1.5,
    },
    "scrna.exploratory_clustering": {
        "clustering": 3.0, "marker_genes": 1.5, "dimensionality": 1.0,
    },
    "spatial.morans_svg": {
        "spatial": 2.0, "spatial_statistics": 3.0,
    },    "survival.kaplan_meier": {"survival": 3.0},
    "scvi.probabilistic_vae": {"generative_model": 3.0},
    "variant.acmg_classification": {"variant": 3.0},
    "scrna.annotation_evidence": {"annotation": 3.0},
    "nextflow.pipeline_launch": {"pipeline": 3.0},
    "allotrope.format_conversion": {"instrument": 3.0},
    "cluster.hpc_dispatch": {"hpc": 3.0},
    "bigdata.out_of_core_audit": {"memory": 3.0},
    "scfm.geneformer_canonical": {"foundation_model": 3.0},
    "scfm.scgpt_canonical": {"foundation_model": 3.0},
    "perturbation.gears_prediction": {"combinatorial_perturbation": 3.0},
    "spatial.nicheformer_forecasting": {"foundation_model": 1.5, "niche": 2.5, "spatial": 1.0},
    "closed_loop.perturbation_to_niche": {"perturbation_generic": 1.5, "niche": 2.0},
    "spatial.tangram_deconvolution": {"spatial": 2.0, "annotation": 1.0},
    "spatial.inference_validity": {"spatial": 1.0, "validity_assessment": 3.0},
}

#: Minimum normalized score for a semantic nomination to be considered.
MIN_SEMANTIC_SCORE = 0.55
#: Minimum lead of the best candidate over the runner-up (ambiguity guard).
MIN_MARGIN = 0.18

_TOKEN_RE = re.compile(r"[a-z0-9\-]+")


@dataclass
class SemanticNomination:
    """Audit record for one semantic routing attempt."""

    nominated_capability: Optional[str]
    layer: str  # "pattern" | "semantic" | "nominated" | "none"
    score: float = 0.0
    runner_up: Optional[str] = None
    runner_up_score: float = 0.0
    matched_concepts: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return {
            "nominated_capability": self.nominated_capability,
            "layer": self.layer,
            "score": round(self.score, 4),
            "runner_up": self.runner_up,
            "runner_up_score": round(self.runner_up_score, 4),
            "matched_concepts": list(self.matched_concepts),
        }


def _detect_concepts(query_lower: str) -> List[str]:
    """Return concepts whose surface variants appear in the query."""
    found: List[str] = []
    for concept, variants in _CONCEPT_SYNONYMS.items():
        for v in variants:
            if v in query_lower:
                found.append(concept)
                break
    return found


def score_capabilities(query: str, candidates: Optional[List[str]] = None) -> List[Tuple[str, float]]:
    """
    Deterministically score candidate capabilities against the query.

    Score = (sum of matched concept weights) / (total profile weight), so 1.0
    means every concept the capability is built from was evidenced. Returns
    candidates sorted by descending score.
    """
    query_lower = query.lower()
    concepts = set(_detect_concepts(query_lower))
    pool = candidates if candidates is not None else list(_CAPABILITY_CONCEPTS)
    scored: List[Tuple[str, float]] = []
    for cap_id in pool:
        profile = _CAPABILITY_CONCEPTS.get(cap_id)
        if not profile:
            continue
        total = sum(profile.values())
        hit = sum(w for c, w in profile.items() if c in concepts)
        scored.append((cap_id, hit / total if total else 0.0))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored


def nominate_semantically(query: str, candidates: Optional[List[str]] = None) -> SemanticNomination:
    """
    Attempt a semantic nomination. Fails closed: returns layer="none" unless a
    single candidate clears both MIN_SEMANTIC_SCORE and MIN_MARGIN.
    """
    ranked = score_capabilities(query, candidates)
    matched = _detect_concepts(query.lower())
    if not ranked or ranked[0][1] < MIN_SEMANTIC_SCORE:
        return SemanticNomination(None, "none", matched_concepts=matched)
    best_id, best_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0.0
    if best_score - second_score < MIN_MARGIN:
        return SemanticNomination(
            None, "none", score=best_score, runner_up=ranked[1][0] if len(ranked) > 1 else None,
            runner_up_score=second_score, matched_concepts=matched,
        )
    return SemanticNomination(
        best_id, "semantic", score=best_score,
        runner_up=ranked[1][0] if len(ranked) > 1 else None,
        runner_up_score=second_score, matched_concepts=matched,
    )


def validate_nomination(
    nominated_capability: str, registry: Dict[str, object], query: str = ""
) -> Tuple[Optional[object], SemanticNomination]:
    """
    Validate a host-supplied nomination against the canonical registry.

    The host may nominate; it cannot create capabilities, bypass frontier
    gating (enforced later by the router), or skip forbidden-claim screening
    (also enforced later). Returns (contract_or_None, audit_record).
    """
    cap_id = str(nominated_capability).strip().lower()
    if cap_id in registry:
        return registry[cap_id], SemanticNomination(cap_id, "nominated")
    fallback = nominate_semantically(query, [cap_id])
    return None, SemanticNomination(
        None, "none", matched_concepts=fallback.matched_concepts
    )
