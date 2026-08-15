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

__all__ = [
    "ABSTAIN",
    "GRADE_A",
    "GRADE_B",
    "GRADE_C",
    "attach_meta",
    "is_available",
    "probe",
    "refuse",
]
