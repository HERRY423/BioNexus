"""Single import surface for skill scripts.

Scripts should `from bionexus.skill_runtime import attach_meta, is_available`
after ensuring `src/` is on sys.path (see ensure_src_on_path).
"""

from __future__ import annotations

import sys
from pathlib import Path

from .backends import BackendUnavailable, is_available, probe, require
from .contracts import (
    ABSTAIN,
    GRADE_A,
    GRADE_B,
    GRADE_C,
    RESEARCH_USE_ONLY,
    attach_meta,
    refuse,
)
from .doctor import run_doctor
from .inventory import SKILLS, get_skill
from .provenance import sidecar


def ensure_src_on_path(start: Path | None = None) -> Path | None:
    """Walk parents until src/bionexus is found and prepend it to sys.path."""
    here = start or Path(__file__).resolve()
    for parent in [here, *here.parents] if here.is_file() else [here, *here.parents]:
        src = parent / "src" if parent.name != "src" else parent
        if (src / "bionexus" / "__init__.py").exists():
            path = str(src)
            if path not in sys.path:
                sys.path.insert(0, path)
            return src
        candidate = parent / "src"
        if (candidate / "bionexus" / "__init__.py").exists():
            path = str(candidate)
            if path not in sys.path:
                sys.path.insert(0, path)
            return candidate
    return None


__all__ = [
    "ABSTAIN",
    "GRADE_A",
    "GRADE_B",
    "GRADE_C",
    "RESEARCH_USE_ONLY",
    "BackendUnavailable",
    "SKILLS",
    "attach_meta",
    "ensure_src_on_path",
    "get_skill",
    "is_available",
    "probe",
    "refuse",
    "require",
    "run_doctor",
    "sidecar",
]
