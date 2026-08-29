"""
BioNexus Machine-Readable Scientific Capability Contracts.

Defines formal, machine-actionable contracts for biological analyses:
- Input semantic requirements (e.g. raw integer counts vs normalized continuous scales)
- Preconditions (e.g. minimum biological replicates, non-degenerate coordinates)
- Canonical backend specifications
- Deterministic refusal triggers & actionable remedies
- Evidence requirements & mandatory limitations

Enables AI Coding Agents to understand *when an analysis is scientifically valid*
and *when it is scientifically invalid and must be refused*.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple

from bionexus.backends import probe
from bionexus.contracts import (
    _MATURITY_RANK,
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


class SemanticInputType(str, Enum):
    """Semantic data type expected for analytical inputs."""

    RAW_COUNTS = "raw_counts"  # Non-negative integer count matrix
    NORMALIZED_MATRIX = "normalized_matrix"  # Log-normalized / scaled continuous expression
    SPATIAL_COORDINATES = "spatial_coordinates"  # 2D/3D spot/cell centroid coordinates
    SAMPLE_METADATA = "sample_metadata"  # Per-sample/cell covariate annotations
    VARIANT_RECORDS = "variant_records"  # HGVS, VCF, or genomic variant coordinates
    SURVIVAL_DATA = "survival_data"  # Time-to-event and censoring indicators
    INSTRUMENT_TABLE = "instrument_table"  # Raw analytical instrument output (plate reader, chromatography)
    PROTEIN_SEQUENCE = "protein_sequence"  # Amino acid sequence string / FASTA
    PDB_STRUCTURE = "pdb_structure"  # 3D atomic coordinates (PDB/mmCIF)
    COMPUTE_SPECIFICATION = "compute_specification"  # HPC / Cloud batch resource descriptor
    BIGDATA_STORE = "bigdata_store"  # H5AD, AnnData Zarr, or TileDB-SOMA store


@dataclass
class InputSpecification:
    """Specification of an input artifact and its semantic requirements."""

    name: str
    semantic_type: str
    required: bool = True
    description: str = ""
    validation_rule: Optional[str] = None


@dataclass
class Precondition:
    """Mathematical or biological invariant required before execution."""

    id: str
    rule: str
    description: str
    fatal_if_violated: bool = True
    provenance: Optional[RuleProvenance] = None

    def __post_init__(self) -> None:
        if self.provenance is None:
            self.provenance = default_provenance_for_condition_id(self.id)


@dataclass
class BackendRequirement:
    """Canonical community package required for gold-standard execution."""

    canonical_name: str
    import_name: str
    minimum_version: Optional[str] = None
    extra: Optional[str] = None
    description: str = ""
    # Dotted import paths (module or module.attribute) that the declared backend
    # MUST expose for this capability. Backend Identity Conformance resolves
    # each entry point at audit time: an unresolvable entry point is an
    # identity violation (BN-F010), never a silent substitute.
    entry_points: Tuple[str, ...] = ()


@dataclass
class RefusalTrigger:
    """Condition that deterministically mandates an agent refusal with scientific justification."""

    condition_id: str
    description: str
    remedy: str
    violated_rule: str
    provenance: Optional[RuleProvenance] = None

    def __post_init__(self) -> None:
        if self.provenance is None:
            self.provenance = default_provenance_for_condition_id(self.condition_id)


@dataclass
class EvidenceRequirement:
    """Evidence criteria that must be reported in the output EvidenceCard."""

    multiple_testing: str = "required"  # "required" | "recommended" | "optional"
    effect_size: str = "required"
    min_fdr_alpha: float = 0.05
    uncertainty_quantification: str = "recommended"
    mandatory_limitations: List[str] = field(default_factory=list)


@dataclass
class CapabilityContract:
    """
    Machine-readable Scientific Capability Contract.

    The `forbidden_claims` and `evidence_ceiling_without_external_validation`
    fields are the normative source for the Biological Capability ABI
    (`bionexus.abi`); the ABI projection is generated from this contract and
    MUST NOT drift from it (BNS-CC-010..013).
    """

    id: str
    version: int = 1
    display_name: str = ""
    skill_name: str = ""
    summary: str = ""
    intent: List[str] = field(default_factory=list)
    inputs: Dict[str, InputSpecification] = field(default_factory=dict)
    preconditions: List[Precondition] = field(default_factory=list)
    backend: BackendRequirement = field(
        default_factory=lambda: BackendRequirement(canonical_name="none", import_name="none")
    )
    refusal_conditions: List[RefusalTrigger] = field(default_factory=list)
    outputs: List[str] = field(default_factory=list)
    evidence_requirements: EvidenceRequirement = field(default_factory=EvidenceRequirement)
    forbidden_claims: List[str] = field(default_factory=list)
    evidence_ceiling_without_external_validation: str = "SUPPORTED"

    def to_dict(self) -> Dict[str, Any]:
        """Serialize contract to dictionary."""
        return asdict(self)

    def evaluate_viability(
        self,
        *,
        input_metadata: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> CapabilityEvaluationResult:
        """
        Evaluate whether the requested analysis is scientifically valid.
        """
        meta = input_metadata or {}
        violations: List[str] = []
        triggered_refusals: List[RefusalTrigger] = []
        remedies: List[str] = []

        # 1. Input Semantic Check
        for inp_name, inp_spec in self.inputs.items():
            if inp_spec.required:
                present = meta.get(f"{inp_name}_present", True)
                if not present:
                    violations.append(f"Missing required input '{inp_name}'")
                    remedies.append(f"Provide valid input artifact for '{inp_name}' ({inp_spec.semantic_type}).")

                # Semantic type verification
                if inp_spec.semantic_type == SemanticInputType.RAW_COUNTS.value:
                    if meta.get("is_normalized") is True or meta.get("is_integer_like") is False:
                        trigger = next(
                            (r for r in self.refusal_conditions if r.condition_id == "normalized_matrix_only"),
                            RefusalTrigger(
                                condition_id="normalized_matrix_only",
                                description="Input matrix contains normalized continuous floats where raw integer counts are required.",
                                remedy="Provide raw un-normalized count matrix (e.g. adata.raw.X or raw integer counts layer).",
                                violated_rule="Raw integer counts distribution assumption",
                            ),
                        )
                        triggered_refusals.append(trigger)
                        violations.append(trigger.description)
                        remedies.append(trigger.remedy)

        # 2. Precondition Evaluation
        # Minimum replicates check
        min_reps = meta.get("min_replicates_per_condition")
        if min_reps is not None and min_reps < 2:
            trigger = next(
                (r for r in self.refusal_conditions if r.condition_id == "missing_replicates"),
                RefusalTrigger(
                    condition_id="missing_replicates",
                    description=f"Found {min_reps} replicates per condition, minimum required is 2.",
                    remedy="Condition differential expression requires at least 2 biological replicates per group to estimate within-group biological dispersion.",
                    violated_rule="Biological replicate requirement",
                ),
            )
            triggered_refusals.append(trigger)
            violations.append(trigger.description)
            remedies.append(trigger.remedy)

        # Spatial spots check
        n_spots = meta.get("n_spatial_spots")
        if n_spots is not None and n_spots < 5:
            trigger = next(
                (r for r in self.refusal_conditions if r.condition_id == "insufficient_spatial_spots"),
                RefusalTrigger(
                    condition_id="insufficient_spatial_spots",
                    description=f"Found {n_spots} spatial spots, minimum required is 5 for graph construction.",
                    remedy="Provide spatial dataset with sufficient spatial coordinate entries.",
                    violated_rule="Spatial neighborhood graph connectivity",
                ),
            )
            triggered_refusals.append(trigger)
            violations.append(trigger.description)
            remedies.append(trigger.remedy)

        # Spatial coordinate variance check
        if meta.get("coordinate_variance_zero") is True:
            trigger = RefusalTrigger(
                condition_id="degenerate_spatial_coordinates",
                description="Spatial coordinates have zero variance along spatial axes.",
                remedy="Provide non-degenerate spatial coordinates with varied positions.",
                violated_rule="Spatial geometry variance invariant",
            )
            triggered_refusals.append(trigger)
            violations.append(trigger.description)
            remedies.append(trigger.remedy)

        # Survival zero events check
        if meta.get("n_events") == 0:
            trigger = next(
                (r for r in self.refusal_conditions if r.condition_id == "all_censored"),
                RefusalTrigger(
                    condition_id="all_censored",
                    description="Zero events observed in cohort (100% censoring).",
                    remedy="Survival estimation requires at least one uncensored event.",
                    violated_rule="Event observation requirement",
                ),
            )
            triggered_refusals.append(trigger)
            violations.append(trigger.description)
            remedies.append(trigger.remedy)

        # 3. Backend Availability Gate (bound to the Capability, never to a skill).
        # A missing canonical backend is a violation, not an advisory note:
        # availability is decided here, deterministically, for every caller.
        backend_name = self.backend.import_name
        backend_available: Optional[bool] = None
        if backend_name and backend_name != "none":
            backend_status = probe(backend_name)
            backend_available = backend_status.available
            if not backend_status.available:
                # Deterministic violation wording (always names the backend) so
                # downstream classification (BN-F010 / BACKEND_UNAVAILABLE) never
                # depends on per-contract phrasing; only the remedy may be bespoke.
                contract_trigger = next(
                    (r for r in self.refusal_conditions if r.condition_id == "missing_backend"),
                    None,
                )
                trigger = RefusalTrigger(
                    condition_id="missing_backend",
                    description=(
                        f"Canonical backend '{self.backend.canonical_name}' required by capability "
                        f"'{self.id}' is not available in this environment ({backend_status.state.value})."
                    ),
                    remedy=(
                        contract_trigger.remedy
                        if contract_trigger
                        else (
                            f"Install via `pip install {self.backend.import_name}` "
                            f"or `pip install bionexus-reliability[{self.backend.extra or 'all'}]`."
                        )
                    ),
                    violated_rule="Gold-standard backend requirement",
                )
                triggered_refusals.append(trigger)
                violations.append(trigger.description)
                remedies.append(trigger.remedy)

        # 4. Synthesize Evaluation
        permitted = len(triggered_refusals) == 0 and len(violations) == 0
        if not permitted:
            exec_state = ExecutionState.REFUSED.value
            concl_maturity = ConclusionMaturity.ABSTAIN.value
            card = EvidenceCard(
                execution_state=exec_state,
                input_integrity=DimensionGrade.GRADE_C.value
                if any("normalized" in v.lower() for v in violations)
                else DimensionGrade.UNTESTED.value,
                assumption_validity=DimensionGrade.GRADE_C.value,
                statistical_support=DimensionGrade.UNTESTED.value,
                details={
                    "contract_id": self.id,
                    "refusal_triggers": [r.condition_id for r in triggered_refusals],
                    "violations": violations,
                },
            )
            status = "REFUSED"
        else:
            exec_state = ExecutionState.PERMITTED.value
            concl_maturity = ConclusionMaturity.UNASSESSED.value
            card = EvidenceCard(
                execution_state=exec_state,
                input_integrity=DimensionGrade.GRADE_A.value if meta else DimensionGrade.UNTESTED.value,
                assumption_validity=DimensionGrade.GRADE_A.value if meta else DimensionGrade.GRADE_B.value,
                statistical_support=DimensionGrade.UNTESTED.value,
                parameter_robustness=DimensionGrade.UNTESTED.value,
                cross_method_concordance=DimensionGrade.UNTESTED.value,
                external_validation=DimensionGrade.UNTESTED.value,
                details={
                    "contract_id": self.id,
                    "execution_backend": self.backend.canonical_name,
                    "evaluation_stage": "preflight_viability",
                    "notes": (
                        "Preconditions satisfied and required backend verified. "
                        "Execution is permitted; conclusion maturity remains PRELIMINARY "
                        "until post-execution statistical tests (p-values, FDR, effect size) are computed."
                    ),
                },
            )
            status = "PERMITTED"

        return CapabilityEvaluationResult(
            capability_id=self.id,
            status=status,
            permitted=permitted,
            violations=violations,
            refusal_triggers=triggered_refusals,
            remedies=remedies,
            evidence_card=card,
            conclusion_maturity=concl_maturity,
            backend_available=backend_available,
        )

    def evaluate_viability_with_purpose(
        self,
        *,
        input_metadata: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
        purpose_context: Optional[PurposeContext] = None,
        lab_policy: Optional[LabPolicyProfile] = None,
        evidence_factors: Sequence[Any] = (),
        claim_context: Optional[Any] = None,
        documented_extras: Sequence[str] = (),
    ) -> CapabilityEvaluationResult:
        """Purpose-aware, warrant/policy-separated evaluation.

        Three strictly separated objects:

        1. **EvidenceAssessment** (purpose- and policy-independent): what the
           evidence IS worth, from declared evidence factors and active
           violations.  Purpose never raises or lowers it.
        2. **WarrantAssessment** (policy-independent): the capped claim
           maturity and unsupported claims, starting from the evidence
           assessment.  Identical in every lab.
        3. **PolicyDecision** (deployment posture): does BioNexus intervene?
           ALLOW / ALLOW_WITH_ACK (shadow) / ALLOW_WITH_LIMITS (low-risk
           discovery) / REQUIRE_OVERRIDE (higher-risk advisory) / BLOCK
           (enforced or integrity invariant) / ESCALATE (safety).

        Additionally a **SufficiencyAssessment** compares the evidence against
        the intended-use requirement (purpose + claim class): WARRANTED or
        NOT_SUFFICIENT_FOR_INTENDED_USE.  Purpose decides the requirement,
        never the evidence value.

        Execution invariants (safety/integrity) and missing canonical backends
        always BLOCK/ESCALATE regardless of policy or override.
        """
        from bionexus.evidence_model import assess_evidence, evaluate_sufficiency
        from bionexus.rule_classification import RuleCategory
        from bionexus.warrant import PolicyAction, assess_warrant, decide_policy

        policy = lab_policy or DEFAULT_LAB_POLICY
        pctx = purpose_context or PurposeContext()
        base = self.evaluate_viability(input_metadata=input_metadata, context=context)

        def _attach(
            card: EvidenceCard,
            assessment: Any,
            decision: Any,
            evidence: Any = None,
            sufficiency: Any = None,
        ) -> None:
            card.details.setdefault("lab_policy", policy.name)
            if evidence is not None:
                card.details["evidence_assessment"] = evidence.to_dict()
            card.details["warrant_assessment"] = assessment.to_dict()
            if sufficiency is not None:
                card.details["sufficiency"] = sufficiency.to_dict()
            card.details["policy_decision"] = {k: v for k, v in decision.to_dict().items() if k != "warrant"}

        # If the base evaluation is permitted, the assessment carries no
        # violations; the ceiling is what the evidence itself is worth.
        if base.permitted:
            evidence = assess_evidence(
                base_maturity=base.conclusion_maturity,
                satisfied_factors=evidence_factors,
            )
            assessment = assess_warrant(
                purpose_context=pctx,
                warrant_triggers=[],
                invariant_triggers=[],
                base_maturity=base.conclusion_maturity,
                evidence=evidence,
            )
            sufficiency = evaluate_sufficiency(
                evidence=evidence,
                purpose_context=pctx,
                claim_context=claim_context,
                documented_extras=documented_extras,
                override_acknowledged=pctx.override_active,
            )
            decision = decide_policy(
                policy=policy,
                assessment=assessment,
                invariant_triggers=[],
                warrant_triggers=[],
            )
            base.research_purpose = pctx.purpose.value
            base.evidence_ceiling = assessment.evidence_ceiling
            base.lab_policy_name = policy.name
            base.evidence_assessment = evidence.to_dict()
            base.warrant_assessment = assessment.to_dict()
            base.sufficiency = sufficiency.to_dict()
            base.policy_decision = decision.to_dict()
            capped = cap_conclusion_by_purpose(
                base.conclusion_maturity, ConclusionMaturity(assessment.evidence_ceiling)
            )
            base.conclusion_maturity = capped
            if base.evidence_card:
                base.evidence_card.research_purpose = pctx.purpose.value
                base.evidence_card.evidence_ceiling = assessment.evidence_ceiling
                _attach(base.evidence_card, assessment, decision, evidence, sufficiency)
            return base

        # ------------------------------------------------------------------
        # Stage 1: split triggers into invariants vs warrants.
        # This classification is POLICY-INDEPENDENT: it reflects what the
        # rules *are*, not how this lab enforces them.
        # ------------------------------------------------------------------
        invariant_triggers: List[RefusalTrigger] = []
        warrant_triggers: List[RefusalTrigger] = []

        for trigger in base.refusal_triggers:
            if trigger.condition_id == "missing_backend":
                # Backend identity is an integrity invariant; the only softness
                # is the frontier fallback consent path, which predates policies.
                from bionexus.capabilities import FRONTIER_CAPABILITIES

                if self.id in FRONTIER_CAPABILITIES:
                    warrant_triggers.append(trigger)
                else:
                    invariant_triggers.append(trigger)
                continue
            classification = None
            prov = trigger.provenance
            if prov is not None:
                classification = prov.classification
            if classification is None:
                classification = classify_condition(trigger.condition_id)
            if classification is not None and classification.category in (
                RuleCategory.INVARIANT_SAFETY,
                RuleCategory.INVARIANT_INTEGRITY,
            ):
                invariant_triggers.append(trigger)
            else:
                warrant_triggers.append(trigger)

        # ------------------------------------------------------------------
        # Stage 2: the scientific assessment.  Identical in every lab.
        # The evidence assessment is purpose-independent; the warrant
        # assessment starts from what the evidence is worth.
        # ------------------------------------------------------------------
        evidence = assess_evidence(
            base_maturity=base.conclusion_maturity,
            satisfied_factors=evidence_factors,
            warrant_triggers=warrant_triggers,
            invariant_triggers=invariant_triggers,
        )
        assessment = assess_warrant(
            purpose_context=pctx,
            warrant_triggers=warrant_triggers,
            invariant_triggers=invariant_triggers,
            base_maturity=base.conclusion_maturity,
            evidence=evidence,
        )
        sufficiency = evaluate_sufficiency(
            evidence=evidence,
            purpose_context=pctx,
            claim_context=claim_context,
            documented_extras=documented_extras,
            override_acknowledged=pctx.override_active,
        )

        # ------------------------------------------------------------------
        # Stage 3: the policy decision.  Intervention only.
        # ------------------------------------------------------------------
        decision = decide_policy(
            policy=policy,
            assessment=assessment,
            invariant_triggers=invariant_triggers,
            warrant_triggers=warrant_triggers,
            override_active=pctx.override_active,
        )

        # Invariants (ESCALATE/BLOCK) always refuse, in every lab.
        if invariant_triggers:
            base.research_purpose = pctx.purpose.value
            base.evidence_ceiling = assessment.evidence_ceiling
            base.lab_policy_name = policy.name
            base.evidence_assessment = evidence.to_dict()
            base.warrant_assessment = assessment.to_dict()
            base.sufficiency = sufficiency.to_dict()
            base.policy_decision = decision.to_dict()
            if base.evidence_card:
                _attach(base.evidence_card, assessment, decision, evidence, sufficiency)
            return base

        # Shadow posture: proceed without intervention — but the assessment
        # ceiling still applies to every claim made from this run.
        if decision.action == PolicyAction.ALLOW_WITH_ACK:
            capped = cap_conclusion_by_purpose(ConclusionMaturity.UNASSESSED.value, assessment.evidence_ceiling)
            card = EvidenceCard(
                execution_state=ExecutionState.PERMITTED.value,
                input_integrity=base.evidence_card.input_integrity
                if base.evidence_card
                else DimensionGrade.UNTESTED.value,
                assumption_validity=base.evidence_card.assumption_validity
                if base.evidence_card
                else DimensionGrade.GRADE_B.value,
                statistical_support=DimensionGrade.UNTESTED.value,
                details={
                    "contract_id": self.id,
                    "execution_backend": self.backend.canonical_name,
                    "shadow_mode": True,
                    "shadow_violations": [t.description for t in warrant_triggers],
                    "shadow_condition_ids": [t.condition_id for t in warrant_triggers],
                    "notes": (
                        "Shadow posture: no intervention, but the scientific "
                        "assessment is unchanged — the evidence ceiling still "
                        "bounds every claim from this run."
                    ),
                },
                research_purpose=pctx.purpose.value,
                evidence_ceiling=assessment.evidence_ceiling,
                blocked_claims=assessment.unsupported_claims,
                residual_limitations=assessment.residual_uncertainty,
            )
            _attach(card, assessment, decision, evidence, sufficiency)
            return CapabilityEvaluationResult(
                capability_id=self.id,
                status="PERMITTED",
                permitted=True,
                violations=[],
                refusal_triggers=[],
                remedies=base.remedies,
                evidence_card=card,
                conclusion_maturity=capped,
                backend_available=base.backend_available,
                research_purpose=pctx.purpose.value,
                evidence_ceiling=assessment.evidence_ceiling,
                lab_policy_name=policy.name,
                shadow_violations=[t.description for t in warrant_triggers],
                evidence_assessment=evidence.to_dict(),
                warrant_assessment=assessment.to_dict(),
                sufficiency=sufficiency.to_dict(),
                policy_decision=decision.to_dict(),
            )

        # Low-friction discovery posture: compute proceeds without manufacturing
        # an override record.  The return state remains explicitly limited, and
        # every scientific consequence from the warrant assessment is retained.
        if decision.action == PolicyAction.ALLOW_WITH_LIMITS:
            capped = cap_conclusion_by_purpose(
                ConclusionMaturity.FRAGILE.value, assessment.evidence_ceiling
            )
            card = EvidenceCard(
                execution_state=ExecutionState.PERMITTED_WITH_LIMITS.value,
                input_integrity=base.evidence_card.input_integrity
                if base.evidence_card
                else DimensionGrade.UNTESTED.value,
                assumption_validity=base.evidence_card.assumption_validity
                if base.evidence_card
                else DimensionGrade.GRADE_C.value,
                statistical_support=base.evidence_card.statistical_support
                if base.evidence_card
                else DimensionGrade.UNTESTED.value,
                details={
                    "contract_id": self.id,
                    "execution_backend": self.backend.canonical_name,
                    "low_friction_discovery": True,
                    "acknowledged_condition_ids": [t.condition_id for t in warrant_triggers],
                    "notes": (
                        "Exploratory/screening execution proceeds without a separate "
                        "override. Scientific limits and unsupported claims remain binding."
                    ),
                },
                research_purpose=pctx.purpose.value,
                evidence_ceiling=assessment.evidence_ceiling,
                blocked_claims=assessment.unsupported_claims,
                residual_limitations=assessment.residual_uncertainty,
            )
            _attach(card, assessment, decision, evidence, sufficiency)
            return CapabilityEvaluationResult(
                capability_id=self.id,
                status="PERMITTED_WITH_LIMITS",
                permitted=True,
                violations=[],
                refusal_triggers=[],
                remedies=base.remedies,
                evidence_card=card,
                conclusion_maturity=capped,
                backend_available=base.backend_available,
                research_purpose=pctx.purpose.value,
                evidence_ceiling=assessment.evidence_ceiling,
                soft_violations=[t.description for t in warrant_triggers],
                residual_limitations=assessment.residual_uncertainty,
                blocked_claims=assessment.unsupported_claims,
                lab_policy_name=policy.name,
                evidence_assessment=evidence.to_dict(),
                warrant_assessment=assessment.to_dict(),
                sufficiency=sufficiency.to_dict(),
                policy_decision=decision.to_dict(),
            )

        # Advisory posture with a documented override: PERMITTED_WITH_LIMITS.
        if decision.action == PolicyAction.REQUIRE_OVERRIDE and pctx.override_active:
            from bionexus.researcher_override import create_override_record

            override_dicts = []
            all_residual: List[str] = []
            all_blocked: List[str] = []
            override_denied: List[str] = []
            # The override negotiation starts from what the evidence is worth
            # (evidence-derived ceiling), never from the purpose.
            min_ceiling = ConclusionMaturity(assessment.evidence_ceiling)

            for trigger in warrant_triggers:
                try:
                    record = create_override_record(
                        rule_id=trigger.condition_id,
                        rule_description=trigger.description,
                        justification=pctx.override_justification or "Researcher override invoked.",
                        purpose=pctx.purpose,
                        provenance=trigger.provenance,
                    )
                    override_dicts.append(record.to_dict())
                    all_residual.extend(record.residual_limitations)
                    all_blocked.extend(record.blocked_claims)
                    if _MATURITY_RANK.get(record.evidence_ceiling_override, 0) < _MATURITY_RANK.get(min_ceiling, 0):
                        min_ceiling = record.evidence_ceiling_override
                except Exception:
                    # Override denied for this rule; treat as hard block.
                    override_denied.append(trigger.description)

            if override_denied:
                # Some overrides were denied; still blocked.
                decision.rationale += " Override denied for: " + "; ".join(override_denied)
                base.research_purpose = pctx.purpose.value
                base.evidence_ceiling = assessment.evidence_ceiling
                base.lab_policy_name = policy.name
                base.evidence_assessment = evidence.to_dict()
                base.warrant_assessment = assessment.to_dict()
                base.sufficiency = sufficiency.to_dict()
                base.policy_decision = decision.to_dict()
                if base.evidence_card:
                    _attach(base.evidence_card, assessment, decision, evidence, sufficiency)
                return base

            # All overrides accepted: PERMITTED_WITH_LIMITS.  The override is
            # the ack; the warrant assessment is untouched.
            capped = cap_conclusion_by_purpose(ConclusionMaturity.FRAGILE.value, min_ceiling)
            decision.override_records = override_dicts
            card = EvidenceCard(
                execution_state=ExecutionState.PERMITTED_WITH_LIMITS.value,
                input_integrity=base.evidence_card.input_integrity
                if base.evidence_card
                else DimensionGrade.GRADE_C.value,
                assumption_validity=base.evidence_card.assumption_validity
                if base.evidence_card
                else DimensionGrade.GRADE_C.value,
                statistical_support=base.evidence_card.statistical_support
                if base.evidence_card
                else DimensionGrade.UNTESTED.value,
                details={
                    "contract_id": self.id,
                    "execution_backend": self.backend.canonical_name,
                    "override_active": True,
                    "override_justification": pctx.override_justification,
                },
                research_purpose=pctx.purpose.value,
                evidence_ceiling=min_ceiling.value,
                override_records=override_dicts,
                residual_limitations=all_residual,
                blocked_claims=list(set(all_blocked)),
            )
            _attach(card, assessment, decision, evidence, sufficiency)
            return CapabilityEvaluationResult(
                capability_id=self.id,
                status="PERMITTED_WITH_LIMITS",
                permitted=True,
                violations=[],
                refusal_triggers=[],
                remedies=base.remedies,
                evidence_card=card,
                conclusion_maturity=capped,
                backend_available=base.backend_available,
                research_purpose=pctx.purpose.value,
                evidence_ceiling=min_ceiling.value,
                soft_violations=[t.description for t in warrant_triggers],
                override_records=override_dicts,
                residual_limitations=all_residual,
                blocked_claims=list(set(all_blocked)),
                lab_policy_name=policy.name,
                evidence_assessment=evidence.to_dict(),
                warrant_assessment=assessment.to_dict(),
                sufficiency=sufficiency.to_dict(),
                policy_decision=decision.to_dict(),
            )

        # REQUIRE_OVERRIDE without override, or BLOCK: refuse, with the
        # assessment recorded so the scientist sees *why* the evidence is capped.
        base.research_purpose = pctx.purpose.value
        base.evidence_ceiling = assessment.evidence_ceiling
        base.lab_policy_name = policy.name
        base.evidence_assessment = evidence.to_dict()
        base.warrant_assessment = assessment.to_dict()
        base.sufficiency = sufficiency.to_dict()
        base.policy_decision = decision.to_dict()
        if base.evidence_card:
            _attach(base.evidence_card, assessment, decision, evidence, sufficiency)
        return base


@dataclass
class CapabilityEvaluationResult:
    """Result of evaluating a scientific capability contract against execution context."""

    capability_id: str
    status: str  # "PERMITTED" | "PERMITTED_WITH_LIMITS" | "REFUSED" | "DEGRADED"
    permitted: bool
    violations: List[str]
    refusal_triggers: List[RefusalTrigger]
    remedies: List[str]
    evidence_card: EvidenceCard
    conclusion_maturity: str
    # None when the capability declares no backend; otherwise the live probe result.
    backend_available: Optional[bool] = None
    # Purpose-aware fields
    research_purpose: Optional[str] = None
    evidence_ceiling: Optional[str] = None
    soft_violations: List[str] = field(default_factory=list)  # overridden soft blocks
    override_records: List[Dict[str, Any]] = field(default_factory=list)  # active overrides
    residual_limitations: List[str] = field(default_factory=list)  # remaining limitations
    blocked_claims: List[str] = field(default_factory=list)  # claims still not warranted
    # Lab-policy fields
    lab_policy_name: Optional[str] = None  # profile name resolved for this evaluation
    shadow_violations: List[str] = field(default_factory=list)  # observed but not enforced
    # Warrant / policy separation (the assessment is policy-independent)
    warrant_assessment: Optional[Dict[str, Any]] = None
    policy_decision: Optional[Dict[str, Any]] = None
    # Evidence model (evidence strength vs intended-use requirement)
    evidence_assessment: Optional[Dict[str, Any]] = None
    sufficiency: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert evaluation result to dictionary."""
        d = {
            "capability_id": self.capability_id,
            "status": self.status,
            "permitted": self.permitted,
            "violations": self.violations,
            "refusal_triggers": [asdict(r) for r in self.refusal_triggers],
            "remedies": self.remedies,
            "evidence_card": self.evidence_card.to_dict(),
            "conclusion_maturity": self.conclusion_maturity,
            "backend_available": self.backend_available,
        }
        # Include purpose-aware fields only when populated
        if self.research_purpose:
            d["research_purpose"] = self.research_purpose
            d["evidence_ceiling"] = self.evidence_ceiling
            d["soft_violations"] = self.soft_violations
            d["override_records"] = self.override_records
            d["residual_limitations"] = self.residual_limitations
            d["blocked_claims"] = self.blocked_claims
        if self.lab_policy_name:
            d["lab_policy"] = self.lab_policy_name
        if self.shadow_violations:
            d["shadow_violations"] = self.shadow_violations
        if self.warrant_assessment:
            d["warrant_assessment"] = self.warrant_assessment
        if self.policy_decision:
            d["policy_decision"] = self.policy_decision
        if self.evidence_assessment:
            d["evidence_assessment"] = self.evidence_assessment
        if self.sufficiency:
            d["sufficiency"] = self.sufficiency
        return d


# ==============================================================================
# Canonical Scientific Capability Contracts
# ==============================================================================

CANONICAL_CAPABILITIES: Dict[str, CapabilityContract] = {
    # 1. Single-cell Pseudobulk Differential Expression
    "scrna.pseudobulk_de": CapabilityContract(
        id="scrna.pseudobulk_de",
        version=1,
        display_name="Single-Cell Pseudobulk Differential Expression",
        skill_name="single-cell-rna-qc",
        summary="Condition differential expression across biological replicate groups using negative binomial GLM (PyDESeq2).",
        intent=[
            "compare_conditions",
            "differential_expression",
            "condition_de",
            "treatment_effect",
            "disease_vs_control",
        ],
        inputs={
            "expression": InputSpecification(
                name="expression",
                semantic_type=SemanticInputType.RAW_COUNTS.value,
                required=True,
                description="Pseudobulk summed count matrix of integer counts per sample x condition.",
                validation_rule="audit_expression_matrix:counts",
            ),
            "sample_design": InputSpecification(
                name="sample_design",
                semantic_type=SemanticInputType.SAMPLE_METADATA.value,
                required=True,
                description="Sample metadata table with biological replicate identifiers and condition factors.",
            ),
        },
        preconditions=[
            Precondition(
                id="min_replicates",
                rule="n_replicates_per_condition >= 2",
                description="Each experimental condition must contain at least 2 biological replicates to estimate dispersion.",
                fatal_if_violated=True,
            ),
            Precondition(
                id="raw_integer_counts",
                rule="is_integer_like(counts) == True",
                description="Negative binomial GLM requires raw integer counts, not normalized floats.",
                fatal_if_violated=True,
            ),
        ],
        backend=BackendRequirement(
            canonical_name="pydeseq2",
            import_name="pydeseq2",
            minimum_version="0.4.0",
            extra="deseq",
            entry_points=("pydeseq2.dds.DeseqDataSet", "pydeseq2.ds.DeseqStats"),
            description="PyDESeq2 Wald tests on pseudobulk counts",
        ),
        refusal_conditions=[
            RefusalTrigger(
                condition_id="normalized_matrix_only",
                description="Normalized continuous matrix passed where raw counts required.",
                remedy="Sum unnormalized raw counts (adata.raw.X) over (sample, cell_type, condition) groups before testing.",
                violated_rule="Negative binomial dispersion estimation requires integer count distribution",
            ),
            RefusalTrigger(
                condition_id="missing_replicates",
                description="Fewer than 2 biological replicates per experimental condition.",
                remedy="Condition DE is statistically invalid without biological replicates (pseudoreplication). Collect additional replicates or report exploratory marker rankings only.",
                violated_rule="Biological replication invariant",
            ),
            RefusalTrigger(
                condition_id="missing_backend",
                description="PyDESeq2 backend not available in environment.",
                remedy="Install via `pip install bionexus-reliability[deseq]` or `pip install pydeseq2`.",
                violated_rule="Gold-standard backend requirement",
            ),
        ],
        outputs=[
            "differential_expression_table (CSV)",
            "volcano_plot (PNG)",
            "dispersion_plot (PNG)",
            "evidence_card (JSON/Markdown)",
            "provenance_sidecar (JSON)",
        ],
        evidence_requirements=EvidenceRequirement(
            multiple_testing="required",
            effect_size="required",
            min_fdr_alpha=0.05,
            mandatory_limitations=[
                "Condition DE requires pseudobulk replicate aggregation to prevent false discoveries from single-cell pseudoreplication.",
                "Research Use Only. Not for clinical diagnosis.",
            ],
        ),
        forbidden_claims=[
            "causal_interaction",
            "clinical_diagnosis",
            "treatment_recommendation",
        ],
        evidence_ceiling_without_external_validation="SUPPORTED",
    ),
    # 2. Single-cell Exploratory Clustering & Markers
    "scrna.exploratory_clustering": CapabilityContract(
        id="scrna.exploratory_clustering",
        version=1,
        display_name="Single-Cell Exploratory Clustering & Marker Identification",
        skill_name="single-cell-rna-qc",
        summary="scverse exploratory workflow: MAD QC, normalization, HVG, PCA, UMAP, Leiden clustering, and Wilcoxon marker detection.",
        intent=[
            "cluster_cells",
            "scrna_clustering",
            "marker_genes",
            "dimension_reduction",
            "umap_visualization",
        ],
        inputs={
            "counts": InputSpecification(
                name="counts",
                semantic_type=SemanticInputType.RAW_COUNTS.value,
                required=True,
                description="Single-cell count matrix (.h5ad/.h5).",
                validation_rule="audit_expression_matrix:counts",
            ),
        },
        preconditions=[
            Precondition(
                id="min_cells_and_genes",
                rule="n_cells >= 20 and n_genes >= 100",
                description="Sufficient cells and features for meaningful manifold learning.",
                fatal_if_violated=True,
            ),
        ],
        backend=BackendRequirement(
            canonical_name="scanpy",
            import_name="scanpy",
            minimum_version="1.10.0",
            extra="goldchain",
            entry_points=("scanpy.pp", "scanpy.tl"),
            description="Scanpy single-cell analysis toolkit",
        ),
        refusal_conditions=[
            RefusalTrigger(
                condition_id="missing_backend",
                description="Scanpy or anndata is not installed.",
                remedy="Install via `pip install bionexus-reliability[goldchain]` or `pip install scanpy anndata`.",
                violated_rule="scverse gold chain backend requirement",
            ),
            RefusalTrigger(
                condition_id="hallucinated_cell_types",
                description="Attempting to fabricate biological cell type identity without validated reference markers.",
                remedy="Keep cluster identifiers numeric ('0', '1', '2') unless validated against reference atlases.",
                violated_rule="Zero hallucination of cell-type identity invariant",
            ),
        ],
        outputs=[
            "clustered_anndata (.h5ad)",
            "marker_genes_table (CSV)",
            "umap_leiden_plot (PNG)",
            "dotplot_markers (PNG)",
            "evidence_card (JSON/Markdown)",
        ],
        evidence_requirements=EvidenceRequirement(
            multiple_testing="required",
            effect_size="required",
            mandatory_limitations=[
                "Cluster labels are numeric only. Biological cell types must be verified with orthogonal references.",
                "Marker p-values from rank_genes_groups are exploratory and must not be cited as treatment condition DE.",
            ],
        ),
        forbidden_claims=[
            "cell_type_identity_without_reference",
            "causal_interaction",
            "clinical_diagnosis",
        ],
        evidence_ceiling_without_external_validation="PRELIMINARY",
    ),
    # 3. Spatial Transcriptomics Moran's I SVG Detection
    "spatial.morans_svg": CapabilityContract(
        id="spatial.morans_svg",
        version=1,
        display_name="Spatial Transcriptomics Spatially Variable Gene Detection",
        skill_name="spatial-transcriptomics",
        summary="Squidpy spatial KNN graph construction, Moran's I spatial autocorrelation, and spatial scatter plots.",
        intent=[
            "spatial_transcriptomics",
            "spatially_variable_genes",
            "morans_i",
            "spatial_patterns",
            "visium_analysis",
        ],
        inputs={
            "expression": InputSpecification(
                name="expression",
                semantic_type=SemanticInputType.NORMALIZED_MATRIX.value,
                required=True,
                description="Spatial transcriptomics expression matrix (.h5ad / SpatialData .zarr).",
            ),
            "coordinates": InputSpecification(
                name="coordinates",
                semantic_type=SemanticInputType.SPATIAL_COORDINATES.value,
                required=True,
                description="2D/3D spatial coordinate matrix (adata.obsm['spatial']).",
                validation_rule="audit_spatial_coordinates",
            ),
            "spatial_state": InputSpecification(
                name="spatial_state",
                semantic_type=SemanticInputType.BIGDATA_STORE.value,
                required=True,
                description=(
                    "Expression, gene names, cell labels, coordinate system, and immutable dataset/state/"
                    "segmentation/label revision identifiers; exact contact graph and covariates when applicable."
                ),
            ),
        },
        preconditions=[
            Precondition(
                id="spatial_coords_present",
                rule="'spatial' in adata.obsm and shape[1] in (2, 3)",
                description="Spatial coordinates must be present in obsm['spatial'].",
                fatal_if_violated=True,
            ),
            Precondition(
                id="non_degenerate_geometry",
                rule="variance(spatial_coords) > 1e-8",
                description="Coordinates must have non-zero variance along spatial axes.",
                fatal_if_violated=True,
            ),
        ],
        backend=BackendRequirement(
            canonical_name="squidpy",
            import_name="squidpy",
            minimum_version="1.3.0",
            extra="spatial",
            entry_points=("squidpy.gr.spatial_neighbors", "squidpy.gr.spatial_autocorr"),
            description="Squidpy spatial analysis library",
        ),
        refusal_conditions=[
            RefusalTrigger(
                condition_id="missing_coordinates",
                description="Dataset contains no spatial coordinate arrays.",
                remedy="Provide spatial data containing obsm['spatial'] (Visium, Slide-seq, MERFISH, or SpatialData).",
                violated_rule="Spatial geometry requirement",
            ),
            RefusalTrigger(
                condition_id="missing_backend",
                description="Squidpy library not available.",
                remedy="Install via `pip install bionexus-reliability[spatial]` or `pip install squidpy spatialdata`.",
                violated_rule="Squidpy spatial backend requirement",
            ),
        ],
        outputs=[
            "spatially_variable_genes_table (CSV)",
            "spatial_scatter_plot (PNG)",
            "moran_i_distribution (PNG)",
            "evidence_card (JSON/Markdown)",
        ],
        evidence_requirements=EvidenceRequirement(
            multiple_testing="required",
            effect_size="required",
            min_fdr_alpha=0.05,
            mandatory_limitations=[
                "Spatial Moran's I identifies spatial autocorrelation, not mechanistic cell-cell signaling.",
                "Research Use Only.",
            ],
        ),
        forbidden_claims=[
            "causal_interaction",
            "cell_cell_communication",
            "cell_type_identity_without_reference",
        ],
        evidence_ceiling_without_external_validation="FRAGILE",
    ),
    # 4. Clinical Cohort Kaplan-Meier Survival Analysis
    "survival.kaplan_meier": CapabilityContract(
        id="survival.kaplan_meier",
        version=1,
        display_name="Clinical Cohort Kaplan-Meier Survival Estimation & Log-Rank Test",
        skill_name="clinical-cohort-analysis",
        summary="Non-parametric Kaplan-Meier survival curve estimation, log-rank hazard equality tests, and median survival confidence intervals.",
        intent=[
            "survival_analysis",
            "kaplan_meier",
            "log_rank_test",
            "cohort_stratification",
            "prognostic_biomarker",
        ],
        inputs={
            "duration": InputSpecification(
                name="duration",
                semantic_type=SemanticInputType.SURVIVAL_DATA.value,
                required=True,
                description="Time-to-event or last follow-up duration array (positive numbers).",
            ),
            "event": InputSpecification(
                name="event",
                semantic_type=SemanticInputType.SURVIVAL_DATA.value,
                required=True,
                description="Binary event indicator (1 = event/death, 0 = censored).",
            ),
            "group": InputSpecification(
                name="group",
                semantic_type=SemanticInputType.SAMPLE_METADATA.value,
                required=True,
                description="Categorical patient stratification group (e.g. Biomarker High vs Low).",
            ),
        },
        preconditions=[
            Precondition(
                id="positive_durations",
                rule="all(durations >= 0)",
                description="All follow-up durations must be non-negative.",
                fatal_if_violated=True,
            ),
            Precondition(
                id="non_zero_events",
                rule="sum(events) > 0",
                description="At least one observed event required to compute survival probability.",
                fatal_if_violated=True,
            ),
        ],
        backend=BackendRequirement(
            canonical_name="lifelines",
            import_name="lifelines",
            minimum_version="0.27.0",
            extra="survival",
            entry_points=("lifelines.KaplanMeierFitter", "lifelines.CoxPHFitter"),
            description="Lifelines survival analysis library",
        ),
        refusal_conditions=[
            RefusalTrigger(
                condition_id="all_censored",
                description="Zero events observed in cohort (100% censoring).",
                remedy="Survival estimation requires at least one uncensored event.",
                violated_rule="Event observation requirement",
            ),
            RefusalTrigger(
                condition_id="missing_backend",
                description="Lifelines survival package not installed.",
                remedy="Install via `pip install bionexus-reliability[survival]` or `pip install lifelines`.",
                violated_rule="Survival analysis backend requirement",
            ),
        ],
        outputs=[
            "kaplan_meier_curve (PNG)",
            "log_rank_test_summary (CSV/JSON)",
            "median_survival_table (CSV)",
            "evidence_card (JSON/Markdown)",
        ],
        evidence_requirements=EvidenceRequirement(
            multiple_testing="optional",
            effect_size="required",
            mandatory_limitations=[
                "Kaplan-Meier estimates unadjusted univariate associations and does not control for confounding clinical covariates.",
                "Research Use Only. Not for individual clinical treatment assignment.",
            ],
        ),
        forbidden_claims=[
            "hazard_causation",
            "clinical_diagnosis",
            "treatment_recommendation",
        ],
        evidence_ceiling_without_external_validation="SUPPORTED",
    ),
    # 5. scvi-tools Deep Generative Modeling
    "scvi.probabilistic_vae": CapabilityContract(
        id="scvi.probabilistic_vae",
        version=1,
        display_name="scvi-tools Deep Generative Latent Modeling & Integration",
        skill_name="scvi-tools",
        summary="Train official scvi-tools variational autoencoder models (scVI, scANVI, totalVI) on raw counts for batch correction and latent representation.",
        intent=[
            "train_scvi",
            "batch_integration",
            "latent_embedding",
            "deep_generative_model",
            "zero_shot_imputation",
        ],
        inputs={
            "counts": InputSpecification(
                name="counts",
                semantic_type=SemanticInputType.RAW_COUNTS.value,
                required=True,
                description="Raw un-normalized single-cell count matrix.",
                validation_rule="audit_expression_matrix:counts",
            ),
        },
        preconditions=[
            Precondition(
                id="raw_counts_only",
                rule="is_integer_like(counts) == True",
                description="scvi-tools models the discrete data-generating process (Negative Binomial/ZINB) and strictly requires un-normalized raw counts.",
                fatal_if_violated=True,
            ),
        ],
        backend=BackendRequirement(
            canonical_name="scvi-tools",
            import_name="scvi",
            minimum_version="1.0.0",
            extra="scverse",
            entry_points=("scvi.model.SCVI",),
            description="scvi-tools probabilistic generative modeling framework",
        ),
        refusal_conditions=[
            RefusalTrigger(
                condition_id="normalized_input",
                description="Log-normalized or scaled float matrix provided instead of raw counts.",
                remedy="Train scvi-tools models exclusively on raw integer counts (adata.raw.X or layer='counts'). Do not log-transform beforehand.",
                violated_rule="Discrete likelihood distribution invariant",
            ),
            RefusalTrigger(
                condition_id="missing_backend",
                description="scvi-tools and PyTorch packages are not installed.",
                remedy="Install via `pip install bionexus-reliability[scverse]` or `pip install scvi-tools torch`.",
                violated_rule="scvi-tools backend requirement",
            ),
        ],
        outputs=[
            "latent_representation (adata.obsm['X_scVI'])",
            "trained_model_checkpoint",
            "normalized_expression_denoised",
            "evidence_card (JSON/Markdown)",
        ],
        evidence_requirements=EvidenceRequirement(
            multiple_testing="optional",
            effect_size="required",
            uncertainty_quantification="required",
            mandatory_limitations=[
                "scVI embeddings represent a probabilistic latent space and do not guarantee biological cell-type identity.",
                "Requires GPU acceleration for large datasets (>50k cells).",
            ],
        ),
        forbidden_claims=[
            "cell_type_identity_without_reference",
            "true_expression_recovery",
            "clinical_diagnosis",
        ],
        evidence_ceiling_without_external_validation="PRELIMINARY",
    ),
    # 6. Instrument Table to Allotrope ASM Standardization
    "allotrope.format_conversion": CapabilityContract(
        id="allotrope.format_conversion",
        version=1,
        display_name="Analytical Instrument Table to Allotrope ASM JSON Standardization",
        skill_name="instrument-data-to-allotrope",
        summary="Convert laboratory instrument tabular outputs (plate readers, qPCR, chromatography, spectrophotometry) to standardized Allotrope Simple Model (ASM) JSON.",
        intent=[
            "allotrope_conversion",
            "standardize_instrument_data",
            "plate_reader_parser",
            "lims_ingest",
            "asm_json",
        ],
        inputs={
            "raw_file": InputSpecification(
                name="raw_file",
                semantic_type=SemanticInputType.INSTRUMENT_TABLE.value,
                required=True,
                description="Analytical instrument export file (.csv, .xlsx, .txt).",
            ),
        },
        preconditions=[
            Precondition(
                id="supported_instrument_or_mapping",
                rule="has_native_adapter(file) or has_yaml_mapping(file)",
                description="File format must match a supported allotropy parser or custom YAML mapping configuration.",
                fatal_if_violated=True,
            ),
        ],
        backend=BackendRequirement(
            canonical_name="allotropy",
            import_name="allotropy",
            minimum_version="0.1.30",
            extra="allotrope",
            entry_points=("allotropy",),
            description="Allotropy open-source instrument parser library",
        ),
        refusal_conditions=[
            RefusalTrigger(
                condition_id="missing_mapping",
                description="Instrument file format is unrecognized and no custom YAML mapping was provided.",
                remedy="Provide an allotropy-compatible vendor export or create a declarative YAML mapping schema.",
                violated_rule="Deterministic data transformation invariant",
            ),
            RefusalTrigger(
                condition_id="missing_backend",
                description="allotropy parser package not installed.",
                remedy="Install via `pip install bionexus-reliability[allotrope]` or `pip install allotropy`.",
                violated_rule="Allotropy backend requirement",
            ),
        ],
        outputs=[
            "allotrope_asm_record (.json)",
            "flattened_2d_table (.csv)",
            "evidence_card (JSON/Markdown)",
            "provenance_sidecar (JSON)",
        ],
        evidence_requirements=EvidenceRequirement(
            multiple_testing="not_applicable",
            effect_size="not_applicable",
            mandatory_limitations=[
                "Conversion maps syntax and schema only; does not validate analytical sensor calibration.",
                "Research Use Only. Not an FDA 21 CFR Part 11 certified data converter.",
            ],
        ),
        forbidden_claims=[
            "sensor_calibration_validated",
            "regulatory_compliance",
        ],
        evidence_ceiling_without_external_validation="PRELIMINARY",
    ),
    # 7. Nextflow Pipeline Launch Artifacts & Cluster Preflight
    "nextflow.pipeline_launch": CapabilityContract(
        id="nextflow.pipeline_launch",
        version=1,
        display_name="Nextflow nf-core Samplesheet & Launch Artifact Preparation",
        skill_name="nextflow-development",
        summary="Generate canonical nf-core samplesheets, validate execution profiles, and generate reproducibility launch commands for Slurm/AWS/GCP.",
        intent=[
            "nextflow_pipeline",
            "nf_core_samplesheet",
            "cluster_config",
            "batch_compute_launch",
            "rnaseq_pipeline",
        ],
        inputs={
            "sample_manifest": InputSpecification(
                name="sample_manifest",
                semantic_type=SemanticInputType.SAMPLE_METADATA.value,
                required=True,
                description="Directory of FASTQ/BAM files or raw sample CSV metadata.",
            ),
        },
        preconditions=[
            Precondition(
                id="valid_paired_reads",
                rule="fastq_1 and (fastq_2 or is_single_end)",
                description="Sequencing read paths must resolve to valid existing FASTQ files.",
                fatal_if_violated=True,
            ),
        ],
        backend=BackendRequirement(
            canonical_name="nf-core",
            import_name="bionexus",
            minimum_version="0.8.0",
            extra="dev",
            description="nf-core sample generator and cluster launch compiler",
        ),
        refusal_conditions=[
            RefusalTrigger(
                condition_id="missing_fastq_files",
                description="Specified sequencing read files do not exist on disk.",
                remedy="Check sample path patterns and provide valid absolute paths to raw sequencing files.",
                violated_rule="File existence prerequisite",
            ),
        ],
        outputs=[
            "samplesheet.csv",
            "nextflow.config",
            "launch_command.sh",
            "evidence_card (JSON/Markdown)",
        ],
        evidence_requirements=EvidenceRequirement(
            multiple_testing="not_applicable",
            effect_size="not_applicable",
            mandatory_limitations=[
                "Generates deployment configurations; pipeline execution requires Nextflow runtime and container engine (Docker/Singularity).",
            ],
        ),
        forbidden_claims=[
            "pipeline_results_without_execution",
            "regulatory_compliance",
        ],
        evidence_ceiling_without_external_validation="PRELIMINARY",
    ),
    # 8. Deterministic ACMG Variant Tiering
    "variant.acmg_classification": CapabilityContract(
        id="variant.acmg_classification",
        version=1,
        display_name="Deterministic ACMG/AMP Genetic Variant Pathogenicity Classification",
        skill_name="variant-interpretation",
        summary="Deterministic Bayesian and rule-based combination of caller-supplied ACMG/AMP criteria (PVS1, PS1-4, PM1-6, PP1-5, BA1, BS1-4, BP1-7).",
        intent=[
            "variant_interpretation",
            "acmg_classification",
            "pathogenicity_scoring",
            "clinical_genetics",
            "variant_tiering",
        ],
        inputs={
            "variant_id": InputSpecification(
                name="variant_id",
                semantic_type=SemanticInputType.VARIANT_RECORDS.value,
                required=True,
                description="Genomic variant HGVS descriptor or coordinate string.",
            ),
            "acmg_codes": InputSpecification(
                name="acmg_codes",
                semantic_type=SemanticInputType.SAMPLE_METADATA.value,
                required=True,
                description="Caller-verified ACMG criteria codes with evidence rationales.",
            ),
        },
        preconditions=[
            Precondition(
                id="no_auto_pvs1_without_mechanism",
                rule="pvs1_applied -> lof_mechanism_verified == True",
                description="PVS1 null variant criterion strictly requires verified loss-of-function disease mechanism for the target gene.",
                fatal_if_violated=True,
            ),
        ],
        backend=BackendRequirement(
            canonical_name="local combiner",
            import_name="bionexus",
            minimum_version="0.8.0",
            description="Deterministic ACMG/AMP Bayesian posterior combiner",
        ),
        refusal_conditions=[
            RefusalTrigger(
                condition_id="unverified_clinical_diagnosis",
                description="Attempting to issue formal clinical diagnostic report without CLIA/CAP certification.",
                remedy="Attach mandatory RUO disclaimer. Output must state 'Research Use Only' and cannot be used for direct patient management.",
                violated_rule="Regulatory and clinical honesty invariant",
            ),
        ],
        outputs=[
            "acmg_classification_record (JSON)",
            "clinical_monograph (Markdown)",
            "posterior_probability_score",
            "evidence_card (JSON/Markdown)",
        ],
        evidence_requirements=EvidenceRequirement(
            multiple_testing="not_applicable",
            effect_size="required",
            mandatory_limitations=[
                "Deterministic combiner only; does not query live clinical registries (ClinVar/gnomAD) unless MCP tools are connected.",
                "Research Use Only. Not for clinical diagnostic use.",
            ],
        ),
        forbidden_claims=[
            "clinical_diagnosis",
            "treatment_recommendation",
        ],
        evidence_ceiling_without_external_validation="ROBUST",
    ),
    # 9. Cell Annotation Evidence Assessment (flagship capability B, BNS-013)
    "scrna.annotation_evidence": CapabilityContract(
        id="scrna.annotation_evidence",
        version=1,
        display_name="Cell Annotation Evidence Assessment",
        skill_name="single-cell-rna-qc",
        summary=(
            "Not another annotator: assesses how much evidence backs each candidate cell-type label "
            "(reference mapping, marker consistency, negative markers, doublet risk, ontology compatibility, "
            "open-set detection, cross-method agreement) and returns per-label verdicts."
        ),
        intent=[
            "annotation_evidence",
            "label_support",
            "cell_type_verification",
            "open_set_annotation",
            "annotation_audit",
        ],
        inputs={
            "expression": InputSpecification(
                name="expression",
                semantic_type=SemanticInputType.NORMALIZED_MATRIX.value,
                required=True,
                description="Cell-level expression used for marker consistency and doublet assessment.",
            ),
            "candidate_labels": InputSpecification(
                name="candidate_labels",
                semantic_type=SemanticInputType.SAMPLE_METADATA.value,
                required=True,
                description="Candidate label assignment per cluster or per cell to be assessed (never asserted).",
            ),
            "reference": InputSpecification(
                name="reference",
                semantic_type=SemanticInputType.SAMPLE_METADATA.value,
                required=False,
                description="Reference atlas mapping or curated marker panel with positive and negative markers.",
            ),
        },
        preconditions=[
            Precondition(
                id="annotation_source_recorded",
                rule="every non-numeric label cites an evidence source",
                description="A label without a recorded evidence source is a candidate, not an identity (BNS-II-008).",
                fatal_if_violated=True,
            ),
            Precondition(
                id="negative_markers_evaluated",
                rule="negative_marker_violation is measured or explicitly declared unmeasured",
                description="Positive-marker coherence alone cannot separate related lineages.",
                fatal_if_violated=False,
            ),
        ],
        backend=BackendRequirement(
            canonical_name="local deterministic evidence combiner",
            import_name="bionexus",
            minimum_version="0.10.0",
            description="Deterministic annotation-evidence scoring (annotation_evidence.assess_annotation_evidence)",
            entry_points=("bionexus.annotation_evidence",),
        ),
        refusal_conditions=[
            RefusalTrigger(
                condition_id="no_annotation_evidence",
                description="No reference mapping, marker panel, or cross-method evidence is available for the labels.",
                remedy="Keep labels numeric or explicitly putative; attach a reference atlas or curated marker panel with negative markers.",
                violated_rule="Annotation evidence requirement (BN-F003)",
            ),
            RefusalTrigger(
                condition_id="open_set_population",
                description="An unknown/open-set population is being forced onto a known reference label.",
                remedy="Report the population as unknown/novel (ABSTAIN verdict) until orthogonal evidence is collected.",
                violated_rule="Open-set honesty invariant (BN-F003)",
            ),
        ],
        outputs=[
            "per_label_verdicts (SUPPORTED | TENTATIVE | ABSTAIN) (JSON/CSV)",
            "missing_evidence_requests (list)",
            "evidence_card (JSON/Markdown)",
        ],
        evidence_requirements=EvidenceRequirement(
            multiple_testing="optional",
            effect_size="recommended",
            mandatory_limitations=[
                "Verdicts describe evidence support for labels, not ground-truth identity.",
                "ABSTAIN for open-set labels is the honest answer, not a failure.",
            ],
        ),
        forbidden_claims=[
            "cell_type_identity_without_reference",
            "causal_interaction",
            "clinical_diagnosis",
        ],
        evidence_ceiling_without_external_validation="SUPPORTED",
    ),
    # 10. Spatial Inference Validity Assessment (flagship capability C, BNS-013)
    "spatial.inference_validity": CapabilityContract(
        id="spatial.inference_validity",
        version=2,
        display_name="Spatial Alternative Explanation Battery",
        skill_name="spatial-transcriptomics",
        summary=(
            "An executable, empirically calibrated challenge battery for a declared spatial observation: tests "
            "segmentation perturbations, transcript leakage, morphology, density, contact geometry, batch/FOV, "
            "neighborhood radius, coordinate nulls, and cell-label perturbations. It does not run a generic "
            "spatial workflow or silently substitute expert magic numbers."
        ),
        intent=[
            "spatial_inference_validity",
            "alternative_explanation_testing",
            "spatial_conclusion_robustness",
            "spatial_confound_audit",
        ],
        inputs={
            "observation": InputSpecification(
                name="observation",
                semantic_type=SemanticInputType.SAMPLE_METADATA.value,
                required=True,
                description="The spatial finding under test, stated as an observation (not a mechanism).",
            ),
            "coordinates": InputSpecification(
                name="coordinates",
                semantic_type=SemanticInputType.SPATIAL_COORDINATES.value,
                required=True,
                description="Physical spatial coordinates in micrometers; embeddings are not accepted.",
                validation_rule="audit_spatial_coordinates",
            ),
            "alternative_controls": InputSpecification(
                name="alternative_controls",
                semantic_type=SemanticInputType.SAMPLE_METADATA.value,
                required=False,
                description="Status of each alternative-explanation control (TESTED / CONTROLLED / UNTESTED / FAILED).",
            ),
            "battery_plan": InputSpecification(
                name="battery_plan",
                semantic_type=SemanticInputType.SAMPLE_METADATA.value,
                required=True,
                description=(
                    "Predeclared radii, leakage sensitivity, perturbation counts, seed, minimum group size, and "
                    "graph bound for executable alternative-explanation testing."
                ),
            ),
        },
        preconditions=[
            Precondition(
                id="coordinate_provenance_recorded",
                rule="coordinate origin is physical tissue space in micrometers",
                description="Embeddings substituted for tissue coordinates invalidate spatial statistics (BNS-II-006).",
                fatal_if_violated=True,
            ),
            Precondition(
                id="core_confound_controls_tested",
                rule=(
                    "cell_size, transcript_density, segmentation_uncertainty, transcript_leakage, and "
                    "contact_geometry are TESTED or CONTROLLED"
                ),
                description="The canonical spatial confound controls must be addressed before any validity verdict.",
                fatal_if_violated=False,
            ),
        ],
        backend=BackendRequirement(
            canonical_name="local deterministic alternative-explanation tester",
            import_name="bionexus",
            minimum_version="0.10.0",
            description=(
                "Bounded perturbation battery with profile-conditioned warrant decisions "
                "(spatial_alternative_battery.run_spatial_alternative_battery)"
            ),
            entry_points=(
                "bionexus.spatial_alternative_battery",
                "bionexus.spatial_inference",
            ),
        ),
        refusal_conditions=[
            RefusalTrigger(
                condition_id="no_controls_provided",
                description="Validity requested with zero alternative-explanation controls.",
                remedy=(
                    "Run the bounded battery with segmentation/leakage variants, morphology and density covariates, "
                    "contact geometry, radius sensitivity, coordinate nulls, and label perturbations."
                ),
                violated_rule="Alternative-explanation requirement (BN-F006)",
            ),
            RefusalTrigger(
                condition_id="embedding_substitution",
                description="UMAP/PCA coordinates offered where physical tissue coordinates are required.",
                remedy="Provide physical tissue coordinates in micrometers; no embedding fallback is permitted.",
                violated_rule="Spatial provenance invariant (BN-F009)",
            ),
        ],
        outputs=[
            "alternative_explanation_battery (per-control scores, perturbations, and calibration resolution) (JSON)",
            "validity_verdict (ROBUST | SUPPORTED | FRAGILE | CONFLICTED | ABSTAIN)",
            "unresolved_alternatives (list)",
            "state-bound provenance and input hashes",
            "evidence_card (JSON/Markdown)",
        ],
        evidence_requirements=EvidenceRequirement(
            multiple_testing="recommended",
            effect_size="recommended",
            mandatory_limitations=[
                "A FRAGILE verdict names the untested alternatives, not a negative result.",
                "An unapproved or absent empirical calibration profile cannot produce a CONTROLLED diagnostic.",
                "Assumed leakage fractions are sensitivity analyses, not estimates of true transcript leakage.",
                "Orthogonal validation is required to assert beyond FRAGILE for confound-sensitive observations.",
            ],
        ),
        forbidden_claims=[
            "causal_interaction",
            "cell_cell_communication",
            "cell_type_identity_without_reference",
        ],
        evidence_ceiling_without_external_validation="FRAGILE",
    ),
    # 11. HPC & Cloud-Native Batch Job Generation, Dispatch & Lifecycle Management
    "cluster.hpc_dispatch": CapabilityContract(
        id="cluster.hpc_dispatch",
        version=1,
        display_name="HPC & Cloud-Native Batch Job Generation, Dispatch & Lifecycle Management",
        skill_name="nextflow-development",
        summary="Generate native batch scripts (Slurm/PBS/LSF/Kubernetes/AWS/GCP), submit jobs, track queue status, and perform OOM/timeout post-mortem diagnosis.",
        intent=[
            "cluster_dispatch",
            "hpc_submit",
            "slurm_job",
            "batch_job",
            "cloud_compute",
            "job_diagnostics",
            "kubernetes_job",
        ],
        inputs={
            "command": InputSpecification(
                name="command",
                semantic_type=SemanticInputType.COMPUTE_SPECIFICATION.value,
                required=True,
                description="Bioinformatics command line string or list of execution commands.",
            ),
        },
        preconditions=[
            Precondition(
                id="positive_cpus_and_memory",
                rule="cpus > 0 and memory_specified == True",
                description="HPC batch jobs must declare valid positive CPU and memory allocation limits.",
                fatal_if_violated=True,
            ),
        ],
        backend=BackendRequirement(
            canonical_name="bionexus-cluster",
            import_name="bionexus.cluster",
            minimum_version="0.9.0",
            description="BioNexus unified HPC and cloud batch dispatcher",
            entry_points=("bionexus.cluster",),
        ),
        refusal_conditions=[
            RefusalTrigger(
                condition_id="unsupported_scheduler",
                description="Target scheduler is not recognized or supported by BioNexus.",
                remedy="Select a supported scheduler: slurm, pbs, lsf, sge, kubernetes, aws_batch, or gcp_batch.",
                violated_rule="Scheduler compatibility rule",
            ),
        ],
        outputs=[
            "job_script (bash/YAML/JSON)",
            "job_id",
            "job_submission_result (JSON)",
            "job_diagnostic_report (Markdown/JSON)",
        ],
        evidence_requirements=EvidenceRequirement(
            multiple_testing="not_applicable",
            effect_size="not_applicable",
            mandatory_limitations=[
                "Generates and dispatches batch job manifests; execution outcome depends on remote cluster infrastructure health.",
            ],
        ),
        forbidden_claims=[
            "pipeline_results_without_execution",
            "regulatory_compliance",
        ],
        evidence_ceiling_without_external_validation="SUPPORTED",
    ),
    # 12. Large-Scale Biological Matrix Memory Estimation & Out-of-Core Streaming Audit
    "bigdata.out_of_core_audit": CapabilityContract(
        id="bigdata.out_of_core_audit",
        version=1,
        display_name="Large-Scale Biological Matrix Memory Estimation & Out-of-Core Streaming Audit",
        skill_name="single-cell-rna-qc",
        summary="Audit storage format, estimate RAM requirements for multi-million cell datasets, prevent OOM crashes, and generate out-of-core streaming execution plans.",
        intent=[
            "bigdata_audit",
            "memory_estimation",
            "out_of_core",
            "zarr_streaming",
            "oom_prevention",
            "large_matrix_plan",
        ],
        inputs={
            "matrix_dimensions": InputSpecification(
                name="matrix_dimensions",
                semantic_type=SemanticInputType.BIGDATA_STORE.value,
                required=True,
                description="Dataset dimensions (n_cells, n_genes) or file path to H5AD/Zarr store.",
            ),
        },
        preconditions=[
            Precondition(
                id="valid_positive_dimensions",
                rule="n_cells > 0 and n_genes > 0",
                description="Dataset matrix dimensions must be non-zero positive integers.",
                fatal_if_violated=True,
            ),
        ],
        backend=BackendRequirement(
            canonical_name="bionexus-bigdata",
            import_name="bionexus.bigdata",
            minimum_version="0.9.0",
            description="BioNexus large-scale matrix memory and streaming estimator",
            entry_points=("bionexus.bigdata",),
        ),
        refusal_conditions=[
            RefusalTrigger(
                condition_id="critical_oom_in_memory",
                description="Attempting to perform in-memory dense matrix operations that exceed 200% of host RAM.",
                remedy="Must switch to AnnData backed mode (backed='r'), convert to chunked Zarr, or dispatch to HPC cluster with higher RAM.",
                violated_rule="Host memory safety invariant",
            ),
        ],
        outputs=[
            "memory_estimation_report (JSON)",
            "streaming_execution_plan (Markdown)",
            "storage_audit_report (JSON)",
        ],
        evidence_requirements=EvidenceRequirement(
            multiple_testing="not_applicable",
            effect_size="not_applicable",
            mandatory_limitations=[
                "Calculates theoretical and empirical working memory bounds based on sparse/dense representations.",
            ],
        ),
        forbidden_claims=[
            "regulatory_compliance",
        ],
        evidence_ceiling_without_external_validation="SUPPORTED",
    ),
    # 13. Spatial Transcriptomics Tangram Single-Cell to Spatial Deconvolution
    "spatial.tangram_deconvolution": CapabilityContract(
        id="spatial.tangram_deconvolution",
        version=1,
        display_name="Spatial Transcriptomics Tangram Single-Cell to Spatial Deconvolution",
        skill_name="spatial-transcriptomics",
        summary="Optimal transport & deep learning mapping of single-cell reference transcriptomes to spatial coordinates with spot deconvolution.",
        intent=[
            "tangram_mapping",
            "spatial_deconvolution",
            "spot_deconvolution",
            "cell_to_space",
            "visium_deconvolution",
        ],
        inputs={
            "sc_reference": InputSpecification(
                name="sc_reference",
                semantic_type=SemanticInputType.RAW_COUNTS.value,
                required=True,
                description="Annotated single-cell RNA-seq reference AnnData.",
            ),
            "spatial_target": InputSpecification(
                name="spatial_target",
                semantic_type=SemanticInputType.SPATIAL_COORDINATES.value,
                required=True,
                description="Spatial transcriptomics AnnData containing obsm['spatial'].",
                validation_rule="audit_spatial_coordinates",
            ),
        },
        preconditions=[
            Precondition(
                id="spatial_coords_present",
                rule="'spatial' in spatial_adata.obsm and shape[1] in (2, 3)",
                description="Spatial coordinates must be present in target obsm['spatial'].",
                fatal_if_violated=True,
            ),
            Precondition(
                id="reference_cell_types_present",
                rule="cell_type_col in sc_adata.obs",
                description="Single-cell reference must contain cell type annotations in obs.",
                fatal_if_violated=True,
            ),
            Precondition(
                id="shared_genes_sufficient",
                rule="len(shared_marker_genes) >= 10",
                description="At least 10 marker genes must overlap between single-cell reference and spatial target.",
                fatal_if_violated=True,
            ),
        ],
        backend=BackendRequirement(
            canonical_name="tangram-sc",
            import_name="tangram",
            minimum_version="1.0.4",
            extra="spatial",
            entry_points=("tangram.mapper",),
            description="Tangram optimal transport spatial mapping library",
        ),
        refusal_conditions=[
            RefusalTrigger(
                condition_id="missing_coordinates",
                description="Spatial target contains no 2D/3D coordinate arrays.",
                remedy="Ensure spatial AnnData contains valid 2D coordinates in obsm['spatial'].",
                violated_rule="Spatial geometry requirement",
            ),
            RefusalTrigger(
                condition_id="unannotated_reference",
                description="Single-cell reference lacks cell type annotations.",
                remedy="Provide single-cell AnnData with labeled cell types in obs (e.g. obs['cell_type']).",
                violated_rule="Reference annotation requirement",
            ),
            RefusalTrigger(
                condition_id="insufficient_shared_genes",
                description="Fewer than 10 marker genes overlap between scRNA and spatial target.",
                remedy="Harmonize gene symbol / Ensembl ID nomenclature between single-cell and spatial datasets.",
                violated_rule="Feature overlap requirement",
            ),
        ],
        outputs=[
            "tangram_cell_proportions (adata_sp.obsm['tangram_ct_pred'])",
            "dominant_cell_types (adata_sp.obs['dominant_cell_type'])",
            "cell_to_spot_mapping_matrix (.h5ad)",
            "deconvolution_summary (CSV)",
            "evidence_card (JSON/Markdown)",
        ],
        evidence_requirements=EvidenceRequirement(
            multiple_testing="not_applicable",
            effect_size="not_applicable",
            mandatory_limitations=[
                "Predicted spot proportions represent probabilistic optimal transport weights, not physical microscopic counting.",
                "Research Use Only. Not for clinical diagnosis.",
            ],
        ),
        forbidden_claims=[
            "clinical_diagnosis",
            "causal_interaction",
            "cell_type_identity_without_reference",
        ],
        evidence_ceiling_without_external_validation="SUPPORTED",
    ),
}

# ==============================================================================
# Frontier / Experimental Capabilities (BNS-010 / Research Track)
# Segregated from Stable Canonical v1.0 Release.
# ==============================================================================

FRONTIER_CAPABILITIES: Dict[str, CapabilityContract] = {
    # 14. Single-Cell Foundation Model Geneformer Official Inference (Frontier)
    "scfm.geneformer_canonical": CapabilityContract(
        id="scfm.geneformer_canonical",
        version=1,
        display_name="Single-Cell Geneformer Foundation Model Official Inference (Checkpoint Required)",
        skill_name="single-cell-rna-qc",
        summary="Canonical Geneformer rank-value Transformer inference using official pretrained checkpoints (ctheodoris/Geneformer).",
        intent=[
            "geneformer_canonical",
            "geneformer_embedding",
            "geneformer_inference",
            "geneformer_perturbation",
            "foundation_model_embedding",
        ],
        inputs={
            "expression": InputSpecification(
                name="expression",
                semantic_type=SemanticInputType.RAW_COUNTS.value,
                required=True,
                description="Single-cell expression matrix (.h5ad / counts).",
            ),
            "model_checkpoint": InputSpecification(
                name="model_checkpoint",
                semantic_type=SemanticInputType.SAMPLE_METADATA.value,
                required=True,
                description="Path to official pretrained Geneformer checkpoint (e.g. 'ctheodoris/Geneformer' or local weights dir).",
            ),
        },
        preconditions=[
            Precondition(
                id="non_empty_matrix",
                rule="n_cells > 0 and n_genes > 0",
                description="Input single-cell dataset must not be empty.",
                fatal_if_violated=True,
            ),
            Precondition(
                id="checkpoint_specified",
                rule="model_checkpoint is not None",
                description="Canonical Geneformer execution strictly requires an official pretrained model checkpoint.",
                fatal_if_violated=True,
            ),
        ],
        backend=BackendRequirement(
            canonical_name="geneformer-transformers",
            import_name="transformers",
            minimum_version="4.30.0",
            extra="scverse",
            entry_points=("transformers.AutoModel", "transformers.AutoConfig"),
            description="Geneformer rank-value Transformer neural network with official checkpoint weights",
        ),
        refusal_conditions=[
            RefusalTrigger(
                condition_id="missing_checkpoint",
                description="No official Geneformer model checkpoint or weights directory was provided.",
                remedy="Provide official model checkpoint via `model_name_or_path` (e.g. 'ctheodoris/Geneformer' or local dir), or invoke `scfm.rank_proxy_embedding` for Grade C heuristic proxy.",
                violated_rule="Official model checkpoint invariant (BNS-EF-002)",
            ),
            RefusalTrigger(
                condition_id="empty_matrix",
                description="Dataset contains 0 cells or 0 genes.",
                remedy="Provide valid single-cell AnnData count matrix.",
                violated_rule="Matrix non-emptiness rule",
            ),
        ],
        outputs=[
            "cell_embeddings (adata.obsm['X_geneformer'])",
            "perturbation_report (JSON/CSV)",
            "evidence_card (JSON/Markdown)",
        ],
        evidence_requirements=EvidenceRequirement(
            multiple_testing="not_applicable",
            effect_size="not_applicable",
            mandatory_limitations=[
                "Zero-shot embeddings and in silico perturbation shifts are computational hypotheses.",
                "Official model weights must be loaded and disclosed in provenance.",
                "Research Use Only. Not for clinical diagnosis.",
            ],
        ),
        forbidden_claims=[
            "model_substitution",
            "clinical_diagnosis",
            "causal_interaction",
            "cell_type_identity_without_reference",
        ],
        evidence_ceiling_without_external_validation="PRELIMINARY",
    ),
    # 15. Single-Cell Foundation Model scGPT Official Inference (Frontier)
    "scfm.scgpt_canonical": CapabilityContract(
        id="scfm.scgpt_canonical",
        version=1,
        display_name="Single-Cell scGPT Foundation Model Official Inference (Checkpoint Required)",
        skill_name="single-cell-rna-qc",
        summary="Canonical scGPT Generative Transformer inference using official pretrained checkpoints.",
        intent=[
            "scgpt_canonical",
            "scgpt_embedding",
            "scgpt_inference",
            "scgpt_representation",
        ],
        inputs={
            "expression": InputSpecification(
                name="expression",
                semantic_type=SemanticInputType.RAW_COUNTS.value,
                required=True,
                description="Single-cell expression matrix (.h5ad / counts).",
            ),
            "model_checkpoint": InputSpecification(
                name="model_checkpoint",
                semantic_type=SemanticInputType.SAMPLE_METADATA.value,
                required=True,
                description="Path to official pretrained scGPT checkpoint weights.",
            ),
        },
        preconditions=[
            Precondition(
                id="non_empty_matrix",
                rule="n_cells > 0 and n_genes > 0",
                description="Input single-cell dataset must not be empty.",
                fatal_if_violated=True,
            ),
            Precondition(
                id="checkpoint_specified",
                rule="model_checkpoint is not None",
                description="Canonical scGPT execution strictly requires an official pretrained model checkpoint.",
                fatal_if_violated=True,
            ),
        ],
        backend=BackendRequirement(
            canonical_name="scgpt-transformers",
            import_name="transformers",
            minimum_version="4.30.0",
            extra="scverse",
            entry_points=("transformers.AutoModel", "transformers.AutoConfig"),
            description="scGPT generative Transformer neural network with official checkpoint weights",
        ),
        refusal_conditions=[
            RefusalTrigger(
                condition_id="missing_checkpoint",
                description="No official scGPT model checkpoint or weights directory was provided.",
                remedy="Provide official scGPT weights directory, or invoke `scfm.rank_proxy_embedding` for Grade C heuristic proxy.",
                violated_rule="Official model checkpoint invariant (BNS-EF-002)",
            ),
        ],
        outputs=[
            "cell_embeddings (adata.obsm['X_scgpt'])",
            "evidence_card (JSON/Markdown)",
        ],
        evidence_requirements=EvidenceRequirement(
            multiple_testing="not_applicable",
            effect_size="not_applicable",
            mandatory_limitations=[
                "scGPT representations are high-dimensional latent embeddings.",
                "Research Use Only. Not for clinical diagnosis.",
            ],
        ),
        forbidden_claims=[
            "model_substitution",
            "clinical_diagnosis",
            "causal_interaction",
            "cell_type_identity_without_reference",
        ],
        evidence_ceiling_without_external_validation="PRELIMINARY",
    ),
    # 16. Single-Cell Rank-Value SVD Embedding Proxy (Grade C Experimental Frontier)
    "scfm.rank_proxy_embedding": CapabilityContract(
        id="scfm.rank_proxy_embedding",
        version=1,
        display_name="Single-Cell Rank-Value SVD Embedding Proxy (Grade C Experimental)",
        skill_name="single-cell-rna-qc",
        summary="Grade C Experimental: Rank-weighted Truncated SVD embedding proxy for exploratory zero-shot manifold visualization without neural network checkpoints.",
        intent=[
            "rank_proxy_embedding",
            "rank_embedding",
            "scfm_proxy",
            "rank_value_svd",
            "heuristic_rank_embedding",
        ],
        inputs={
            "expression": InputSpecification(
                name="expression",
                semantic_type=SemanticInputType.RAW_COUNTS.value,
                required=True,
                description="Single-cell expression matrix (.h5ad / counts).",
            ),
        },
        preconditions=[
            Precondition(
                id="non_empty_matrix",
                rule="n_cells > 0 and n_genes > 0",
                description="Input single-cell dataset must not be empty.",
                fatal_if_violated=True,
            ),
        ],
        backend=BackendRequirement(
            canonical_name="local rank-svd heuristic proxy (bionexus)",
            import_name="bionexus.scfm",
            minimum_version="0.9.0",
            entry_points=("bionexus.scfm",),
            description="Deterministic rank-weighted Truncated SVD heuristic proxy (Grade C)",
        ),
        refusal_conditions=[
            RefusalTrigger(
                condition_id="model_substitution_attempt",
                description="Attempting to cite or present Rank-SVD proxy output as official Geneformer or scGPT Transformer output.",
                remedy="Acknowledge output as a Grade C experimental rank-weighted SVD proxy, not an official foundation model checkpoint.",
                violated_rule="Epistemic honesty and model attribution invariant (BNS-EF-002)",
            ),
        ],
        outputs=[
            "cell_embeddings (adata.obsm['X_rank_proxy'])",
            "evidence_card (JSON/Markdown)",
        ],
        evidence_requirements=EvidenceRequirement(
            multiple_testing="not_applicable",
            effect_size="not_applicable",
            mandatory_limitations=[
                "Grade C Experimental proxy only. Does not execute deep Transformer attention mechanisms.",
                "Research Use Only. Not for clinical diagnosis.",
            ],
        ),
        forbidden_claims=[
            "model_substitution",
            "clinical_diagnosis",
            "causal_interaction",
            "cell_type_identity_without_reference",
        ],
        evidence_ceiling_without_external_validation="PRELIMINARY",
    ),
    # 17. GEARS Combinatorial Genetic Perturbation Prediction (Frontier)
    "perturbation.gears_prediction": CapabilityContract(
        id="perturbation.gears_prediction",
        version=1,
        display_name="GEARS Graph-Enhanced Single-Cell Genetic Perturbation Modeling",
        skill_name="single-cell-rna-qc",
        summary="Predict post-perturbation transcriptomic states and downstream gene shifts under genetic knockouts or overexpressions using GNNs.",
        intent=[
            "gears_perturbation",
            "genetic_perturbation_prediction",
            "combinatorial_knockout",
            "in_silico_crispr",
        ],
        inputs={
            "expression": InputSpecification(
                name="expression",
                semantic_type=SemanticInputType.RAW_COUNTS.value,
                required=True,
                description="Baseline single-cell expression matrix (.h5ad / counts).",
            ),
        },
        preconditions=[
            Precondition(
                id="non_empty_matrix",
                rule="n_cells > 0 and n_genes > 0",
                description="Input single-cell dataset must not be empty.",
                fatal_if_violated=True,
            ),
        ],
        backend=BackendRequirement(
            canonical_name="gears",
            import_name="gears",
            minimum_version="0.1.0",
            extra="scverse",
            entry_points=("gears",),
            description="GEARS Graph-Enhanced Perturbation Prediction GNN",
        ),
        refusal_conditions=[
            RefusalTrigger(
                condition_id="empty_matrix",
                description="Dataset contains 0 cells or 0 genes.",
                remedy="Provide valid single-cell AnnData count matrix.",
                violated_rule="Matrix non-emptiness rule",
            ),
            RefusalTrigger(
                condition_id="missing_target_genes",
                description="Target perturbation genes are not present in dataset.",
                remedy="Check gene symbol spelling or provide full transcriptome matrix.",
                violated_rule="Target gene presence rule",
            ),
        ],
        outputs=[
            "predicted_perturbed_matrix (adata_perturbed.X)",
            "top_upregulated_genes (List[str])",
            "top_downregulated_genes (List[str])",
            "evidence_card (JSON/Markdown)",
        ],
        evidence_requirements=EvidenceRequirement(
            multiple_testing="not_applicable",
            effect_size="not_applicable",
            mandatory_limitations=[
                "GEARS in silico perturbation shifts are computational predictions.",
                "Experimental validation via CRISPR knockout or qPCR is mandatory.",
                "Research Use Only. Not for clinical diagnosis.",
            ],
        ),
        forbidden_claims=[
            "model_substitution",
            "clinical_diagnosis",
            "causal_interaction",
            "cell_type_identity_without_reference",
        ],
        evidence_ceiling_without_external_validation="PRELIMINARY",
    ),
    # 18. NicheFormer Spatial Niche Forecasting (Frontier)
    "spatial.nicheformer_forecasting": CapabilityContract(
        id="spatial.nicheformer_forecasting",
        version=1,
        display_name="NicheFormer Spatial Microenvironment & Niche Forecasting",
        skill_name="spatial-transcriptomics",
        summary="Forecast spatial niche composition, microenvironment boundaries, and cellular neighborhood shifts using foundation models.",
        intent=[
            "nicheformer_forecasting",
            "spatial_niche_prediction",
            "microenvironment_forecasting",
            "spatial_niche_remodeling",
        ],
        inputs={
            "expression": InputSpecification(
                name="expression",
                semantic_type=SemanticInputType.RAW_COUNTS.value,
                required=True,
                description="Single-cell or spot expression matrix (.h5ad).",
            ),
            "spatial_coordinates": InputSpecification(
                name="spatial_coordinates",
                semantic_type=SemanticInputType.SPATIAL_COORDINATES.value,
                required=True,
                description="Spatial coordinates in adata.obsm['spatial'].",
            ),
        },
        preconditions=[
            Precondition(
                id="spatial_coordinates_present",
                rule="'spatial' in adata.obsm",
                description="Spatial reference must contain 2D coordinates.",
                fatal_if_violated=True,
            ),
        ],
        backend=BackendRequirement(
            canonical_name="nicheformer",
            import_name="nicheformer",
            minimum_version="0.1.0",
            extra="scverse",
            entry_points=("nicheformer",),
            description="NicheFormer Spatial Microenvironment Foundation Model",
        ),
        refusal_conditions=[
            RefusalTrigger(
                condition_id="missing_coordinates",
                description="Dataset lacks 2D coordinates in obsm['spatial'].",
                remedy="Provide spatial AnnData with valid obsm['spatial'] matrix.",
                violated_rule="Spatial geometry requirement",
            ),
        ],
        outputs=[
            "niche_proportions (adata_spatial.obsm['nicheformer_niche_pred'])",
            "dominant_niche (adata_spatial.obs['dominant_niche'])",
            "evidence_card (JSON/Markdown)",
        ],
        evidence_requirements=EvidenceRequirement(
            multiple_testing="not_applicable",
            effect_size="not_applicable",
            mandatory_limitations=[
                "NicheFormer spatial compositions are in silico exploratory forecasts.",
                "Research Use Only. Not for clinical diagnosis.",
            ],
        ),
        forbidden_claims=[
            "model_substitution",
            "clinical_diagnosis",
            "causal_interaction",
            "cell_type_identity_without_reference",
        ],
        evidence_ceiling_without_external_validation="PRELIMINARY",
    ),
    # 19. Dry-Wet Closed Loop Perturbation to Spatial Niche (Frontier)
    "closed_loop.perturbation_to_niche": CapabilityContract(
        id="closed_loop.perturbation_to_niche",
        version=1,
        display_name="Dry-Wet Closed Loop: Perturbation -> Spatial Niche Remodeling",
        skill_name="spatial-transcriptomics",
        summary="Chains GEARS genetic perturbation with NicheFormer spatial microenvironment forecasting into an actionable wet-lab validation card.",
        intent=[
            "dry_wet_closed_loop",
            "perturbation_to_spatial_niche",
            "niche_remodeling_closed_loop",
            "wet_lab_validation_handoff",
        ],
        inputs={
            "expression": InputSpecification(
                name="expression",
                semantic_type=SemanticInputType.RAW_COUNTS.value,
                required=True,
                description="Baseline single-cell expression matrix (.h5ad).",
            ),
            "spatial_coordinates": InputSpecification(
                name="spatial_coordinates",
                semantic_type=SemanticInputType.SPATIAL_COORDINATES.value,
                required=True,
                description="Spatial reference coordinates in adata_spatial.obsm['spatial'].",
            ),
        },
        preconditions=[
            Precondition(
                id="non_empty_matrix",
                rule="n_cells > 0 and n_genes > 0",
                description="Input single-cell dataset must not be empty.",
                fatal_if_violated=True,
            ),
            Precondition(
                id="spatial_coordinates_present",
                rule="'spatial' in adata_spatial.obsm",
                description="Spatial reference must contain 2D coordinates.",
                fatal_if_violated=True,
            ),
        ],
        backend=BackendRequirement(
            canonical_name="bionexus-closed-loop",
            import_name="gears",
            minimum_version="0.1.0",
            extra="scverse",
            entry_points=("gears", "bionexus.closed_loop"),
            description="BioNexus GEARS + NicheFormer Closed-Loop Integration Pipeline",
        ),
        refusal_conditions=[
            RefusalTrigger(
                condition_id="empty_matrix",
                description="Dataset contains 0 cells or 0 genes.",
                remedy="Provide valid single-cell AnnData count matrix.",
                violated_rule="Matrix non-emptiness rule",
            ),
            RefusalTrigger(
                condition_id="missing_coordinates",
                description="Spatial reference lacks 2D coordinates.",
                remedy="Provide spatial AnnData with valid obsm['spatial'] matrix.",
                violated_rule="Spatial geometry requirement",
            ),
        ],
        outputs=[
            "remodeling_scores (Dict[str, float])",
            "wet_lab_hypothesis_card (JSON/Markdown)",
            "evidence_card (JSON/Markdown)",
        ],
        evidence_requirements=EvidenceRequirement(
            multiple_testing="not_applicable",
            effect_size="not_applicable",
            mandatory_limitations=[
                "Closed-loop perturbation-to-niche forecasts are computational hypotheses.",
                "Wet-lab validation is required prior to translational claims.",
                "Research Use Only. Not for clinical diagnosis.",
            ],
        ),
        forbidden_claims=[
            "model_substitution",
            "clinical_diagnosis",
            "causal_interaction",
            "cell_type_identity_without_reference",
        ],
        evidence_ceiling_without_external_validation="PRELIMINARY",
    ),
}

ALL_CAPABILITIES: Dict[str, CapabilityContract] = {
    **CANONICAL_CAPABILITIES,
    **FRONTIER_CAPABILITIES,
}


# ==============================================================================
# Helper Query Functions
# ==============================================================================


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
