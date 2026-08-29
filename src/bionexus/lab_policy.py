"""
Lab Policy Profiles: Shadow / Advisory / Enforced enforcement modes.

Different laboratories operate under different compliance postures, and a
reliability layer that only knows how to *block* is unusable in most of them.
BioNexus therefore separates the scientific rule from its enforcement posture:

- The **rule** (provenance + classification) says what is scientifically true:
  "n=1 cannot support population-level inference."
- The **lab policy** says how strictly that truth is enforced in this lab,
  for *warrant constraints only*.

Three enforcement modes, ordered by strictness:

- **SHADOW**: the violation is recorded in the EvidenceCard and provenance
  sidecar but does not change the routing decision or cap the claim.  Use for
  evaluation, migration, or telemetry-only deployments where the lab wants to
  *see* what BioNexus would flag before turning enforcement on.
- **ADVISORY**: the analysis is permitted, but the conclusion maturity is capped
  and the run is returned as PERMITTED_WITH_LIMITS with a documented advisory.
  This is the default for most research labs — the compute proceeds, the claim
  is honestly bounded.
- **ENFORCED**: warrant constraints are enforced at their registry-declared
  severity.  For a rule whose classification is ENFORCED this means blocking;
  for ADVISORY-classified rules it means capping.

**Execution invariants are never relaxed.**  A lab policy cannot downgrade
INVARIANT_SAFETY or INVARIANT_INTEGRITY rules — patient safety and data
integrity are not subject to lab preference.  The policy only modulates
WARRANT_EPISTEMIC constraints.

This keeps BioNexus honest in both directions: it does not silently block
legitimate exploratory work in a discovery lab, and it cannot be configured to
let a clinical claim slip through in any lab.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional, Tuple

from bionexus.rule_classification import (
    EnforcementLevel,
    RuleCategory,
    RuleClassification,
)

# Strictness ordering used to compare modes.  Higher = stricter.
_MODE_RANK: Dict["EnforcementMode", int] = {}


class EnforcementMode(str, Enum):
    """How strictly a lab enforces warrant constraints.

    Ordered by strictness: SHADOW < ADVISORY < ENFORCED.
    """

    SHADOW = "SHADOW"
    ADVISORY = "ADVISORY"
    ENFORCED = "ENFORCED"


_MODE_RANK.update(
    {
        EnforcementMode.SHADOW: 0,
        EnforcementMode.ADVISORY: 1,
        EnforcementMode.ENFORCED: 2,
    }
)


def mode_rank(mode: EnforcementMode) -> int:
    """Numeric strictness rank for a mode (0=shadow, 1=advisory, 2=enforced)."""
    return _MODE_RANK[mode]


def stricter(a: EnforcementMode, b: EnforcementMode) -> EnforcementMode:
    """Return the stricter of two enforcement modes."""
    return a if mode_rank(a) >= mode_rank(b) else b


def laxer(a: EnforcementMode, b: EnforcementMode) -> EnforcementMode:
    """Return the laxer of two enforcement modes."""
    return a if mode_rank(a) <= mode_rank(b) else b


@dataclass
class LabPolicyProfile:
    """A laboratory's enforcement posture for BioNexus warrant constraints.

    Attributes:
        name: Human-readable identifier for the profile.
        warrant_mode: How warrant constraints are enforced.  Invariants ignore
            this field entirely.
        require_override_justification: When True, any researcher override must
            carry a non-empty justification string (recommended for ADVISORY and
            ENFORCED labs).
        auto_acknowledge_purposes: Intended-use purposes for which an advisory
            warrant gap may proceed without a separate override.  This only
            reduces interaction friction; the evidence ceiling, unsupported
            claims, and residual uncertainty remain unchanged.
        notes: Free-text description of when to use this profile.
    """

    name: str
    warrant_mode: EnforcementMode = EnforcementMode.ADVISORY
    require_override_justification: bool = True
    auto_acknowledge_purposes: Tuple[str, ...] = ()
    notes: str = ""

    def effective_mode_for(self, classification: Optional[RuleClassification]) -> EnforcementMode:
        """Compute the enforcement mode that actually applies to a rule under
        this lab policy.

        Semantics:
        - Execution invariants (safety / integrity) are ALWAYS ENFORCED,
          regardless of lab policy.
        - A warrant constraint that the evidence registry itself marks ENFORCED
          cannot be relaxed by a lax lab policy — it stays ENFORCED.
        - Every other warrant constraint follows the lab's declared warrant_mode.
        """
        if classification is None:
            # Unknown classification: fail toward the lab's default posture.
            return self.warrant_mode

        if classification.category in (
            RuleCategory.INVARIANT_SAFETY,
            RuleCategory.INVARIANT_INTEGRITY,
        ):
            return EnforcementMode.ENFORCED

        # Warrant constraint the registry says must block: a lab cannot relax it.
        if classification.enforcement_level == EnforcementLevel.ENFORCED:
            return EnforcementMode.ENFORCED

        # Otherwise the lab's posture decides how this warrant is handled.
        return self.warrant_mode

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "warrant_mode": self.warrant_mode.value,
            "require_override_justification": self.require_override_justification,
            "auto_acknowledge_purposes": list(self.auto_acknowledge_purposes),
            "notes": self.notes,
        }


def _level_to_mode(level: EnforcementLevel) -> EnforcementMode:
    """Map a rule's EnforcementLevel to the corresponding EnforcementMode."""
    return {
        EnforcementLevel.SHADOW: EnforcementMode.SHADOW,
        EnforcementLevel.ADVISORY: EnforcementMode.ADVISORY,
        EnforcementLevel.ENFORCED: EnforcementMode.ENFORCED,
    }[level]


# ---------------------------------------------------------------------------
# Pre-built lab policy profiles
# ---------------------------------------------------------------------------

#: Telemetry / migration mode.  Records every warrant violation but never blocks
#: or caps.  Use while evaluating BioNexus or migrating an existing pipeline.
SHADOW_AUDIT = LabPolicyProfile(
    name="shadow_audit",
    warrant_mode=EnforcementMode.SHADOW,
    require_override_justification=False,
    notes=(
        "Observe-only: warrant violations are logged to the EvidenceCard but do "
        "not alter routing or cap claims.  Invariants still block."
    ),
)

#: Default research posture.  Permits the compute, caps the claim, documents the
#: limit.  The right default for exploratory and discovery labs.
DISCOVERY_LAB = LabPolicyProfile(
    name="discovery_lab",
    warrant_mode=EnforcementMode.ADVISORY,
    require_override_justification=True,
    auto_acknowledge_purposes=("exploratory", "screening"),
    notes=(
        "Low-friction discovery: exploratory and screening warrant gaps proceed "
        "as PERMITTED_WITH_LIMITS without a separate override; confirmatory and "
        "causal gaps require a documented override.  Invariants still block."
    ),
)

#: Strict / pre-clinical / regulated posture.  Enforces every warrant constraint
#: at its registry-declared severity.
ENFORCED_LAB = LabPolicyProfile(
    name="enforced_lab",
    warrant_mode=EnforcementMode.ENFORCED,
    require_override_justification=True,
    notes=(
        "Enforced: warrant constraints apply at full registry severity.  Use for "
        "confirmatory, regulated, or pre-clinical workflows.  Invariants always block."
    ),
)

#: Registry of built-in profiles, keyed by name.
LAB_POLICY_PROFILES: Dict[str, LabPolicyProfile] = {
    SHADOW_AUDIT.name: SHADOW_AUDIT,
    DISCOVERY_LAB.name: DISCOVERY_LAB,
    ENFORCED_LAB.name: ENFORCED_LAB,
}

#: The default profile applied when a caller does not specify one.
DEFAULT_LAB_POLICY: LabPolicyProfile = DISCOVERY_LAB


def get_lab_policy(name: Optional[str]) -> LabPolicyProfile:
    """Resolve a lab policy by name; None or unknown names fall back to the default.

    Unknown names deliberately fall back to the default (advisory) rather than
    raising, so a typo cannot accidentally harden a pipeline into refusal — but
    the chosen profile name is always recorded in the EvidenceCard for audit.
    """
    if not name:
        return DEFAULT_LAB_POLICY
    return LAB_POLICY_PROFILES.get(name, DEFAULT_LAB_POLICY)


def policy_from_string(value: Optional[str]) -> LabPolicyProfile:
    """Alias for :func:`get_lab_policy` for API symmetry with other from_string helpers."""
    return get_lab_policy(value)
