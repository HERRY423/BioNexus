# BioNexus Eval 2.0: Multi-Tier Host Agent & Scientific Outcome Benchmark Report

> **DO NOT CITE as current results.** This page is a historical architecture
> write-up, not the canonical benchmark. The living conformance record is
> [`evals/reports/benchmark_report.md`](../../evals/reports/benchmark_report.md)
> (timestamp `2026-08-16`, execution mode `OFFLINE TRACE REPLAY`, model
> `simulated_trace_v1`). That canonical report records L3 **0/4 executed**
> (`SKIPPED_NO_BACKEND`), gating 61/61 attempted, frontier 7/14, and union
> calibration **MISALIGNED**. Tables below that show L3 4/4 or CRI 100% are
> **not verified** by the canonical report and MUST NOT be quoted as current
> scientific outcome evidence.

## Executive Summary

BioNexus Eval 2.0 is the formal evaluation harness for validating scientific coding agent plugins and reliability substrates. It evaluates computational biology coding assistants across three hierarchically decoupled tiers:

- **L1 (Router & Precondition Contract Regression)**: Deterministic evaluation of query intent routing, single-cell vs sample-level precondition validation, and required statistical remedies (e.g., negative binomial GLM vs Welch's t-test).
- **L2 (Host-Agent Claim Audit & Anti-Hallucination)**: Live host model invocation (OpenAI Codex/GPT-4o, Anthropic Claude 3.5 Sonnet, Google Gemini, Antigravity) and offline trace replay, auditing generated natural language and code outputs against prohibited uncertified claims (e.g., cell-type over-assignment, clinical diagnostic assertions, uncalibrated biomarker claims).
- **L3 (Scientific Outcome & Ground Truth Recovery)**: Rigorous end-to-end biological execution benchmarks on synthetic and benchmark datasets with planted ground truth, verifying actual statistical signal recovery (marker gene recall, spatial Moran's $I$ gradient recovery, PyDESeq2 condition DEG discovery, and Leiden clustering parameter stability).

---

## Benchmark Architecture & Execution Modes

```
+-------------------------------------------------------------------------------+
|                           BioNexus Eval 2.0 Suite                             |
+-------------------------------------------------------------------------------+
                                        |
       +--------------------------------+-------------------------------+
       |                                |                               |
       v                                v                               v
+-------------------------------+ +-----------------------------+ +-----------------------------+
|    Tier L1: Router & Gates    | | Tier L2: Host Agent Audit   | | Tier L3: Scientific Outcome |
|  - Intent Matching (29 cases) | |  - Live LLM Adapters:       | |  - Scanpy Marker Recall     |
|  - Precondition Violations    | |    * OpenAI (GPT-4o/Codex)  | |  - Squidpy Moran's I SVGs   |
|  - Remedy Prescriptions       | |    * Anthropic (Claude 3.5) | |  - PyDESeq2 Condition DEGs  |
|  - Fail-Closed Epistemic Gate | |    * Google Gemini          | |  - Leiden ARI Stability     |
|                               | |  - Deterministic Trace      | |  - Zero Swallowed Runtime   |
|                               | |    Replay Mode (CI Matrix)  | |    Exceptions (Fail-Strict) |
+-------------------------------+ +-----------------------------+ +-----------------------------+
```

### Execution Mode Matrix

| Mode | Target Platform / Provider | Purpose | Network / Key Requirements |
|---|---|---|---|
| **Live Host Invocation** | OpenAI (`gpt-4o`, `gpt-4o-mini`), Anthropic (`claude-3-5-sonnet`), Gemini (`gemini-1.5-pro`) | Real-world interactive agent evaluation | Requires `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, or `GEMINI_API_KEY` |
| **Offline Trace Replay** | Deterministic Replay Engine (`simulated_trace_v1`) | Fast, reproducible CI matrix validation across 12 OS/Python targets | Offline, 0 API keys required |

---

## Comprehensive Evaluation Results

### 1. Multi-Tier Benchmark Scores — superseded, do not cite

The scores originally printed here (L1/L2/L3 100%, CRI 100%) are **not** the
canonical record. Cite [`evals/reports/benchmark_report.md`](../../evals/reports/benchmark_report.md) instead:

| Level | Canonical status (2026-08-16 replay) |
|---|---|
| **L1** | 55/55 attempted (router & precondition regression) |
| **L2** | 6/6 attempted in **offline trace replay**, not live host providers |
| **L3** | **0/4 executed** (`SKIPPED_NO_BACKEND`; planted-truth outcomes not verified) |
| **Union calibration** | **MISALIGNED** (gating + frontier) |

---

### 2–3. Reliability metrics and calibration — superseded, do not cite

Score tables that previously appeared here (including CRI 100%, routing 100%,
and a local warrant confusion matrix) have been removed so they cannot be
quoted as current results. Use
[`evals/reports/benchmark_report.md`](../../evals/reports/benchmark_report.md).

---

## Ground-Truth Biological Outcome Benchmarks (L3 Breakdown)

**Canonical status:** these four L3 cases were **not executed** in
`evals/reports/benchmark_report.md` (`SKIPPED_NO_BACKEND`). The outcomes
below are historical narrative from this page and are **not** verified
planted-truth results. Re-run with `pip install -e ".[goldchain,spatial]"`
and `BIONEXUS_EVAL_STRICT=1` before treating any L3 number as evidence.

Historical write-up (unverified in the canonical report):

1. **Single-Cell Marker Recovery (`l3-outcome-marker-recovery-001`)**:
   - **Pipeline**: Scanpy gold-chain preprocessing $\to$ PCA $\to$ UMAP $\to$ Leiden $\to$ Wilcoxon rank-sum marker calling.
   - **Ground Truth**: Planted marker genes `CD3D`, `MS4A1`, `CD14`.
   - **Outcome**: unverified on this page; canonical report skipped this case (`SKIPPED_NO_BACKEND`).
2. **Spatial Variable Gene Discovery (`l3-outcome-spatial-svg-002`)**:
   - **Pipeline**: Squidpy spatial coordinate graph $\to$ Spatial neighborhood connectivity $\to$ Moran's $I$ autocorrelation.
   - **Ground Truth**: Planted spatial gradient `SVG_LEFT` (Target Moran's $I \ge 0.30$).
   - **Outcome**: unverified on this page; canonical report skipped this case (`SKIPPED_NO_BACKEND`).
3. **Condition Pseudobulk Differential Expression (`l3-outcome-pseudobulk-deseq-003`)**:
   - **Pipeline**: Sample-level pseudobulk count aggregation $\to$ PyDESeq2 negative binomial dispersion modeling $\to$ Wald test.
   - **Ground Truth**: Planted condition DEG `g0` with log2 fold change $\ge 2.0$.
   - **Outcome**: unverified on this page; canonical report skipped this case (`SKIPPED_NO_BACKEND`).
4. **Leiden Resolution Stability (`l3-outcome-clustering-ari-stability-004`)**:
   - **Pipeline**: Resolution perturbation sweep ($r=0.5$ vs $r=0.8$) $\to$ Cluster partition comparison.
   - **Ground Truth**: Partition stability $\text{ARI} \ge 0.80$.
   - **Outcome**: unverified on this page; canonical report skipped this case (`SKIPPED_NO_BACKEND`).

---

## Machine-Readable Run Artifact Contract Handoff

BioNexus guarantees that every scientific analysis run emits a standard machine-readable artifact bundle:

```
run/
├── run.json            # Machine-readable entry point & run metadata
├── inputs.json         # Input dataset paths, hashes, and preconditions
├── parameters.json     # Hyperparameters, random seeds, and resolution sweeps
├── results/            # Primary tabular outputs (DEGs, markers, SVGs)
├── figures/            # High-resolution vector/raster figures
├── evidence.json       # EvidenceCard 2.0 3-layer epistemic assessment
├── provenance.json     # Git commit, dirty status, environment, CLI invocations
├── environment.json    # Exact Python runtime, installed package versions, CUDA state
└── logs/               # Full execution logs and terminal captures
```

Downstream host agents can programmatically inspect `run.json` and `evidence.json` via:

```bash
bionexus inspect-run <run_directory> --json
```

---

## CLI Usage Instructions

### Running Multi-Tier Evaluations

```bash
# Run all benchmark tiers (L1 + L2 + L3) offline in replay mode
python -m bionexus.cli eval --level all --provider replay

# Run live OpenAI host evaluation (requires OPENAI_API_KEY)
python -m bionexus.cli eval --level L2 --provider openai --model gpt-4o-mini

# Run live Anthropic Claude host evaluation (requires ANTHROPIC_API_KEY)
python -m bionexus.cli eval --level L2 --provider anthropic --model claude-3-5-sonnet-20241022

# Save benchmark report to the canonical path (do not write a second 100% page)
python -m bionexus.cli eval --level all --provider replay --report evals/reports/benchmark_report.md
```
