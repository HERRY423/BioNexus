"""
BioNexus Machine-Readable Scientific Capability Contracts.

Compatibility Facade:
Implementation has been modularized into `bionexus.capability_catalog`:
- `bionexus.capability_catalog.models`: Core contracts & validation result structures
- `bionexus.capability_catalog.definitions.canonical`: 12 canonical flagship capability specs
- `bionexus.capability_catalog.definitions.frontier`: Frontier capability specs
- `bionexus.capability_catalog.registry`: Lookup and precondition evaluation API

All public symbols are re-exported here for 100% backward compatibility.
"""

from bionexus.capability_catalog import (
    ALL_CAPABILITIES,
    CANONICAL_CAPABILITIES,
    DEFAULT_LAB_POLICY,
    FRONTIER_CAPABILITIES,
    BackendRequirement,
    CapabilityContract,
    CapabilityEvaluationResult,
    ConclusionMaturity,
    DimensionGrade,
    EvidenceCard,
    EvidenceRequirement,
    ExecutionState,
    InputSpecification,
    LabPolicyProfile,
    Precondition,
    PurposeContext,
    RefusalTrigger,
    RuleProvenance,
    SemanticInputType,
    cap_conclusion_by_purpose,
    classify_condition,
    default_provenance_for_condition_id,
    evaluate_capability_preconditions,
    find_capabilities_by_intent,
    get_capability,
    list_capabilities,
    probe,
)

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
