# [BioNexus Eval 2.0] Multi-Tier Scientific Agent Benchmark
**Selection**: suite=`l3_scientific_outcomes`, level=`L3`, excluded suites=`[]`. Scores cover this selection only.
> **Evidence scope**: L1 checks routing contracts; replay L2 checks scripted text; planted-signal L3 executes backends on synthetic fixtures. Passing these checks does not establish independent scientific validation or an APPROVED empirical calibration profile.

**Timestamp**: `2026-09-04T09:42:03.218669+00:00` | **Gating Cases**: `5` | **Passed**: `5` | **Failed**: `0` | **Skipped (backend unavailable)**: `0` | **Gating Accuracy (attempted)**: `100.0%`
**Union (gating + frontier)**: `5` cases | **Union Accuracy**: `100.0%` (the honest number, BNS-LC-006)
**Execution Mode**: `OFFLINE TRACE REPLAY` | **Host Provider**: `replay` | **Model**: `simulated_trace_v1` | **Strict Mode**: `ON`

> ⚠️ **REPLAY DISCLAIMER**: L2 scores in OFFLINE TRACE REPLAY mode audit *scripted* (`simulated_agent_response`) texts authored in the same YAML as the expectations — they are regression fixtures, **not** live host-agent behavior. Do not cite them as live-agent results. Use `--provider openai|anthropic|gemini` for live host evaluation.

## Multi-Tier Benchmark Levels

| Tier Level | Evaluation Scope | Total | Passed | Failed | Skipped | Accuracy (attempted) |
|---|---|---|---|---|---|---|
| **L1** | L1: Router & Precondition Regression | 0 | 0 | 0 | 0 | `0.0%` |
| **L2** | L2: Host-Agent Prohibited Claims Audit | 0 | 0 | 0 | 0 | `0.0%` |
| **L3** | L3: Scientific Outcome & Ground Truth | 5 | 5 | 0 | 0 | `100.0%` |

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
- **Cases Evaluated**: `5` (calibration claims are only valid over stated case counts, BNS-EM-009)

### Per-Class Maturity Discrimination

| Maturity Class | Support | Precision | Recall | F1 |
|---|---|---|---|---|
| `SUPPORTED` | 5 | `100.0%` | `100.0%` | `100.0%` |

### Maturity Confusion Matrix (Rows: Expected Warrant | Cols: Predicted Warrant)

| Expected \ Pred | SUPPORTED |
|---|---|
| **SUPPORTED** | 5 |

---

## Category Breakdown

| Category | Total | Passed | Failed | Skipped | Accuracy (attempted) |
|---|---|---|---|---|---|
| `scientific_outcome` | 5 | 5 | 0 | 0 | `100.0%` |