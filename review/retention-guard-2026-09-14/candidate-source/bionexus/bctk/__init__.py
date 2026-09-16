"""
BioNexus Conformance Test Kit (BCTK).

Target-bound development diagnostics. Certification and badging are suspended.
"""

from bionexus.bctk.engine import BCTK_VERSION, run_conformance_test
from bionexus.bctk.reporters import (
    BadgeIssuanceSuspended,
    generate_svg_badge,
    render_markdown_report,
    render_terminal_report,
)
from bionexus.bctk.spec import (
    BCTK_RULE_CATALOG,
    ConformanceDimension,
    ConformanceReport,
    ConformanceTier,
    DimensionResult,
    DimensionStatus,
    RuleDefinition,
    RuleEvaluation,
    RuleSeverity,
)
from bionexus.bctk.targets import TargetDescriptor, TargetSnapshot, TargetType, detect_target, snapshot_target

__all__ = [
    "BCTK_VERSION",
    "run_conformance_test",
    "detect_target",
    "render_terminal_report",
    "render_markdown_report",
    "generate_svg_badge",
    "BadgeIssuanceSuspended",
    "ConformanceReport",
    "ConformanceTier",
    "ConformanceDimension",
    "DimensionStatus",
    "DimensionResult",
    "RuleEvaluation",
    "RuleDefinition",
    "RuleSeverity",
    "BCTK_RULE_CATALOG",
    "TargetDescriptor",
    "TargetType",
    "TargetSnapshot",
    "snapshot_target",
]
