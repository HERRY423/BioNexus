# BNS-021: Scientific Evidence Debt & Epistemic DAG Amortization

**Status**: Active | **Version**: 1.0 | **Supersedes**: none  
**Applies to**: `src/bionexus/debt.py`, `bionexus debt`, `src/bionexus/ledger.py`, all research projects and scientific agents.

---

## 1. Motivation: Rejecting Vanity "Reliability Scores"

In software engineering, **Technical Debt** does not assign a fake aggregate metric like `"Code Quality = 83%"`. Rather, it identifies specific deferred refactorings, architectural shortcuts, and unmaintained dependencies that incur operational risk.

Similarly, in scientific discovery and computational biology, complex research projects generate dozens of interdependent claims ($C_1, C_2, \dots, C_n$). A naive reliability score (e.g. `83%`) is scientifically meaningless and dangerous because a single foundational flaw (such as an atlas domain mismatch in cell-type annotation) invalidates an entire downstream subgraph of claims.

**BioNexus Evidence Debt (BNS-021)** establishes the formal accounting framework for scientific shortcuts and deferred verifications:
1. Replaces flat percentages with structured, typed **Evidence Debt Items**.
2. Traces debt propagation across the scientific **Claim Dependency DAG**.
3. Identifies **Epistemic Keystones** (critical upstream nodes).
4. Computes the **Optimal Scientific Repayment Schedule** ranked by **Payoff Leverage Multiplier**.

---

## 2. Evidence Debt Taxonomy (`DebtKind`)

| Debt Kind | Description | Primary Epistemic Danger | Typical Remediation Target |
| :--- | :--- | :--- | :--- |
| `UNRESOLVED_ALTERNATIVE_EXPLANATION` | Confounder hypotheses left untested (donor batch, cell cycle, library depth) | False positive associations attributed to biological condition | Confounder regression & alternative battery audit |
| `HEURISTIC_DEPENDENCY` | Manual or uncalibrated marker gating without reference concordance | Unreliable cell subsetting & cluster misidentification | Automated reference mapping (CellTypist/Azimuth) |
| `MISSING_INDEPENDENT_REPLICATION` | Claim derived from single discovery cohort ($N=1$ donor or single dataset) | Overfitting to cohort-specific technical artifacts | Cross-cohort validation on public GEO/SRA datasets |
| `PARAMETER_SENSITIVITY` | Cluster partitions or marker sets unstable under hyperparameter sweeps | Brittle findings tied to arbitrary parameter choices | Multi-resolution stability audit (ARI > 0.80) |
| `UNREVIEWED_CALIBRATION_THRESHOLD` | Arbitrary p-value or effect-size cutoffs without empirical calibration | Inflated false discovery rate | Empirical Bayes FDR calibration |
| `DOMAIN_MISMATCH` | Reference atlas transferred across disparate tissues or disease states | False cell identity mapping due to biological shift | Domain-adapted latent projection (scANVI/scVI) |
| `UNACCOUNTED_CONFOUNDER` | Known technical/clinical covariates unmodeled in design matrix | Confounded differential signals | Multivariable linear / generalized linear modeling |
| `CAUSAL_IDENTIFICATION_GAP` | Asserting causal mechanism from observational correlation | Unwarranted causal claims without perturbation | Structural Causal Model & DAG backdoor closure |
| `UNVALIDATED_BATCH_CORRECTION` | Batch correction applied without verifying bio-conservation metrics | Over-correction removing true biological variance | scIB benchmark audit (ASW_label > 0.65) |
| `AMBIENT_SIGNAL_CONTAMINATION` | Droplet cell-free mRNA soup uncorrected in count matrix | False marker expression across disparate cell types | CellBender / DecontX ambient background subtraction |

---

## 3. Epistemic DAG Propagation & Keystone Identification

A scientific claim graph is a Directed Acyclic Graph (DAG) $G = (V, E)$ where vertices $V = V_{\text{evid}} \cup V_{\text{claim}}$ and directed edges $E = \{ (u, v) \mid v \text{ depends on } u \}$.

### 3.1 Maturity Ceiling Propagation
A claim $C_i$ inherits an evidence maturity ceiling clamped by the minimum maturity of all upstream supporting nodes in its ancestor set $\text{Anc}(C_i)$:
$$\text{MaturityCeiling}(C_i) = \min_{u \in \text{Anc}(C_i)} \text{Maturity}(u)$$

### 3.2 Epistemic Keystones
An **Epistemic Keystone** is an upstream evidence or transformation node $K \in V_{\text{evid}}$ that carries active evidence debt and whose descendant set contains multiple downstream claims:
$$\text{Impact}(K) = |\{ C \in V_{\text{claim}} \mid K \in \text{Anc}(C) \}|$$

---

## 4. Payoff Leverage & Optimal Repayment Optimization

Every Evidence Debt item $D_j$ has an associated severity weight $w(D_j)$:
- `CRITICAL`: $w = 10.0$ (forces `ABSTAIN` / `FRAGILE` on downstream claims)
- `HIGH`: $w = 5.0$ (caps claims at `SUPPORTED` / `PRELIMINARY`)
- `MEDIUM`: $w = 2.0$ (prevents graduation to `ROBUST`)
- `LOW`: $w = 1.0$ (advisory)

### Payoff Leverage Multiplier ($L$)
The scientific payoff multiplier represents the total epistemic value unlocked by remediating $D_j$:
$$L(D_j) = |\text{DescendantClaims}(D_j)| \times w(D_j)$$

### Optimal Repayment Schedule
The BioNexus Evidence Debt Engine sorts all detected debt items in descending order of $L(D_j)$:
$$\text{Schedule} = \text{SortByDescending}\left( \{ D_j \}, \text{key}=L(D_j) \right)$$

Remediating the top-ranked item amortizes debt across the widest claim subgraph with the highest scientific return on experimental effort.

---

## 5. Standard CLI & JSON Schema

### CLI Usage
```bash
# Audit project evidence debt
bionexus debt audit [target]

# Compute optimal repayment schedule
bionexus debt payoff [target]

# Generate Mermaid DAG visualization
bionexus debt graph [target]

# Audit sample 20-claim project
bionexus debt sample
```
