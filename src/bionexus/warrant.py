"""
Warrant / Policy separation: the scientific assessment and the intervention.

BioNexus distinguishes two objects that must never be conflated:

1. **WarrantAssessment** — the *scientific* evaluation of what the evidence is
   worth.  It depends only on the data design, the triggered rules, and the
   declared research purpose.  It is **policy-independent**: n=1 donor per
   condition caps population-level inference at FRAGILE whether the lab runs
   shadow, advisory, or enforced mode.

2. **PolicyDecision** — the *deployment* decision of whether and how BioNexus
   intervenes.  Policy can decide whether BioNexus acts, but it can never
   change what the evidence is worth.

Policy actions (ordered by intervention strength):

- **ALLOW**: no violations; proceed.
- **ALLOW_WITH_ACK**: shadow posture — proceed, warnings recorded, the warrant
  ceiling still applies to any claim.
- **REQUIRE_OVERRIDE**: advisory posture — proceed only after a documented
  researcher override; the ceiling still applies.
- **BLOCK**: enforced posture or a data-integrity invariant — stop.
- **ESCALATE**: a safety invariant (e.g. uncertified clinical claim) — stop and
  route to human / regulatory review; not merely a refusal.

This module is the theoretical core of the warrant engine: policy modulates
intervention, never evidence value.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Union

from bionexus.contracts import _MATURITY_RANK, ConclusionMaturity
from bionexus.evidence_model import EvidenceAssessment
from bionexus.lab_policy import EnforcementMode
from bionexus.research_purpose import PurposeContext

# The policy-independent scientific content (what remains uncertain, what
# cannot be claimed, per-rule ceiling caps) lives in researcher_override and
# is shared by both the warrant assessment and the override mechanism.
from bionexus.researcher_override import scientific_consequences_for
from bionexus.rule_classification import RuleCategory

# Any active warrant violation caps conclusions at FRAGILE by construction:
# the design flaw means the claim rests on unreplicated or unvalidated ground.
VIOLATION_MATURITY_CAP = ConclusionMaturity.FRAGILE


class PolicyAction(str, Enum):
    """Whether and how BioNexus intervenes.  Ordered by strength."""

    ALLOW = "ALLOW"
    ALLOW_WITH_ACK = "ALLOW_WITH_ACK"
    REQUIRE_OVERRIDE = "REQUIRE_OVERRIDE"
    BLOCK = "BLOCK"
    ESCALATE = "ESCALATE"


#: Which action each lab enforcement mode maps a warrant violation to.
WARRANT_ACTION_BY_MODE: Dict[EnforcementMode, PolicyAction] = {
    EnforcementMode.SHADOW: PolicyAction.ALLOW_WITH_ACK,
    EnforcementMode.ADVISORY: PolicyAction.REQUIRE_OVERRIDE,
    EnforcementMode.ENFORCED: PolicyAction.BLOCK,
}

#: Invariant categories and the action they always demand, in every lab.
INVARIANT_ACTION: Dict[RuleCategory, PolicyAction] = {
    RuleCategory.INVARIANT_SAFETY: PolicyAction.ESCALATE,
    RuleCategory.INVARIANT_INTEGRITY: PolicyAction.BLOCK,
}


@dataclass
class RuleBasisEntry:
    """One rule grounding the assessment, with its epistemic pedigree."""

    rule_id: str
    category: str = ""
    description: str = ""
    citation: str = ""
    consensus: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class WarrantAssessment:
    """The policy-independent scientific assessment of the evidence.

    Attributes:
        claim_maturity: The capped conclusion maturity this evidence can
            currently support.
        evidence_ceiling: The highest ConclusionMaturity reachable given the
            declared purpose and the active violations.  Identical in every lab.
        unsupported_claims: Claims this evidence cannot warrant (e.g.
            ``population_level_inference`` from n=1).
        residual_uncertainty: Uncertainties that remain regardless of any
            override or policy posture.
        rule_basis: The rules (with provenance) grounding this assessment.
        purpose: The declared research purpose value.
    """

    claim_maturity: str
    evidence_ceiling: str
    unsupported_claims: List[str] = field(default_factory=list)
    residual_uncertainty: List[str] = field(default_factory=list)
    rule_basis: List[RuleBasisEntry] = field(default_factory=list)
    purpose: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "claim_maturity": self.claim_maturity,
            "evidence_ceiling": self.evidence_ceiling,
            "unsupported_claims": self.unsupported_claims,
            "residual_uncertainty": self.residual_uncertainty,
            "rule_basis": [r.to_dict() for r in self.rule_basis],
            "purpose": self.purpose,
            "policy_independent": True,
        }


@dataclass
class PolicyDecision:
    """The lab-policy decision about intervention.  Carries — never mutates —
    the warrant assessment.

    Attributes:
        action: The intervention chosen by the policy.
        policy_name: The lab policy profile that produced this decision.
        warrant: The scientific assessment this decision is grounded in.
        rationale: Human-readable explanation.
        intervention_notes: What the lab must do to proceed (if anything).
        override_records: Documented researcher overrides (REQUIRE_OVERRIDE
            satisfied) — the ack, not a change to the warrant.
    """

    action: PolicyAction
    policy_name: str
    warrant: WarrantAssessment
    rationale: str = ""
    intervention_notes: List[str] = field(default_factory=list)
    override_records: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action.value,
            "policy_name": self.policy_name,
            "rationale": self.rationale,
            "intervention_notes": self.intervention_notes,
            "override_records": self.override_records,
            "warrant": self.warrant.to_dict(),
        }


# ---------------------------------------------------------------------------
# Warrant assessment (policy-independent)
# ---------------------------------------------------------------------------


def _classification_of(trigger: Any) -> Optional[Any]:
    """Resolve a trigger's RuleClassification from provenance or the catalog."""
    from bionexus.rule_classification import classify_condition

    prov = getattr(trigger, "provenance", None)
    classification = getattr(prov, "classification", None) if prov else None
    if classification is None:
        classification = classify_condition(getattr(trigger, "condition_id", ""))
    return classification


def _rule_basis_entry(trigger: Any) -> RuleBasisEntry:
    prov = getattr(trigger, "provenance", None)
    classification = _classification_of(trigger)
    return RuleBasisEntry(
        rule_id=getattr(trigger, "condition_id", ""),
        category=classification.category.value if classification else "",
        description=getattr(trigger, "description", ""),
        citation=getattr(prov, "source_citation", "") if prov else "",
        consensus=getattr(prov, "consensus", "").value if prov and getattr(prov, "consensus", None) else "",
    )


def assess_warrant(
    *,
    purpose_context: PurposeContext,
    warrant_triggers: Sequence[Any],
    invariant_triggers: Sequence[Any],
    base_maturity: Union[str, ConclusionMaturity] = ConclusionMaturity.UNASSESSED,
    evidence: Optional[EvidenceAssessment] = None,
) -> WarrantAssessment:
    """Compute the policy-independent scientific assessment.

    The evidence ceiling starts from **what the evidence is worth** — the
    ``evidence`` assessment's maturity when provided — and is then lowered by
    per-rule caps and by any active violation.  Purpose never raises the
    ceiling: it sets the use requirement (see ``evidence_model.py``), not the
    evidence value.  When no ``EvidenceAssessment`` is supplied the legacy
    purpose-derived value is used as a compatibility fallback only.

    The same inputs yield the same assessment in every lab — that is the
    contract.
    """
    pctx = purpose_context
    if evidence is not None:
        ceiling = ConclusionMaturity(evidence.evidence_maturity)
    else:
        # Legacy compatibility path: pre-evidence-model callers.  The value
        # returned here is the use requirement, read as a conservative cap.
        ceiling = pctx.evidence_ceiling

    unsupported: List[str] = []
    residual: List[str] = []
    basis: List[RuleBasisEntry] = []

    all_triggers = list(invariant_triggers) + list(warrant_triggers)
    for trigger in all_triggers:
        rule_id = getattr(trigger, "condition_id", "")
        basis.append(_rule_basis_entry(trigger))
        consequences = scientific_consequences_for(rule_id)
        unsupported.extend(consequences["unsupported_claims"])
        residual.extend(consequences["residual_uncertainty"])
        rule_cap = consequences["evidence_ceiling"]
        if _MATURITY_RANK.get(rule_cap.value, 0) < _MATURITY_RANK.get(ceiling.value, 0):
            ceiling = rule_cap

    if all_triggers and _MATURITY_RANK.get(VIOLATION_MATURITY_CAP.value, 0) < _MATURITY_RANK.get(ceiling.value, 0):
        ceiling = VIOLATION_MATURITY_CAP

    base = base_maturity.value if isinstance(base_maturity, ConclusionMaturity) else str(base_maturity)
    claim_maturity = base if _MATURITY_RANK.get(base, 0) <= _MATURITY_RANK.get(ceiling.value, 0) else ceiling.value

    return WarrantAssessment(
        claim_maturity=claim_maturity,
        evidence_ceiling=ceiling.value,
        unsupported_claims=sorted(set(unsupported)),
        residual_uncertainty=sorted(set(residual)),
        rule_basis=basis,
        purpose=pctx.purpose.value,
    )


# ---------------------------------------------------------------------------
# Policy decision (intervention only)
# ---------------------------------------------------------------------------


def decide_policy(
    *,
    policy: Any,
    assessment: WarrantAssessment,
    invariant_triggers: Sequence[Any],
    warrant_triggers: Sequence[Any],
    override_active: bool = False,
) -> PolicyDecision:
    """Derive the lab-policy intervention for a warrant assessment.

    Precedence: ESCALATE > BLOCK > REQUIRE_OVERRIDE > ALLOW_WITH_ACK > ALLOW.
    Invariant actions ignore the lab profile entirely.
    """
    notes: List[str] = []

    # Safety invariants escalate in every lab.
    strongest = PolicyAction.ALLOW
    for trigger in invariant_triggers:
        classification = _classification_of(trigger)
        category = classification.category if classification else RuleCategory.INVARIANT_INTEGRITY
        action = INVARIANT_ACTION.get(category, PolicyAction.BLOCK)
        if action == PolicyAction.ESCALATE:
            strongest = PolicyAction.ESCALATE
        elif strongest != PolicyAction.ESCALATE:
            strongest = PolicyAction.BLOCK
    if invariant_triggers:
        rationale = "Execution invariant violated: this rule cannot be modulated by any lab policy profile."
        if strongest == PolicyAction.ESCALATE:
            notes.append("Route to human / regulatory review before any further action.")
        return PolicyDecision(
            action=strongest,
            policy_name=policy.name,
            warrant=assessment,
            rationale=rationale,
            intervention_notes=notes,
        )

    if not warrant_triggers:
        return PolicyDecision(
            action=PolicyAction.ALLOW,
            policy_name=policy.name,
            warrant=assessment,
            rationale="No rule violations; execution and claims proceed at the assessed ceiling.",
        )

    # Warrant violations: the lab posture chooses the intervention, and ONLY
    # the intervention.  The assessment above is identical in every lab.
    modes = {policy.effective_mode_for(_classification_of(t)) for t in warrant_triggers}
    actions = {WARRANT_ACTION_BY_MODE.get(m, PolicyAction.REQUIRE_OVERRIDE) for m in modes}
    # Registry-declared ENFORCED warrants always block (mapped via effective_mode).
    for rank_action in (PolicyAction.BLOCK, PolicyAction.REQUIRE_OVERRIDE, PolicyAction.ALLOW_WITH_ACK):
        if rank_action in actions:
            action = rank_action
            break
    else:  # pragma: no cover - defensive
        action = PolicyAction.REQUIRE_OVERRIDE

    rationale = (
        f"Warrant constraints active; lab policy '{policy.name}' maps them to "
        f"{action.value}.  The scientific assessment (ceiling="
        f"{assessment.evidence_ceiling}) is identical under every policy."
    )
    if action == PolicyAction.ALLOW_WITH_ACK:
        notes.append(
            "Shadow posture: proceeding without intervention, but the evidence "
            "ceiling still applies to every claim made from this run."
        )
    elif action == PolicyAction.REQUIRE_OVERRIDE:
        if override_active:
            notes.append("Researcher override documented; limits and blocked claims preserved.")
        else:
            notes.append(
                "Provide an explicit override justification to proceed; the "
                "ceiling and blocked claims are preserved either way."
            )
    elif action == PolicyAction.BLOCK:
        notes.append("Enforced posture: remedy the violation before proceeding.")

    return PolicyDecision(
        action=action,
        policy_name=policy.name,
        warrant=assessment,
        rationale=rationale,
        intervention_notes=notes,
    )
