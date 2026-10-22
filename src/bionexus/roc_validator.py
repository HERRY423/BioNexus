"""Official RO-Crate validator wrapper (BNS-IO-010).

Handwritten JSON checks in ``interop.validate_ro_crate`` are a structural
precheck only. Profile compliance is established solely by the pinned
CRS4 ``roc-validator`` CLI (``rocrate-validator``). Absence of the CLI is
recorded as ``VALIDATOR_UNAVAILABLE``; it is never treated as a pass.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

logger = logging.getLogger(__name__)

PINNED_ROC_VALIDATOR_VERSION = "0.11.2"
ROC_VALIDATOR_PACKAGE = "roc-validator"
ROC_VALIDATOR_CLI = "rocrate-validator"
DEFAULT_PROFILE = "provenance-run-crate-0.5"

STATUS_VALIDATED = "THIRD_PARTY_TOOL_VALIDATED"
STATUS_PRECHECK = "STRUCTURAL_PRECHECK_ONLY"
STATUS_UNAVAILABLE = "VALIDATOR_UNAVAILABLE"
STATUS_FAILED = "FAILED"
STATUS_NOT_RUN = "NOT_RUN"

PathLike = Union[str, Path]


@dataclass(frozen=True)
class RocValidatorResult:
    """Outcome of one official ``rocrate-validator`` invocation."""

    available: bool
    ran: bool
    passed: bool
    status: str
    version: Optional[str] = None
    log: str = ""
    command: List[str] = field(default_factory=list)
    crate_path: str = ""
    profile: str = DEFAULT_PROFILE
    returncode: Optional[int] = None
    scope_note: str = (
        "Official CLI validation establishes technical profile conformance of "
        "this crate only; it is not certification, endorsement, or adoption."
    )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def discover_rocrate_validator() -> Optional[str]:
    """Return the ``rocrate-validator`` executable path, or None if absent."""
    found = shutil.which(ROC_VALIDATOR_CLI)
    return found


def _installed_package_version() -> Optional[str]:
    try:
        import importlib.metadata

        return importlib.metadata.version(ROC_VALIDATOR_PACKAGE)
    except Exception:
        return None


def _crate_dir(crate_path: Path) -> Path:
    if crate_path.is_dir():
        return crate_path
    if crate_path.is_file() and crate_path.name == "ro-crate-metadata.json":
        return crate_path.parent
    raise FileNotFoundError(f"RO-Crate directory or ro-crate-metadata.json not found: {crate_path}")


def _success_marker(profile: str) -> str:
    return f"RO-Crate is a valid {profile}"


def run_rocrate_validator(
    crate_path: PathLike,
    *,
    profile: str = DEFAULT_PROFILE,
    timeout: int = 120,
    require_pinned_version: bool = False,
    extra_args: Optional[Sequence[str]] = None,
) -> RocValidatorResult:
    """Run the official CLI against a crate directory.

    Never uses ``shell=True``. A missing CLI is ``VALIDATOR_UNAVAILABLE``,
    not a pass. ``require_pinned_version`` records a failure when the
    installed package is not ``PINNED_ROC_VALIDATOR_VERSION``.
    """
    crate = Path(crate_path)
    try:
        crate_dir = _crate_dir(crate)
    except FileNotFoundError as exc:
        return RocValidatorResult(
            available=False,
            ran=False,
            passed=False,
            status=STATUS_FAILED,
            log=str(exc),
            crate_path=str(crate),
            profile=profile,
        )

    cli = discover_rocrate_validator()
    version = _installed_package_version()
    if cli is None:
        return RocValidatorResult(
            available=False,
            ran=False,
            passed=False,
            status=STATUS_UNAVAILABLE,
            version=version,
            log=f"{ROC_VALIDATOR_CLI} is not on PATH",
            crate_path=str(crate_dir),
            profile=profile,
        )

    if require_pinned_version and version != PINNED_ROC_VALIDATOR_VERSION:
        return RocValidatorResult(
            available=True,
            ran=False,
            passed=False,
            status=STATUS_FAILED,
            version=version,
            log=(
                f"Expected {ROC_VALIDATOR_PACKAGE}=={PINNED_ROC_VALIDATOR_VERSION}, "
                f"found {version!r}"
            ),
            crate_path=str(crate_dir),
            profile=profile,
        )

    command = [
        cli,
        "--no-interactive",
        "--disable-color",
        "validate",
        "--profile-identifier",
        profile,
        "--requirement-severity",
        "required",
        "--output-format",
        "text",
        "--offline",
        str(crate_dir),
    ]
    if extra_args:
        command.extend(str(a) for a in extra_args)

    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except (UnicodeDecodeError, ValueError) as exc:
        logger.warning("rocrate-validator output was not decodable: %s", exc)
        return RocValidatorResult(
            available=True,
            ran=True,
            passed=False,
            status=STATUS_FAILED,
            version=version,
            log=f"validator output decode failed: {exc}",
            command=command,
            crate_path=str(crate_dir),
            profile=profile,
        )
    except subprocess.TimeoutExpired as exc:
        logger.warning("rocrate-validator timed out after %ss", timeout)
        return RocValidatorResult(
            available=True,
            ran=True,
            passed=False,
            status=STATUS_FAILED,
            version=version,
            log=f"timed out after {timeout}s: {exc}",
            command=command,
            crate_path=str(crate_dir),
            profile=profile,
        )
    except OSError as exc:
        logger.warning("rocrate-validator failed to start: %s", exc)
        return RocValidatorResult(
            available=True,
            ran=False,
            passed=False,
            status=STATUS_FAILED,
            version=version,
            log=str(exc),
            command=command,
            crate_path=str(crate_dir),
            profile=profile,
        )

    log_text = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
    marker_ok = _success_marker(profile) in log_text
    passed = proc.returncode == 0 and marker_ok
    return RocValidatorResult(
        available=True,
        ran=True,
        passed=passed,
        status=STATUS_VALIDATED if passed else STATUS_FAILED,
        version=version,
        log=log_text[-8000:],
        command=command,
        crate_path=str(crate_dir),
        profile=profile,
        returncode=int(proc.returncode),
    )
