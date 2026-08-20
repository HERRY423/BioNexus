"""
Create standard labels, seed roadmap issues, and discussion documentation on GitHub.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any, Dict, List

TOKEN = os.environ.get("GH_TOKEN", "")
REPO = "HERRY423/BioNexus"
API_BASE = f"https://api.github.com/repos/{REPO}"

LABELS = [
    {
        "name": "scientific-rule",
        "color": "0e8a16",
        "description": "Scientific rule, invariant, or statistical warrant challenge",
    },
    {
        "name": "biofailurebench",
        "color": "d93f0b",
        "description": "BioFailureBench biological trap or failure mode",
    },
    {
        "name": "external-validation",
        "color": "1d76db",
        "description": "External dataset validation or benchmark submission",
    },
    {
        "name": "scientific-review-needed",
        "color": "5319e7",
        "description": "Requires independent domain expert scientific review",
    },
    {
        "name": "cross-host",
        "color": "006b75",
        "description": "Multi-host agent evaluation (Codex, Claude Code, Cursor)",
    },
    {
        "name": "flagship-track",
        "color": "b60205",
        "description": "BioNexus Flagship Capability Certification track",
    },
    {
        "name": "epistemic-warrant",
        "color": "fbca04",
        "description": "Epistemic warrant ceiling or claim boundary",
    },
    {
        "name": "help-wanted",
        "color": "008672",
        "description": "Extra attention is needed from the community",
    },
    {
        "name": "good-first-issue",
        "color": "7057ff",
        "description": "Good for newcomers to biological AI benchmarks",
    },
]

ROADMAP_ISSUES = [
    {
        "title": "[External Validation] scrna.pseudobulk_de: Conduct independent scientific reviewer sign-off",
        "labels": ["external-validation", "scientific-review-needed", "flagship-track"],
        "body": """### Capability ID
`scrna.pseudobulk_de` (Flagship Capability A)

### Context & Goal
BioNexus requires 14/14 criteria under BNS-CF-001 to reach the `CERTIFIED` tier.
Currently, `scrna.pseudobulk_de` has satisfied 12/14 criteria (validated on real GEO GSE96583 data with PyDESeq2, 7-dimensional perturbation tests, and failure trap refusal).

The remaining criteria are:
1. `external_reviewer`: Independent scientific review of the pseudobulk invariants (BNS-010, BNS-015, BN-F001, BN-F006).
2. `cross_host_test`: Multi-host L2 claim audit execution across 2+ host agents.

### Acceptance Criteria
- [ ] Complete independent review sign-off by 1+ computational biology / biostatistics domain experts in `review/SCIENTIFIC_REVIEW.json`.
- [ ] Verify that all mathematical invariants and warrant ceilings align with published consensus.
""",
    },
    {
        "title": "[Flagship Track] scrna.annotation_evidence: Real-data benchmark on CITE-seq Hao et al. 2021",
        "labels": ["flagship-track", "external-validation", "help-wanted"],
        "body": """### Capability ID
`scrna.annotation_evidence` (Flagship Capability B)

### Context & Goal
Validate cell-type annotation warrant rules against a real-world multi-modal benchmark where cell identity ground truth is established orthogonally via CITE-seq surface protein antibody markers (e.g., Hao et al. 2021 PBMC dataset).

### Scientific Invariants under Test
- Marker-only evidence without independent reference remains capped at `TENTATIVE` / `PRELIMINARY`.
- Surface protein antibody concordance upgrades warrant to `SUPPORTED`.
- Discordant RNA vs Protein markers triggers `CONFLICTED` or `FRAGILE`.

### Acceptance Criteria
- [ ] Add data loader for CITE-seq PBMC reference.
- [ ] Generate validation report under `validation/annotation/REPORT.json`.
- [ ] Verify `published_support_fraction >= 0.50`.
""",
    },
    {
        "title": "[Flagship Track] spatial.inference_validity: Negative control null models on 10x Visium & Xenium",
        "labels": ["flagship-track", "external-validation", "help-wanted"],
        "body": """### Capability ID
`spatial.inference_validity` (Flagship Capability C)

### Context & Goal
Spatial transcriptomics analyses (Squidpy Moran's I, spatial autocorrelation, neighborhood enrichment) frequently suffer from technical edge effects and spot density artifacts.

### Scientific Invariants under Test
- Spatial autocorrelation claims require coordinate permutation negative controls (`permuted_coords_null`).
- Without negative controls, conclusion maturity is strictly capped at `FRAGILE`.
- With permutation null controls verifying empirical FDR <= 0.05, warrant advances to `SUPPORTED` / `ROBUST`.

### Acceptance Criteria
- [ ] Implement spatial coordinate shuffling null evaluation in `evals/`.
- [ ] Execute on public 10x Genomics Visium / Xenium dataset.
- [ ] Produce `validation/spatial/REPORT.json`.
""",
    },
    {
        "title": "[Cross-Host] Execute BioFailureBench claim audits across Codex and Claude Code",
        "labels": ["cross-host", "biofailurebench", "help-wanted"],
        "body": """### Context & Goal
BNS-CF-001 requires cross-host conformance verification across at least 2 independent AI agent hosts (e.g., OpenAI Codex and Anthropic Claude Code) to ensure that epistemic claim auditing and failure traps behave consistently.

### Roadmap Tasks
- [ ] Run L2 claim audits against the 30 BioFailureBench trap prompts on Claude Code.
- [ ] Run L2 claim audits against the same trap prompts on OpenAI Codex.
- [ ] Populate `cross-host/COMPARISON.json` with per-trap agreement rate (target: >= 90% concordance).
""",
    },
    {
        "title": "[BioFailureBench] Expand biological failure traps corpus from 30 to 50 traps",
        "labels": ["biofailurebench", "good-first-issue", "help-wanted"],
        "body": """### Context & Goal
BioFailureBench is the gold-standard benchmark for testing whether biological AI agents detect methodological traps (e.g. pseudoreplication, circular cell annotation, zero-replicate DE, survival analysis leakage).

We are expanding the benchmark corpus from 30 to 50 traps across new biological domains:
1. Spatial transcriptomics segmentation artifacts.
2. ATAC-seq peak calling without TSS enrichment QC.
3. Batch-confounded CRISPR Perturb-seq screens.
4. Mass spectrometry proteomics ratio compression.

### How to Contribute
Submit a new YAML trap definition following the schema in `evals/datasets/`.
""",
    },
    {
        "title": "[Scientific Rule Challenge] Formalize survival analysis Hazard Ratio vs Empirical Event Rate boundary",
        "labels": ["scientific-rule", "epistemic-warrant", "help-wanted"],
        "body": """### Epistemic Rule Under Design
Survival Analysis Warrant Ceiling (`clinical.survival_analysis`).

### Problem Statement
AI agents analyzing Kaplan-Meier curves or Cox proportional hazards models often report statistically significant Hazard Ratios (p < 0.05) on cohorts with fewer than 5 total events, leading to extreme effect size instability.

### Proposed Rule
- Require minimum event count (e.g., $E \ge 10$) per stratum before permitting `SUPPORTED` hazard ratio conclusions.
- If $E < 5$, force `FRAGILE` or `ABSTAIN` due to sparse-data bias in partial likelihood estimation.

We welcome feedback and literature citations on optimal event-per-variable thresholds.
""",
    },
    {
        "title": "[Integration] Validate Allotrope Simple Model (ASM) YAML mapping on real plate reader outputs",
        "labels": ["integration", "help-wanted"],
        "body": """### Capability ID
`instrument.allotrope_mapping` (Plugin skill: `instrument-data-to-allotrope`)

### Context & Goal
Standardizing laboratory analytical instruments (SpectraMax, EnVision, Vi-CELL) to Allotrope Simple Model (ASM) JSON / 2D CSV format using declarative YAML schemas.

### Acceptance Criteria
- [ ] Validate 5+ real plate reader raw files (TXT, CSV, Excel) against official ASM JSON schemas.
- [ ] Verify zero data loss in metadata extraction (wavelengths, temperatures, well IDs).
""",
    },
    {
        "title": "[Documentation] Create interactive Jupyter tutorial notebook for BioNexus Epistemic Warrant Engine",
        "labels": ["good-first-issue"],
        "body": """### Goal
Create a beginner-friendly, runnable Jupyter Notebook tutorial (`tutorials/01_epistemic_warrants.ipynb`) demonstrating:
1. How BioNexus evaluates `EvidenceCard` 2.0.
2. How the 4 pseudobulk inferential regimes work with live data.
3. How `audit_prohibited_claims` catches overclaims in scientific manuscripts.

### Acceptance Criteria
- [ ] Self-contained notebook running on synthetic / downsampled PBMC data.
- [ ] Includes clear diagrams and markdown explanations of epistemic maturity levels.
""",
    },
    {
        "title": "[CI/CD] Automated BioFailureBench regression matrix on GitHub Actions",
        "labels": ["conformance", "good-first-issue"],
        "body": """### Goal
Integrate the full BioFailureBench suite into `.github/workflows/ci.yml` so that every PR automatically runs:
1. `pytest tests/unit/`
2. `evals/runner.py --suite canonical`
3. Backend identity conformance audits (`verify_all_backend_identity`)

### Acceptance Criteria
- [ ] Workflow executes cleanly within GitHub Actions free-tier runners (< 5 minutes).
- [ ] PR checks block on any silent backend degradation (BN-F010) or invariant violation.
""",
    },
]


def github_request(endpoint: str, data: Dict[str, Any] | None = None, method: str = "GET", max_retries: int = 5) -> Any:
    import time
    url = f"{API_BASE}/{endpoint.lstrip('/')}"
    headers = {
        "Authorization": f"token {TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "BioNexus-Community-Init",
        "Content-Type": "application/json",
    }
    body = json.dumps(data).encode("utf-8") if data else None
    
    for attempt in range(1, max_retries + 1):
        try:
            req = urllib.request.Request(url, data=body, headers=headers, method=method)
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in (404, 422):
                raise
            if attempt == max_retries:
                raise
            time.sleep(2 * attempt)
        except Exception as e:
            if attempt == max_retries:
                raise
            time.sleep(2 * attempt)


def main() -> None:
    print(f"Connecting to GitHub API for {REPO}...")

    # 1. Create or update labels
    print("\n--- Creating / Updating GitHub Labels ---")
    for label in LABELS:
        try:
            github_request("labels", label, method="POST")
            print(f"  [CREATED] Label '{label['name']}'")
        except urllib.error.HTTPError as e:
            if e.code == 422:  # Already exists, update it
                try:
                    github_request(f"labels/{label['name']}", label, method="PATCH")
                    print(f"  [UPDATED] Label '{label['name']}'")
                except Exception as ex:
                    print(f"  [SKIP] Label '{label['name']}': {ex}")
            else:
                print(f"  [ERROR] Label '{label['name']}': {e}")
        except Exception as e:
            print(f"  [ERROR] Label '{label['name']}': {e}")

    # 2. Check existing issues
    try:
        existing_issues = github_request("issues?state=all")
        existing_titles = {i["title"] for i in existing_issues}
        print(f"\nFound {len(existing_issues)} existing issues in repository.")
    except Exception as e:
        print(f"\nCould not list issues: {e}")
        existing_titles = set()

    # 3. Create roadmap issues
    print("\n--- Creating Seed Roadmap Issues ---")
    for issue in ROADMAP_ISSUES:
        if issue["title"] in existing_titles:
            print(f"  [EXISTS] Issue '{issue['title']}' already exists, skipping.")
            continue
        try:
            created = github_request("issues", issue, method="POST")
            print(f"  [CREATED] Issue #{created['number']}: {issue['title']}")
        except Exception as e:
            print(f"  [ERROR] Failed to create issue '{issue['title']}': {e}")

    print("\nInitialization complete!")


if __name__ == "__main__":
    main()
