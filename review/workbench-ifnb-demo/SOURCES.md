# Sources and provenance

- Primary study: Kang et al., *Multiplexed droplet single-cell RNA-sequencing using natural genetic variation*, Nature Biotechnology 36, 89–94 (2018). https://www.nature.com/articles/nbt.4042 ; DOI 10.1038/nbt.4042.
- GEO: https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE96583 . Control GSM2560248, stimulated GSM2560249. The existing local SOFT record identifies SLE PBMCs and 6-hour IFN-beta stimulation.
- Direct public inputs: https://ftp.ncbi.nlm.nih.gov/geo/series/GSE96nnn/GSE96583/suppl/ . Exact names and SHA-256 values are in `fetch_inputs.py`; these hashes freeze the bytes used here, not an independently signed producer attestation.
- Original matrix gene features use unique Ensembl IDs; symbols remain display metadata. Condition and barcode jointly identify a cell. The author's merged metadata suffix `-11` is resolved to original barcode `-1` inside its stated condition; all resulting joins must be unique and present.
- We do not use the repository's `pbmc_ifnb_counts.h5ad` or previously computed differential-expression tables for this run. Thus its 13,487-cell subset is not the denominator of this analysis.
- Official Workbench introduction and onboarding: https://developers.openai.com/blog/rosalind-workbench (2026-08-28). Open Workbench, follow guided onboarding, choose a question and connect relevant tools. Explore mode uses available ChatGPT models; special GPT-Rosalind access is not a prerequisite for preparing this public-data demo.
- Official entry: https://openai.com/rosalind/ . UI wording can change; do not assume a fixed single-cell menu item exists.

The public-count analysis is a processed-matrix reanalysis, not FASTQ alignment or an independent scientific replication. The t-SNE panel uses the deposited author coordinates. The new computations are condition-aware input reconstruction, QC summaries, pseudobulk aggregation, paired differential expression, donor-level plots, and BioNexus source-annotation assessment.
