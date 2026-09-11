# BN-METHODS-20260908: prospective local computational protocol

This protocol is written before this experiment's outcomes are generated. It is a local, timestamped analysis freeze, **not** a publicly preregistered, blinded, or independently conducted study. The author has inspected the software and the historical results. No claim of unseen benchmarks is permitted.

## Claim under test

For completed multi-donor differential-expression results, does the frozen BioNexus audit reject demonstrably unsupported claims and broken evidence while retaining valid, bounded claims? Statistical-method performance and audit performance are separate endpoints. Passing a software audit is not a biological truth label.

## E1: controlled statistical operating characteristics

Generate 800 datasets: 4 or 8 independent donors per group; 20 or 100 cells per donor; donor log-expression standard deviation 0 or 0.8; 0 or 20% non-null genes; 50 independent seeds per factorial cell. Each dataset has 200 genes. Baseline expression is lognormal; donor effects are shared by that donor's cells; individual counts follow a negative binomial distribution with dispersion 0.3. Non-null genes have balanced up/down twofold effects. Compare two-sided Welch tests on individual log1p counts with Welch tests on donor means of the identical log1p counts. These are transparent statistical controls, not comprehensive comparisons of single-cell DE packages and not PyDESeq2 results.

Apply Benjamini-Hochberg at 0.05 separately per result table. Primary descriptive metrics: mean false discovery proportion (FDP, zero when no discoveries), sensitivity (undefined for all-null datasets), and probability of any false positive. Preserve every seed, gene p/q/effect/truth, and dataset-level outcome. Report 95% percentile bootstrap intervals across independent simulation datasets, using 2,000 resamples, separately within each factorial cell. Fifty replicates give at best coarse Monte Carlo precision (worst-case binomial SE 0.071); this is a local mechanism experiment, not a powered confirmatory study. Donor and cell numbers are not a universal acceptance threshold.

## E2: public-data null experiment and paired reanalysis

Use the existing GSE96583 count file (13,487 cells, eight donors), hash-bound at freeze. For the null experiment, use **control-condition CD14+ monocytes only** and the 1,000 most abundant genes after filtering total counts >=10, using no artificial group labels. Enumerate all 35 unique balanced 4-versus-4 donor partitions (complementary assignments are identical for two-sided tests). Compare cell-level Welch, donor-mean Welch on log1p library-normalized counts, and exact donor-label randomization tests based on the difference in donor means. BH is applied per partition and method. These are overlapping partitions of one cohort: report conditional assignment frequencies, no independent-study confidence interval, and no invented external truth. Under the sharp artificial-treatment null, all rejections are false positive assignments; this does not imply that real donor biological differences are absent. Exact two-sided p values have minimum 1/35 and can be very conservative after BH.

For a separate real IFN-beta response sensitivity analysis, aggregate GSE96583 PBMC raw counts per donor and condition and use the existing Parse-10M donor/condition pseudobulk file (24 samples, 12 donors). Revalidate nonnegative integer counts and the recorded Parse output hash. Preserve its known source metadata/expression-count discrepancies. Run official PyDESeq2 0.5.4 with both `~ condition` and `~ donor + condition`, refit_cooks=True, alpha=0.05, at most two worker CPUs. Select a fixed 2,000-gene universe by largest pooled mean normalized abundance among common genes with >=10 counts in >=4 samples **in each cohort**, before fitting. This is a deliberately bounded sensitivity analysis, not a genome-wide benchmark or unseen external validation. Use BH on all finite raw p values for the common comparison; retain native PyDESeq2 adjusted p values separately.

Report model-matrix rank, residual degrees of freedom, fit failures, significant-gene counts, sign changes and Jaccard overlap; more discoveries alone are not better. Select the top 100 genes by paired-model raw p value in GSE96583; measure direction agreement in Parse, descriptive only. Also report an exact donor sign-flip test in Parse on the mean direction-aligned log-CPM effect across that fixed signature (all 4,096 sign assignments, two-sided). This holds the discovery signature fixed, uses donors as units, and provides a diagnostic within two already-known datasets; shared cell composition and study provenance limit biological interpretation. No gene-as-independent-replicate significance test.

## E3: actual-artifact audit challenge and ablations

Generate challenges from the real fitted GSE96583 paired-model result, its actual model matrix, and execution receipt. Freeze family definitions in the runner before executing the audit. Families include correct positive/negative table statements, absent gene, inverted direction, unsupported significance, contradicted negative claims, causal and clinical overclaims, missing FDR, invalid probabilities, missing execution receipt, changed table after execution, wrong receipt hash, failed fit status, and incorrect design. Claims about table facts are evaluated against the actual table; causal/clinical restrictions are developer-authored logical labels, **not** independent expert adjudication. Mark families ineligible when the necessary positive/negative gene is unavailable, without substituting a favourable case.

Use three prespecified English phrasings per claim family; they are correlated paraphrases, not independent experiments. Compare full frozen BioNexus, the same audit without targeted claim text, the same audit without execution metadata, a transparent deterministic checklist (donor counts, FDR presence/range, self-reported donor unit), and accept-all/reject-all boundary controls. These are deterministic comparators, **not** real LLM or human baselines. No artifact-binding or calibration ablation will be claimed if that mechanism does not exist in the tested path. Primary endpoint: unsupported acceptance among invalid cases **jointly** with valid-case retention, broken down by failure family. `NEEDS_DATA` and `NOT_ASSESSED` are abstentions, not successful issue identification. Also report targeted issue identification separately from withholding, full per-case outputs, missing evidence, and latency (machine time only).

## Reproducibility and exclusions

Copy the dirty working source into a fresh capsule and import the frozen copy. Bind input files, protocol, runner, source files and environment in FREEZE.json before analysis. Never overwrite an existing execution directory; new attempts receive new run IDs. Exceptions remain in failure records; failed runs are not dropped from denominators. No tuning of product code or thresholds during the frozen experiment. Harness defects require a recorded amendment, retaining previous attempts. Report outcome differences after any bugfix as exploratory.

## Work that cannot be invented

No provider API credentials are configured for OpenAI, Anthropic or Gemini in this environment at preflight. Live model baselines are NOT_RUN; trace replay is not live generation. External expert labels, real human review minutes, independent laboratory adoption, wet-lab validation and blinded replication are NOT_ESTABLISHED. Prepare a handoff protocol and empty data forms for these, not synthetic evidence. An SCI/Q1 acceptance claim cannot be established by this experiment.

## Primary methodological sources

- Squair et al., 2021, biological-replicate variation and false discoveries: https://www.nature.com/articles/s41467-021-25960-2
- Official PyDESeq2 0.5.4 workflow and multi-factor design: https://pydeseq2.readthedocs.io/en/stable/auto_examples/plot_minimal_pydeseq2_pipeline.html
- Nature life-sciences reporting: https://www.nature.com/documents/nr-reporting-life-sciences-research.pdf

These sources motivate design and reporting; they do not validate BioNexus or this implementation.
