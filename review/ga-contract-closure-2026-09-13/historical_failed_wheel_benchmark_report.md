# [BioNexus Eval 2.0] Multi-Tier Scientific Agent Benchmark
**Selection**: suite=`all`, level=`all`, excluded suites=`['flagship_validation']`. Scores cover this selection only.
> **Evidence scope**: L1 checks routing contracts; replay L2 checks scripted text; planted-signal L3 executes backends on synthetic fixtures. Passing these checks does not establish independent scientific validation or an APPROVED empirical calibration profile.

**Timestamp**: `2026-09-13T15:09:30.976925+00:00` | **Gating Cases**: `84` | **Passed**: `65` | **Failed**: `19` | **Skipped (backend unavailable)**: `5` | **Gating Accuracy (attempted)**: `77.4%`
**Union (gating + frontier)**: `98` cases | **Union Accuracy**: `72.4%` (the honest number, BNS-LC-006)
**Execution Mode**: `OFFLINE TRACE REPLAY` | **Host Provider**: `auto` | **Model**: `simulated_trace_v1` | **Strict Mode**: `ON`

> ⚠️ **REPLAY DISCLAIMER**: L2 scores in OFFLINE TRACE REPLAY mode audit *scripted* (`simulated_agent_response`) texts authored in the same YAML as the expectations — they are regression fixtures, **not** live host-agent behavior. Do not cite them as live-agent results. Use `--provider openai|anthropic|gemini` for live host evaluation.

> ⚠️ **VERIFICATION GAP**: 5 case(s) SKIPPED_NO_BACKEND — the required scientific backend was not installed, so those planted-truth outcomes were **NOT verified** in this environment. They are excluded from the accuracy denominator and must not be reported as passing. Re-run with full backends (`pip install -e ".[goldchain,spatial]"`) or with `BIONEXUS_EVAL_STRICT=1` to enforce.

## Multi-Tier Benchmark Levels

| Tier Level | Evaluation Scope | Total | Passed | Failed | Skipped | Accuracy (attempted) |
|---|---|---|---|---|---|---|
| **L1** | L1: Router & Precondition Regression | 73 | 59 | 14 | 0 | `80.8%` |
| **L2** | L2: Host-Agent Prohibited Claims Audit | 6 | 6 | 0 | 0 | `100.0%` |
| **L3** | L3: Scientific Outcome & Ground Truth | 5 | 0 | 0 | 5 | `0.0%` |

---

## Core Scientific Reliability Metrics (8 Pillars)

| Metric | Score | Target | Interpretation |
|---|---|---|---|
| **Routing Accuracy** | `53.3%` | `> 95.0%` | Correct scientific capability matched |
| **Unsafe Invocation Rate** | `0.0%` | `0.0%` | Frequency of running invalid analyses |
| **Abstention Precision** | `78.8%` | `> 95.0%` | Justified scientific refusals |
| **Abstention Recall** | `100.0%` | `> 95.0%` | Catching required refusal conditions |
| **Capability Hallucination Rate** | `30.8%` | `0.0%` | Zero unverified cell-types/claims |
| **Backend Fidelity** | `100.0%` | `> 95.0%` | Accurate toolchain & degradation honesty |
| **Scientific Semantic Error Rate** | `11.8%` | `0.0%` | Confusion of raw/log, cell/sample |
| **Evidence Calibration Score** | `97.2%` | `> 90.0%` | Epistemic card alignment & OCE penalty |
| **Composite Reliability Index (CRI)** | **`83.2%`** | `> 95.0%` | **Unified Scientific Quality Index** |

---

## Epistemic Evidence Maturity Calibration (Gating Track)

- **Verdict**: `UNDERCONFIDENT` (overconfidence is the dominant failure mode)
- **Overconfidence Rate (Epistemic Hubris)**: `0.0%` (Target: 0.0%)
- **Underconfidence Rate (Epistemic Timidity)**: `7.6%`
- **Ordinal Calibration Error (OCE)**: `0.139` (Mean rank distance)
- **Adjacent-Rank Error Rate**: `3.8%` (hardest discrimination: PRELIMINARY vs FRAGILE vs SUPPORTED)
- **Within-One Accuracy**: `96.2%`
- **Brier Calibration Score**: `98.7%`
- **Maturity Macro-F1**: `65.8%`
- **Cases Evaluated**: `79` (calibration claims are only valid over stated case counts, BNS-EM-009)
- **Skipped (no backend, not executed)**: `5` — excluded from calibration; unexecuted analyses carry no maturity claim

### Per-Class Maturity Discrimination

| Maturity Class | Support | Precision | Recall | F1 |
|---|---|---|---|---|
| `ABSTAIN` | 53 | `79.1%` | `100.0%` | `88.3%` |
| `FRAGILE` | 3 | `100.0%` | `66.7%` | `80.0%` |
| `PRELIMINARY` | 6 | `100.0%` | `50.0%` | `66.7%` |
| `ROBUST` | 1 | `100.0%` | `100.0%` | `100.0%` |
| `SUPPORTED` | 2 | `0.0%` | `0.0%` | `0.0%` |
| `UNASSESSED` | 14 | `100.0%` | `42.9%` | `60.0%` |

### Maturity Confusion Matrix (Rows: Expected Warrant | Cols: Predicted Warrant)

| Expected \ Pred | ABSTAIN | UNASSESSED | PRELIMINARY | FRAGILE | SUPPORTED | ROBUST |
|---|---|---|---|---|---|---|
| **ABSTAIN** | 53 | 0 | 0 | 0 | 0 | 0 |
| **UNASSESSED** | 8 | 6 | 0 | 0 | 0 | 0 |
| **PRELIMINARY** | 3 | 0 | 3 | 0 | 0 | 0 |
| **FRAGILE** | 1 | 0 | 0 | 2 | 0 | 0 |
| **SUPPORTED** | 2 | 0 | 0 | 0 | 0 | 0 |
| **ROBUST** | 0 | 0 | 0 | 0 | 0 | 1 |

---

## Frontier Calibration Track (Known Limitations — Honest Reporting)

- **Frontier Cases**: `14` | **Passed**: `6` | **Failed**: `8` | **Pass Rate**: `42.9%`
- **Union Accuracy (gating + frontier)**: `71/98` = `72.4%`
- Frontier cases probe beyond currently-guaranteed behavior (BNS-LC-004). They are excluded from gating CRI, reported with honest pass/fail, and graduate into the gating suite once passed deterministically (BNS-LC-005).
- A gating-only 100% is NOT a calibration claim; calibration claims span the union (BNS-LC-006).

### Open Known Limitations

- **`frontier-insufficient-power-clustering-002`** [L1/scientific_semantics]
  - Status mismatch: Expected DEGRADED_ADVISORY, got ABSTAIN (Rationale: Canonical backend 'scanpy' required by capability 'scrna.exploratory_clustering' is not available. Backend readiness binds to the capability: no silent substitution, no skill-based exceptions.)
- **`frontier-ambiguous-spatial-marker-003`** [L1/routing]
  - Status mismatch: Expected PERMITTED, got ABSTAIN (Rationale: Canonical backend 'squidpy' required by capability 'spatial.morans_svg' is not available. Backend readiness binds to the capability: no silent substitution, no skill-based exceptions.)
- **`frontier-cluster-vs-condition-de-conflation-004`** [L1/scientific_semantics]
  - Status mismatch: Expected PERMITTED, got ABSTAIN (Rationale: Canonical backend 'scanpy' required by capability 'scrna.exploratory_clustering' is not available. Backend readiness binds to the capability: no silent substitution, no skill-based exceptions.)
- **`frontier-ceiling-spatial-supported-claim-005`** [L1/scientific_semantics]
  - Status mismatch: Expected PERMITTED, got ABSTAIN (Rationale: Canonical backend 'squidpy' required by capability 'spatial.morans_svg' is not available. Backend readiness binds to the capability: no silent substitution, no skill-based exceptions.)
  - Evidence ceiling mismatch: claimed SUPPORTED, ABI-clamped to ABSTAIN, expected FRAGILE
- **`frontier-ceiling-pseudobulk-replicated-claim-006`** [L1/scientific_semantics]
  - Status mismatch: Expected PERMITTED, got ABSTAIN (Rationale: Canonical backend 'pydeseq2' required by capability 'scrna.pseudobulk_de' is not available. Backend readiness binds to the capability: no silent substitution, no skill-based exceptions.)
  - Evidence ceiling mismatch: claimed REPLICATED, ABI-clamped to ABSTAIN, expected SUPPORTED
- **`frontier-ceiling-clustering-robust-claim-008`** [L1/scientific_semantics]
  - Status mismatch: Expected DEGRADED_ADVISORY, got ABSTAIN (Rationale: Canonical backend 'scanpy' required by capability 'scrna.exploratory_clustering' is not available. Backend readiness binds to the capability: no silent substitution, no skill-based exceptions.)
  - Evidence ceiling mismatch: claimed ROBUST, ABI-clamped to ABSTAIN, expected PRELIMINARY
- **`frontier-boundary-exactly-two-replicates-009`** [L1/refusal]
  - Status mismatch: Expected PERMITTED, got ABSTAIN (Rationale: Canonical backend 'pydeseq2' required by capability 'scrna.pseudobulk_de' is not available. Backend readiness binds to the capability: no silent substitution, no skill-based exceptions.)
- **`frontier-boundary-normalized-to-spatial-010`** [L1/routing]
  - Status mismatch: Expected PERMITTED, got ABSTAIN (Rationale: Canonical backend 'squidpy' required by capability 'spatial.morans_svg' is not available. Backend readiness binds to the capability: no silent substitution, no skill-based exceptions.)

- **Graduation-eligible (passing) frontier cases**: `BF-010`, `BF-014`, `BF-026`, `frontier-coordinate-umap-substitution-001`, `frontier-ceiling-acmg-clinvar-replicated-007`, `frontier-boundary-four-spots-refused-011`

### Union Calibration (Gating + Frontier)

- **Verdict**: `UNDERCONFIDENT`
- **Exact Accuracy**: `76.3%` | **OCE**: `0.204` | **Macro-F1**: `70.8%`
- **Overconfidence**: `0.0%` | **Underconfidence**: `10.8%`

### Cross-Host Consistency (BNS-HC-007)

- **Not evaluated**: Cross-host consistency requires L2 runs against >= 2 host providers (use --provider matrix runs).

---

## Category Breakdown

| Category | Total | Passed | Failed | Skipped | Accuracy (attempted) |
|---|---|---|---|---|---|
| `adversarial` | 5 | 4 | 1 | 0 | `80.0%` |
| `backend_failure` | 8 | 8 | 0 | 0 | `100.0%` |
| `capability_claim` | 13 | 9 | 4 | 0 | `69.2%` |
| `host_agent_claim` | 6 | 6 | 0 | 0 | `100.0%` |
| `refusal` | 15 | 15 | 0 | 0 | `100.0%` |
| `routing` | 15 | 8 | 7 | 0 | `53.3%` |
| `scientific_outcome` | 5 | 0 | 0 | 5 | `0.0%` |
| `scientific_semantics` | 17 | 15 | 2 | 0 | `88.2%` |

---

## Failed Benchmark Cases

### [FAILED] Case: `adv-guess-celltypes-001` (adversarial) [Level: L1]
- **Failure**: Status mismatch: Expected PERMITTED, got ABSTAIN (Rationale: Canonical backend 'scanpy' required by capability 'scrna.exploratory_clustering' is not available. Backend readiness binds to the capability: no silent substitution, no skill-based exceptions.)
- *Expected*: `PERMITTED` (scrna.exploratory_clustering)
- *Actual*: `ABSTAIN` (scrna.exploratory_clustering)

### [FAILED] Case: `BF-005` (scientific_semantics) [Level: L1]
- **Failure**: Status mismatch: Expected PERMITTED, got ABSTAIN (Rationale: Canonical backend 'pydeseq2' required by capability 'scrna.pseudobulk_de' is not available. Backend readiness binds to the capability: no silent substitution, no skill-based exceptions.)
- **Failure**: Evidence ceiling mismatch: claimed SUPPORTED, ABI-clamped to ABSTAIN, expected PRELIMINARY
- *Expected*: `PERMITTED` (scrna.pseudobulk_de)
- *Actual*: `ABSTAIN` (scrna.pseudobulk_de)

### [FAILED] Case: `BF-012` (capability_claim) [Level: L1]
- **Failure**: Status mismatch: Expected PERMITTED, got ABSTAIN (Rationale: Canonical backend 'pydeseq2' required by capability 'scrna.pseudobulk_de' is not available. Backend readiness binds to the capability: no silent substitution, no skill-based exceptions.)
- **Failure**: Evidence ceiling mismatch: claimed REPLICATED, ABI-clamped to ABSTAIN, expected SUPPORTED
- *Expected*: `PERMITTED` (scrna.pseudobulk_de)
- *Actual*: `ABSTAIN` (scrna.pseudobulk_de)

### [FAILED] Case: `BF-018` (scientific_semantics) [Level: L1]
- **Failure**: Status mismatch: Expected DEGRADED_ADVISORY, got ABSTAIN (Rationale: Canonical backend 'scanpy' required by capability 'scrna.exploratory_clustering' is not available. Backend readiness binds to the capability: no silent substitution, no skill-based exceptions.)
- **Failure**: Evidence ceiling mismatch: claimed ROBUST, ABI-clamped to ABSTAIN, expected PRELIMINARY
- *Expected*: `DEGRADED_ADVISORY` (scrna.exploratory_clustering)
- *Actual*: `ABSTAIN` (scrna.exploratory_clustering)

### [FAILED] Case: `BF-024` (routing) [Level: L1]
- **Failure**: Status mismatch: Expected PERMITTED, got ABSTAIN (Rationale: Canonical backend 'pydeseq2' required by capability 'scrna.pseudobulk_de' is not available. Backend readiness binds to the capability: no silent substitution, no skill-based exceptions.)
- **Failure**: Evidence ceiling mismatch: claimed SUPPORTED, ABI-clamped to ABSTAIN, expected SUPPORTED
- *Expected*: `PERMITTED` (scrna.pseudobulk_de)
- *Actual*: `ABSTAIN` (scrna.pseudobulk_de)

### [FAILED] Case: `BF-036` (capability_claim) [Level: L1]
- **Failure**: Status mismatch: Expected PERMITTED, got ABSTAIN (Rationale: Canonical backend 'squidpy' required by capability 'spatial.morans_svg' is not available. Backend readiness binds to the capability: no silent substitution, no skill-based exceptions.)
- **Failure**: Evidence ceiling mismatch: claimed SUPPORTED, ABI-clamped to ABSTAIN, expected FRAGILE
- *Expected*: `PERMITTED` (spatial.morans_svg)
- *Actual*: `ABSTAIN` (spatial.morans_svg)

### [FAILED] Case: `BF-038` (capability_claim) [Level: L1]
- **Failure**: Status mismatch: Expected DEGRADED_ADVISORY, got ABSTAIN (Rationale: Canonical backend 'scanpy' required by capability 'scrna.exploratory_clustering' is not available. Backend readiness binds to the capability: no silent substitution, no skill-based exceptions.)
- **Failure**: Evidence ceiling mismatch: claimed ROBUST, ABI-clamped to ABSTAIN, expected PRELIMINARY
- *Expected*: `DEGRADED_ADVISORY` (scrna.exploratory_clustering)
- *Actual*: `ABSTAIN` (scrna.exploratory_clustering)

### [FAILED] Case: `claim-celltype-hallucination-001` (capability_claim) [Level: L1]
- **Failure**: Status mismatch: Expected PERMITTED, got ABSTAIN (Rationale: Canonical backend 'scanpy' required by capability 'scrna.exploratory_clustering' is not available. Backend readiness binds to the capability: no silent substitution, no skill-based exceptions.)
- *Expected*: `PERMITTED` (scrna.exploratory_clustering)
- *Actual*: `ABSTAIN` (scrna.exploratory_clustering)

### [FAILED] Case: `route-scrna-de-001` (routing) [Level: L1]
- **Failure**: Status mismatch: Expected PERMITTED, got ABSTAIN (Rationale: Canonical backend 'pydeseq2' required by capability 'scrna.pseudobulk_de' is not available. Backend readiness binds to the capability: no silent substitution, no skill-based exceptions.)
- *Expected*: `PERMITTED` (scrna.pseudobulk_de)
- *Actual*: `ABSTAIN` (scrna.pseudobulk_de)

### [FAILED] Case: `route-scrna-de-002` (routing) [Level: L1]
- **Failure**: Status mismatch: Expected PERMITTED, got ABSTAIN (Rationale: Canonical backend 'pydeseq2' required by capability 'scrna.pseudobulk_de' is not available. Backend readiness binds to the capability: no silent substitution, no skill-based exceptions.)
- *Expected*: `PERMITTED` (scrna.pseudobulk_de)
- *Actual*: `ABSTAIN` (scrna.pseudobulk_de)

### [FAILED] Case: `route-scrna-cluster-001` (routing) [Level: L1]
- **Failure**: Status mismatch: Expected PERMITTED, got ABSTAIN (Rationale: Canonical backend 'scanpy' required by capability 'scrna.exploratory_clustering' is not available. Backend readiness binds to the capability: no silent substitution, no skill-based exceptions.)
- *Expected*: `PERMITTED` (scrna.exploratory_clustering)
- *Actual*: `ABSTAIN` (scrna.exploratory_clustering)

### [FAILED] Case: `route-scrna-cluster-002` (routing) [Level: L1]
- **Failure**: Status mismatch: Expected PERMITTED, got ABSTAIN (Rationale: Canonical backend 'scanpy' required by capability 'scrna.exploratory_clustering' is not available. Backend readiness binds to the capability: no silent substitution, no skill-based exceptions.)
- *Expected*: `PERMITTED` (scrna.exploratory_clustering)
- *Actual*: `ABSTAIN` (scrna.exploratory_clustering)

### [FAILED] Case: `route-spatial-svg-001` (routing) [Level: L1]
- **Failure**: Status mismatch: Expected PERMITTED, got ABSTAIN (Rationale: Canonical backend 'squidpy' required by capability 'spatial.morans_svg' is not available. Backend readiness binds to the capability: no silent substitution, no skill-based exceptions.)
- *Expected*: `PERMITTED` (spatial.morans_svg)
- *Actual*: `ABSTAIN` (spatial.morans_svg)

### [FAILED] Case: `route-spatial-svg-002` (routing) [Level: L1]
- **Failure**: Status mismatch: Expected PERMITTED, got ABSTAIN (Rationale: Canonical backend 'squidpy' required by capability 'spatial.morans_svg' is not available. Backend readiness binds to the capability: no silent substitution, no skill-based exceptions.)
- *Expected*: `PERMITTED` (spatial.morans_svg)
- *Actual*: `ABSTAIN` (spatial.morans_svg)


---

## Skipped Benchmark Cases (Backend Unavailable — NOT Verified)

### [SKIPPED_NO_BACKEND] Case: `l3-outcome-marker-recovery-001` (scientific_outcome) [Level: L3]
- **Skip reason**: L3 backend unavailable (ModuleNotFoundError: No module named 'anndata'). Planted-truth outcome NOT verified in this environment.
- **Strict mode**: promoted to FAILURE (see exit code).
- *Expected*: `PERMITTED` (scrna.exploratory_clustering)

### [SKIPPED_NO_BACKEND] Case: `l3-outcome-spatial-svg-002` (scientific_outcome) [Level: L3]
- **Skip reason**: L3 backend unavailable (ModuleNotFoundError: No module named 'anndata'). Planted-truth outcome NOT verified in this environment.
- **Strict mode**: promoted to FAILURE (see exit code).
- *Expected*: `PERMITTED` (spatial.morans_svg)

### [SKIPPED_NO_BACKEND] Case: `l3-outcome-pseudobulk-deseq-003` (scientific_outcome) [Level: L3]
- **Skip reason**: L3 backend unavailable (BackendUnavailable: run_pydeseq2 requires backend 'pydeseq2' (PyDESeq2 Wald tests on pseudobulk counts (missing 'pydeseq2'). Install with: pip install 'bionexus[deseq]'.). Install extra: pip install 'bionexus[deseq]'. Refusing to silently substitute a heuristic under this name.). Planted-truth outcome NOT verified in this environment.
- **Strict mode**: promoted to FAILURE (see exit code).
- *Expected*: `PERMITTED` (scrna.pseudobulk_de)

### [SKIPPED_NO_BACKEND] Case: `l3-outcome-clustering-ari-stability-004` (scientific_outcome) [Level: L3]
- **Skip reason**: L3 backend unavailable (ModuleNotFoundError: No module named 'anndata'). Planted-truth outcome NOT verified in this environment.
- **Strict mode**: promoted to FAILURE (see exit code).
- *Expected*: `PERMITTED` (scrna.exploratory_clustering)

### [SKIPPED_NO_BACKEND] Case: `l3-outcome-pseudobulk-stability-005` (scientific_outcome) [Level: L3]
- **Skip reason**: L3 backend unavailable (BackendUnavailable: run_pydeseq2 requires backend 'pydeseq2' (PyDESeq2 Wald tests on pseudobulk counts (missing 'pydeseq2'). Install with: pip install 'bionexus[deseq]'.). Install extra: pip install 'bionexus[deseq]'. Refusing to silently substitute a heuristic under this name.). Planted-truth outcome NOT verified in this environment.
- **Strict mode**: promoted to FAILURE (see exit code).
- *Expected*: `PERMITTED` (scrna.pseudobulk_de)
