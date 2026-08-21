"""Lightweight SHA-256 + environment snapshot. Not a GxP / 21 CFR 11 system."""

from __future__ import annotations

import hashlib
import importlib.metadata
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Union

PathLike = Union[str, Path]

KEY_PACKAGES = (
    "numpy",
    "scipy",
    "pandas",
    "scanpy",
    "anndata",
    "torch",
    "scvi-tools",
    "optuna",
    "allotropy",
    "polars",
    "lifelines",
    "squidpy",
    "pydeseq2",
    "abnumber",
    "biotite",
    "scikit-learn",
)


def sha256_file(path: PathLike) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while True:
            chunk = handle.read(65536)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def package_version(name: str) -> Optional[str]:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def capture_environment() -> Dict[str, Any]:
    packages = {}
    for name in KEY_PACKAGES:
        version = package_version(name)
        if version:
            packages[name] = version
    snapshot: Dict[str, Any] = {
        "os_name": platform.system(),
        "os_release": platform.release(),
        "os_version": platform.version(),
        "architecture": platform.machine(),
        "python_version": sys.version.split()[0],
        "python_executable": sys.executable,
        "packages": packages,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "cuda_available": False,
    }
    try:
        import torch

        snapshot["cuda_available"] = bool(torch.cuda.is_available())
        if snapshot["cuda_available"]:
            snapshot["cuda_device_count"] = torch.cuda.device_count()
            snapshot["cuda_device_name"] = torch.cuda.get_device_name(0)
            snapshot["cuda_version"] = torch.version.cuda
    except Exception:
        snapshot["cuda_available"] = False
    return snapshot


def get_git_info(repo_root: Optional[PathLike] = None) -> Dict[str, Any]:

    """Retrieve git commit SHA and dirty status safely."""
    commit = "unknown"
    dirty = False
    cwd = str(repo_root) if repo_root else None
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=5,
        )
        if res.returncode == 0:
            commit = res.stdout.strip()
    except Exception:
        pass

    try:
        res_status = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=5,
        )
        if res_status.returncode == 0:
            dirty = bool(res_status.stdout.strip())
    except Exception:
        pass

    return {"commit_sha": commit, "dirty": dirty}


def compute_lockfile_hash(repo_root: Optional[PathLike] = None) -> Dict[str, str]:
    """Compute sha256 hashes of repository environment / lock files."""
    root = Path(repo_root) if repo_root else Path(__file__).resolve().parents[2]
    candidate_files = [
        "pyproject.toml",
        "requirements-dev.txt",
        "requirements.txt",
        "poetry.lock",
        "Pipfile.lock",
    ]
    hashes: Dict[str, str] = {}
    for name in candidate_files:
        f = root / name
        if f.is_file():
            hashes[name] = sha256_file(f)
    return hashes


def capture_execution_provenance(
    *,
    data_source: str = "unknown",
    download_date: Optional[str] = None,
    repo_root: Optional[PathLike] = None,
    generator_version: Optional[str] = None,
    extra_metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Capture full runtime execution provenance for validation reports.

    Records:
    - Data source & download/generation date
    - Git commit SHA and dirty status
    - Environment lockfile / dependency file hashes
    - Full command line invocation (sys.argv)
    - Report generator / code version
    """
    git_info = get_git_info(repo_root)
    lock_hashes = compute_lockfile_hash(repo_root)

    if generator_version is None:
        try:
            from bionexus.versions import VERSION
            generator_version = VERSION
        except Exception:
            generator_version = "0.10.0"

    now_iso = datetime.now(timezone.utc).isoformat()
    return {
        "data_source": data_source,
        "download_date": download_date or now_iso,
        "commit_sha": git_info["commit_sha"],
        "git_dirty": git_info["dirty"],
        "environment_lockfile_hashes": lock_hashes,
        "command": sys.argv,
        "command_str": " ".join(sys.argv),
        "generator_version": generator_version,
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "timestamp": now_iso,
        "extra_metadata": extra_metadata or {},
    }


def sidecar(
    *,
    activity_name: str,
    input_files: Optional[Iterable[PathLike]] = None,
    output_files: Optional[Iterable[PathLike]] = None,
    parameters: Optional[Dict[str, Any]] = None,
    method: Optional[str] = None,
    backend: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a research-grade provenance sidecar. Not an electronic signature."""

    def _hash_existing(paths: Iterable[PathLike], role: str) -> List[Dict[str, Any]]:
        items = []
        for raw in paths:
            path = Path(raw)
            item = {
                "file_name": path.name,
                "path": str(path),
                "role": role,
            }
            if path.is_file():
                item["sha256"] = sha256_file(path)
            else:
                item["sha256"] = None
                item["missing"] = True
            items.append(item)
        return items

    return {
        "activity_name": activity_name,
        "method": method,
        "backend": backend,
        "parameters": dict(parameters or {}),
        "input_files": _hash_existing(input_files or [], "input"),
        "output_files": _hash_existing(output_files or [], "output"),
        "environment_snapshot": capture_environment(),
        "execution_provenance": capture_execution_provenance(),
        "compliance_note": (
            "SHA-256 + package versions for reproducibility. "
            "This is not 21 CFR Part 11, GxP, ALCOA+, or CLIA audit evidence."
        ),
    }
