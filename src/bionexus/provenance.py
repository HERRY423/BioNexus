"""Lightweight SHA-256 + environment snapshot. Not a GxP / 21 CFR 11 system."""

from __future__ import annotations

import hashlib
import importlib.metadata
import platform
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
        "compliance_note": (
            "SHA-256 + package versions for reproducibility. "
            "This is not 21 CFR Part 11, GxP, ALCOA+, or CLIA audit evidence."
        ),
    }
