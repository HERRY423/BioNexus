# BNS-017: Scientific Claim Semantics & Deterministic Warrant IR

**Status**: Active | **Version**: 1.0 | **Supersedes**: none
**Applies to**: `src/bionexus/claim_semantics.py`, `src/bionexus/claim_checker.py`, `src/bionexus/ledger.py`
**Normative language**: RFC 2119 / RFC 8174. Requirement IDs are stable and never reused.

## 1. Purpose & Epistemic Core

Scientific claims in biology (e.g. transcriptomics, spatial biology, proteomics, oncology) are frequently phrased in natural language with varying syntax, hedging, and modal qualifiers.
Traditional validation architectures suffer from a critical dilemma:
1. **Heuristic/Regex Pattern Matching** (`HEURISTIC_DETECTOR`): High false-negative and false-positive rates; easily bypassed by paraphrasing.
2. **Unconstrained LLM Judges**: Non-deterministic, irreproducible, hallucination-prone, and vulnerable to prompt injection—violating the fail-closed reliability requirements of BioNexus.

**BNS-017** specifies the **Scientific Claim Intermediate Representation (IR)** and the **Deterministic Warrant Engine**:
- Natural-language scientific statements are parsed into a strictly typed, canonical semantic schema (`ScientificClaimIR`).
- A deterministic, rule-based epistemic warrant engine evaluates the claim IR against empirical evidence facts in the Claim–Evidence Ledger (or `EvidenceProfile`), evaluating exact multi-tier warrant verdicts with zero stochasticity.

---

## 2. Scientific Claim IR (Normative Schema)

- **BNS-CS-001** Every scientific claim MUST decompose into the following typed semantic fields:
  - `claim_id` (str): Unique, stable identifier.
  - `source_text` (str): Raw input sentence.
  - `subject_entity` (ScientificEntity): Primary biological agent/predictor/biomarker (name, entity type, features).
  - `object_entity` (Optional[ScientificEntity]): Target phenotype, downstream pathway, cell type, or clinical outcome.
  - `relationship` (ClaimRelationshipType): Closed vocabulary: `CORRELATION`, `DIFFERENTIAL_ABUNDANCE`, `CELL_CELL_INTERACTION`, `REGULATORY_EFFECT`, `PHENOTYPE_DRIVER`, `THERAPEUTIC_RESPONSE`, `IDENTITY_ASSERTION`, `DIAGNOSTIC_ASSERTION`, `MODEL_FIDELITY`.
  - `direction` (Directionality): `DIRECTED_FORWARD` ($A \to B$), `DIRECTED_REVERSE` ($B \to A$), `BIDIRECTIONAL` ($A \leftrightarrow B$), `UNDIRECTED`.
  - `comparison` (Optional[str]): Contrast groups (e.g. treated vs vehicle, responder vs non-responder).
  - `population_scope` (str): Target species/disease/tissue population (e.g. "NSCLC", "human PBMC").
  - `generalization_scope` (GeneralizationScope): `SAMPLE_SPECIFIC`, `STRATUM_SPECIFIC`, `COHORT_SPECIFIC`, `POPULATION_GENERAL`.
  - `association_type` (AssociationType): `OBSERVATIONAL_CORRELATION`, `SPATIAL_COLOCALIZATION`, `LIGAND_RECEPTOR_INFERENCE`, `DIFFERENTIAL_EXPRESSION`, `TEMPORAL_COVARIANCE`, `SURVIVAL_HAZARD`.
  - `causal_strength` (CausalStrength): `NONE`, `ASSOCIATIONAL`, `HYPOTHESIZED_CAUSAL`, `COUNTERFACTUAL_CAUSAL`, `MECHANISTIC_DRIVER`.
  - `mechanism_depth` (MechanismDepth): `BLACK_BOX`, `PATHWAY_ENRICHMENT`, `SIGNALING_CASCADE`, `MOLECULAR_BINDING`, `PERTURBATIVE_FUNCTION`.
  - `clinical_actionability` (ClinicalActionability): `NONE`, `EXPLORATORY_BIOMARKER`, `PRESCRIPTIVE_TREATMENT`, `DIAGNOSTIC_ASSERTION`.
  - `claim_class` (ClaimClass): Epistemic tier mapping (`DESCRIPTIVE`, `ASSOCIATION`, `POPULATION_EFFECT`, `CELL_IDENTITY`, `SPATIAL_DEPENDENCY`, `MECHANISTIC`, `CAUSAL`, `PREDICTIVE`, `CLINICAL_ACTIONABILITY`).
  - `qualifiers` (List[str]): Hedges and epistemic qualifiers (`putative`, `candidate`, `exploratory`, `hypothesized`, `suggests`).
  - `negated` (bool): True if statement asserts lack of causation or inability to prove.

---

## 3. Deterministic Warrant Engine Rules

- **BNS-CS-002 (Causal Identifiability Invariant)**:
  A claim asserting `causal_strength == COUNTERFACTUAL_CAUSAL` or `claim_class == CAUSAL` MUST NOT resolve to `WARRANTED` unless supported by:
  1. `perturbation == True` (experimental knockout, knockdown, CRISPR, or drug intervention), OR
  2. `causal_identification_status == "BACKDOOR_SATISFIED"` (formal SCM d-separation with zero open backdoor paths and no unobserved confounding).
  Spatial colocalization and ligand-receptor co-expression ALONE MUST be rejected as causal evidence.

- **BNS-CS-003 (Mechanistic Cascade Invariant)**:
  A claim asserting `mechanism_depth >= SIGNALING_CASCADE` or `claim_class == MECHANISTIC` (e.g. "CD8 T cells drive macrophage polarization") MUST NOT resolve to `WARRANTED` without functional perturbation or verified temporal kinetics. Spatial colocalization + ligand-receptor inference warrants only spatial association (`ClaimClass.SPATIAL_DEPENDENCY`).

- **BNS-CS-004 (Population Generalization Invariant)**:
  A claim asserting `generalization_scope == POPULATION_GENERAL` (e.g. "in NSCLC", "in humans") MUST NOT resolve to `WARRANTED` without $n \ge 3$ biological replicates and sample-level pseudobulk aggregation. Observational single-cell $p$-values without replicate aggregation confound sample noise with population effects (Love et al. 2014, Soneson & Robinson 2018).

- **BNS-CS-005 (Cell-Type Identity Invariant)**:
  A claim asserting `relationship == IDENTITY_ASSERTION` or `claim_class == CELL_IDENTITY` MUST remain numeric or carry explicit qualifiers (`candidate`, `putative`, `exploratory`) unless verified against a reference atlas or sorted ground-truth marker panel (BNS-II-008).

- **BNS-CS-006 (Clinical & Regulatory Firewall)**:
  Claims asserting `clinical_actionability in (PRESCRIPTIVE_TREATMENT, DIAGNOSTIC_ASSERTION)` MUST NOT be emitted on research pipelines without explicit CLIA/CAP/FDA certification and mandatory RUO disclaimers.

- **BNS-CS-007 (Negation & Epistemic Honesty)**:
  Claims explicitly declaring negative findings or acknowledging inferential limits (e.g. "Marker p-values cannot prove causal treatment effects") MUST resolve to `WARRANTED` without penalty.

---

## 4. Example Evaluation Scenario

**Claim**: *"CXCL13+ CD8 T cells drive macrophage polarization in NSCLC."*

**Parsed IR**:
```json
{
  "subject_entity": {"name": "CXCL13+ CD8 T cells", "features": ["CXCL13+", "CD8+"]},
  "object_entity": {"name": "macrophage polarization", "features": []},
  "relationship": "cell_cell_interaction",
  "direction": "directed_forward",
  "population_scope": "NSCLC",
  "generalization_scope": "population_general",
  "causal_strength": "counterfactual_causal",
  "mechanism_depth": "signaling_cascade",
  "claim_class": "mechanistic"
}
```

**Evidence Profile**:
- `spatial_colocalization`: `true`
- `ligand_receptor_inference`: `true`
- `perturbation`: `false`
- `temporal_evidence`: `false`
- `biological_replicates_count`: 1

**Warrant Engine Verdict**:
- `association_claim`: **WARRANTED**
- `mechanistic_claim`: **NOT_WARRANTED** (Gap: `missing_functional_perturbation`)
- `causal_claim`: **NOT_WARRANTED** (Gap: `missing_causal_identification`)
- `population_claim`: **NOT_WARRANTED** (Gap: `missing_biological_replicates`)
- **Max Warranted Class**: `SPATIAL_DEPENDENCY` / `ASSOCIATION`
- **Evidence Ceiling**: `SUPPORTED`

---

## 5. Conformance Verification

| Requirement | Verified by |
|---|---|
| BNS-CS-001..007 | `tests/unit/test_claim_semantics.py` |
| BNS-CS-002 (Causal Identifiability) | `test_causal_warrant_rules` |
| BNS-CS-003 (Mechanistic Cascade) | `test_mechanistic_warrant_with_spatial_lr_only` |
| BNS-CS-004 (Population Replicates) | `test_population_generalization_warrant` |
| BNS-CS-005 (Cell Identity) | `test_cell_identity_qualifier_warrant` |
| BNS-CS-007 (Negation Honesty) | `test_negated_claim_honesty` |
