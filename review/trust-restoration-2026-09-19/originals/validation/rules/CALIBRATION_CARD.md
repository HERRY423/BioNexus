# BioNexus Scientific Rule Empirical Calibration Card

**Benchmark Version**: `1.0.0`  
**Holdout SHA-256**: `8050d7e734899e82385e75f823b73e337c23899f1319571e65316acab61e7835`  
**Calibration Timestamp**: `2026-09-18T03:46:32.616327+00:00`  
**Evaluated Cohort Cases**: `12`  

## 1. Overall System Empirical Metrics

| Metric | Value | Theoretical Standard | Status |
| :--- | :--- | :--- | :--- |
| **False Positive Rate (FPR)** | 0.00% | <= 5.0% | PASS |
| **False Negative Rate (FNR)** | 0.00% | <= 5.0% | PASS |
| **Expected Calibration Error (ECE)** | 0.0400 | <= 0.08 | PASS |
| **Human Expert Concordance** | 100.00% | >= 90.0% | PASS |
| **Cohen's Kappa (κ)** | 1.0000 | >= 0.80 (Almost Perfect) | PASS |

## 2. Per-Rule Research Object Calibration Breakdown

| Rule ID | Name | Sample N | TP | FP | TN | FN | FPR | FNR | ECE | Cohen's κ |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `BFA-001` | Cell-Level Pseudoreplication in Cross-Co | 3 | 1 | 0 | 2 | 0 | 0.0% | 0.0% | 0.040 | 1.000 |
| `BFA-001b` | Small Biological Replicate Cohort (N=2)  | 2 | 1 | 0 | 1 | 0 | 0.0% | 0.0% | 0.085 | 1.000 |
| `BFA-002` | Raw Integer Count Matrix Integrity for N | 1 | 1 | 0 | 0 | 0 | 0.0% | 0.0% | 0.010 | 1.000 |
| `BFA-003` | Multiple Testing Correction & Selective  | 2 | 1 | 0 | 1 | 0 | 0.0% | 0.0% | 0.035 | 1.000 |
| `BFA-004` | Complete Technical Batch vs Biological C | 1 | 1 | 0 | 0 | 0 | 0.0% | 0.0% | 0.010 | 1.000 |
| `BFA-007` | Single-Donor Cell Contribution Dominance | 1 | 1 | 0 | 0 | 0 | 0.0% | 0.0% | 0.050 | 1.000 |
| `BFA-008` | Unwarranted Causal and Diagnostic Biomar | 1 | 1 | 0 | 0 | 0 | 0.0% | 0.0% | 0.040 | 1.000 |
| `BFA-014` | Execution Binding Hallucination and Past | 1 | 1 | 0 | 0 | 0 | 0.0% | 0.0% | 0.010 | 1.000 |

## 3. Audited Case Adjudication Trace

| Case ID | Rule ID | Rule Verdict | Expert Adjudication | Concordance |
| :--- | :--- | :--- | :--- | :--- |
| `case_01_gse96583_clean_pb` | `BFA-001` | PASS | SCIENTIFICALLY SOUND | **MATCH** |
| `case_02_gse96583_naive_cell_wilcoxon` | `BFA-001` | FLAGGED (BLOCKER) | FLAW CONFIRMED | **MATCH** |
| `case_03_rare_disease_n2_exploratory` | `BFA-001b` | PASS | SCIENTIFICALLY SOUND | **MATCH** |
| `case_04_n4_complete_batch_confounding` | `BFA-004` | FLAGGED (BLOCKER) | FLAW CONFIRMED | **MATCH** |
| `case_05_extreme_donor_dominance` | `BFA-007` | FLAGGED (HIGH_IMPACT) | FLAW CONFIRMED | **MATCH** |
| `case_06_honest_null_freeze` | `BFA-003` | PASS | SCIENTIFICALLY SOUND | **MATCH** |
| `case_07_p_hacking_raw_p_reporting` | `BFA-003` | FLAGGED (HIGH_IMPACT) | FLAW CONFIRMED | **MATCH** |
| `case_08_log_counts_fed_to_deseq2` | `BFA-002` | FLAGGED (BLOCKER) | FLAW CONFIRMED | **MATCH** |
| `case_09_causal_overclaim_on_observational` | `BFA-008` | FLAGGED (HIGH_IMPACT) | FLAW CONFIRMED | **MATCH** |
| `case_10_cite_seq_surface_protein_truth` | `BFA-001` | PASS | SCIENTIFICALLY SOUND | **MATCH** |
| `case_11_subtle_effect_underpowered_n3` | `BFA-001b` | FLAGGED (HIGH_IMPACT) | FLAW CONFIRMED | **MATCH** |
| `case_12_execution_fact_hallucination` | `BFA-014` | FLAGGED (BLOCKER) | FLAW CONFIRMED | **MATCH** |
