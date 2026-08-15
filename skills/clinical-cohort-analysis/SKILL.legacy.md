---
name: clinical-cohort-analysis
description: Only if the user explicitly asked for a grade-C heuristic. KM/log-rank on caller arrays; Cox only with lifelines; NNLS only with a signature. Not a default analysis skill. Does not download DepMap.
---

# Clinical cohort helpers

- KM + log-rank are real estimators (grade B).
- `calculate_cox_hazard_ratio` is **lifelines CoxPH** when installed, otherwise an event-rate ratio labeled `event_rate_ratio_not_cox`.
- Synthetic lethality does not fetch CERES matrices.
- Immune NNLS **refuses** without a signature matrix.

Research-use only. Not a clinical biostatistics report.
