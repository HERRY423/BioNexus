# StartingPointAssessment
Date: 2026-09-04. Status: INPUT_INSPECTION_COMPLETE; NEW_ANALYSIS_NOT_STARTED.
Project: C:\Plugin\BioNexus. README.zh-CN.md, WORKBENCH_PROMPT.md and SOURCES.md read successfully.
Applied installed NGS Analysis Workbench 0.2.16 skills: understand-ngs-data and design-ngs-analysis, with AnalysisContext and single-cell/bulk reference guidance. Applied BioNexus 1.0.0-rc.4 start environment check.

## Objective
Explore the donor-paired ctrl/stim expression contrast in source-annotated CD14+ Monocytes from Kang 2018 / GSE96583. This is a public processed-count reanalysis.

## Observed inputs and SHA-256
- data/flagship/kang2018_pbmc_ifnb/GSE96583_RAW.tar: 76,195,840 bytes; e5d41a3248a813f99d68fd5c9eb9773de7f46a83680a67f4a02d683b8955fe80
- data/flagship/kang2018_pbmc_ifnb/GSE96583_batch2.total.tsne.df.tsv.gz: 756,342 bytes; 1d57e72e92ca8695250e88cc0f1c3fa8c0be1175d974f8b427c58f1274dc6c09
- review/workbench-ifnb-demo/GSE96583_batch2.genes.tsv.gz: 277,054 bytes; 93aa4e9b530ef9d6411ca129b416324c5cc1cc5a01a1fa6ed4f4a845480ed3ca

All three match fetch_inputs.py frozen hashes. These prove byte consistency with the prepared inputs, not producer authentication.

## Observed contents and relationships
Raw tar includes batch-1 A/B/C files and batch-2 control/stimulation files. Only batch-2 GSM2560248_2.1.mtx.gz and GSM2560249_2.2.mtx.gz plus their barcode files are relevant.
- ctrl matrix: 35,635 genes x 14,619 barcodes; 8,732,747 stored entries.
- stim matrix: 35,635 genes x 14,446 barcodes; 8,838,098 stored entries.
- Matrix Market parser returns float64, but every stored value is finite, nonnegative and exactly integer-valued. No normalization or DE performed in this inspection.
- 35,635 unique Ensembl IDs; symbols are display metadata.
- Metadata: 29,065 rows, unique row names; columns tsne1, tsne2, ind, stim, cluster, cell, multiplets.
- Author multiplets: 24,679 singlet; 3,169 doublet; 1,217 ambs.
- 24,679 retained singlets: ctrl 12,315; stim 12,364. No missing donors or conditions; no zero-count singlets.
- Six singlets have missing source cell labels; they are not members of the CD14+ Monocytes subset. Nine source labels are missing across all metadata rows.
- 5,385 source-annotated CD14+ Monocytes: ctrl 2,785; stim 2,600.
- Condition plus barcode joins are unique and complete after the documented suffix -11 to -1 resolution within condition. Unselected matrix barcodes: ctrl 2,304; stim 2,082, corresponding to non-singlet metadata counts.
- Source fields: ind -> donor, stim -> condition, cell -> source_cell_type; retain multiplets == singlet. Labels and singlet assignments are inherited, not independently validated.
- 13 MT- features; total mitochondrial counts across retained singlets = 0 in both matrices. Mitochondrial QC: NOT_ASSESSED.

| Donor | ctrl CD14+ cells | stim CD14+ cells |
|---|---:|---:|
|101|202|253|
|1015|779|671|
|1016|369|329|
|1039|126|165|
|107|209|169|
|1244|415|290|
|1256|390|375|
|1488|295|348|

## Reference provenance
Local GSE96583_family.soft identifies human SLE PBMCs, 6-hour control/IFN-beta conditions, Cell Ranger 1.2 for batch 2 and hg19.
Live GEO GSM2560249 confirms human SLE PBMCs, 6-hour IFN-beta stimulation, Cell Ranger processing and hg19:
https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSM2560249
Live series/control-page retrieval encountered a browser challenge. Their content was read from the local SOFT record, not claimed as freshly retrieved.
Exact annotation release and chemistry details are not established here; no new alignment or reference substitution is planned.

## Live plugin and execution checks
list_workflows succeeded: 12 active registered workflows. None covers existing single-cell count matrices through paired donor pseudobulk DE. scrnaseq and oai_scrnaseq_fastq_to_count generate counts from FASTQ; rnaseq and oai_bulk_rnaseq_counts_qc are upstream quantification workflows. See ngs_catalog.json.
list_compute_targets succeeded: local is the sole registered target.
inspect_compute_target and get_runtime_environment did not deliver results within this inspection wait; the orchestration cell was terminated. Their results and NGS workflow readiness remain UNVERIFIED. No plan_nextflow, plan_snakemake or execute_plan was called.
Local Python: C:\Users\13264\anaconda3\python.exe; 3.13.9.
Installed and import-checked: anndata 0.13.1, pydeseq2 0.5.4, numpy 2.3.5, pandas 2.3.3, scipy 1.16.3, matplotlib 3.10.6. DeseqDataSet and DeseqStats imports succeed.
BioNexus source import: C:\Plugin\BioNexus\src\bionexus\__init__.py.
python scripts/doctor.py succeeded: plugin_version 1.0.0-rc.4, tier full; core/scverse/spatial ready; scvi/survival/nextflow not ready. These optional backends are not required by the prepared pseudobulk entry point.
The installed BioNexus manifest is 1.0.0-rc.4; the prepared analysis explicitly imports repository src, which is distinct from proof of the MCP server code identity.
Existing repository has substantial user changes; no source files or historical rehearsal outputs were modified.

## BioNexus pre-execution checks
First request used an unsupported free-text research_purpose and was rejected with the valid purpose enumeration.
A corrected exploratory request returned NEEDS_DATA because the required min_replicates_per_condition field was not supplied; preserve bionexus_warrant_initial.json.
After live input inspection, a request supplied eight paired donor IDs, observed count semantics and min_replicates_per_condition=8, while explicitly retaining condition/library confounding. It returned PERMITTED for preflight viability, with statistical_support and external_validation UNTESTED.
The same response's claim_warrant_evaluation remains ABSTAIN / association_claim NOT_WARRANTED. Generic declared-factor SUPPORTED/A fields and an empty residual_limitations list do not establish independent validation or resolve condition-library confounding. Preserve the entire return in bionexus_warrant_verified_inputs.json.
No human approval has been given and no new DE, aggregation, plotting, data fetch or final-result audit was executed.

## Handoff
Inputs support the proposed bounded exploratory combined condition/library contrast. An IFN-beta-specific effect separated from library effects is not identifiable with these data.
Pending user decision: approve the linked analysis_plan.md for the prepared local Python route.
