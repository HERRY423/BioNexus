# Computational methods and results supplement — BN-METHODS-20260908

Draft based on executed local experiments; not an independently validated submission-ready manuscript.

## Study design and reproducibility

The evaluated software was a snapshot of working-tree BioNexus based on commit bdf38e1942ff4f517ae696c3c413bf481d8ebac4, including uncommitted pre-existing changes. Source files, data, analysis protocol and runner were hashed before execution; the copied source was imported during evaluation. This was a prospective local analysis freeze, not public preregistration. Authors had previously inspected both software and historical data. The original source was not changed during the experiment. Python/package versions are in FREEZE.json. No observations or failed cases were excluded from the completed stages.

## Controlled simulations

Eight hundred independently seeded negative-binomial datasets represented the factorial combination of 4/8 donors per group, 20/100 cells per donor, donor log-expression SD 0/0.8, and 0/20% non-null genes (50 datasets per stratum; 200 genes each). Baseline gene means followed a lognormal distribution (log mean 1.5, SD 0.6); donor-specific log shifts were shared across cells. Count dispersion was 0.3. Non-null genes had balanced positive/negative log effects of ln(2). Two-sided Welch tests were applied either to log1p cell counts or to donor means of the same transformed counts. BH adjustment was applied separately within each table at 0.05. This intentionally simple comparison isolates statistical-unit effects; it is neither a comprehensive benchmark of DE packages nor an evaluation of BioNexus-specific statistical innovation.

Mean FDP, false-positive dataset frequency and sensitivity were computed with all seeds retained; FDP was zero in the absence of discoveries. Sensitivity was undefined in all-null datasets. Within-stratum 95% percentile intervals used 2,000 bootstrap resamples of datasets, not genes. Fifty replicates imply coarse Monte Carlo precision. Supplementary post-outcome Wilson intervals were added for binary frequencies to avoid degenerate bootstrap intervals at the boundaries. Under donor heterogeneity and non-zero signal, cell tests yielded mean FDP 0.708–0.781. Donor-mean tests yielded 0–0.027, with sensitivity only 0.001–0.0125 under these difficult settings. Reduced errors therefore coexisted with considerable loss of power. All zero-heterogeneity and all-null controls are retained in the source data.

## Public-data negative control

The real-data negative control used 2,155 control-condition CD14+ monocytes from eight GSE96583 donors. The 1,000 most abundant genes with total counts >=10 were selected before generating artificial donor-group labels. Counts were normalized to 10,000 total counts per cell and log1p transformed. All 35 unique balanced 4-versus-4 donor partitions were enumerated; complementary assignments gave identical two-sided results. Cell-level Welch, donor-mean Welch, and exact donor-label randomization tests were BH-adjusted separately. Individual-cell tests produced discoveries in 35/35 partitions (median 229 genes, maximum 348); donor Welch in 1/35 (one gene); exact donor randomization in 0/35. These overlapping partitions support conditional assignment diagnostics, not 35 independent studies. The artificial-assignment null does not deny actual between-donor biological variation. The exact two-sided minimum p=1/35 and multiple-testing adjustment limit power.

## Paired public-cohort reanalysis

GSE96583 PBMC counts were summed by donor and condition (16 samples, eight donors). The existing Parse-10M pseudobulk artifact contained 24 samples from 12 donors; its extraction metadata reported 725,031 source cells. This study reanalyzed the aggregate artifact rather than re-extracting those cells. Its recorded output hash was verified; metadata/expression-count discrepancies involving 30,634 cells were retained. Genes required >=10 counts in >=4 samples in each cohort. The 2,000 common genes with greatest mean library-normalized abundance pooled across the cohorts formed a fixed comparison universe. This restriction is an analysis limitation and not an unseen validation holdout.

Official PyDESeq2 0.5.4 models used either ~condition or ~donor+condition, refit_cooks=True, alpha=0.05 and two CPUs. Model matrices, ranks, residual degrees of freedom, native adjusted p values, and BH adjustment over all finite raw p values were exported. Residual degrees of freedom changed from 14 to 7 in GSE96583 and 22 to 11 in Parse. Significant-gene counts changed from 1,044 to 1,219 and from 964 to 1,516, respectively. The corresponding set Jaccard indices were 0.844 and 0.635; numbers of effect-direction changes were 15 and 32. Increased discovery counts alone cannot establish improved accuracy. Both GSE96583 fits reported failure of the parametric dispersion trend and the library's fallback to a mean trend; these warnings were retained.

A fixed signature of the 100 smallest paired-model p values in GSE96583 exhibited 95% effect-direction agreement in Parse. For each Parse donor, the mean direction-aligned log2(CPM+1) difference across this signature was computed using panel-normalized libraries. Exhaustive two-sided donor sign flipping (4,096 assignments) yielded p=0.0009765625. This exploratory diagnostic assumes independent donor scores and sign exchangeability under the null. Mixed PBMC composition, panel normalization, prior use of these data and cross-cohort abundance selection limit interpretation. It does not supersede historical preregistered endpoints or establish independent replication.

## Audit challenge and controlled ablations

The real GSE96583 paired-model table, recorded design matrix and actual execution receipt provided 54 cases in 18 prespecified families with three correlated English phrasings. Twelve cases contained bounded valid statements; 42 contained contradictory table statements, absent genes, causal/clinical overclaims or deliberately damaged evidence. Labels were author-defined logical/consistency labels, not expert ground truth. The four genuine-record valid families retained matching table, metadata and design hashes. The full audit, two input-omission ablations, a transparent deterministic checklist and accept-all/reject-all boundary controls were evaluated. None was described as a live LLM or human comparator.

| Arm | Unsupported cases accepted | Valid cases retained |
|---|---:|---:|
| accept_all | 42/42 | 12/12 |
| bionexus_full | 0/42 | 0/12 |
| deterministic_checklist | 33/42 | 12/12 |
| reject_all | 0/42 | 0/12 |
| without_claim_text | 0/42 | 0/12 |
| without_execution_metadata | 0/42 | 0/12 |
| heuristic_advisory (post-outcome) | 24/42 | 9/12 |
| heuristic_advisory_without_claim (post-outcome) | 33/42 | 12/12 |

The frozen audit rejected all cases, yielding zero valid retention. All cases triggered the extreme-p heuristic BFA-001c because the actual donor-model table contained 18 p values below 1e-100 (none equal to zero). A post-outcome in-memory ablation changed only that finding's severity to advisory, retaining the finding and unchanged input data. This retained 9/12 valid cases while accepting 24/42 invalid cases. The post-outcome analysis is explicitly exploratory and not a shipped product revision.

The original binding check nevertheless marked all 12 cases with wrong output hashes, altered results, failed fit status or a conflicting model formula ASSESSED. Several false gene-level statements were also marked ASSESSED. Conversely, the valid IL1RN upregulation sentence was classified as a causal request. The original case-outcome field named issue_identified is only a mechanical rejection/high-severity flag, including a flag in the reject-all control; it is **not a correctly localized error measure**. Generic rejection cannot be credited with detecting an unrelated altered artifact. Check-level results and all raw findings are supplied for audit.

## Verification, limits and remaining studies

An independent second local execution reproduced all 14 model/input/signature CSV artifacts byte-for-byte. BH was checked against scipy.stats.false_discovery_control and the exact null calculation against SciPy's exhaustive 70-assignment test for 25 genes. All 800 simulation seeds and 1,600 method records were checked for completeness, finite p values and correct denominators. This is computational verification within one environment, not independent laboratory validation or proof of biological truth.

No live model calls were made because no provider API credentials were configured. External expert labels, human-time savings, independent laboratory adoption and blinded external replication remain unestablished. A randomized-ID reviewer packet and blank expert/time forms are provided for a future study; there are zero completed ratings. These findings support concrete engineering priorities and bounded statistical-mechanism conclusions. They do not establish BioNexus superiority, scientific certification, clinical validity or readiness for acceptance in a Q1 journal.

## Figure legends

Figure 1. Joint operating characteristics. A–B: mean FDP and sensitivity at donor SD 0.8 and 20% non-null genes, 50 independent datasets per stratum; error bars are 95% percentile bootstrap intervals over 2,000 resamples. All other strata are in source CSV. C: numbers of discoveries in each of 35 dependent artificial donor partitions; horizontal segments show medians. D: unsupported acceptance plotted jointly with valid retention in developer-authored cases. The advisory point is an explicitly post-outcome ablation; the frozen product coincides with reject-all.

Figure 2. Paired-design sensitivity and exploratory cross-cohort consistency. A: significant genes in the fixed 2,000-gene panel; counts are not accuracy measures. B: effects for the 100 discovery-ranked genes, with 95% directional agreement. C: 12 Parse donor signature scores; donors, not genes, form the sign-flip units. These are already-known public datasets, and no independent blinded labels were obtained.

## References

1. Squair JW et al. Confronting false discoveries in single-cell differential expression. Nature Communications 12, 5692 (2021). https://www.nature.com/articles/s41467-021-25960-2
2. PyDESeq2 0.5.4 official documentation. https://pydeseq2.readthedocs.io/en/stable/auto_examples/plot_minimal_pydeseq2_pipeline.html
3. Nature, Reporting Life Sciences Research. https://www.nature.com/documents/nr-reporting-life-sciences-research.pdf
