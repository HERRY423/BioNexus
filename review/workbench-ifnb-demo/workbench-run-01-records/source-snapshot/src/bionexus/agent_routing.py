"""Default-visible skills. Heuristics live in-tree but are not default routes."""

from __future__ import annotations

from pathlib import Path
from typing import FrozenSet, Union

DEFAULT_SKILLS: FrozenSet[str] = frozenset(
    {
        "start",
        "scientific-problem-selection",
        "single-cell-rna-qc",
        "scvi-tools",
        "nextflow-development",
        "instrument-data-to-allotrope",
        "provenance-and-audit",
        "external-evidence-audit",
        "spatial-transcriptomics",
    }
)

LEGACY_SKILLS: FrozenSet[str] = frozenset(
    {
        "biologics-design",
        "protein-language-models",
        "clinical-cohort-analysis",
        "variant-interpretation",
        "protein-structure-analysis",
        "multiome-integration",
        "experiment-design-agent",
        "research-workflow-orchestrator",
        "knowledge-graph-augmentation",
    }
)


def is_default_skill(name: str) -> bool:
    return name in DEFAULT_SKILLS


def discoverable_skill_names(skills_root: Union[str, Path]) -> FrozenSet[str]:
    """Skill directories that still expose SKILL.md (agent auto-discovery)."""
    root = Path(skills_root)
    return frozenset(p.parent.name for p in root.glob("*/SKILL.md") if p.is_file())


# Re-export Scientific Intent Routing API
from bionexus.intent_router import (  # noqa: E402
    RoutingDecision,
    RoutingStatus,
    ScientificIntentRequest,
    extract_scientific_capability,
    route_scientific_intent,
)

__all__ = [
    "DEFAULT_SKILLS",
    "LEGACY_SKILLS",
    "RoutingDecision",
    "RoutingStatus",
    "ScientificIntentRequest",
    "discoverable_skill_names",
    "extract_scientific_capability",
    "is_default_skill",
    "route_scientific_intent",
]
