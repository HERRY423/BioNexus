"""
Registry, lookup, and query interface for BioNexus Capabilities.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from bionexus.capability_catalog.definitions.canonical import CANONICAL_CAPABILITIES
from bionexus.capability_catalog.definitions.frontier import FRONTIER_CAPABILITIES
from bionexus.capability_catalog.models import (
    CapabilityContract,
    CapabilityEvaluationResult,
)

ALL_CAPABILITIES: Dict[str, CapabilityContract] = {
    **CANONICAL_CAPABILITIES,
    **FRONTIER_CAPABILITIES,
}

def get_capability(capability_id: str, include_frontier: bool = True) -> CapabilityContract:
    """Retrieve capability contract by ID."""
    registry = ALL_CAPABILITIES if include_frontier else CANONICAL_CAPABILITIES
    if capability_id not in registry:
        raise KeyError(f"Unknown capability contract ID: '{capability_id}'. Available: {list(registry.keys())}")
    return registry[capability_id]


def list_capabilities(
    intent: Optional[str] = None,
    skill_name: Optional[str] = None,
    include_frontier: bool = True,
) -> List[CapabilityContract]:
    """Filter and list capability contracts by intent or skill."""
    registry = ALL_CAPABILITIES if include_frontier else CANONICAL_CAPABILITIES
    caps = list(registry.values())
    if skill_name:
        caps = [c for c in caps if c.skill_name == skill_name]
    if intent:
        caps = [c for c in caps if intent in c.intent]
    return caps


def find_capabilities_by_intent(intent: str, include_frontier: bool = True) -> List[CapabilityContract]:
    """Find capabilities matching a specific scientific intent."""
    return list_capabilities(intent=intent, include_frontier=include_frontier)


def evaluate_capability_preconditions(
    capability_id: str,
    *,
    input_metadata: Optional[Dict[str, Any]] = None,
    context: Optional[Dict[str, Any]] = None,
) -> CapabilityEvaluationResult:
    """
    Evaluate whether a planned analysis satisfies all scientific preconditions.
    """
    contract = get_capability(capability_id)
    return contract.evaluate_viability(
        input_metadata=input_metadata,
        context=context,
    )

