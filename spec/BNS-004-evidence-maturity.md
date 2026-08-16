# BNS-004: Evidence Maturity (EvidenceCard 2.0)

**Status**: Active | **Version**: 1.0 | **Supersedes**: none
**Applies to**: `src/bionexus/contracts.py` (EvidenceCard, DimensionGrade, ConclusionMaturity), `evals/metrics.py`
**Normative language**: RFC 2119 / RFC 8174. Requirement IDs are stable and never reused.

## 1. Purpose

EvidenceCard 2.0 is the epistemic reporting contract of BioNexus. Its job is to make
**calibrated uncertainty** machine-readable: what ran, what was verified, and how much
warrant the evidence actually carries. The companion obligation — that reported
maturity must be *calibrated against ground truth*, not merely self-consistent — is
defined here and measured by the epistemic calibration benchmark.

## 2. Three-layer structure

- **BNS-EM-001** Every analytical result MUST attach an `EvidenceCard` with three
  layers, in order of authority:
  - **Layer 1 — Execution State** (BNS-003): what physically happened.
  - **Layer 2 — Evidence Dimensions**: graded quality of inputs, assumptions,
    statistics, parameter robustness, cross-method concordance, external validation.
  - **Layer 3 — Conclusion Maturity**: the single ordinal warrant label synthesized
    from Layers 1–2.
- **BNS-EM-002** Layer 2 dimensions MUST use the `DimensionGrade` vocabulary:
  `A` (strong), `B` (moderate), `C` (marginal/violated), `UNTESTED`, `UNASSESSED`,
  `NOT_APPLICABLE`, `INSUFFICIENT` (power-inadequate), `CONFLICTED`.
- **BNS-EM-003** `UNTESTED` MUST NOT be conflated with `GRADE_C`: untested means the
  dimension was not evaluated; Grade C means it was evaluated and found weak.

## 3. Conclusion maturity ladder

- **BNS-EM-004** Layer 3 MUST be drawn from the ordinal `ConclusionMaturity` ladder:

  | Rank | Maturity | Meaning |
  |---|---|---|
  | 0 | `ABSTAIN` | Refused, failed, or claim beyond warrant |
  | 0 | `UNASSESSED` | Preflight passed, nothing executed yet |
  | 1 | `PRELIMINARY` | Plausible single run, standard parameters |
  | 2 | `FRAGILE` | Violated assumption / degraded / parameter-sensitive |
  | 2 | `CONFLICTED` | Methods disagree |
  | 3 | `SUPPORTED` | Inputs A/B + assumptions A/B + statistics A on current data |
  | 4 | `ROBUST` | SUPPORTED + parameter stability verified (Grade A) |
  | 5 | `REPLICATED` | ROBUST + independent external validation |

- **BNS-EM-005** Synthesis MUST be a pure function of Layers 1–2
  (`synthesize_conclusion_maturity`): refusal/failure forces `ABSTAIN`;
  `CONFLICTED` concordance forces `CONFLICTED`; any Grade C on input integrity,
  assumptions, parameter robustness — or degraded execution, or insufficient
  statistical power — caps the result at `FRAGILE`. Higher rungs REQUIRE Grade A
  statistics plus the rung-specific evidence; they MUST NOT be asserted otherwise.
- **BNS-EM-006** A capability MAY declare an **evidence ceiling** (BNS-CC-013) below
  `REPLICATED`; the synthesized maturity MUST then be clamped to the ceiling whenever
  the ceiling's enabling condition (e.g. external validation) is absent.

## 4. Calibration obligations

- **BNS-EM-007** Reported maturity is a *prediction* of epistemic warrant. It MUST be
  evaluated against expected warrant on benchmark cases, not merely checked for
  internal consistency. The platform MUST report: exact accuracy, overconfidence rate
  (asserted rank > warranted rank), underconfidence rate, ordinal calibration error
  (OCE), Brier calibration score, and macro-F1 across maturity classes
  (`evals/metrics.compute_epistemic_calibration`).
- **BNS-EM-008** Overconfidence is strictly worse than underconfidence: the evidence
  calibration score MUST penalize overconfidence at least twice as heavily per unit
  as dispersion (`1 - OCE/5 - 2*overconfidence_rate`).
- **BNS-EM-009** A maturity label for which no benchmark case exists MUST NOT be
  claimed as calibrated. Calibration claims MUST state the number of evaluated cases
  and the confusion matrix; macro-F1 over a single populated class is NOT a
  calibration result.
- **BNS-EM-010** Benchmark suites SHOULD include adjacent-rank discrimination cases
  (PRELIMINARY vs FRAGILE, SUPPORTED vs ROBUST). A suite that only contains
  far-apart classes MUST report the limitation alongside its scores.

## 5. Reporting

- **BNS-EM-011** An EvidenceCard MUST serialize losslessly (`to_dict`) and SHOULD
  render human-readable (`to_markdown`) with all six dimensions and the synthesized
  maturity visible.
- **BNS-EM-012** Cards MUST be attached at refusal time too: a refusal carries a card
  with untested dimensions, the refusal reason, and maturity `ABSTAIN`
  (`contracts.refuse`).

## 6. Conformance verification

| Requirement | Verified by |
|---|---|
| BNS-EM-001..003 | `tests/unit/test_evidence_card.py` |
| BNS-EM-004..006 | `contracts.synthesize_conclusion_maturity`; `tests/unit/test_abi.py` (ceiling clamp) |
| BNS-EM-007..009 | `evals/metrics.py`; `tests/unit/test_epistemic_calibration.py`; benchmark report calibration section |
| BNS-EM-010 | frontier calibration track (`evals/datasets/calibration_edge.yaml`) |
| BNS-EM-011..012 | `contracts.attach_meta`, `contracts.refuse`; `tests/unit/test_artifacts.py` |
