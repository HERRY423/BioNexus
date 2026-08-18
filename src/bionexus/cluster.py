"""
BioNexus High-Performance Computing (HPC) & Cloud-Native Batch Cluster Engine.

Provides unified capabilities for top-tier biological laboratories:
1. Schedulers: Slurm, PBS/Torque, LSF, SGE, Kubernetes Jobs, AWS Batch, GCP Batch.
2. Cluster Environment Probing: automatic detection of available schedulers, GPU accelerators, and queues.
3. Job Script & Manifest Generation: generation of submission scripts with resource bounds, walltime, and auto-retry policies.
4. Job Lifecycle & Dispatching: submission, monitoring, status normalization, and cancellation.
5. Post-Mortem Diagnostics: exit code analysis (e.g. OOM killer 137, SIGTERM 143, timeout) with actionable biological remedies.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union


class SchedulerType(str, Enum):
    """Supported HPC and Cloud Batch schedulers."""

    SLURM = "slurm"
    PBS = "pbs"
    LSF = "lsf"
    SGE = "sge"
    KUBERNETES = "kubernetes"
    AWS_BATCH = "aws_batch"
    GCP_BATCH = "gcp_batch"
    LOCAL = "local"


class JobState(str, Enum):
    """Normalized job execution state across heterogenous schedulers."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    TIMEOUT = "TIMEOUT"
    UNKNOWN = "UNKNOWN"


@dataclass
class JobResourceConfig:
    """Resource specifications for HPC and Cloud jobs."""

    job_name: str = "bionexus_job"
    cpus: int = 8
    memory: str = "32GB"
    time_limit: str = "24:00:00"  # HH:MM:SS
    partition: Optional[str] = None  # Queue / partition / nodegroup
    account: Optional[str] = None  # Allocation / project account
    qos: Optional[str] = None  # Quality of service
    gpus: int = 0  # GPU count
    gpu_type: Optional[str] = None  # e.g., 'a100', 'v100', 'h100'
    container_image: Optional[str] = None  # Docker/Singularity image
    container_engine: str = "singularity"  # 'singularity' | 'apptainer' | 'docker'
    workdir: Optional[str] = None
    output_log: Optional[str] = None
    error_log: Optional[str] = None
    email: Optional[str] = None
    email_events: str = "FAIL,END"
    modules_to_load: List[str] = field(default_factory=list)
    env_vars: Dict[str, str] = field(default_factory=dict)
    auto_retry_oom: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ==============================================================================
# Cluster Environment Prober
# ==============================================================================


@dataclass
class ClusterEnvironmentReport:
    """Diagnostic report on host HPC and cloud cluster tooling."""

    available_schedulers: List[str] = field(default_factory=list)
    default_scheduler: str = "local"
    has_slurm: bool = False
    has_pbs: bool = False
    has_lsf: bool = False
    has_sge: bool = False
    has_kubernetes: bool = False
    has_aws_cli: bool = False
    has_gcp_cli: bool = False
    has_singularity: bool = False
    has_docker: bool = False
    has_gpus: bool = False
    gpu_count: int = 0
    gpu_devices: List[str] = field(default_factory=list)
    system_cores: int = 1
    system_ram_gb: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def probe_cluster_environment() -> ClusterEnvironmentReport:
    """Probe the local host environment to discover available HPC and Cloud tools."""
    report = ClusterEnvironmentReport()

    # Schedulers
    if shutil.which("sbatch") or shutil.which("squeue"):
        report.has_slurm = True
        report.available_schedulers.append("slurm")

    if shutil.which("qsub") and not report.has_slurm:
        # Check if PBS or SGE
        try:
            res = subprocess.run(["qsub", "--version"], capture_output=True, text=True, timeout=2)
            if "pbs" in (res.stdout + res.stderr).lower():
                report.has_pbs = True
                report.available_schedulers.append("pbs")
            else:
                report.has_sge = True
                report.available_schedulers.append("sge")
        except Exception:
            report.has_pbs = True
            report.available_schedulers.append("pbs")

    if shutil.which("bsub") or shutil.which("bjobs"):
        report.has_lsf = True
        report.available_schedulers.append("lsf")

    if shutil.which("kubectl"):
        report.has_kubernetes = True
        report.available_schedulers.append("kubernetes")

    if shutil.which("aws"):
        report.has_aws_cli = True
        report.available_schedulers.append("aws_batch")

    if shutil.which("gcloud"):
        report.has_gcp_cli = True
        report.available_schedulers.append("gcp_batch")

    if report.available_schedulers:
        report.default_scheduler = report.available_schedulers[0]
    else:
        report.default_scheduler = "local"

    # Container engines
    report.has_singularity = bool(shutil.which("singularity") or shutil.which("apptainer"))
    report.has_docker = bool(shutil.which("docker"))

    # System resources
    try:
        report.system_cores = os.cpu_count() or 1
    except Exception:
        report.system_cores = 1

    try:
        import psutil

        report.system_ram_gb = round(psutil.virtual_memory().total / (1024**3), 2)
    except Exception:
        report.system_ram_gb = 0.0

    # GPU probe
    if shutil.which("nvidia-smi"):
        try:
            res = subprocess.run(
                ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                capture_output=True,
                text=True,
                timeout=3,
            )
            if res.returncode == 0 and res.stdout.strip():
                gpus = [line.strip() for line in res.stdout.strip().split("\n") if line.strip()]
                report.has_gpus = len(gpus) > 0
                report.gpu_count = len(gpus)
                report.gpu_devices = gpus
        except Exception:
            pass

    return report


# ==============================================================================
# Job Script & Manifest Generators
# ==============================================================================


def generate_slurm_script(
    command: str,
    resources: JobResourceConfig,
    header_comment: str = "BioNexus Automated Slurm Job",
) -> str:
    """Generate a high-reliability Slurm submission bash script."""
    out_log = resources.output_log or f"{resources.job_name}_%j.out"
    err_log = resources.error_log or f"{resources.job_name}_%j.err"

    lines = [
        "#!/usr/bin/env bash",
        f"# ==============================================================================",
        f"# {header_comment}",
        f"# Generated by BioNexus High-Performance Computing Layer",
        f"# ==============================================================================",
        f"#SBATCH --job-name={resources.job_name}",
        f"#SBATCH --cpus-per-task={resources.cpus}",
        f"#SBATCH --mem={resources.memory}",
        f"#SBATCH --time={resources.time_limit}",
        f"#SBATCH --output={out_log}",
        f"#SBATCH --error={err_log}",
    ]

    if resources.partition:
        lines.append(f"#SBATCH --partition={resources.partition}")
    if resources.account:
        lines.append(f"#SBATCH --account={resources.account}")
    if resources.qos:
        lines.append(f"#SBATCH --qos={resources.qos}")
    if resources.workdir:
        lines.append(f"#SBATCH --chdir={resources.workdir}")
    if resources.email:
        lines.append(f"#SBATCH --mail-user={resources.email}")
        lines.append(f"#SBATCH --mail-type={resources.email_events}")

    if resources.gpus > 0:
        if resources.gpu_type:
            lines.append(f"#SBATCH --gres=gpu:{resources.gpu_type}:{resources.gpus}")
        else:
            lines.append(f"#SBATCH --gres=gpu:{resources.gpus}")

    lines.extend([
        "",
        "# Fail-closed bash safety options",
        "set -euo pipefail",
        "",
        "# Logging environment and node metadata for reproducibility",
        "echo \"=== BioNexus Job Execution ===\"",
        "echo \"JobID:       ${SLURM_JOB_ID:-N/A}\"",
        "echo \"Node:        $(hostname)\"",
        "echo \"CPUs:        ${SLURM_CPUS_PER_TASK:-1}\"",
        "echo \"Start Time:  $(date -u +'%Y-%m-%dT%H:%M:%SZ')\"",
        "echo \"==============================\"",
        "",
    ])

    # Environment variables
    if resources.env_vars:
        lines.append("# User-defined Environment Variables")
        for k, v in resources.env_vars.items():
            lines.append(f"export {k}=\"{v}\"")
        lines.append("")

    # Modules
    if resources.modules_to_load:
        lines.append("# Module loading")
        for mod in resources.modules_to_load:
            lines.append(f"module load {mod}")
        lines.append("")

    # Execution payload
    lines.append("# Main Command Execution")
    lines.append(command)
    lines.append("")
    lines.append("echo \"Job finished successfully at $(date -u +'%Y-%m-%dT%H:%M:%SZ')\"")

    return "\n".join(lines) + "\n"


def generate_pbs_script(
    command: str,
    resources: JobResourceConfig,
    header_comment: str = "BioNexus Automated PBS Job",
) -> str:
    """Generate a PBS/Torque batch submission script."""
    out_log = resources.output_log or f"{resources.job_name}.o"
    err_log = resources.error_log or f"{resources.job_name}.e"

    lines = [
        "#!/usr/bin/env bash",
        f"# ==============================================================================",
        f"# {header_comment}",
        f"# Generated by BioNexus High-Performance Computing Layer",
        f"# ==============================================================================",
        f"#PBS -N {resources.job_name}",
        f"#PBS -l select=1:ncpus={resources.cpus}:mem={resources.memory}",
        f"#PBS -l walltime={resources.time_limit}",
        f"#PBS -o {out_log}",
        f"#PBS -e {err_log}",
    ]

    if resources.partition:
        lines.append(f"#PBS -q {resources.partition}")
    if resources.account:
        lines.append(f"#PBS -A {resources.account}")
    if resources.email:
        lines.append(f"#PBS -M {resources.email}")
        lines.append(f"#PBS -m abe")

    lines.extend([
        "",
        "set -euo pipefail",
        "cd ${PBS_O_WORKDIR:-$PWD}",
        "",
        "# Main Command Execution",
        command,
        "",
    ])
    return "\n".join(lines) + "\n"


def generate_lsf_script(
    command: str,
    resources: JobResourceConfig,
    header_comment: str = "BioNexus Automated LSF Job",
) -> str:
    """Generate an IBM Spectrum LSF batch submission script."""
    out_log = resources.output_log or f"{resources.job_name}_%J.out"
    err_log = resources.error_log or f"{resources.job_name}_%J.err"

    lines = [
        "#!/usr/bin/env bash",
        f"# ==============================================================================",
        f"# {header_comment}",
        f"# Generated by BioNexus High-Performance Computing Layer",
        f"# ==============================================================================",
        f"#BSUB -J {resources.job_name}",
        f"#BSUB -n {resources.cpus}",
        f"#BSUB -M {resources.memory}",
        f"#BSUB -W {resources.time_limit[:5]}",  # LSF expects HH:MM
        f"#BSUB -o {out_log}",
        f"#BSUB -e {err_log}",
    ]

    if resources.partition:
        lines.append(f"#BSUB -q {resources.partition}")
    if resources.account:
        lines.append(f"#BSUB -P {resources.account}")

    lines.extend([
        "",
        "set -euo pipefail",
        "",
        "# Main Command Execution",
        command,
        "",
    ])
    return "\n".join(lines) + "\n"


def generate_k8s_job_yaml(
    command: List[str],
    resources: JobResourceConfig,
    image: Optional[str] = None,
    namespace: str = "default",
    pvc_claim_name: Optional[str] = None,
    mount_path: str = "/data",
) -> str:
    """Generate a production-ready Kubernetes Batch Job YAML manifest."""
    img = image or resources.container_image or "bionexus/bioinformatics:latest"
    cpu_str = str(resources.cpus)
    mem_str = resources.memory.replace("GB", "Gi").replace("MB", "Mi")

    job_dict: Dict[str, Any] = {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {
            "name": re.sub(r"[^a-z0-9\-]", "-", resources.job_name.lower())[:63],
            "namespace": namespace,
            "labels": {
                "app.kubernetes.io/managed-by": "bionexus",
                "bionexus.io/job-type": "computational-biology",
            },
        },
        "spec": {
            "backoffLimit": 2 if resources.auto_retry_oom else 0,
            "template": {
                "metadata": {
                    "labels": {
                        "job-name": resources.job_name.lower(),
                    }
                },
                "spec": {
                    "restartPolicy": "Never",
                    "containers": [
                        {
                            "name": "worker",
                            "image": img,
                            "command": command if isinstance(command, list) else ["/bin/sh", "-c", command],
                            "resources": {
                                "requests": {
                                    "cpu": cpu_str,
                                    "memory": mem_str,
                                },
                                "limits": {
                                    "cpu": cpu_str,
                                    "memory": mem_str,
                                },
                            },
                        }
                    ],
                },
            },
        },
    }

    if resources.gpus > 0:
        job_dict["spec"]["template"]["spec"]["containers"][0]["resources"]["limits"]["nvidia.com/gpu"] = str(resources.gpus)

    if pvc_claim_name:
        job_dict["spec"]["template"]["spec"]["volumes"] = [
            {
                "name": "data-volume",
                "persistentVolumeClaim": {"claimName": pvc_claim_name},
            }
        ]
        job_dict["spec"]["template"]["spec"]["containers"][0]["volumeMounts"] = [
            {
                "name": "data-volume",
                "mountPath": mount_path,
            }
        ]

    # Convert to clean formatted JSON/YAML-like text
    return json.dumps(job_dict, indent=2)


def generate_aws_batch_job(
    command: List[str],
    job_queue: str,
    job_definition: str,
    resources: JobResourceConfig,
) -> Dict[str, Any]:
    """Generate AWS Batch submit-job JSON payload."""
    payload: Dict[str, Any] = {
        "jobName": re.sub(r"[^a-zA-Z0-9_\-]", "-", resources.job_name)[:128],
        "jobQueue": job_queue,
        "jobDefinition": job_definition,
        "containerOverrides": {
            "command": command if isinstance(command, list) else ["/bin/sh", "-c", command],
            "resourceRequirements": [
                {"type": "VCPU", "value": str(resources.cpus)},
                {"type": "MEMORY", "value": str(int(resources.memory.replace("GB", "").replace("G", "")) * 1024)},
            ],
        },
    }
    if resources.gpus > 0:
        payload["containerOverrides"]["resourceRequirements"].append(
            {"type": "GPU", "value": str(resources.gpus)}
        )
    return payload


def generate_gcp_batch_job(
    command: str,
    project: str,
    region: str,
    resources: JobResourceConfig,
    image_uri: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate Google Cloud Batch job descriptor JSON."""
    img = image_uri or resources.container_image or "ubuntu:22.04"
    mem_mib = int(resources.memory.replace("GB", "").replace("G", "")) * 1024

    return {
        "taskGroups": [
            {
                "taskSpec": {
                    "runnables": [
                        {
                            "container": {
                                "imageUri": img,
                                "commands": ["/bin/sh", "-c", command],
                            }
                        }
                    ],
                    "computeResource": {
                        "cpuMilli": resources.cpus * 1000,
                        "memoryMib": mem_mib,
                    },
                },
                "taskCount": 1,
            }
        ],
        "allocationPolicy": {
            "location": {"allowedLocations": [f"regions/{region}"]},
        },
    }


def _normalize_scheduler(scheduler: Union[SchedulerType, str]) -> str:
    """Normalize scheduler enum or string to canonical lowercase identifier."""
    val = scheduler.value if hasattr(scheduler, "value") else str(scheduler)
    return str(val).lower().replace("-", "_")


def generate_job_script(
    scheduler: Union[SchedulerType, str],
    command: Union[str, List[str]],
    resources: Optional[JobResourceConfig] = None,
    **kwargs: Any,
) -> str:
    """Unified dispatcher to generate job scripts across all supported schedulers."""
    res = resources or JobResourceConfig()
    sched = _normalize_scheduler(scheduler)

    cmd_str = command if isinstance(command, str) else " ".join(command)
    cmd_list = command if isinstance(command, list) else ["/bin/sh", "-c", command]

    if sched in ("slurm", "sbatch"):
        return generate_slurm_script(cmd_str, res, **kwargs)
    elif sched in ("pbs", "torque"):
        return generate_pbs_script(cmd_str, res, **kwargs)
    elif sched in ("lsf", "bsub"):
        return generate_lsf_script(cmd_str, res, **kwargs)
    elif sched in ("kubernetes", "k8s"):
        return generate_k8s_job_yaml(cmd_list, res, **kwargs)
    elif sched in ("aws", "aws_batch"):
        queue = kwargs.get("job_queue", "arn:aws:batch:default-queue")
        job_def = kwargs.get("job_definition", "bionexus-job-def")
        return json.dumps(generate_aws_batch_job(cmd_list, queue, job_def, res), indent=2)
    elif sched in ("gcp", "google", "gcp_batch"):
        project = kwargs.get("project", "default-project")
        region = kwargs.get("region", "us-central1")
        return json.dumps(generate_gcp_batch_job(cmd_str, project, region, res), indent=2)
    else:
        # Default fallback: self-contained robust local script
        return (
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            f"# BioNexus Local Background Execution Wrapper for {res.job_name}\n"
            f"echo \"Starting {res.job_name} on $(hostname)...\"\n"
            f"{cmd_str}\n"
            f"echo \"Completed at $(date)\"\n"
        )


# ==============================================================================
# Job Dispatch & Lifecycle Management
# ==============================================================================


@dataclass
class JobSubmissionResult:
    """Result of dispatching a job to a scheduler."""

    success: bool
    job_id: Optional[str] = None
    scheduler: str = "local"
    submission_command: str = ""
    message: str = ""
    script_path: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def submit_job(
    script_path: Union[str, Path],
    scheduler: Union[SchedulerType, str] = SchedulerType.SLURM,
    dry_run: bool = False,
) -> JobSubmissionResult:
    """
    Submit a prepared script file to the target scheduler.
    Extracts the newly generated Job ID in a fail-closed manner.
    """
    p = Path(script_path)
    sched = _normalize_scheduler(scheduler)

    if not p.is_file():
        return JobSubmissionResult(
            success=False,
            scheduler=sched,
            message=f"Script file '{script_path}' not found.",
        )

    if sched == "slurm":
        submit_cmd = ["sbatch", str(p.resolve())]
    elif sched == "pbs":
        submit_cmd = ["qsub", str(p.resolve())]
    elif sched == "lsf":
        submit_cmd = ["bsub", "<", str(p.resolve())]
    elif sched in ("kubernetes", "k8s"):
        submit_cmd = ["kubectl", "apply", "-f", str(p.resolve())]
    else:
        submit_cmd = ["bash", str(p.resolve())]

    if dry_run:
        return JobSubmissionResult(
            success=True,
            job_id="DRY_RUN_ID_12345",
            scheduler=sched,
            submission_command=" ".join(submit_cmd),
            message="Dry run submission verified successfully without execution.",
            script_path=str(p.resolve()),
        )

    binary = submit_cmd[0]
    if not shutil.which(binary):
        return JobSubmissionResult(
            success=False,
            scheduler=sched,
            submission_command=" ".join(submit_cmd),
            message=f"Scheduler binary '{binary}' is not installed or not in PATH.",
            script_path=str(p.resolve()),
        )

    try:
        res = subprocess.run(
            submit_cmd if sched != "lsf" else f"bsub < {p.resolve()}",
            shell=(sched == "lsf"),
            capture_output=True,
            text=True,
            timeout=30,
        )
        out = (res.stdout or "") + (res.stderr or "")

        if res.returncode != 0:
            return JobSubmissionResult(
                success=False,
                scheduler=sched,
                submission_command=" ".join(submit_cmd),
                message=f"Submission failed (code {res.returncode}): {out.strip()}",
                script_path=str(p.resolve()),
            )

        # Parse Job ID
        job_id = None
        if sched == "slurm":
            m = re.search(r"Submitted batch job (\d+)", out)
            if m:
                job_id = m.group(1)
        elif sched == "pbs":
            m = re.search(r"^(\d+(\.[a-zA-Z0-9_\-]+)?)", out.strip())
            if m:
                job_id = m.group(1)
        elif sched == "lsf":
            m = re.search(r"Job <(\d+)> is submitted", out)
            if m:
                job_id = m.group(1)

        return JobSubmissionResult(
            success=True,
            job_id=job_id or out.strip().split()[-1] if out.strip() else "UNKNOWN_ID",
            scheduler=sched,
            submission_command=" ".join(submit_cmd),
            message="Job successfully submitted to cluster queue.",
            script_path=str(p.resolve()),
        )

    except Exception as e:
        return JobSubmissionResult(
            success=False,
            scheduler=sched,
            submission_command=" ".join(submit_cmd),
            message=f"Submission exception: {str(e)}",
            script_path=str(p.resolve()),
        )


def get_job_status(
    job_id: str,
    scheduler: Union[SchedulerType, str] = SchedulerType.SLURM,
) -> Tuple[JobState, str]:
    """Query current status of an HPC / cloud job."""
    sched = _normalize_scheduler(scheduler)

    if sched == "slurm":
        if not shutil.which("squeue"):
            return JobState.UNKNOWN, "squeue not available"
        try:
            res = subprocess.run(
                ["squeue", "-j", str(job_id), "-h", "-o", "%T"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            state_str = res.stdout.strip().upper()
            if not state_str:
                if shutil.which("sacct"):
                    res_acct = subprocess.run(
                        ["sacct", "-j", str(job_id), "-n", "-P", "-o", "State"],
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    acct_state = res_acct.stdout.strip().split("\n")[0].upper()
                    if "COMPLETED" in acct_state:
                        return JobState.COMPLETED, "Job finished successfully"
                    elif "OUT_OF_MEMORY" in acct_state or "OOM" in acct_state:
                        return JobState.FAILED, "Job killed due to Out-Of-Memory (OOM)"
                    elif "FAILED" in acct_state:
                        return JobState.FAILED, "Job exited with failure"
                    elif "CANCELLED" in acct_state:
                        return JobState.CANCELLED, "Job was cancelled"
                    elif "TIMEOUT" in acct_state:
                        return JobState.TIMEOUT, "Job exceeded walltime limit"
                return JobState.COMPLETED, "Job no longer in queue"

            if state_str in ("RUNNING", "R"):
                return JobState.RUNNING, "Job is actively running"
            elif state_str in ("PENDING", "PD", "CONFIGURING", "CF"):
                return JobState.PENDING, "Job is queued and waiting for resources"
            elif state_str in ("COMPLETED", "CD"):
                return JobState.COMPLETED, "Job finished successfully"
            elif state_str in ("FAILED", "F", "NODE_FAIL", "NF"):
                return JobState.FAILED, "Job failed"
            elif state_str in ("CANCELLED", "CA"):
                return JobState.CANCELLED, "Job cancelled"
            elif state_str in ("TIMEOUT", "TO"):
                return JobState.TIMEOUT, "Job timed out"
            return JobState.UNKNOWN, f"Unknown Slurm state: {state_str}"
        except Exception as e:
            return JobState.UNKNOWN, str(e)

    return JobState.UNKNOWN, f"Status check not implemented for scheduler '{sched}'"


# ==============================================================================
# Post-Mortem Diagnostics & OOM Analysis
# ==============================================================================


@dataclass
class JobDiagnostic:
    """Post-mortem scientific diagnosis of an HPC or batch run failure."""

    exit_code: int
    primary_cause: str
    remedy: str
    is_oom: bool = False
    is_timeout: bool = False
    is_permission_error: bool = False
    suggested_resource_adjustment: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def diagnose_job_failure(
    exit_code: int,
    log_content: str = "",
    current_memory_gb: float = 32.0,
    current_cpus: int = 8,
) -> JobDiagnostic:
    """
    Analyze job exit codes and logs to identify root causes and recommend actionable remedies.
    Detects Linux signal exits (137 = SIGKILL / OOM, 143 = SIGTERM / Slurm Scancel, 127 = command not found).
    """
    log_lower = log_content.lower()

    if exit_code in (137, 134) or "out of memory" in log_lower or "oom-killer" in log_lower or "memory cgroup out of memory" in log_lower:
        escalated_mem = round(current_memory_gb * 2.0, 1)
        return JobDiagnostic(
            exit_code=exit_code,
            primary_cause="Process terminated by Linux OOM-Killer (Out of Memory).",
            remedy=f"Double allocated memory from {current_memory_gb}GB to {escalated_mem}GB, or enable out-of-core chunked processing (bionexus bigdata).",
            is_oom=True,
            suggested_resource_adjustment={"memory": f"{int(escalated_mem)}GB"},
        )

    if exit_code in (140, 143) or "time limit exceeded" in log_lower or "due to time limit" in log_lower:
        return JobDiagnostic(
            exit_code=exit_code,
            primary_cause="Job exceeded allocated walltime limit and was terminated.",
            remedy="Increase --time limit by 2-3x and verify data storage I/O throughput.",
            is_timeout=True,
            suggested_resource_adjustment={"time_limit": "48:00:00"},
        )

    if exit_code == 127 or "command not found" in log_lower:
        return JobDiagnostic(
            exit_code=exit_code,
            primary_cause="Required executable or bioinformatics binary was not found in PATH on the worker node.",
            remedy="Ensure required modules are loaded in the script header (e.g. 'module load singularity') or execute inside a container.",
            is_permission_error=False,
        )

    if exit_code == 126 or "permission denied" in log_lower:
        return JobDiagnostic(
            exit_code=exit_code,
            primary_cause="Execution permission denied on the script or working directory.",
            remedy="Ensure chmod +x is granted on the script and worker node has write permissions to workdir.",
            is_permission_error=True,
        )

    return JobDiagnostic(
        exit_code=exit_code,
        primary_cause=f"Job exited with non-zero exit code {exit_code}.",
        remedy="Inspect worker node stderr log tail for specific traceback details.",
    )
