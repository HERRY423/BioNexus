---
name: nextflow-development
description: Prepare nf-core samplesheets, cluster nextflow.config, and write launch artifacts. nfcore_launch.py only wraps nf-core/rnaseq and nf-core/scrnaseq with optional nextflow -preview. Other pipelines still use generate_samplesheet.py plus a hand-written nextflow run. Does not reimplement the pipelines.
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
