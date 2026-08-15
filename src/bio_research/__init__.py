"""Bio-research plugin kernel: contracts, backend probes, I/O, provenance."""

from .agent_routing import DEFAULT_SKILLS, LEGACY_SKILLS, is_default_skill
from .backends import BackendUnavailable, is_available, probe, probe_all, require
from .contracts import (
    ABSTAIN,
    GRADE_A,
    GRADE_B,
    GRADE_C,
    RESEARCH_USE_ONLY,
    EvidenceGrade,
    attach_meta,
    refuse,
)
from .doctor import run_doctor
from .gate import DoctorGateError, require_doctor, write_doctor_report
from .inventory import SKILLS, as_markdown_table, core_skills, get_skill
from .pipeline_config import load_pipeline_config, merge_config
from .provenance import capture_environment, sha256_file, sidecar
from .versions import PINS, PITFALLS, PLUGIN_VERSION

__version__ = PLUGIN_VERSION

__all__ = [
    "ABSTAIN",
    "GRADE_A",
    "GRADE_B",
    "GRADE_C",
    "RESEARCH_USE_ONLY",
    "BackendUnavailable",
    "EvidenceGrade",
    "DEFAULT_SKILLS",
    "LEGACY_SKILLS",
    "SKILLS",
    "PINS",
    "PITFALLS",
    "__version__",
    "as_markdown_table",
    "attach_meta",
    "core_skills",
    "run_doctor",
    "require_doctor",
    "DoctorGateError",
    "write_doctor_report",
    "capture_environment",
    "get_skill",
    "is_available",
    "is_default_skill",
    "load_pipeline_config",
    "merge_config",
    "probe",
    "probe_all",
    "refuse",
    "require",
    "sha256_file",
    "sidecar",
]
