# End-to-End on Real Data: three gates, one donor-aware analysis

This tutorial runs the complete BioNexus workflow on a **real public dataset
already committed to this repository**: Kang et al. 2018 (GSE96583), 8 lupus
donors x 2 conditions (IFN-beta stimulation vs control), 13,487 cells x 14,053
genes of raw counts (`data/flagship/kang2018_pbmc_ifnb/pbmc_ifnb_counts.h5ad`,
SHA-256-pinned in `validation/pseudobulk/`). Every output block below was
captured from an actual run.

**What you will see**: the same gate that blocks the classic pseudoreplication
trap (the front-page case), a permitted donor-aware analysis, a static audit of
the analysis script, and a claim verification that caps the conclusion at
exactly the evidence that supports it.

Requirements: `pip install -e ".[goldchain,deseq]"` (or use the container image
— see `container/apptainer.def`), and the repository checked out.

---

## Gate 1 — preflight: the trap refuses itself

An agent proposes cell-by-cell differential expression (treating ~6,700 cells
per condition as replicates). Declared as a single-replicate design, preflight
refuses **before any compute**:

```console
$ echo '{"min_replicates_per_condition": 1}' > /tmp/meta_single_rep.json
$ bionexus preflight data/flagship/kang2018_pbmc_ifnb/pbmc_ifnb_counts.h5ad \
      --intent de --metadata /tmp/meta_single_rep.json

=== BioNexus Preflight ===

INTENT
Single-Cell Pseudobulk Differential Expression  (scrna.pseudobulk_de)

DATA STATE
[OK] matrix state: raw integer-like counts present
[OK] cells: 13487 cells x 14053 features
[OK] condition metadata: condition column 'condition' present
[OK] biological samples: 8 unique donors across 2 conditions; minimum 8 donors in a group

RISKS
[!!] BN-F002: one group contains only 1 biological replicate(s)

DECISION
ABSTAIN -> REFUSE
  Analysis is scientifically invalid or prohibited by BioNexus capability contract 'scrna.pseudobulk_de'.
  failure modes: BN-F002

FORBIDDEN CLAIM
- causal_interaction: ...
- clinical_diagnosis: ...

REMEDY
- Condition DE is statistically invalid without biological replicates (pseudoreplication).
  Collect additional replicates or report exploratory marker rankings only.
```

Note what the gate did **not** do: it did not silently run a cell-level test,
and it did not refuse the dataset itself — the same file passes when the design
is declared honestly (next step), because the cohort really has 8 donors.

## Gate 1 (again) — the honest design is permitted

```console
$ bionexus preflight data/flagship/kang2018_pbmc_ifnb/pbmc_ifnb_counts.h5ad --intent de

DATA STATE
[OK] matrix state: raw integer-like counts present
[OK] biological samples: 8 unique donors across 2 conditions; minimum 8 donors in a group

RISKS
(none detected by the deterministic trap screen)

DECISION
PERMITTED -> RUN PERMITTED
  ... Purpose: unspecified; evidence ceiling: FRAGILE. Research purpose is
  UNSPECIFIED: conclusions are capped at FRAGILE until a purpose
  (exploratory / screening / confirmatory / causal / clinical) is explicitly declared.
```

Preconditions satisfied — but note the **evidence ceiling**: with no declared
research purpose the conclusion is capped. The gate constrains claims, not just
executions.

## The analysis — donor-aware pseudobulk DE

`examples/pseudobulk_de_tutorial.py` aggregates cells to donor x condition
pseudobulk samples (8 x 2 = 16 samples), runs the canonical PyDESeq2 Wald test,
and records the claim in a Claim–Evidence Ledger:

```console
$ python examples/pseudobulk_de_tutorial.py --out results
{
  "summary": {
    "n_pseudobulk_samples": 16,
    "donors_per_condition": {"ctrl": 8, "stim": 8},
    "n_genes_tested": 14053,
    "n_significant_padj_lt_0_05": 2788,
    "n_significant_abs_lfc_ge_1": 1381,
    "top5": [
      {"gene": "IFI16",  "log2FoldChange": 2.61, "padj": 5.1e-191},
      {"gene": "DDX58",  "log2FoldChange": 4.39, "padj": 2.3e-172},
      {"gene": "TRIM22", "log2FoldChange": 3.58, "padj": 2.8e-145}, ...
    ]
  }
}
```

The recovered genes are canonical interferon-stimulated genes (IFI16, DDX58,
TRIM22, ISG family) — the biology is where the literature says it is.

## Gate 2 — audit the analysis script

```console
$ bionexus audit examples/pseudobulk_de_tutorial.py

VERDICT: PASSED (no FATAL findings) | ADVISORY: 0 | failure modes: none

DISCLAIMER: Static-analysis heuristics: findings are evidence of scientific
flaws, but absence of findings is NOT proof of validity.
```

Try auditing a script that runs `rank_genes_groups` between conditions on
single cells — the BFA rules catch cell-level pseudoreplication.

## Gate 3 — verify the claim against its evidence

```console
$ bionexus verify results/bionexus.ledger.json

Warrant: PRELIMINARY
Not warranted:
- "Claiming causal molecular interaction or regulation from correlational
   evidence ..." (forbidden: causal_interaction)
- "Issuing clinical diagnosis or confirmatory disease calls ..." (forbidden: clinical_diagnosis)

OVERALL: VERIFIED (1/1 claims clean)
```

The ledger claim is deliberately worded as **associational** ("is associated
with differential expression…"), and verification holds it at
`PRELIMINARY`: the design supports a stimulation response, not a causal
mechanism. Reword the claim to "IFN-beta *causes* …" and `verify` fails the
warrant — try it.

---

## Where the three gates live on a cluster

`cluster/slurm/` contains an sbatch template and a Slurm-native dependency
chain wiring exactly these three gates into `sbatch` jobs (preflight refusal
cancels the analysis job; verify rejection fails the verify job so downstream
`--dependency=afterok` chains cannot consume unwarranted results), plus the
Apptainer image definition (`container/apptainer.def`) and its CI build.

## Honest boundaries of this tutorial

- Outputs above were captured from a real run on the committed cohort; your
  exact numbers can differ slightly across PyDESeq2 versions.
- The evidence ceiling mechanics (`FRAGILE` / `PRELIMINARY`) reflect declared
  purpose and evidence, not opinion; declare a purpose only if you have one.
- This tutorial demonstrates research-use-only analysis. Nothing here is a
  clinical or diagnostic claim.
