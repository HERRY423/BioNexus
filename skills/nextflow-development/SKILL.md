---
name: nextflow-development
description: Prepare nf-core samplesheets, cluster nextflow.config, write launch artifacts, and execute them. nfcore_launch.py wraps nf-core/rnaseq and nf-core/scrnaseq; nfcore_sarek_launch.py wraps nf-core/sarek (germline/somatic). nfcore_execute.py runs a launch script for real when Nextflow is on PATH and records a Run Capsule. Other pipelines still use generate_samplesheet.py plus a hand-written nextflow run. Does not reimplement the pipelines.
---

# nf-core Pipeline Deployment & Cluster Execution

Run nf-core bioinformatics pipelines on local machines, HPC clusters (Slurm, PBS, SGE, LSF), or Cloud Batch environments (AWS Batch, Google Cloud Batch).

## Supported nf-core Pipelines

| Data Type | Pipeline | Version | Primary Purpose |
|---|---|---|---|
| Bulk RNA-seq | `rnaseq` | 3.22.2 | Gene expression quantification & DESeq2 |
| Single-Cell RNA | `scrnaseq` | 2.7.2 | STARsolo, Alevin, 10X count matrices |
| WGS / WES | `sarek` | 3.7.1 | Germline & somatic variant calling |
| ATAC-seq | `atacseq` | 2.1.2 | Peak calling & chromatin accessibility |
| DNA Methylation | `methylseq` | 2.7.0 | Bismark / bwa-meth CpG methylation |
| Protein Structure | `proteinfold` | 1.1.1 | AlphaFold2, ColabFold, ESMFold 3D models |
| Nanopore Long-Reads | `nanoseq` | 3.1.0 | Demultiplexing, Minimap2, SV calling |

---

## HPC & Cloud Cluster Profile Generator (`scripts/cluster_profile_generator.py`)

Generate tailored `nextflow.config` files with dynamic resource escalation (auto-retry on OOM errors) and container engine bindings:

```bash
# Slurm cluster profile with Singularity/Apptainer
python scripts/cluster_profile_generator.py \
    --executor slurm \
    --partition standard \
    --account my_lab_account \
    --max-memory 256.GB \
    -o nextflow_slurm.config

# AWS Batch profile
python scripts/cluster_profile_generator.py \
    --executor awsbatch \
    --aws-queue arn:aws:batch:... \
    --work-bucket s3://my-lab-bucket/nextflow_work \
    -o nextflow_aws.config

# Google Cloud Batch profile
python scripts/cluster_profile_generator.py \
    --executor googlebatch \
    --google-project my-gcp-project \
    --google-region us-central1 \
    --work-bucket gs://my-lab-bucket/work \
    -o nextflow_gcp.config
```

Run pipelines on your cluster:
```bash
nextflow run nf-core/scrnaseq \
    -c nextflow_slurm.config \
    -profile singularity \
    --input samplesheet.csv \
    --genome GRCh38 \
    --aligner starsolo \
    --outdir ./results
```

---

## Workflow Steps

1. **Step 0: Acquire Data (GEO/SRA)**: `python scripts/sra_geo_fetch.py download GSE110004 -o ./fastq`
2. **Step 1: Check Environment**: `python scripts/check_environment.py --samplesheet samplesheet.csv --config nextflow.config`
2b. **Launch artifact**: `python scripts/nfcore_launch.py --pipeline rnaseq --samplesheet samplesheet.csv --outdir results -o run.sh --preview`
3. **Step 2: Generate Samplesheet**: `python scripts/generate_samplesheet.py ./fastq scrnaseq -o samplesheet.csv`
4. **Step 3: Generate Cluster Profile**: `python scripts/cluster_profile_generator.py --executor slurm`
5. **Step 4: Execute Pipeline**: `nextflow run nf-core/<pipeline> -c nextflow_cluster.config ...`
   *or, on hosts with Nextflow installed, execute the launch artifact directly (below).*

---

## Real Execution (`scripts/nfcore_execute.py`)

`nfcore_launch.py` writes `run.sh`; `nfcore_execute.py` actually runs it when `nextflow`
and `bash` are on PATH, capturing exit status, stdout/stderr tails, and a full Run
Capsule (`run.json`, `evidence.json`, `provenance.json`, logs). A missing Nextflow
binary or a non-zero exit is reported honestly — the tool never simulates success.

```bash
# Probe the environment without executing
python scripts/nfcore_execute.py --script run.sh --dry-run

# Execute for real; capsule written under runs/
python scripts/nfcore_execute.py --script run.sh --outdir results --capsule-root runs
```

Execution fidelity is recorded (`EXECUTED` / `FAILED`); biological interpretation of
pipeline outputs remains the analyst's responsibility.

---

## Sarek Variant Calling (`scripts/nfcore_sarek_launch.py`)

Wraps `nf-core/sarek` (3.x) launch artifacts with Sarek-specific samplesheet validation:
required columns `patient, sample, fastq_1, fastq_2`; optional `lane` and `status`
(`0`/`normal` or `1`/`tumor`, auto-normalized for somatic calling). An explicit `--step`
is mandatory — BioNexus never silently assumes a Sarek entry point.

```bash
# Germline calling
python scripts/nfcore_sarek_launch.py \
    --samplesheet sarek_samplesheet.csv --outdir results \
    --step germline -o run_sarek.sh --preview

# Somatic tumor/normal calling (status column required)
python scripts/nfcore_sarek_launch.py \
    --samplesheet sarek_samplesheet.csv --outdir results \
    --step somatic --normalized-sheet normalized.csv -o run_sarek_somatic.sh
```

Allowed `--step` values follow the canonical Sarek 3.x interface:
`ubam, mapping, markdup, prepare_recalibration, recalibrate, germline, somatic, controlfreec`.

---

## Chain with Other BioNexus Stages

Launch, execute, and downstream BioNexus analyses can be wired into a fail-closed
Run Capsule chain (`bionexus chain workflow.yaml`); see
`skills/research-workflow-orchestrator/SKILL.md` and `docs/artifact-contract.md`.
