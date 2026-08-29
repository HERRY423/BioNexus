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
# Variants are matched as whole-token sequences after light plural folding,
# never as raw substrings ("tangram" must not trigger the "ram" memory
# concept; "zoom" must not trigger "oom").
# ---------------------------------------------------------------------------

_CONCEPT_SYNONYMS: Dict[str, Tuple[str, ...]] = {
    # pseudobulk DE concept family
    "differential_expression": (
        "differential expression", "differentially expressed", "de analysis",
        "deseq2", "pydeseq2", "edger", "condition effect", "treatment effect",
        "bulk-level", "pseudobulk", "differential state", "differential states",
        "upregulated", "downregulated", "expression changes", "expression shift",
        "de genes", "differential testing",
    ),
    "condition_comparison": (
        "vs", "versus", "between conditions", "across conditions",
        "treated control", "case control", "stimulated", "perturbed",
        "between groups", "across groups", "case versus control",
        "stimulated versus control", "compared between",
    ),
    # clustering / exploratory family
    "clustering": (
        "cluster", "clusters", "clustering", "leiden", "louvain",
        "communities", "populations", "unsupervised groups",
    ),
    "marker_genes": (
        "marker genes", "markers", "signature genes", "canonical markers",
        "rank genes groups", "positive markers", "top expressed genes",
    ),
    "dimensionality": ("umap", "tsne", "pca", "embedding", "manifold", "latent space"),
    # spatial family
    "spatial": (
        "spatial", "space", "tissue coordinates", "visium", "slide-seq", "slide seq",
        "merfish", "cosmx", "xenium", "spots", "spot", "tissue positions",
        "histological", "in situ", "stereoseq", "tangram", "spatial deconvolution",
        "imaging based", "physical coordinates",
    ),
    "spatial_statistics": (
        "moran", "morans i", "autocorrelation", "spatially variable", "svg",
        "spatial graph", "neighborhood enrichment", "ripley", "co-occurrence",
        "neighborhood graph", "spatially variable genes",
    ),
    "validity_assessment": (
        "alternative explanation", "conclusion valid", "does the conclusion hold",
        "conclusion survive", "robust to", "confound control", "permutation null",
        "sensitivity of the conclusion", "invalidated",
        "alternative explanations", "does the finding hold",
        "would the conclusion survive", "negative control", "robustness check",
    ),
    # survival family
    "survival": (
        "survival", "kaplan meier", "kaplan-meier", "log-rank", "logrank",
        "cox", "hazard", "prognosis", "prognostic", "overall survival",
        "progression-free", "time-to-event", "censoring", "clinical outcome",
    ),
    # generative models
    "generative_model": (
        "scvi", "scvi-tools", "scanvi", "totalvi", "variational",
        "deep generative", "vae", "latent embedding", "generative representation",
    ),
    # variant family
    "variant": (
        "variant", "variants", "mutation", "snv", "indel", "cnv",
        "pathogenicity", "acmg", "clinvar", "hgvs", "vus", "pathogenic",
    ),
    # annotation evidence
    # NOTE: no bare "cell-type" variant — cell types are usually the PAYLOAD of
    # spatial mapping / DE queries; bare mentions must not nominate
    # scrna.annotation_evidence. Label/annotate/reference vocabulary carries
    # the annotation-evidence intent instead.
    "annotation": (
        "annotate", "annotation", "cell type label", "identity labels",
        "reference mapping", "label transfer", "reference atlas", "azimuth",
        "celltypist", "scmap", "singler", "annotation confidence",
    ),
    # pipelines / infra
    "pipeline": ("nextflow", "nf-core", "nfcore", "pipeline", "samplesheet", "workflow launch"),
    "instrument": ("allotrope", "plate reader", "chromatography", "instrument export", "asm json"),
    "hpc": ("slurm", "sbatch", "pbs", "qsub", "lsf", "bsub", "kubernetes", "aws batch", "hpc"),
    "memory": ("memory", "ram", "out-of-core", "oom", "zarr chunking", "large matrix",
               "ram estimate", "memory footprint", "chunk size"),
    # foundation models / perturbation
    "foundation_model": ("geneformer", "scgpt", "scbert", "foundation model", "pretrained scfm"),
    "perturbation_generic": (
        "knockout", "perturbation", "perturb-seq", "perturb seq", "overexpression",
        "in silico deletion", "crispr", "knockdown", "crispr screen", "drug perturbation",
    ),
    "combinatorial_perturbation": (
        "gears", "combinatorial knockout", "combinatorial perturbation",
        "graph-enhanced perturbation", "double perturbation", "pairwise knockout",
    ),
    "niche": ("niche", "microenvironment", "tumor microenvironment", "spatial niche",
              "microenvironment composition"),
}

# ---------------------------------------------------------------------------
# Deterministic tokenization + light plural folding.
#
# Both the query and every synonym variant are normalized through the SAME
# pipeline, so inflected forms match exactly at token granularity:
#   "clusters" -> "cluster", "genes" -> "gene", "studies" -> "study".
# Matching is whole-token contiguous-subsequence, never substring, which
# removes lexical false positives such as "tangram" -> "ram" or
# "zoom" -> "oom".
# ---------------------------------------------------------------------------


def _fold(token: str) -> str:
    """Light deterministic plural fold (S-stemmer style). No dictionary needed."""
    if len(token) > 4 and token.endswith("ies"):
        return token[:-3] + "y"
    if token.endswith("sses"):
        return token[:-2]
    if len(token) > 3 and token.endswith("s") and not token.endswith(("ss", "us", "is")):
        return token[:-1]
    return token


def _tokenize(text: str) -> List[str]:
    """Lowercase, split on non-alphanumeric, fold plurals. Pure function."""
    return [_fold(t) for t in re.split(r"[^a-z0-9]+", text.lower()) if t]


def _normalize_variant_tokens(variant: str) -> List[str]:
    return _tokenize(variant)



_VARIANT_INDEX: Dict[Tuple[str, ...], str] = {}
# Normalized token tuple -> original variant string (for audit output).
_VARIANT_ORIGINAL: Dict[Tuple[str, ...], str] = {}
for _concept, _variants in _CONCEPT_SYNONYMS.items():
    for _v in _variants:
        _key = tuple(_normalize_variant_tokens(_v))
        _VARIANT_INDEX[_key] = _concept
        _VARIANT_ORIGINAL.setdefault(_key, _v)

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
    matched_variants: List[str] = field(default_factory=list)  # original synonym strings that hit

    def to_dict(self) -> Dict[str, object]:
        return {
            "nominated_capability": self.nominated_capability,
            "layer": self.layer,
            "score": round(self.score, 4),
            "runner_up": self.runner_up,
            "runner_up_score": round(self.runner_up_score, 4),
            "matched_concepts": list(self.matched_concepts),
            "matched_variants": list(self.matched_variants),
        }


def detect_concepts_and_variants(query: str) -> Tuple[List[str], List[str]]:
    """
    Whole-token variant detection over the query.

    A variant matches when its normalized token sequence appears as a
    contiguous subsequence of the query's normalized tokens. Returns
    (concepts_in_registry_order, matched_variant_original_strings).
    Deterministic and offline.
    """
    qtokens = _tokenize(query)
    found: List[str] = []
    hits: List[str] = []
    seen: set = set()
    for vkey, concept in _VARIANT_INDEX.items():
        n = len(vkey)
        if n == 0 or len(qtokens) < n:
            continue
        matched = False
        for i in range(len(qtokens) - n + 1):
            if tuple(qtokens[i:i + n]) == vkey:
                matched = True
                break
        if matched:
            hits.append(_VARIANT_ORIGINAL[vkey])
            if concept not in seen:
                seen.add(concept)
                found.append(concept)
    return found, hits


def _detect_concepts(query_lower: str) -> List[str]:
    """Return concepts whose surface variants appear in the query (token-boundary exact)."""
    return detect_concepts_and_variants(query_lower)[0]


def _rank_with_concepts(
    concepts: set, candidates: Optional[List[str]] = None
) -> List[Tuple[str, float]]:
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


def score_capabilities(query: str, candidates: Optional[List[str]] = None) -> List[Tuple[str, float]]:
    """
    Deterministically score candidate capabilities against the query.

    Score = (sum of matched concept weights) / (total profile weight), so 1.0
    means every concept the capability is built from was evidenced. Returns
    candidates sorted by descending score.
    """
    return _rank_with_concepts(set(detect_concepts_and_variants(query)[0]), candidates)


def nominate_semantically(query: str, candidates: Optional[List[str]] = None) -> SemanticNomination:
    """
    Attempt a semantic nomination. Fails closed: returns layer="none" unless a
    single candidate clears both MIN_SEMANTIC_SCORE and MIN_MARGIN.
    """
    concepts, variants = detect_concepts_and_variants(query)
    ranked = _rank_with_concepts(set(concepts), candidates)
    if not ranked or ranked[0][1] < MIN_SEMANTIC_SCORE:
        return SemanticNomination(None, "none", matched_concepts=concepts, matched_variants=variants)
    best_id, best_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0.0
    if best_score - second_score < MIN_MARGIN:
        return SemanticNomination(
            None, "none", score=best_score, runner_up=ranked[1][0] if len(ranked) > 1 else None,
            runner_up_score=second_score, matched_concepts=concepts, matched_variants=variants,
        )
    return SemanticNomination(
        best_id, "semantic", score=best_score,
        runner_up=ranked[1][0] if len(ranked) > 1 else None,
        runner_up_score=second_score, matched_concepts=concepts, matched_variants=variants,
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
