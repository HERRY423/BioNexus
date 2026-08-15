"""
Unit tests for Nextflow cluster profile generator and pipeline catalog.
"""

import pytest
import yaml
from pathlib import Path
from cluster_profile_generator import generate_hpc_profile, generate_cloud_profile
from generate_samplesheet import load_pipeline_config


def test_generate_slurm_profile():
    """Verify Slurm HPC profile generation containing proper queue, account, and retry policies."""
    config_str = generate_hpc_profile(
        executor="slurm",
        partition="gpu_nodes",
        account="cancer_research_lab",
        qos="high",
        max_memory="512.GB",
        max_cpus=128,
        container_engine="singularity"
    )

    assert "executor = 'slurm'" in config_str
    assert "queue = 'gpu_nodes'" in config_str
    assert "--account=cancer_research_lab" in config_str
    assert "--qos=high" in config_str
    assert "singularity {" in config_str
    assert "errorStrategy = { task.exitStatus in [140, 143, 137, 104, 134, 139] ? 'retry' : 'finish' }" in config_str
    assert "check_max" in config_str


def test_generate_aws_batch_profile():
    """Verify AWS Batch cloud configuration."""
    config_str = generate_cloud_profile(
        provider="aws",
        queue_or_region="arn:aws:batch:us-east-1:123456789:job-queue/bio-queue",
        work_bucket="s3://my-lab-bucket/work"
    )

    assert "executor = 'awsbatch'" in config_str
    assert "queue    = 'arn:aws:batch:us-east-1:123456789:job-queue/bio-queue'" in config_str
    assert "workDir = 's3://my-lab-bucket/work'" in config_str


def test_generate_google_batch_profile():
    """Verify Google Cloud Batch configuration."""
    config_str = generate_cloud_profile(
        provider="google",
        queue_or_region="us-central1",
        project="bionexus-gcp-prod",
        work_bucket="gs://bionexus-bucket/work"
    )

    assert "executor = 'google-batch'" in config_str
    assert "project  = 'bionexus-gcp-prod'" in config_str
    assert "location = 'us-central1'" in config_str


def test_all_pipeline_configs_loadable():
    """Verify that all 7 supported nf-core pipeline YAML configs are valid and parseable."""
    pipelines = ["rnaseq", "scrnaseq", "sarek", "atacseq", "methylseq", "proteinfold", "nanoseq"]
    for p in pipelines:
        config = load_pipeline_config(p)
        assert config is not None
        assert "name" in config
        assert config["name"] == p
        assert "version" in config
        assert "samplesheet" in config
        assert "columns" in config["samplesheet"]
