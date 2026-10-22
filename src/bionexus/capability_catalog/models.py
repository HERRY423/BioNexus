"""
BioNexus Machine-Readable Scientific Capability Contracts - Models & Contract Engine.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple

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
            # Resolve the public compatibility seam at call time so host-supplied
            # probes keep working after modularization.
            from bionexus.capabilities import probe as backend_probe

            backend_status = backend_probe(backend_name)
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
        tool_receipts: Sequence[Dict[str, Any]] = (),
    ) -> CapabilityEvaluationResult:
        """Purpose-aware, warrant/policy-separated evaluation.

        Three strictly separated objects:

        1. **EvidenceAssessment** (purpose- and policy-independent): what the
           evidence IS worth, from declared evidence factors, tool receipts, and active
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
        from bionexus.evidence_model import (
            assess_evidence,
            evaluate_sufficiency,
            extract_evidence_factors,
        )
        from bionexus.rule_classification import RuleCategory
        from bionexus.warrant import PolicyAction, assess_warrant, decide_policy

        policy = lab_policy or DEFAULT_LAB_POLICY
        pctx = purpose_context or PurposeContext()
        base = self.evaluate_viability(input_metadata=input_metadata, context=context)

        # Extract and merge evidence factors from explicit argument, input_metadata, tool receipts, and execution integrity
        backend_ok = base.backend_available is not False
        combined_factors = extract_evidence_factors(
            metadata=input_metadata,
            backend_fidelity=backend_ok,
            has_provenance=True,
            explicit_factors=evidence_factors,
            tool_receipts=tool_receipts,
        )

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
                satisfied_factors=combined_factors,
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
            satisfied_factors=combined_factors,
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
            capped = cap_conclusion_by_purpose(ConclusionMaturity.UNASSESSED.value, ConclusionMaturity(assessment.evidence_ceiling))
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
                ConclusionMaturity.FRAGILE.value, ConclusionMaturity(assessment.evidence_ceiling)
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

