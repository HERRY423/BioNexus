# [BioNexus Eval 2.0] Multi-Tier Scientific Agent Benchmark
**Selection**: suite=`all`, level=`all`, excluded suites=`[]`. Scores cover this selection only.
> **Evidence scope**: L1 checks routing contracts; replay L2 checks scripted text; planted-signal L3 executes backends on synthetic fixtures. Passing these checks does not establish independent scientific validation or an APPROVED empirical calibration profile.

**Timestamp**: `2026-09-04T12:23:32.217045+00:00` | **Gating Cases**: `92` | **Passed**: `92` | **Failed**: `0` | **Skipped (backend unavailable)**: `0` | **Gating Accuracy (attempted)**: `100.0%`
**Union (gating + frontier)**: `106` cases | **Union Accuracy**: `100.0%` (the honest number, BNS-LC-006)
**Execution Mode**: `OFFLINE TRACE REPLAY` | **Host Provider**: `replay` | **Model**: `simulated_trace_v1` | **Strict Mode**: `ON`

> ⚠️ **REPLAY DISCLAIMER**: L2 scores in OFFLINE TRACE REPLAY mode audit *scripted* (`simulated_agent_response`) texts authored in the same YAML as the expectations — they are regression fixtures, **not** live host-agent behavior. Do not cite them as live-agent results. Use `--provider openai|anthropic|gemini` for live host evaluation.

## Multi-Tier Benchmark Levels

| Tier Level | Evaluation Scope | Total | Passed | Failed | Skipped | Accuracy (attempted) |
|---|---|---|---|---|---|---|
| **L1** | L1: Router & Precondition Regression | 73 | 73 | 0 | 0 | `100.0%` |
| **L2** | L2: Host-Agent Prohibited Claims Audit | 6 | 6 | 0 | 0 | `100.0%` |
| **L3** | L3: Scientific Outcome & Ground Truth | 13 | 13 | 0 | 0 | `100.0%` |

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
| **Evidence Calibration Score** | `96.3%` | `> 90.0%` | Epistemic card alignment & OCE penalty |
| **Composite Reliability Index (CRI)** | **`100.0%`** | `> 95.0%` | **Unified Scientific Quality Index** |

---

## Epistemic Evidence Maturity Calibration (Gating Track)

- **Verdict**: `UNDERCONFIDENT` (overconfidence is the dominant failure mode)
- **Overconfidence Rate (Epistemic Hubris)**: `0.0%` (Target: 0.0%)
- **Underconfidence Rate (Epistemic Timidity)**: `7.6%`
- **Ordinal Calibration Error (OCE)**: `0.185` (Mean rank distance)
- **Adjacent-Rank Error Rate**: `2.2%` (hardest discrimination: PRELIMINARY vs FRAGILE vs SUPPORTED)
- **Within-One Accuracy**: `94.6%`
- **Brier Calibration Score**: `98.0%`
- **Maturity Macro-F1**: `88.2%`
- **Cases Evaluated**: `92` (calibration claims are only valid over stated case counts, BNS-EM-009)

### Per-Class Maturity Discrimination

| Maturity Class | Support | Precision | Recall | F1 |
|---|---|---|---|---|
| `ABSTAIN` | 53 | `100.0%` | `100.0%` | `100.0%` |
| `FRAGILE` | 3 | `60.0%` | `100.0%` | `75.0%` |
| `PRELIMINARY` | 6 | `100.0%` | `100.0%` | `100.0%` |
| `ROBUST` | 1 | `100.0%` | `100.0%` | `100.0%` |
| `SUPPORTED` | 15 | `100.0%` | `53.3%` | `69.6%` |
| `UNASSESSED` | 14 | `73.7%` | `100.0%` | `84.9%` |

### Maturity Confusion Matrix (Rows: Expected Warrant | Cols: Predicted Warrant)

| Expected \ Pred | ABSTAIN | UNASSESSED | PRELIMINARY | FRAGILE | SUPPORTED | ROBUST |
|---|---|---|---|---|---|---|
| **ABSTAIN** | 53 | 0 | 0 | 0 | 0 | 0 |
| **UNASSESSED** | 0 | 14 | 0 | 0 | 0 | 0 |
| **PRELIMINARY** | 0 | 0 | 6 | 0 | 0 | 0 |
| **FRAGILE** | 0 | 0 | 0 | 3 | 0 | 0 |
| **SUPPORTED** | 0 | 5 | 0 | 2 | 8 | 0 |
| **ROBUST** | 0 | 0 | 0 | 0 | 0 | 1 |

---

## Frontier Calibration Track (Known Limitations — Honest Reporting)

- **Frontier Cases**: `14` | **Passed**: `14` | **Failed**: `0` | **Pass Rate**: `100.0%`
- **Union Accuracy (gating + frontier)**: `106/106` = `100.0%`
- Frontier cases probe beyond currently-guaranteed behavior (BNS-LC-004). They are excluded from gating CRI, reported with honest pass/fail, and graduate into the gating suite once passed deterministically (BNS-LC-005).
- A gating-only 100% is NOT a calibration claim; calibration claims span the union (BNS-LC-006).

- **Graduation-eligible (passing) frontier cases**: `BF-010`, `BF-014`, `BF-026`, `frontier-coordinate-umap-substitution-001`, `frontier-insufficient-power-clustering-002`, `frontier-ambiguous-spatial-marker-003`, `frontier-cluster-vs-condition-de-conflation-004`, `frontier-ceiling-spatial-supported-claim-005`, `frontier-ceiling-pseudobulk-replicated-claim-006`, `frontier-ceiling-acmg-clinvar-replicated-007`, `frontier-ceiling-clustering-robust-claim-008`, `frontier-boundary-exactly-two-replicates-009`, `frontier-boundary-normalized-to-spatial-010`, `frontier-boundary-four-spots-refused-011`

### Union Calibration (Gating + Frontier)

- **Verdict**: `UNDERCONFIDENT`
- **Exact Accuracy**: `93.4%` | **OCE**: `0.160` | **Macro-F1**: `93.4%`
- **Overconfidence**: `0.0%` | **Underconfidence**: `6.6%`

### Cross-Host Consistency (BNS-HC-007)

- **Not evaluated**: Cross-host consistency requires L2 runs against >= 2 host providers (use --provider matrix runs).

---

## Category Breakdown

| Category | Total | Passed | Failed | Skipped | Accuracy (attempted) |
|---|---|---|---|---|---|
| `adversarial` | 5 | 5 | 0 | 0 | `100.0%` |
| `backend_failure` | 8 | 8 | 0 | 0 | `100.0%` |
| `capability_claim` | 13 | 13 | 0 | 0 | `100.0%` |
| `host_agent_claim` | 6 | 6 | 0 | 0 | `100.0%` |
| `refusal` | 15 | 15 | 0 | 0 | `100.0%` |
| `routing` | 15 | 15 | 0 | 0 | `100.0%` |
| `scientific_outcome` | 13 | 13 | 0 | 0 | `100.0%` |
| `scientific_semantics` | 17 | 17 | 0 | 0 | `100.0%` |