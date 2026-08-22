# Scientific Evidence Debt (证据债务) — Developer & PI Guide

> **"Scientific reliability is not a vanity score. It is an auditable ledger of deferred verifications across the research DAG."**

---

## 1. Why Evidence Debt?

In software engineering, teams manage **Technical Debt** rather than claiming an arbitrary "Code Quality: 83%".

In scientific research and computational biology, projects accumulate **Evidence Debt**:
- A single-cell pipeline uses **heuristic marker gating** instead of reference atlas concordance.
- A spatial transcriptomics run transfers a **PBMC atlas onto lung tumor biopsies** (domain mismatch).
- An observational RNA-seq study asserts **"drug X causes tumor remission"** without causal DAG backdoor closure.
- A differential expression study relies on a **single cohort ($N=1$ donor)** without orthogonal validation.

A vanity score hides these liabilities. **BioNexus Evidence Debt** exposes them as concrete, typed items with exact dependency chains and an **Optimal Repayment Schedule**.

---

## 2. The Keystone Effect: 70x Payoff Multipliers

Consider a research project with 20 core claims:
```
Claim 17 (Target gene CD274 upregulated in Exhausted CD8+ T cells)
   ↓
Claim 12, Claim 7, Claim 4, Claim 1, Claim 19, Claim 20 (6 other claims)
   ↓
TRANSFORM-ANNOTATION-X (Heuristic gating on tumor infiltrate)
   ↓
Atlas Reference Domain Mismatch (PBMC reference)
```

Because 7 claims depend on `TRANSFORM-ANNOTATION-X`, fixing this **single upstream node** amortizes the Evidence Debt for all 7 downstream claims at once:
- **Debt Leverage Multiplier**: $7 \text{ claims} \times 10.0 \text{ (CRITICAL severity)} = \mathbf{70.0\times}$.
- Re-annotating or validating this single step upgrades the project maturity floor from `FRAGILE` to `SUPPORTED`.

---

## 3. Quick Start & CLI Usage

### Audit Project Evidence Debt
```bash
# Audit current repository or ledger.json
bionexus debt audit .

# Output as Markdown report (for lab meetings / grant supplements)
bionexus debt audit . --markdown > EVIDENCE_DEBT_REPORT.md

# Output as machine-readable JSON
bionexus debt audit . --json > evidence-debt.json
```

### Compute Optimal Repayment Schedule
```bash
bionexus debt payoff .
```

### Visual Mermaid Dependency Graph
```bash
bionexus debt graph .
```

### Run on Sample 20-Claim Project
```bash
bionexus debt sample
```

---

## 4. Terminal Dashboard Output

```text
================================================================================
                            BioNexus Scientific Evidence Debt Report            
================================================================================
Total Claims Analyzed:     20
Total Evidence Debt Items: 12
Project Maturity Floor:    [FRAGILE]
Potential Project Ceiling: [ROBUST] (Upon Debt Amortization)
--------------------------------------------------------------------------------
EVIDENCE DEBT BY CATEGORY:
  MISSING_INDEPENDENT_REPLICATION        8  ################
  HEURISTIC_DEPENDENCY                   1  ##
  DOMAIN_MISMATCH                        1  ##
  PARAMETER_SENSITIVITY                  1  ##
  CAUSAL_IDENTIFICATION_GAP              1  ##
--------------------------------------------------------------------------------
EPISTEMIC KEYSTONES (High-Leverage Verification Bottlenecks):
  [*] Node: TRANSFORM-SPATIAL-MAPPING (Spatial neighbor adjacency mapping) -> Affects 8 claims
  [*] Node: TRANSFORM-ANNOTATION-X (Heuristic marker gating on tumor infiltrate) -> Affects 7 claims
--------------------------------------------------------------------------------
OPTIMAL EVIDENCE REPAYMENT SCHEDULE (Ranked by Scientific Payoff):
RANK  DEBT ID    SEVERITY   CLAIMS   PAYOFF   ACTION
--------------------------------------------------------------------------------
#1    DEBT-001   CRITICAL    7 claims   70.0x  Validate TRANSFORM-ANNOTATION-X against Atlas
#2    DEBT-002   CRITICAL    7 claims   70.0x  Execute Domain-Adapted Transfer on Annotation
#3    DEBT-003   HIGH        8 claims   40.0x  Run Multi-Resolution Stability Audit on Spatial
#4    DEBT-011   CRITICAL    1 claims   10.0x  Formulate Causal DAG & Sensitivity for Mechanism
================================================================================
```

---

## 5. Python API Integration

```python
from bionexus.debt import EvidenceDebtEngine, create_sample_debt_ledger
from bionexus.ledger import ClaimLedger

# Load project claim-evidence ledger
ledger = ClaimLedger.load("ledger.json")

# Run full Evidence Debt audit
report = EvidenceDebtEngine.audit_ledger(ledger)

print(f"Total Debt Items: {report.total_debt_items}")
print(f"Project Maturity Floor: {report.project_maturity_floor}")

# Inspect optimal repayment priorities
for priority in report.optimal_repayment_schedule[:3]:
    debt = priority.debt_item
    print(f"Priority #{priority.rank}: {debt.title} (Payoff: {priority.payoff_multiplier}x)")
    print(f"  Remediation: {debt.remediation.action_title}")
    print(f"  Unblocks Claims: {', '.join(priority.claims_unblocked)}")
```
