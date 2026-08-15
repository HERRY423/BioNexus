"""Single source of truth for skill capability grades.

Grades:
  gold-wrapper  — calls a named community tool
  heuristic     — local approximation; never claim the gold-standard name
  refuse        — missing backend must abstain
  outline       — planning / routing text, not analysis

Tiers (defect A — do not treat all 17 skills as equal):
  core       — default route for real analyses
  wrapper    — gold-standard CLI, used when the user names that job
  heuristic  — only after doctor and an explicit grade-C accept
  outline    — orientation / planning, never analysis
"""

from __future__ import annotations

from typing import List, Optional, TypedDict


class SkillRecord(TypedDict):
    name: str
    grade: str
    tier: str
    status: str
    does: str
    does_not: str
    backend: str


SKILLS: List[SkillRecord] = [
    {
        "name": "start",
        "grade": "outline",
        "tier": "outline",
        "status": "canonical",
        "does": "Orient the agent: inventory, MCP fallback vs hosted servers, capability grades.",
        "does_not": "Run analyses or imply every listed method is implemented.",
        "backend": "none",
    },
    {
        "name": "scientific-problem-selection",
        "grade": "outline",
        "tier": "outline",
        "status": "canonical",
        "does": "Decision-tree references for choosing a research problem.",
        "does_not": "Score novelty or guarantee tractability.",
        "backend": "references/",
    },
    {
        "name": "single-cell-rna-qc",
        "grade": "gold-wrapper",
        "tier": "core",
        "status": "canonical",
        "does": "scverse gold chain: inspect, MAD QC, scanpy.pp.scrublet, preprocess, Leiden, markers, plots, pseudobulk, pydeseq2.",
        "does_not": "Claim SoupX/CellBender/scDblFinder. Does not assign cell-type identity.",
        "backend": "scanpy + pydeseq2 (optional)",
    },
    {
        "name": "scvi-tools",
        "grade": "gold-wrapper",
        "tier": "core",
        "status": "canonical",
        "does": "Train scVI/scANVI/totalVI/PeakVI/MultiVI/veloVI via the scvi-tools library.",
        "does_not": "Invent a new VAE. Requires the scverse extra. Train on raw counts only.",
        "backend": "scvi-tools",
    },
    {
        "name": "nextflow-development",
        "grade": "gold-wrapper",
        "tier": "core",
        "status": "canonical",
        "does": "nf-core samplesheets, cluster config, launch artifacts, optional nextflow -preview for rnaseq/scrnaseq.",
        "does_not": "Reimplement rnaseq/sarek. Execution needs Nextflow + containers.",
        "backend": "nf-core + Nextflow",
    },
    {
        "name": "instrument-data-to-allotrope",
        "grade": "gold-wrapper",
        "tier": "wrapper",
        "status": "canonical",
        "does": "Convert instrument tables to Allotrope ASM via allotropy or YAML mappings.",
        "does_not": "Support every vendor file without a mapping.",
        "backend": "allotropy + YAML engine",
    },
    {
        "name": "biologics-design",
        "grade": "heuristic",
        "tier": "heuristic",
        "status": "heuristic",
        "does": "Fv motif liability scan; IMGT numbering if abnumber is installed; codon table rewrite.",
        "does_not": "ANARCI/IMGT without abnumber; SAP; ViennaRNA MFE unless RNA is installed.",
        "backend": "abnumber (optional) + sequence motifs",
    },
    {
        "name": "protein-language-models",
        "grade": "refuse",
        "tier": "heuristic",
        "status": "heuristic",
        "does": "ESM-2 ΔLLR if transformers/fair-esm weights load; otherwise BLOSUM62 under its own name.",
        "does_not": "Call BLOSUM an ESM model. Do not emit ACMG PP3/BP4 from BLOSUM.",
        "backend": "transformers/esm (optional); BLOSUM62 heuristic",
    },
    {
        "name": "clinical-cohort-analysis",
        "grade": "heuristic",
        "tier": "heuristic",
        "status": "heuristic",
        "does": "Kaplan-Meier + log-rank always; Cox PH if lifelines is installed; Cohen's d on caller-supplied arrays.",
        "does_not": "Download DepMap; invent LM22; call event-rate ratios Cox PH.",
        "backend": "lifelines (optional) + scipy",
    },
    {
        "name": "spatial-transcriptomics",
        "grade": "gold-wrapper",
        "tier": "core",
        "status": "canonical",
        "does": "squidpy gold chain: knn graph, Moran SVGs, spatial_scatter plots; SpatialData --table required if multi-table.",
        "does_not": "Cell2location, BayesSpace, SpaGCN, COMMOT, or vendor Visium HD/Xenium pipelines. Legacy fused-graph/NNLS scripts are grade C.",
        "backend": "squidpy (+ spatialdata for .zarr)",
    },
    {
        "name": "variant-interpretation",
        "grade": "heuristic",
        "tier": "heuristic",
        "status": "heuristic",
        "does": "ACMG/AMP combination of caller-supplied criteria; HGVS/VCF parse; PWM splice heuristic.",
        "does_not": "Run VEP/InterVar/gnomAD; auto-apply PM2/PP3/PVS1; issue CLIA reports.",
        "backend": "local combiner; optional VEP/InterVar JSON ingest",
    },
    {
        "name": "protein-structure-analysis",
        "grade": "heuristic",
        "tier": "heuristic",
        "status": "heuristic",
        "does": "Fetch PDB/AlphaFold files, CA geometry, Kabsch RMSD; write AutoDock Vina config.",
        "does_not": "Run AlphaFold, DiffDock, or P2Rank unless those binaries ran.",
        "backend": "RCSB/AF HTTP; vina/fpocket optional",
    },
    {
        "name": "multiome-integration",
        "grade": "heuristic",
        "tier": "heuristic",
        "status": "heuristic",
        "does": "Linear WNN-like fusion, ExtraTrees co-expression, overlap activity scores.",
        "does_not": "SCENIC+, GRNBoost2, chromVAR, MultiVI, or AUCell unless those libraries ran.",
        "backend": "sklearn ExtraTrees",
    },
    {
        "name": "experiment-design-agent",
        "grade": "outline",
        "tier": "outline",
        "status": "outline",
        "does": "Keyword skill routing and a 5-phase study outline template.",
        "does_not": "Execute experiments or compute P(Success).",
        "backend": "none",
    },
    {
        "name": "research-workflow-orchestrator",
        "grade": "outline",
        "tier": "outline",
        "status": "outline",
        "does": "YAML DAG topological runner that can call local MCP tools.",
        "does_not": "Replace Nextflow/Airflow.",
        "backend": "local MCP (optional)",
    },
    {
        "name": "provenance-and-audit",
        "grade": "heuristic",
        "tier": "wrapper",
        "status": "canonical",
        "does": "SHA-256 file hashes, environment snapshot, activity-aware Methods text.",
        "does_not": "Provide 21 CFR Part 11, GxP, or CLIA audit trails.",
        "backend": "bionexus.provenance",
    },
    {
        "name": "knowledge-graph-augmentation",
        "grade": "heuristic",
        "tier": "outline",
        "status": "outline",
        "does": "In-memory directed graph over caller-supplied nodes.",
        "does_not": "Live GraphRAG or automatic Open Targets queries.",
        "backend": "in-memory dict",
    },
]


def get_skill(name: str) -> SkillRecord:
    for rec in SKILLS:
        if rec["name"] == name:
            return rec
    raise KeyError(name)


def core_skills() -> List[SkillRecord]:
    return [s for s in SKILLS if s["tier"] == "core"]


def canonical_skills() -> List[SkillRecord]:
    """Return all skills with status 'canonical'."""
    return [s for s in SKILLS if s.get("status") == "canonical"]


def active_skills() -> List[SkillRecord]:
    """Return active skills (canonical + active heuristics)."""
    return [s for s in SKILLS if s.get("status") in {"canonical", "active"}]


def skills_by_status(status: str) -> List[SkillRecord]:
    """Filter skills by lifecycle status."""
    return [s for s in SKILLS if s.get("status") == status]


def skills_by_tier(tier: str) -> List[SkillRecord]:
    """Filter skills by tier."""
    return [s for s in SKILLS if s.get("tier") == tier]


def as_markdown_table(skills: Optional[List[SkillRecord]] = None) -> str:
    """Render skills as a formatted markdown table."""
    records = skills if skills is not None else SKILLS
    lines = [
        "| Skill | Tier | Status | Grade | Use when | Do not claim | Backend |",
        "|---|---|---|---|---|---|---|",
    ]
    for rec in records:
        status_val = rec.get("status", "active")
        lines.append(
            f"| `{rec['name']}` | {rec['tier']} | {status_val} | {rec['grade']} | {rec['does']} | {rec['does_not']} | `{rec['backend']}` |"
        )
    return "\n".join(lines)

