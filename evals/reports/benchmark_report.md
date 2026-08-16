# [BioNexus Eval 2.0] Multi-Tier Scientific Agent Benchmark
**Timestamp**: `2026-08-16T15:35:55.484888+00:00` | **Gating Cases**: `65` | **Passed**: `61` | **Failed**: `0` | **Skipped (backend unavailable)**: `4` | **Gating Accuracy (attempted)**: `100.0%`
**Union (gating + frontier)**: `79` cases | **Union Accuracy**: `90.7%` (the honest number, BNS-LC-006)
**Execution Mode**: `OFFLINE TRACE REPLAY` | **Host Provider**: `auto` | **Model**: `simulated_trace_v1` | **Strict Mode**: `OFF`

> ⚠️ **REPLAY DISCLAIMER**: L2 scores in OFFLINE TRACE REPLAY mode audit *scripted* (`simulated_agent_response`) texts authored in the same YAML as the expectations — they are regression fixtures, **not** live host-agent behavior. Do not cite them as live-agent results. Use `--provider openai|anthropic|gemini` for live host evaluation.

> ⚠️ **VERIFICATION GAP**: 4 case(s) SKIPPED_NO_BACKEND — the required scientific backend was not installed, so those planted-truth outcomes were **NOT verified** in this environment. They are excluded from the accuracy denominator and must not be reported as passing. Re-run with full backends (`pip install -e ".[goldchain,spatial]"`) or with `BIONEXUS_EVAL_STRICT=1` to enforce.

## Multi-Tier Benchmark Levels

| Tier Level | Evaluation Scope | Total | Passed | Failed | Skipped | Accuracy (attempted) |
|---|---|---|---|---|---|---|
| **L1** | L1: Router & Precondition Regression | 55 | 55 | 0 | 0 | `100.0%` |
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
| **Evidence Calibration Score** | `100.0%` | `> 90.0%` | Epistemic card alignment & OCE penalty |
| **Composite Reliability Index (CRI)** | **`100.0%`** | `> 95.0%` | **Unified Scientific Quality Index** |

---

## Epistemic Evidence Maturity Calibration (Gating Track)

- **Verdict**: `CALIBRATED` (overconfidence is the dominant failure mode)
- **Overconfidence Rate (Epistemic Hubris)**: `0.0%` (Target: 0.0%)
- **Underconfidence Rate (Epistemic Timidity)**: `0.0%`
- **Ordinal Calibration Error (OCE)**: `0.000` (Mean rank distance)
- **Adjacent-Rank Error Rate**: `0.0%` (hardest discrimination: PRELIMINARY vs FRAGILE vs SUPPORTED)
- **Within-One Accuracy**: `100.0%`
- **Brier Calibration Score**: `100.0%`
- **Maturity Macro-F1**: `100.0%`
- **Cases Evaluated**: `61` (calibration claims are only valid over stated case counts, BNS-EM-009)
- **Skipped (no backend, not executed)**: `4` — excluded from calibration; unexecuted analyses carry no maturity claim

### Per-Class Maturity Discrimination

| Maturity Class | Support | Precision | Recall | F1 |
|---|---|---|---|---|
| `ABSTAIN` | 36 | `100.0%` | `100.0%` | `100.0%` |
| `FRAGILE` | 4 | `100.0%` | `100.0%` | `100.0%` |
| `PRELIMINARY` | 5 | `100.0%` | `100.0%` | `100.0%` |
| `SUPPORTED` | 2 | `100.0%` | `100.0%` | `100.0%` |
| `UNASSESSED` | 14 | `100.0%` | `100.0%` | `100.0%` |

### Maturity Confusion Matrix (Rows: Expected Warrant | Cols: Predicted Warrant)

| Expected \ Pred | ABSTAIN | UNASSESSED | PRELIMINARY | FRAGILE | SUPPORTED |
|---|---|---|---|---|---|
| **ABSTAIN** | 36 | 0 | 0 | 0 | 0 |
| **UNASSESSED** | 0 | 14 | 0 | 0 | 0 |
| **PRELIMINARY** | 0 | 0 | 5 | 0 | 0 |
| **FRAGILE** | 0 | 0 | 0 | 4 | 0 |
| **SUPPORTED** | 0 | 0 | 0 | 0 | 2 |

---

## Frontier Calibration Track (Known Limitations — Honest Reporting)

- **Frontier Cases**: `14` | **Passed**: `7` | **Failed**: `7` | **Pass Rate**: `50.0%`
- **Union Accuracy (gating + frontier)**: `68/79` = `90.7%`
- Frontier cases probe beyond currently-guaranteed behavior (BNS-LC-004). They are excluded from gating CRI, reported with honest pass/fail, and graduate into the gating suite once passed deterministically (BNS-LC-005).
- A gating-only 100% is NOT a calibration claim; calibration claims span the union (BNS-LC-006).

### Open Known Limitations

- **`BF-010`** [L1/scientific_semantics]
  - Status mismatch: Expected DEGRADED_ADVISORY, got PERMITTED (Rationale: Scientific preconditions, input semantics, and backend for 'scrna.pseudobulk_de' are fully satisfied.)
  - Missing required remedy keyword: 'power' (Actual: [])
  - Evidence ceiling mismatch: claimed ROBUST, ABI-clamped to SUPPORTED, expected FRAGILE
- **`BF-014`** [L1/scientific_semantics]
  - Status mismatch: Expected DEGRADED_ADVISORY, got PERMITTED (Rationale: Scientific preconditions, input semantics, and backend for 'scrna.exploratory_clustering' are fully satisfied.)
  - Missing required remedy keyword: 'doublet' (Actual: [])
- **`BF-026`** [L1/capability_claim]
  - Missing required remedy keyword: 'negative' (Actual: [])
  - Evidence ceiling mismatch: claimed SUPPORTED, ABI-clamped to SUPPORTED, expected TENTATIVE
- **`frontier-coordinate-umap-substitution-001`** [L1/scientific_semantics]
  - Status mismatch: Expected ABSTAIN, got PERMITTED (Rationale: Scientific preconditions, input semantics, and backend for 'scrna.exploratory_clustering' are fully satisfied.)
  - Capability mismatch: Expected 'spatial.morans_svg', got 'scrna.exploratory_clustering'
  - Missing expected violation keyword: 'embedding' (Actual: [])
- **`frontier-insufficient-power-clustering-002`** [L1/scientific_semantics]
  - Status mismatch: Expected DEGRADED_ADVISORY, got PERMITTED (Rationale: Scientific preconditions, input semantics, and backend for 'scrna.exploratory_clustering' are fully satisfied.)
- **`frontier-ambiguous-spatial-marker-003`** [L1/routing]
  - Capability mismatch: Expected 'spatial.morans_svg', got 'scrna.exploratory_clustering'
- **`frontier-cluster-vs-condition-de-conflation-004`** [L1/scientific_semantics]
  - Status mismatch: Expected PERMITTED, got NEEDS_DATA (Rationale: Condition differential expression requires biological replicate groupings to avoid single-cell pseudoreplication.)
  - Capability mismatch: Expected 'scrna.exploratory_clustering', got 'scrna.pseudobulk_de'

- **Graduation-eligible (passing) frontier cases**: `frontier-ceiling-spatial-supported-claim-005`, `frontier-ceiling-pseudobulk-replicated-claim-006`, `frontier-ceiling-acmg-clinvar-replicated-007`, `frontier-ceiling-clustering-robust-claim-008`, `frontier-boundary-exactly-two-replicates-009`, `frontier-boundary-normalized-to-spatial-010`, `frontier-boundary-four-spots-refused-011`

### Union Calibration (Gating + Frontier)

- **Verdict**: `MISALIGNED`
- **Exact Accuracy**: `93.3%` | **OCE**: `0.107` | **Macro-F1**: `90.1%`
- **Overconfidence**: `2.7%` | **Underconfidence**: `2.7%`

### Cross-Host Consistency (BNS-HC-007)

- **Not evaluated**: Cross-host consistency requires L2 runs against >= 2 host providers (use --provider matrix runs).

---

## Category Breakdown

| Category | Total | Passed | Failed | Skipped | Accuracy (attempted) |
|---|---|---|---|---|---|
| `adversarial` | 3 | 3 | 0 | 0 | `100.0%` |
| `backend_failure` | 3 | 3 | 0 | 0 | `100.0%` |
| `capability_claim` | 9 | 9 | 0 | 0 | `100.0%` |
| `host_agent_claim` | 6 | 6 | 0 | 0 | `100.0%` |
| `refusal` | 12 | 12 | 0 | 0 | `100.0%` |
| `routing` | 12 | 12 | 0 | 0 | `100.0%` |
| `scientific_outcome` | 4 | 0 | 0 | 4 | `0.0%` |
| `scientific_semantics` | 16 | 16 | 0 | 0 | `100.0%` |

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
