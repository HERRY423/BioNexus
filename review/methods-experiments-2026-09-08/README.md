# BN-METHODS-20260908 — completed local experiments

Start with [the Chinese findings](REPORT.zh-CN.md) or [the English methods/results supplement](METHODS_RESULTS.md).

This is a **negative product-readiness result**, with useful statistical and real-data evidence. It is not a certificate, external replication, or completed Q1 submission. The original product accepted 0/42 invalid cases but retained 0/12 valid cases. An explicitly post-outcome heuristic ablation retained 9/12 valid cases and accepted 24/42 invalid cases. Do not cite the first number alone.

| Artifact | Purpose |
|---|---|
| PROTOCOL.md / FREEZE.json / frozen-source | Local pre-execution design, input/source hashes and actual tested code |
| run-01/simulate | 800 simulated datasets, 1,600 method records and 320,000 gene records |
| run-01/real-null | 35 dependent donor partitions of one public control cohort |
| run-01/paired | Four actual PyDESeq2 fits across two already-known public cohorts |
| run-01/challenge | 54 developer-authored cases, six deterministic arms, all raw inputs and outputs |
| exploratory-01 | Post-outcome severity ablation, with two arms and original check-level localization |
| reproducibility-02 / VERIFICATION.json | Re-execution equality and statistical cross-checks |
| plots | Two figures in PNG/PDF/SVG; legends in METHODS_RESULTS.md |
| reviewer-packet.zip | Opaque-ID cases and blank expert forms; no expert reviews received |
| reviewer-key-PRIVATE.csv | Provisional developer labels; exclude from blinded review distribution |
| EXTERNAL_STUDY_HANDOFF.zh-CN.md | Independent evaluation and lab-time study instructions |

Run from the original repository with the frozen data hashes and recorded environment:

```powershell
$env:NUMBA_CACHE_DIR = Join-Path (Get-Location) '.codex-de-pilot-numba'
$env:OPENBLAS_NUM_THREADS = '1'
$env:OMP_NUM_THREADS = '1'
$env:MKL_NUM_THREADS = '1'
python review/methods-experiments-2026-09-08/run_experiments.py simulate --run-id my-reproduction
python review/methods-experiments-2026-09-08/run_experiments.py real-null --run-id my-reproduction
python review/methods-experiments-2026-09-08/run_experiments.py paired --run-id my-reproduction
python review/methods-experiments-2026-09-08/run_experiments.py challenge --run-id my-reproduction --real-run-id my-reproduction
```

Use a fresh run ID; existing stage directories are never overwritten. Do not regenerate FREEZE.json. Raw GSE96583 and Parse artifacts remain at the original repository paths listed in the freeze, with required SHA-256 checks. The capsule includes the selected pseudobulk counts but does not duplicate the original raw datasets. Cross-machine installation remains untested.

`analyze_results.py` verifies and renders the existing run-01 and reproducibility-02 outputs. It can regenerate derived reports/figures; it never alters their underlying experimental outputs. The exploratory script intentionally refuses to overwrite its existing directory. Product source changes require a new study/version, not replacement of the frozen snapshot.

No product source was changed during these experiments. No live LLM calls, independent expert reviews, external messages, publication, release or submission occurred. Record these missing studies as NOT_RUN or NOT_ESTABLISHED.
