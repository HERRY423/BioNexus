"""
BioNexus Scientific Claims Subpackage (BNS-017).
Decoupled into models, parser, engine, policy, and advisory.
"""

from bionexus.claims.advisory import generate_counterfactual_warrant_advice
from bionexus.claims.engine import DeterministicWarrantEngine
from bionexus.claims.models import (
    AssociationType,
    CausalStrength,
    ClaimRelationshipType,
    ClinicalActionability,
    Directionality,
    EvidenceProfile,
    GeneralizationScope,
    MechanismDepth,
    ScientificClaimIR,
    ScientificEntity,
    WarrantEvaluationResult,
    WarrantTierStatus,
    WarrantTierVerdict,
    get_scientific_claim_ir_schema,
)
from bionexus.claims.parser import (
    _ASSERTIVE_CAUSAL_RE,
    _NEGATION_CUE_RE,
    DeterministicClaimParser,
    HybridClaimParser,
    ScientificClaimParser,
    decompose_compound_claim,
    detect_assertive_causal_language,
)
from bionexus.claims.policy import (
    _NON_AUTHORIZING_GOVERNING_STATUSES,
    enforce_governing_status,
)
from bionexus.contracts import ConclusionMaturity
from bionexus.evidence_model import ClaimClass

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
