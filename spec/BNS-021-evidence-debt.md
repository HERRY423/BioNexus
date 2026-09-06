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
| `UNAUTHENTICATED_PRODUCER` | External tool/connector output lacks verified cryptographic execution receipt | Risk of untrusted transmission, MITM injection, or fake tool output | Cryptographic tool execution receipt verification |
| `UNKNOWN_DATABASE_RELEASE` | External database query executed without declaring frozen release/version tag | Silent entity drift and non-reproducible knowledge retrieval | Lock database release version (e.g. Ensembl v110, ChEMBL 33) |
| `MODEL_VERSION_MISSING` | Predictive AI model inference executed without model weights hash or checkpoint tag | Undocumented inference configuration and brittle non-deterministic outputs | Explicit model checkpoint hash and version pinning |
| `SOURCE_LINEAGE_UNRESOLVED` | Connector result delivered without primary literature DOIs, PMIDs, or accessions | Information black box preventing downstream dependency analysis | Primary source extraction and lineage binding |
| `NO_INDEPENDENT_VALIDATION` | Findings derived from a single commercial lab or single assay platform | Technical artifacts specific to platform or reagent batch | Independent multi-laboratory replication across distinct sites |
| `UNCONTROLLED_CONFOUNDING` | Observational dataset association lacks adjustment for technical/clinical covariates | Confounded spurious correlations treated as true disease signatures | Covariate matching or multivariable regression |
| `DERIVED_EVIDENCE_DOUBLE_COUNT` | Multiple connectors collapse to identical underlying primary publications | Artificially inflated consensus and epistemic echo chamber | Lineage de-duplication; conduct orthogonal in-vivo validation |
| `CLAIM_EXCEEDS_CONNECTOR_PROFILE` | Claim asserts in-vivo / clinical efficacy, but evidence is restricted to in-vitro binding | Inferential leap from biochemical binding to organismal efficacy | In-vivo animal model or patient cohort validation |

---

## 3. Epistemic DAG Propagation & Keystone Identification

A scientific claim graph is a Directed Acyclic Graph (DAG) $G = (V, E)$ where vertices $V = V_{\text{evid}} \cup V_{\text{claim}}$ and directed edges $E = \{ (u, v) \mid v \text{ depends on } u \}$.

### 3.1 Maturity Ceiling Propagation
A claim $C_i$ inherits an evidence maturity ceiling clamped by the minimum maturity of all upstream supporting nodes in its ancestor set $\text{Anc}(C_i)$:
$$\text{MaturityCeiling}(C_i) = \min_{u \in \text{Anc}(C_i)} \text{Maturity}(u)$$

### 3.2 Epistemic Keystones
An **Epistemic Keystone** is an upstream evidence or transformation node $K \in V_{\text{evid}}$ that carries active evidence debt and whose descendant set contains multiple downstream claims:
$$\text{Impact}(K) = |\{ C \in V_{\text{claim}} \mid K \in \text{Anc}(C) \}|$$

### 3.3 Atomic Lineage De-duplication & Citation Collapsing
When an agent queries multiple external connectors (e.g. ChEMBL, OpenTargets, Enrichr, Consensus) in support of claim $C$:
1. Let $\mathcal{A}(e)$ denote the set of atomic primary citations (PMIDs, DOIs, raw dataset accessions) underlying evidence $e$.
2. The effective independent evidence degree is $\text{EID}(C) = |\bigcup_{e \in \text{Supp}(C)} \mathcal{A}(e)|$.
3. When $|\text{Supp}(C)| \ge 2$ but $\text{EID}(C) \le 2$, the apparent multi-source consensus collapses into an epistemic echo chamber. BioNexus detects `DERIVED_EVIDENCE_DOUBLE_COUNT` and clamps claim maturity.

### 3.4 Connector Echo Chambers vs. In-Vivo Validation
In multi-connector claim synthesis, the keystone calculation reveals that **querying additional connectors yields zero marginal epistemic gain**, and the optimal repayment action is independent in-vivo / orthogonal validation.

---

## 4. Heuristic Triage Priority & Remediation Schedule

Every Evidence Debt item $D_j$ has an associated severity weight $w(D_j)$:
- `CRITICAL`: $w = 10.0$ (forces `ABSTAIN` / `FRAGILE` on downstream claims)
- `HIGH`: $w = 5.0$ (caps claims at `SUPPORTED` / `PRELIMINARY`)
- `MEDIUM`: $w = 2.0$ (prevents graduation to `ROBUST`)
- `LOW`: $w = 1.0$ (advisory)

### Heuristic Priority Score ($S$)
The structural remediation priority score represents the product of downstream claim impact count and severity weight:
$$S(D_j) = |\text{DescendantClaims}(D_j)| \times w(D_j)$$

> **Epistemic Scope & Boundary**:
> $S(D_j)$ is an analytical triage heuristic to guide the order of investigation and verification across the dependency DAG. It is **NOT** an empirical measurement of risk reduction, nor does it model laboratory experimental cost, technical feasibility, or probability of success. Furthermore, remediating an upstream keystone node does not automatically upgrade downstream claim maturity ceilings; downstream claims remain bound to their observed empirical evidence.

### Remediation Priority Schedule
The BioNexus Evidence Debt Engine sorts all detected debt items in descending order of $S(D_j)$:
$$\text{Schedule} = \text{SortByDescending}\left( \{ D_j \}, \text{key}=S(D_j) \right)$$

Remediating the top-ranked item addresses debt across the widest claim subgraph, clarifying where empirical re-testing yields the broadest topological reach.

---

## 5. Standard CLI & JSON Schema

### CLI Usage
```bash
# Audit project evidence debt
bionexus debt audit [target]

# Compute heuristic remediation priority schedule
bionexus debt payoff [target]

# Generate Mermaid DAG visualization
bionexus debt graph [target]

# Audit sample 20-claim project
bionexus debt sample
```
