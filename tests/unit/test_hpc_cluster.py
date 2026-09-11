"""
Unit tests for BioNexus HPC and Cloud-Native Batch Cluster Engine (bionexus.cluster).
"""

import json

from bionexus.cluster import (
    JobResourceConfig,
    SchedulerType,
    diagnose_job_failure,
    generate_aws_batch_job,
    generate_gcp_batch_job,
    generate_k8s_job_yaml,
    generate_lsf_script,
    generate_pbs_script,
    generate_slurm_script,
    probe_cluster_environment,
    submit_job,
)


def test_generate_slurm_script_complete():
    """Verify Slurm script generation with all resource pragmas and bash safety guards."""
    res = JobResourceConfig(
        job_name="scrna_recluster",
        cpus=32,
        memory="128GB",
        time_limit="48:00:00",
        partition="highmem",
        account="lab_cancer_genomics",
        qos="priority",
        gpus=2,
        gpu_type="a100",
        email="bioinformatician@lab.org",
        modules_to_load=["singularity/3.8.0", "cuda/11.8"],
        env_vars={"NUMBA_NUM_THREADS": "32", "OMP_NUM_THREADS": "32"},
    )
    script = generate_slurm_script("python run_scrna.py --input sample.h5ad", res)

    assert "#!/usr/bin/env bash" in script
    assert "#SBATCH --job-name=scrna_recluster" in script
    assert "#SBATCH --cpus-per-task=32" in script
    assert "#SBATCH --mem=128GB" in script
    assert "#SBATCH --time=48:00:00" in script
    assert "#SBATCH --partition=highmem" in script
    assert "#SBATCH --account=lab_cancer_genomics" in script
    assert "#SBATCH --qos=priority" in script
    assert "#SBATCH --gres=gpu:a100:2" in script
    assert "#SBATCH --mail-user=bioinformatician@lab.org" in script
    assert "set -euo pipefail" in script
    assert "module load singularity/3.8.0" in script
    assert "module load cuda/11.8" in script
    assert 'export NUMBA_NUM_THREADS="32"' in script
    assert "python run_scrna.py --input sample.h5ad" in script


def test_generate_pbs_script():
    """Verify PBS/Torque batch script generation."""
    res = JobResourceConfig(
        job_name="bulk_rnaseq",
        cpus=16,
        memory="64GB",
        time_limit="12:00:00",
        partition="batch",
        account="acc_123",
    )
    script = generate_pbs_script("nextflow run nf-core/rnaseq", res)

    assert "#PBS -N bulk_rnaseq" in script
    assert "#PBS -l select=1:ncpus=16:mem=64GB" in script
    assert "#PBS -l walltime=12:00:00" in script
    assert "#PBS -q batch" in script
    assert "#PBS -A acc_123" in script
    assert "nextflow run nf-core/rnaseq" in script


def test_generate_lsf_script():
    """Verify IBM Spectrum LSF batch script generation."""
    res = JobResourceConfig(
        job_name="sarek_variant_calling",
        cpus=24,
        memory="96GB",
        time_limit="24:00:00",
        partition="genomics",
    )
    script = generate_lsf_script("nextflow run nf-core/sarek", res)

    assert "#BSUB -J sarek_variant_calling" in script
    assert "#BSUB -n 24" in script
    assert "#BSUB -M 96GB" in script
    assert "#BSUB -q genomics" in script
    assert "nextflow run nf-core/sarek" in script


def test_generate_k8s_job_yaml():
    """Verify Kubernetes batch Job manifest structure and GPU limits."""
    res = JobResourceConfig(
        job_name="spatial-moran-job",
        cpus=8,
        memory="32GB",
        gpus=1,
        container_image="quay.io/biocontainers/squidpy:1.3.0",
    )
    yaml_str = generate_k8s_job_yaml(
        command=["python", "compute_svg.py"],
        resources=res,
        namespace="computational-biology",
        pvc_claim_name="nfs-bio-pvc",
    )
    job_dict = json.loads(yaml_str)

    assert job_dict["apiVersion"] == "batch/v1"
    assert job_dict["kind"] == "Job"
    assert job_dict["metadata"]["name"] == "spatial-moran-job"
    assert job_dict["metadata"]["namespace"] == "computational-biology"
    container = job_dict["spec"]["template"]["spec"]["containers"][0]
    assert container["image"] == "quay.io/biocontainers/squidpy:1.3.0"
    assert container["resources"]["requests"]["cpu"] == "8"
    assert container["resources"]["requests"]["memory"] == "32Gi"
    assert container["resources"]["limits"]["nvidia.com/gpu"] == "1"
    assert container["volumeMounts"][0]["mountPath"] == "/data"


def test_generate_aws_and_gcp_batch():
    """Verify Cloud Batch JSON descriptor generation."""
    res = JobResourceConfig(job_name="cloud_scrna", cpus=16, memory="64GB", gpus=1)

    # AWS Batch
    aws_payload = generate_aws_batch_job(
        command=["python", "run.py"],
        job_queue="arn:aws:batch:us-east-1:1234:queue/bio",
        job_definition="bionexus-gpu:1",
        resources=res,
    )
    assert aws_payload["jobName"] == "cloud_scrna"
    assert aws_payload["jobQueue"] == "arn:aws:batch:us-east-1:1234:queue/bio"
    assert aws_payload["containerOverrides"]["resourceRequirements"][0]["value"] == "16"
    assert aws_payload["containerOverrides"]["resourceRequirements"][1]["value"] == "65536"

    # GCP Batch
    gcp_payload = generate_gcp_batch_job(
        command="python run.py",
        project="bionexus-lab",
        region="us-central1",
        resources=res,
    )
    assert gcp_payload["taskGroups"][0]["taskSpec"]["computeResource"]["cpuMilli"] == 16000
    assert gcp_payload["taskGroups"][0]["taskSpec"]["computeResource"]["memoryMib"] == 65536
    assert gcp_payload["allocationPolicy"]["location"]["allowedLocations"] == ["regions/us-central1"]


def test_probe_cluster_environment():
    """Verify cluster environment prober detects host system specifications."""
    report = probe_cluster_environment()
    assert report.system_cores >= 1
    assert report.system_ram_gb >= 0.0
    assert isinstance(report.available_schedulers, list)
    assert isinstance(report.to_dict(), dict)


def test_submit_job_dry_run(tmp_path):
    """Verify dry-run submission returns simulated success without calling system binaries."""
    script_file = tmp_path / "test_job.sh"
    script_file.write_text("#!/bin/bash\necho hello\n", encoding="utf-8")

    res = submit_job(script_path=script_file, scheduler=SchedulerType.SLURM, dry_run=True)
    assert res.success is True
    assert res.job_id == "DRY_RUN_ID_12345"
    assert "sbatch" in res.submission_command


def test_submit_job_missing_file():
    """Verify submit_job cleanly handles non-existent script paths."""
    res = submit_job(script_path="non_existent_file.sh", scheduler=SchedulerType.SLURM)
    assert res.success is False
    assert "not found" in res.message


def test_diagnose_job_failure_oom():
    """Verify diagnosis of exit code 137 (OOM Killer) with resource doubling recommendation."""
    diag = diagnose_job_failure(exit_code=137, log_content="Killed by out of memory cgroup", current_memory_gb=64.0)
    assert diag.is_oom is True
    assert "OOM-Killer" in diag.primary_cause
    assert "128.0GB" in diag.remedy
    assert diag.suggested_resource_adjustment == {"memory": "128GB"}


def test_diagnose_job_failure_timeout():
    """Verify diagnosis of exit code 143 / Slurm time limit."""
    diag = diagnose_job_failure(exit_code=143, log_content="slurmstepd: error: *** JOB 123 ON node01 CANCELLED AT ... DUE TO TIME LIMIT ***")
    assert diag.is_timeout is True
    assert "walltime limit" in diag.primary_cause
    assert "Increase --time" in diag.remedy


def test_diagnose_job_failure_command_not_found():
    """Verify diagnosis of exit code 127 (missing binary)."""
    diag = diagnose_job_failure(exit_code=127, log_content="/tmp/slurm_script.sh: line 12: samtools: command not found")
    assert "not found in PATH" in diag.primary_cause
    assert "module load" in diag.remedy


def test_generate_tes_task_valid_schema():
    """Verify GA4GH Task Execution Service (TES) v1.0.0 descriptor generation."""
    import json

    from bionexus.cluster import JobResourceConfig, generate_job_script, generate_tes_task

    res = JobResourceConfig(job_name="tes_scrna_qc", cpus=16, memory="64GB")
    task = generate_tes_task(
        name="tes_scrna_qc",
        command=["python", "scrna_qc.py", "--input", "/data/sample.h5ad"],
        image="quay.io/biocontainers/scanpy:1.10.0",
        resources=res,
        inputs=[{"path": "/data/sample.h5ad", "url": "s3://bio-bucket/sample.h5ad", "type": "FILE"}],
        outputs=[{"path": "/data/qc_out", "url": "s3://bio-bucket/results", "type": "DIRECTORY"}],
    )

    d = task.to_dict()
    assert d["name"] == "tes_scrna_qc"
    assert len(d["executors"]) == 1
    assert d["executors"][0]["image"] == "quay.io/biocontainers/scanpy:1.10.0"
    assert d["resources"]["cpu_cores"] == 16
    assert d["resources"]["ram_gb"] == 64.0
    assert d["resources"]["preemptible"] is True
    assert d["inputs"][0]["type"] == "FILE"
    assert d["outputs"][0]["type"] == "DIRECTORY"
    assert d["tags"]["framework"] == "BioNexus"

    # Also verify generate_job_script with scheduler="tes"
    script_str = generate_job_script(
        scheduler="tes",
        command=["python", "run.py"],
        resources=res,
    )
    parsed = json.loads(script_str)
    assert parsed["name"] == "tes_scrna_qc"
    assert len(parsed["executors"]) == 1


def test_elastic_scale_policy_retry_escalation():
    """Verify ElasticScalePolicy escalates memory exponentially on exit code 137 (OOM)."""
    from bionexus.cluster import ElasticScalePolicy, JobResourceConfig

    policy = ElasticScalePolicy(max_retries_on_oom=3, oom_memory_multiplier=2.0)
    init_res = JobResourceConfig(job_name="heavy_job", cpus=8, memory="16GB")

    # Attempt 0 -> next attempt 1 (should be 16 * 2^1 = 32GB)
    res_att1 = policy.compute_retry_resources(attempt=0, current_resources=init_res, exit_code=137)
    assert res_att1 is not None
    assert res_att1.memory == "32GB"
    assert res_att1.job_name == "heavy_job_retry1"

    # Attempt 1 -> next attempt 2 (should be 16 * 2^2 = 64GB)
    res_att2 = policy.compute_retry_resources(attempt=1, current_resources=init_res, exit_code=137)
    assert res_att2 is not None
    assert res_att2.memory == "64GB"

    # Attempt 3 -> retries exhausted
    res_exhausted = policy.compute_retry_resources(attempt=3, current_resources=init_res, exit_code=137)
    assert res_exhausted is None


def test_cloud_native_batch_profile():
    """Verify CloudNativeBatchProfile serializes multi-cloud elastic container execution."""
    from bionexus.cluster import CloudNativeBatchProfile, ElasticScalePolicy

    prof = CloudNativeBatchProfile(
        provider="kubernetes",
        container_engine="docker",
        image_uri="quay.io/biocontainers/scanpy:1.10.0",
        storage_mounts={"/mnt/nfs/data": "/data"},
        environment={"BIO_DEBUG": "1"},
        elastic_policy=ElasticScalePolicy(max_nodes=128),
    )
    d = prof.to_dict()
    assert d["provider"] == "kubernetes"
    assert d["storage_mounts"]["/mnt/nfs/data"] == "/data"
    assert d["elastic_policy"]["max_nodes"] == 128

