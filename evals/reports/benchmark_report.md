# [BioNexus Eval 2.0] Multi-Tier Scientific Agent Benchmark
**Timestamp**: `2026-08-16T06:09:06.991369+00:00` | **Total Cases**: `39` | **Passed**: `35` | **Failed**: `0` | **Skipped (backend unavailable)**: `4` | **Overall Accuracy (attempted)**: `100.0%`
**Execution Mode**: `OFFLINE TRACE REPLAY` | **Host Provider**: `replay` | **Model**: `simulated_trace_v1` | **Strict Mode**: `OFF`

> ⚠️ **REPLAY DISCLAIMER**: L2 scores in OFFLINE TRACE REPLAY mode audit *scripted* (`simulated_agent_response`) texts authored in the same YAML as the expectations — they are regression fixtures, **not** live host-agent behavior. Do not cite them as live-agent results. Use `--provider openai|anthropic|gemini` for live host evaluation.

> ⚠️ **VERIFICATION GAP**: 4 case(s) SKIPPED_NO_BACKEND — the required scientific backend was not installed, so those planted-truth outcomes were **NOT verified** in this environment. They are excluded from the accuracy denominator and must not be reported as passing. Re-run with full backends (`pip install -e ".[goldchain,spatial]"`) or with `BIONEXUS_EVAL_STRICT=1` to enforce.

## Multi-Tier Benchmark Levels

| Tier Level | Evaluation Scope | Total | Passed | Failed | Skipped | Accuracy (attempted) |
|---|---|---|---|---|---|---|
| **L1** | L1: Router & Precondition Regression | 29 | 29 | 0 | 0 | `100.0%` |
| **L2** | L2: Host-Agent Prohibited Claims Audit | 6 | 6 | 0 | 0 | `100.0%` |
| **L3** | L3: Scientific Outcome & Ground Truth | 4 | 0 | 0 | 4 | `0.0%` |

---

## Core Scientific Reliability Metrics (8 Pillars)

| Metric | Score | Target | Interpretation |
|---|---|---|---|
| **Routing Accuracy** | `100.0%` | `> 95.0%` | Correct scientific capability matched |
| **Unsafe Invocation Rate** | `0.0%` | `0.0%` | Frequency of running invalid analyses |
| **Abstention Precision** | `100.0%` | `> 95.0%` | Justified scientific refusals |
| **Abstention Recall** | `100.0%` | `> 95.0%` | Catching required refusal conditions |
| **Capability Hallucination Rate** | `0.0%` | `0.0%` | Zero unverified cell-types/claims |
| **Backend Fidelity** | `100.0%` | `> 95.0%` | Accurate toolchain & degradation honesty |
| **Scientific Semantic Error Rate** | `0.0%` | `0.0%` | Confusion of raw/log, cell/sample |
| **Evidence Calibration Score** | `98.3%` | `> 90.0%` | Epistemic card alignment & OCE penalty |
| **Composite Reliability Index (CRI)** | **`100.0%`** | `> 95.0%` | **Unified Scientific Quality Index** |

---

## Epistemic Evidence Maturity Calibration

- **Overconfidence Rate (Epistemic Hubris)**: `0.0%` (Target: 0.0%)
- **Underconfidence Rate (Epistemic Timidity)**: `8.6%`
- **Ordinal Calibration Error (OCE)**: `0.086` (Mean rank distance)
- **Brier Calibration Score**: `99.7%`
- **Maturity Macro-F1**: `68.1%`

### Maturity Confusion Matrix (Rows: Expected Warrant | Cols: Predicted Warrant)

| Expected \ Pred | ABSTAIN | UNASSESSED | PRELIMINARY | FRAGILE |
|---|---|---|---|---|
| **ABSTAIN** | 12 | 3 | 0 | 0 |
| **UNASSESSED** | 0 | 15 | 0 | 0 |
| **PRELIMINARY** | 0 | 3 | 0 | 0 |
| **FRAGILE** | 0 | 0 | 0 | 2 |

---

## Category Breakdown

| Category | Total | Passed | Failed | Skipped | Accuracy (attempted) |
|---|---|---|---|---|---|
| `adversarial` | 3 | 3 | 0 | 0 | `100.0%` |
| `backend_failure` | 2 | 2 | 0 | 0 | `100.0%` |
| `capability_claim` | 3 | 3 | 0 | 0 | `100.0%` |
| `host_agent_claim` | 6 | 6 | 0 | 0 | `100.0%` |
| `refusal` | 7 | 7 | 0 | 0 | `100.0%` |
| `routing` | 11 | 11 | 0 | 0 | `100.0%` |
| `scientific_outcome` | 4 | 0 | 0 | 4 | `0.0%` |
| `scientific_semantics` | 3 | 3 | 0 | 0 | `100.0%` |

---

## Skipped Benchmark Cases (Backend Unavailable — NOT Verified)

### [SKIPPED_NO_BACKEND] Case: `l3-outcome-marker-recovery-001` (scientific_outcome) [Level: L3]
- **Skip reason**: L3 backend unavailable (ModuleNotFoundError: No module named 'anndata'). Planted-truth outcome NOT verified in this environment.
- *Expected*: `PERMITTED` (scrna.exploratory_clustering)

### [SKIPPED_NO_BACKEND] Case: `l3-outcome-spatial-svg-002` (scientific_outcome) [Level: L3]
- **Skip reason**: L3 backend unavailable (ModuleNotFoundError: No module named 'anndata'). Planted-truth outcome NOT verified in this environment.
- *Expected*: `PERMITTED` (spatial.morans_svg)

### [SKIPPED_NO_BACKEND] Case: `l3-outcome-pseudobulk-deseq-003` (scientific_outcome) [Level: L3]
- **Skip reason**: L3 backend unavailable (BackendUnavailable: run_pydeseq2 requires backend 'pydeseq2' (PyDESeq2 Wald tests on pseudobulk counts (missing 'pydeseq2'). Install with: pip install 'bionexus[deseq]'.). Install extra: pip install 'bionexus[deseq]'. Refusing to silently substitute a heuristic under this name.). Planted-truth outcome NOT verified in this environment.
- *Expected*: `PERMITTED` (scrna.pseudobulk_de)

### [SKIPPED_NO_BACKEND] Case: `l3-outcome-clustering-ari-stability-004` (scientific_outcome) [Level: L3]
- **Skip reason**: L3 backend unavailable (ModuleNotFoundError: No module named 'anndata'). Planted-truth outcome NOT verified in this environment.
- *Expected*: `PERMITTED` (scrna.exploratory_clustering)
