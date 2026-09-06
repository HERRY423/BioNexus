"""Hard environment gate. Core CLIs should refuse when doctor says refuse."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, Optional, Union

from .doctor import run_doctor

PathLike = Union[str, Path]
DEFAULT_REPORT = ".bionexus-doctor.json"


class DoctorGateError(RuntimeError):
    """Raised when the gold chain must not start."""


def write_doctor_report(path: PathLike = DEFAULT_REPORT) -> Dict[str, Any]:
    report = run_doctor()
    report["generated_at_unix"] = time.time()
    dest = Path(path)
    dest.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    return report


def load_doctor_report(path: PathLike = DEFAULT_REPORT) -> Optional[Dict[str, Any]]:
    dest = Path(path)
    if not dest.is_file():
        return None
    return json.loads(dest.read_text(encoding="utf-8"))


def require_doctor(
    *,
    path: PathLike = DEFAULT_REPORT,
    require_scverse: bool = False,
    require_spatial: bool = False,
    max_age_seconds: float = 86400.0,
    skip: bool = False,
) -> Dict[str, Any]:
    """Return a fresh or cached doctor report, or raise DoctorGateError."""
    if skip:
        report = run_doctor()
        report["gate"] = "skipped"
        _enforce_ready(report, require_scverse=require_scverse, require_spatial=require_spatial)
        return report

    cached = load_doctor_report(path)
    now = time.time()
    if cached and (now - float(cached.get("generated_at_unix", 0))) <= max_age_seconds:
        report = cached
        report["gate"] = "cached"
    else:
        report = write_doctor_report(path)
        report["gate"] = "fresh"

    _enforce_ready(report, require_scverse=require_scverse, require_spatial=require_spatial)
    return report


def _enforce_ready(
    report: Dict[str, Any],
    *,
    require_scverse: bool,
    require_spatial: bool,
) -> None:
    if report.get("tier") == "refuse":
        raise DoctorGateError("doctor tier=refuse. Install core scientific Python deps and re-run scripts/doctor.py.")
    flags = report.get("ready") or report.get("flags") or {}
    scverse_ok = bool(flags.get("scverse_ready") or flags.get("scverse"))
    if require_scverse and not scverse_ok:
        raise DoctorGateError("scRNA gold chain requires scanpy+anndata. pip install 'bionexus[goldchain]'.")
    spatial_ok = bool(flags.get("spatial_ready") or flags.get("squidpy"))
    if require_spatial and not spatial_ok:
        raise DoctorGateError("spatial gold chain requires squidpy. pip install 'bionexus[spatial]'.")
