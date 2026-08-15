"""Import the plugin kernel from src/ regardless of cwd."""

from __future__ import annotations

import sys
from pathlib import Path


def _ensure_kernel() -> None:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "src"
        if (candidate / "bionexus" / "__init__.py").exists():
            path = str(candidate)
            if path not in sys.path:
                sys.path.insert(0, path)
            return


_ensure_kernel()

from bionexus.backends import is_available, probe  # noqa: E402
from bionexus.contracts import (  # noqa: E402
    ABSTAIN,
    GRADE_A,
    GRADE_B,
    GRADE_C,
    attach_meta,
    refuse,
)
from bionexus.gate import require_doctor  # noqa: E402
from bionexus.pipeline_config import load_pipeline_config, merge_config  # noqa: E402


def add_skip_doctor(parser) -> None:
    parser.add_argument(
        "--skip-doctor",
        action="store_true",
        help="Do not fail closed on a stale/missing doctor report (tests and explicit override).",
    )


def gate_scverse(*, skip: bool = False):
    return require_doctor(require_scverse=True, skip=skip)


__all__ = [
    "ABSTAIN",
    "GRADE_A",
    "GRADE_B",
    "GRADE_C",
    "add_skip_doctor",
    "attach_meta",
    "gate_scverse",
    "is_available",
    "load_pipeline_config",
    "merge_config",
    "probe",
    "refuse",
    "require_doctor",
]
