"""
BioNexus Scientific Claim Semantics & Deterministic Warrant Engine (BNS-017).

Compatibility Facade:
All implementations have been refactored into the modular `bionexus.claims` package:
- `bionexus.claims.models`: IR dataclasses, enums, schema
- `bionexus.claims.parser`: Deterministic & hybrid parsers, regex linguistic extractors
- `bionexus.claims.engine`: Deterministic warrant evaluation engine
- `bionexus.claims.policy`: Non-authorizing route and governing status enforcement
- `bionexus.claims.advisory`: Counterfactual warrant improvement advice

All public symbols are re-exported here for 100% backward compatibility.
"""

from bionexus.claims import (
    _ASSERTIVE_CAUSAL_RE,
    _NEGATION_CUE_RE,
    _NON_AUTHORIZING_GOVERNING_STATUSES,
    AssociationType,
    CausalStrength,
    ClaimClass,
    ClaimRelationshipType,
    ClinicalActionability,
    ConclusionMaturity,
    DeterministicClaimParser,
    DeterministicWarrantEngine,
    Directionality,
    EvidenceProfile,
    GeneralizationScope,
    HybridClaimParser,
    MechanismDepth,
    ScientificClaimIR,
    ScientificClaimParser,
    ScientificEntity,
    WarrantEvaluationResult,
    WarrantTierStatus,
    WarrantTierVerdict,
    decompose_compound_claim,
    detect_assertive_causal_language,
    enforce_governing_status,
    generate_counterfactual_warrant_advice,
    get_scientific_claim_ir_schema,
)

__all__ = [
    "AssociationType",
    "CausalStrength",
    "ClaimClass",
    "ClaimRelationshipType",
    "ClinicalActionability",
    "ConclusionMaturity",
    "DeterministicClaimParser",
    "DeterministicWarrantEngine",
    "Directionality",
    "EvidenceProfile",
    "GeneralizationScope",
    "HybridClaimParser",
    "MechanismDepth",
    "ScientificClaimIR",
    "ScientificClaimParser",
    "ScientificEntity",
    "WarrantEvaluationResult",
    "WarrantTierStatus",
    "WarrantTierVerdict",
    "_ASSERTIVE_CAUSAL_RE",
    "_NEGATION_CUE_RE",
    "_NON_AUTHORIZING_GOVERNING_STATUSES",
    "decompose_compound_claim",
    "detect_assertive_causal_language",
    "enforce_governing_status",
    "generate_counterfactual_warrant_advice",
    "get_scientific_claim_ir_schema",
]
