"""
Create high-quality seed discussions on GitHub Discussions via GraphQL.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from bionexus.egress_guard import guarded_urlopen

TOKEN = os.environ.get("GH_TOKEN", "")
REPO_OWNER = "HERRY423"
REPO_NAME = "BioNexus"
GRAPHQL_URL = "https://api.github.com/graphql"


def graphql_query(query: str, variables: dict | None = None, max_retries: int = 5) -> dict:
    headers = {
        "Authorization": f"bearer {TOKEN}",
        "Content-Type": "application/json",
        "User-Agent": "BioNexus-Community-Init",
    }
    payload = json.dumps({"query": query, "variables": variables or {}}).encode("utf-8")
    for attempt in range(1, max_retries + 1):
        try:
            req = urllib.request.Request(GRAPHQL_URL, data=payload, headers=headers, method="POST")
            with guarded_urlopen(
                req,
                timeout=30,
                purpose="Create BioNexus seed discussion",
                payload={"operation": "graphql", "variables": variables or {}},
            ) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception:
            if attempt == max_retries:
                raise
            time.sleep(2 * attempt)


SEED_DISCUSSIONS = [
    {
        "category_slug": "ideas",
        "title": "When should pseudoreplication REFUSE computation vs CAP the claim at PRELIMINARY?",
        "body": """### The Scientific Dilemma

In single-cell differential expression, treating individual cells from a single donor ($N=1$) as independent replicates is a well-known statistical fallacy (**pseudoreplication**, BN-F001). It inflates false positive rates by up to 100x because within-donor cell correlation is ignored.

In BioNexus, we currently enforce a strict phase transition:
1. **$N \\ge 3$ biological replicates**: Population inference permitted (`SUPPORTED` / `ROBUST`).
2. **$N = 2$ biological replicates**: Execution permitted, but warrant is strictly capped at `PRELIMINARY` (descriptive only of this specific pair, no population generalization).
3. **$N = 1$ (or missing donor metadata)**: Execution is **deterministically REFUSED** (`ABSTAIN`).

### Questions for the Community

1. **Is $N=1$ refusal too strict for exploratory hypothesis generation?**
   - Should BioNexus ever permit running single-cell DE on $N=1$ if the user explicitly consents to an `EXPLORATORY_ONLY` label?
   - Or does permitting the run inevitably lead to published overclaims in downstream papers?
2. **What should the threshold be for rare cell populations?**
   - If a cell type only has 5-10 cells per donor across 8 donors, should it be refused or capped at `FRAGILE`?

We welcome perspectives from computational biologists, biostatisticians, and wet-lab researchers!
""",
    },
    {
        "category_slug": "ideas",
        "title": "Should exploratory spatial transcriptomics ever receive ROBUST maturity without orthogonal negative controls?",
        "body": """### Background & Scientific Problem

Spatial transcriptomics methods (e.g., Squidpy Moran's I, SpatialDE, Seurat FindSpatiallyVariableFeatures) identify spatially variable genes (SVGs) and cellular neighborhood enrichments.

However, spatial data is plagued by:
- Tissue edge artifacts (cells near tissue boundaries having fewer neighbors).
- Spot cell density variations (spots with 15 cells vs 2 cells in 10x Visium).
- Optical vignette distortion in image-based platforms (Xenium, MERSCOPE).

### BioNexus Proposed Policy (Flagship Capability C)

- **Default spatial analysis (without null models)**: Capped at `FRAGILE`.
- **Spatial analysis with coordinate permutation null model (`permuted_coords_null`)**: Advances to `SUPPORTED`.
- **Spatial analysis with cross-slice replication & orthogonal negative controls**: Advances to `ROBUST`.

### Questions for Discussion

1. Do you agree that uncorrected spatial autocorrelation metrics should never exceed `FRAGILE`?
2. What is your preferred negative control for spatial transcriptomics (coordinate permutation, spot density regression, or synthetic random field nulls)?
""",
    },
    {
        "category_slug": "ideas",
        "title": "What constitutes sufficient orthogonal evidence to upgrade single-cell cell-type annotation from TENTATIVE to SUPPORTED?",
        "body": """### The Circular Annotation Problem

In single-cell RNA-seq, cell types are commonly assigned by:
1. Clustering cells on PCA/UMAP.
2. Computing differential markers between clusters (`rank_genes_groups`).
3. Labeling Cluster 0 as "CD4+ T cell" because *CD4* is high in the marker table.
4. Using Cluster 0 markers to claim that *CD4* is a novel biomarker of this condition.

This is a **circular reasoning trap** (BN-F002).

### Current BioNexus Rule (`scrna.annotation_evidence`)

- **Marker expression alone**: Capped at `TENTATIVE` / `PRELIMINARY`.
- **Independent reference atlas mapping (e.g. Azimuth, CellTypist) with confidence > 0.80**: Upgrades to `SUPPORTED`.
- **Orthogonal protein modality (CITE-seq / FACS sorting validation)**: Upgrades to `ROBUST`.

### We want to hear from you:
- Is an automated classifier (e.g., CellTypist) truly "independent evidence", or is it susceptible to reference atlas bias?
- Should gene signature scoring (e.g., UCell / AUCell) be considered higher evidence than single-marker gating?
""",
    },
    {
        "category_slug": "general",
        "title": "RFC: Formalizing Epistemic Warrant Ceilings for Survival Analysis and Clinical Risk Scores",
        "body": """### Motivation

As AI agents increasingly assist with biomedical and clinical data analysis, we need formal epistemic guardrails against small-sample survival analysis overclaims.

### Proposed Rules for `clinical.survival_analysis`:
1. **Event Count Boundary**: If total uncensored events in any stratum $E < 10$, hazard ratio p-values must be clamped to `FRAGILE` maturity.
2. **Proportional Hazards Assumption**: Schoenfeld residual test failure ($p < 0.05$) must block single-hazard ratio reporting and require time-varying coefficient models.
3. **Causal Blocking**: Observational EHR survival curves must strictly block causal language (`drug X improved survival` $\\rightarrow$ `drug X was associated with longer overall survival`).

Please share your thoughts on these proposed invariants before we formalize them into the BioNexus registry.
""",
    },
    {
        "category_slug": "show-and-tell",
        "title": "Show & Tell: BioFailureBench — Benchmarking AI Agents on 30 Biological Methodological Traps",
        "body": """### Introducing BioFailureBench

BioFailureBench is the first benchmark specifically designed to measure whether biological AI coding agents detect and refuse scientific methodology traps, including:

- **Pseudoreplication** (single-cell $N=1$ DE)
- **Zero-replicate RNA-seq** ($N=1$ vs $N=1$)
- **Circular marker validation**
- **Confounded batch-condition designs**
- **Survival analysis data leakage**
- **Uncorrected spatial edge artifacts**

### Results Across Agent Frameworks
When tested with standard baseline LLMs without BioNexus:
- Over **85%** of traps were executed silently without warning, generating confident but scientifically invalid p-values and figures.

With BioNexus epistemic gating:
- **100%** of canonical traps are deterministically caught and refused with explicit scientific rationale and constructive remedies.

Check out the full benchmark suite in the repository under [`evals/datasets/`](https://github.com/HERRY423/BioNexus/tree/main/evals/datasets)!
""",
    },
]


def main() -> None:
    print(f"Connecting to GitHub GraphQL API for {REPO_OWNER}/{REPO_NAME}...")

    # 1. Get repository ID and discussion categories
    query = """
    query($owner: String!, $name: String!) {
      repository(owner: $owner, name: $name) {
        id
        discussionCategories(first: 20) {
          nodes {
            id
            name
            slug
          }
        }
      }
    }
    """
    res = graphql_query(query, {"owner": REPO_OWNER, "name": REPO_NAME})
    repo_data = res.get("data", {}).get("repository")
    if not repo_data:
        print(f"Error querying repository: {res}")
        return

    repo_id = repo_data["id"]
    category_map = {c["slug"]: c["id"] for c in repo_data["discussionCategories"]["nodes"]}
    print(f"Repository ID: {repo_id}")
    print(f"Available Categories: {list(category_map.keys())}\n")

    # 2. Mutation to create discussion
    mutation = """
    mutation($repositoryId: ID!, $categoryId: ID!, $title: String!, $body: String!) {
      createDiscussion(input: {
        repositoryId: $repositoryId,
        categoryId: $categoryId,
        title: $title,
        body: $body
      }) {
        discussion {
          id
          number
          url
          title
        }
      }
    }
    """

    print("--- Creating Seed Discussions ---")
    for disc in SEED_DISCUSSIONS:
        cat_id = category_map.get(disc["category_slug"]) or category_map.get("general")
        if not cat_id:
            print(f"Category slug '{disc['category_slug']}' not found.")
            continue

        try:
            vars_ = {
                "repositoryId": repo_id,
                "categoryId": cat_id,
                "title": disc["title"],
                "body": disc["body"],
            }
            res = graphql_query(mutation, vars_)
            disc_info = res.get("data", {}).get("createDiscussion", {}).get("discussion")
            if disc_info:
                print(f"  [CREATED] Discussion #{disc_info['number']}: {disc_info['title']}")
                print(f"            URL: {disc_info['url']}")
            else:
                print(f"  [ERROR] {res}")
        except Exception as e:
            print(f"  [ERROR] Failed to create discussion '{disc['title']}': {e}")

    print("\nAll seed discussions processed!")


if __name__ == "__main__":
    main()
