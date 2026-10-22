"""
BioNexus Capability Catalog & Contract Specification (BNS-001).
Decoupled into models, static definitions (canonical, frontier), and registry query API.
"""

from bionexus.backends import probe
from bionexus.capability_catalog.definitions.canonical import CANONICAL_CAPABILITIES
from bionexus.capability_catalog.definitions.frontier import FRONTIER_CAPABILITIES
from bionexus.capability_catalog.models import (
    BackendRequirement,
    CapabilityContract,
    CapabilityEvaluationResult,
    EvidenceRequirement,
    InputSpecification,
    Precondition,
    RefusalTrigger,
    SemanticInputType,
)
from bionexus.capability_catalog.registry import (
    ALL_CAPABILITIES,
    evaluate_capability_preconditions,
    find_capabilities_by_intent,
    get_capability,
    list_capabilities,
)
from bionexus.contracts import (
    ConclusionMaturity,
    DimensionGrade,
    EvidenceCard,
    ExecutionState,
    cap_conclusion_by_purpose,
)
from bionexus.lab_policy import (
    DEFAULT_LAB_POLICY,
    LabPolicyProfile,
)
from bionexus.research_purpose import PurposeContext
from bionexus.rule_classification import classify_condition
from bionexus.rule_provenance import RuleProvenance, default_provenance_for_condition_id

__all__ = [
    "ALL_CAPABILITIES",
    "BackendRequirement",
    "CANONICAL_CAPABILITIES",
    "CapabilityContract",
    "CapabilityEvaluationResult",
    "ConclusionMaturity",
    "DEFAULT_LAB_POLICY",
    "DimensionGrade",
    "EvidenceCard",
    "EvidenceRequirement",
    "ExecutionState",
    "FRONTIER_CAPABILITIES",
    "InputSpecification",
    "LabPolicyProfile",
    "Precondition",
    "PurposeContext",
    "RefusalTrigger",
    "RuleProvenance",
    "SemanticInputType",
    "cap_conclusion_by_purpose",
    "classify_condition",
    "default_provenance_for_condition_id",
    "evaluate_capability_preconditions",
    "find_capabilities_by_intent",
    "get_capability",
    "list_capabilities",
    "probe",
]
