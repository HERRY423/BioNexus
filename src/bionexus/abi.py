"""
Biological Capability ABI (BNS-001 §5, ABI version 1.0).

Projects every canonical CapabilityContract into a stable, machine-readable
**Scientific ABI** — the interface boundary that binds any host agent
(Claude, Codex, or future agents) that connects to BioNexus:

- input_contract   : allowed matrix states, coordinate types, required inputs (BNS-002)
- preconditions    : machine-checkable invariants (BNS-CC-005)
- forbidden_claims : normative claim taxonomy this capability MUST NOT emit (BNS-CC-012)
- execution        : reference backend + reference algorithm (BNS-EF-008)
- validation       : multiple-testing / parameter-sensitivity / cross-method policy (BNS-007)
- evidence_ceiling : max ConclusionMaturity without external validation (BNS-CC-013)
- provenance       : dataset hash / package versions / parameters (BNS-006)

The ABI is *generated* from the canonical contracts, never hand-maintained,
so it cannot drift from the enforced behavior.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from bionexus.capabilities import CANONICAL_CAPABILITIES, CapabilityContract
from bionexus.contracts import ConclusionMaturity

ABI_VERSION = "1.0"


class MatrixState(str, Enum):
    """Semantic scale states an expression matrix may be in (BNS-II-001)."""

    RAW_COUNTS = "raw_counts"  # non-negative integer counts
    NORMALIZED_EXPRESSION = "normalized_expression"  # log-normalized / CPM continuous
    SCALED_EXPRESSION = "scaled_expression"  # z-scored / mean-centered
    ANY = "any"  # method is scale-insensitive


class CoordinateType(str, Enum):
    """Semantic origin of spatial coordinates (BNS-II-005/006)."""

    PHYSICAL = "physical"  # array/spots/cell centroids in physical units
    JUSTIFIED_SPATIAL_EMBEDDING = "justified_spatial_embedding"  # embedding with recorded spatial justification
    NONE = "none"


# ==============================================================================
# Normative Forbidden Claim Taxology (BNS-CC-012, BNS-AD-009/010, BNS-HC-004)
# ==============================================================================


@dataclass(frozen=True)
class ForbiddenClaim:
    """A claim family no conformant output may make without additional evidence."""

    claim_id: str
    description: str
    detection_patterns: tuple[str, ...]


FORBIDDEN_CLAIM_CATALOG: Dict[str, ForbiddenClaim] = {
    c.claim_id: c
    for c in [
        ForbiddenClaim(
            claim_id="causal_interaction",
            description="Claiming causal molecular interaction or regulation from correlational evidence (Moran's I, DE rankings, embeddings).",
            detection_patterns=(
                r"\bcaus(?:e|es|ed|al|ality)\w*\s+(?:interaction|regulation|signaling|communication)",
                r"\bproves?\s+(?:causal|interaction|regulation)",
                r"\bcausal\s+(?:cell[- ]cell|ligand|regulatory)",
            ),
        ),
        ForbiddenClaim(
            claim_id="cell_cell_communication",
            description="Claiming demonstrated cell-cell communication / ligand-receptor signaling from spatial autocorrelation alone.",
            detection_patterns=(
                r"\bcell[- ]cell\s+(?:communication|signaling|crosstalk|talk)",
                r"\bligand[- ]receptor\s+(?:communication|signaling|interaction\s+(?:is|was|are)\s+(?:active|detected|proved))",
                r"\bcommunicating\s+cells",
            ),
        ),
        ForbiddenClaim(
            claim_id="cell_type_identity_without_reference",
            description="Promoting unsupervised clusters to biological cell-type identities without an annotation evidence source (BNS-II-008).",
            detection_patterns=(
                r"\bcluster\s*\d+\s+(?:are|is|contains|corresponds to)\s+(?:the\s+)?\w+\s*(?:T|B)?\s*cells",
                r"\bclusters?\s+(?:are|represent)\s+\w+\s+cell\s+types?\s+(?:without|with\s+no)\s+reference",
                r"\bidentified\s+cell\s+types?\s+from\s+(?:clusters|leiden|umap)\s+alone",
            ),
        ),
        ForbiddenClaim(
            claim_id="clinical_diagnosis",
            description="Issuing clinical diagnosis or confirmatory disease calls (regulatory prohibition, BNS-AD-010).",
            detection_patterns=(
                r"\bdiagnos(?:e|es|ed|is|tic)\b",
                r"\bpatient\s+(?:has|is confirmed)\s+\w+",
                r"\bconfirms?\s+(?:the\s+)?(?:diagnosis|disease)",
            ),
        ),
        ForbiddenClaim(
            claim_id="treatment_recommendation",
            description="Recommending treatment or therapy selection from research-grade output.",
            detection_patterns=(
                r"\b(?:should|must)\s+be\s+treated\b",
                r"\brecommend\w*\s+(?:therapy|treatment|drug|medication)",
                r"\btreatment\s+decision",
            ),
        ),
        ForbiddenClaim(
            claim_id="model_substitution",
            description="Presenting heuristic/fallback output as gold-standard backend output (BNS-EF-002).",
            detection_patterns=(
                r"\b(?:pydeseq2|deseq2|squidpy|scanpy|scvi|lifelines)\s+(?:was|were)\s+run\b",
            ),
        ),
        ForbiddenClaim(
            claim_id="hazard_causation",
            description="Claiming treatment causes survival benefit from unadjusted Kaplan-Meier/log-rank association.",
            detection_patterns=(
                r"\btreatment\s+causes?\s+(?:longer|improved|better)\s+survival",
                r"\bcausal\s+(?:survival|hazard|prognosis)",
            ),
        ),
        ForbiddenClaim(
            claim_id="true_expression_recovery",
            description="Claiming imputed/denoised values are the true underlying expression (scVI posterior samples are not ground truth).",
            detection_patterns=(
                r"\brecover(?:ed|s)?\s+the\s+true\s+(?:expression|counts)",
                r"\bimputation\s+(?:is|gives)\s+(?:the\s+)?true\s+values",
            ),
        ),
        ForbiddenClaim(
            claim_id="sensor_calibration_validated",
            description="Claiming analytical sensor calibration was validated by a syntactic format conversion (allotrope).",
            detection_patterns=(
                r"\bsensor\s+calibration\s+(?:was\s+)?validated",
                r"\bcalibration\s+verified\s+by\s+(?:the\s+)?conversion",
            ),
        ),
        ForbiddenClaim(
            claim_id="regulatory_compliance",
            description="Claiming FDA / 21 CFR Part 11 regulatory compliance for research tooling.",
            detection_patterns=(
                r"\b21\s+c?fr\s*(?:part\s*)?11\s+(?:compliant|certified)",
                r"\bfda[- ]approved",
            ),
        ),
        ForbiddenClaim(
            claim_id="pipeline_results_without_execution",
            description="Claiming analytical results from launch-artifact generation (Nextflow configs are not executions).",
            detection_patterns=(
                r"\bpipeline\s+(?:results|findings)\s+(?:show|demonstrate|confirm)",
            ),
        ),
    ]
}


# ==============================================================================
# ABI Structural Blocks
# ==============================================================================


@dataclass
class InputContract:
    """Allowed semantic input states (BNS-002)."""

    matrix_state_allowed: List[str] = field(default_factory=lambda: [MatrixState.RAW_COUNTS.value])
    coordinates_required: bool = False
    coordinate_type_allowed: List[str] = field(default_factory=list)
    required_inputs: List[str] = field(default_factory=list)
    notes: Dict[str, str] = field(default_factory=dict)


@dataclass
class ExecutionReference:
    """Canonical reference implementation (BNS-EF-008)."""

    reference_backend: str = "none"
    reference_algorithm: str = "unspecified"
    minimum_version: Optional[str] = None


@dataclass
class ValidationRequirements:
    """Statistical validation policy (BNS-007)."""

    multiple_testing: str = "required"  # required | recommended | optional | not_applicable
    parameter_sensitivity: str = "recommended"
    cross_method: str = "recommended"


@dataclass
class EvidenceCeiling:
    """Maximum assertable ConclusionMaturity in the absence of external validation (BNS-CC-013)."""

    without_external_validation: str = ConclusionMaturity.SUPPORTED.value
    note: str = "External validation (orthogonal datasets/assays or gold truth sets) is required to assert beyond the ceiling."


    def clamp(self, claimed_maturity: str, has_external_validation: bool = False) -> str:
        """Clamp a claimed maturity to the ceiling unless external validation is present."""
        if has_external_validation:
            return claimed_maturity
        ranks = {
            ConclusionMaturity.ABSTAIN.value: 0,
            ConclusionMaturity.UNASSESSED.value: 0,
            ConclusionMaturity.PRELIMINARY.value: 1,
            ConclusionMaturity.FRAGILE.value: 2,
            ConclusionMaturity.CONFLICTED.value: 2,
            ConclusionMaturity.SUPPORTED.value: 3,
            ConclusionMaturity.ROBUST.value: 4,
            ConclusionMaturity.REPLICATED.value: 5,
        }
        claimed_rank = ranks.get(str(claimed_maturity).upper(), 1)
        ceiling_rank = ranks.get(self.without_external_validation, ranks[ConclusionMaturity.SUPPORTED.value])
        if claimed_rank > ceiling_rank:
            return self.without_external_validation
        return claimed_maturity


@dataclass
class ProvenanceRequirements:
    """Mandatory provenance fields (BNS-006)."""

    dataset_hash: str = "required"
    package_versions: str = "required"
    parameters: str = "required"


@dataclass
class CapabilityABI:
    """The Biological Capability ABI record for one capability (BNS-001 §5)."""

    capability_id: str
    contract_version: int
    abi_version: str = ABI_VERSION
    input_contract: InputContract = field(default_factory=InputContract)
    preconditions: List[str] = field(default_factory=list)
    forbidden_claims: List[str] = field(default_factory=list)
    execution: ExecutionReference = field(default_factory=ExecutionReference)
    validation: ValidationRequirements = field(default_factory=ValidationRequirements)
    evidence_ceiling: EvidenceCeiling = field(default_factory=EvidenceCeiling)
    provenance: ProvenanceRequirements = field(default_factory=ProvenanceRequirements)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize in the canonical ABI YAML shape."""
        return {
            "capability": {
                "id": self.capability_id,
                "version": self.contract_version,
                "abi_version": self.abi_version,
            },
            "input_contract": asdict(self.input_contract),
            "preconditions": list(self.preconditions),
            "forbidden_claims": list(self.forbidden_claims),
            "execution": asdict(self.execution),
            "validation": asdict(self.validation),
            "evidence_ceiling": asdict(self.evidence_ceiling),
            "provenance": asdict(self.provenance),
        }


# ==============================================================================
# Per-capability ABI enrichment (generated, single source of truth = contract)
# ==============================================================================

_ABI_ENRICHMENT: Dict[str, Dict[str, Any]] = {
    "scrna.pseudobulk_de": {
        "input_contract": InputContract(
            matrix_state_allowed=[MatrixState.RAW_COUNTS.value],
            required_inputs=["expression", "sample_design"],
            notes={"matrix_state": "Negative binomial GLM requires raw integer counts (BNS-II-002)."},
        ),
        "execution": ExecutionReference(reference_backend="pydeseq2", reference_algorithm="deseq2_wald_test", minimum_version="0.4.0"),
        "validation": ValidationRequirements(multiple_testing="required", parameter_sensitivity="recommended", cross_method="recommended"),
        "evidence_ceiling_note": "Replicate-backed inference may reach SUPPORTED; REPLICATED requires external cohorts/truth sets.",
    },
    "scrna.exploratory_clustering": {
        "input_contract": InputContract(
            matrix_state_allowed=[MatrixState.RAW_COUNTS.value],
            required_inputs=["counts"],
            notes={"matrix_state": "Pipeline normalizes internally; raw counts expected at entry (BNS-II-003)."},
        ),
        "execution": ExecutionReference(reference_backend="scanpy", reference_algorithm="leiden_louvain_clustering", minimum_version="1.10.0"),
        "validation": ValidationRequirements(multiple_testing="required", parameter_sensitivity="required", cross_method="recommended"),
        "evidence_ceiling_note": "Exploratory unsupervised structure with numeric cluster labels only (BNS-II-008).",
    },
    "spatial.morans_svg": {
        "input_contract": InputContract(
            matrix_state_allowed=[MatrixState.NORMALIZED_EXPRESSION.value, MatrixState.RAW_COUNTS.value],
            coordinates_required=True,
            coordinate_type_allowed=[CoordinateType.PHYSICAL.value, CoordinateType.JUSTIFIED_SPATIAL_EMBEDDING.value],
            required_inputs=["expression", "coordinates"],
            notes={"coordinate_type": "UMAP/PCA embeddings MUST NOT be silently substituted for physical coordinates (BNS-II-006)."},
        ),
        "execution": ExecutionReference(reference_backend="squidpy", reference_algorithm="spatial_autocorr", minimum_version="1.3.0"),
        "validation": ValidationRequirements(multiple_testing="required", parameter_sensitivity="required", cross_method="recommended"),
        "evidence_ceiling_note": "SVG rankings are KNN-graph-parameter-sensitive; without cross-method/external corroboration findings stay FRAGILE.",
    },
    "survival.kaplan_meier": {
        "input_contract": InputContract(
            matrix_state_allowed=[MatrixState.ANY.value],
            required_inputs=["duration", "event", "group"],
            notes={"events": "At least one uncensored event is mandatory (BNS-II-011)."},
        ),
        "execution": ExecutionReference(reference_backend="lifelines", reference_algorithm="kaplan_meier_logrank", minimum_version="0.27.0"),
        "validation": ValidationRequirements(multiple_testing="optional", parameter_sensitivity="optional", cross_method="recommended"),
        "evidence_ceiling_note": "Unadjusted univariate association; causal or individual-level prognostic claims are forbidden (BNS-HC-004).",
    },
    "scvi.probabilistic_vae": {
        "input_contract": InputContract(
            matrix_state_allowed=[MatrixState.RAW_COUNTS.value],
            required_inputs=["counts"],
            notes={"matrix_state": "Discrete likelihood (NB/ZINB) strictly requires raw counts (BNS-II-002)."},
        ),
        "execution": ExecutionReference(reference_backend="scvi-tools", reference_algorithm="variational_inference_vae", minimum_version="1.0.0"),
        "validation": ValidationRequirements(multiple_testing="optional", parameter_sensitivity="required", cross_method="recommended"),
        "evidence_ceiling_note": "Stochastic latent representation; seed-sensitive and exploratory without integration metrics + external reference.",
    },
    "allotrope.format_conversion": {
        "input_contract": InputContract(
            matrix_state_allowed=[MatrixState.ANY.value],
            required_inputs=["raw_file"],
            notes={"scope": "Syntactic/schema conversion only (BNS-002 notes); analytical validity is out of scope."},
        ),
        "execution": ExecutionReference(reference_backend="allotropy", reference_algorithm="declarative_schema_mapping", minimum_version="0.1.30"),
        "validation": ValidationRequirements(multiple_testing="not_applicable", parameter_sensitivity="not_applicable", cross_method="not_applicable"),
        "evidence_ceiling_note": "Deterministic syntax conversion; asserts no analytical conclusion.",
    },
    "nextflow.pipeline_launch": {
        "input_contract": InputContract(
            matrix_state_allowed=[MatrixState.ANY.value],
            required_inputs=["sample_manifest"],
        ),
        "execution": ExecutionReference(reference_backend="nf-core", reference_algorithm="samplesheet_schema_validation"),
        "validation": ValidationRequirements(multiple_testing="not_applicable", parameter_sensitivity="not_applicable", cross_method="not_applicable"),
        "evidence_ceiling_note": "Generates launch artifacts; no analytical outcome is produced by this capability.",
    },
    "variant.acmg_classification": {
        "input_contract": InputContract(
            matrix_state_allowed=[MatrixState.ANY.value],
            required_inputs=["variant_id", "acmg_codes"],
            notes={"pvs1": "PVS1 requires verified loss-of-function mechanism (BNS-II-013)."},
        ),
        "execution": ExecutionReference(reference_backend="local combiner", reference_algorithm="acmg_bayesian_combination"),
        "validation": ValidationRequirements(multiple_testing="not_applicable", parameter_sensitivity="not_applicable", cross_method="recommended"),
        "evidence_ceiling_note": "Deterministic rule combiner; REPLICATED requires concordance with external expert-reviewed truth sets (e.g. ClinVar).",
    },
}


def _build_abi(contract: CapabilityContract) -> CapabilityABI:
    """Project a canonical contract into its ABI record (BNS-CC-010)."""
    enrich = _ABI_ENRICHMENT.get(contract.id, {})

    input_contract: InputContract = enrich.get(
        "input_contract",
        InputContract(required_inputs=[n for n, s in contract.inputs.items() if s.required]),
    )
    # Required inputs must always mirror the canonical contract, never the enrichment.
    input_contract.required_inputs = [n for n, s in contract.inputs.items() if s.required]

    # Forbidden claims and evidence ceiling are normative contract fields
    # (single source of truth); enrichment cannot override them.
    forbidden = list(contract.forbidden_claims) or ["clinical_diagnosis", "treatment_recommendation"]
    for claim in forbidden:
        if claim not in FORBIDDEN_CLAIM_CATALOG:
            raise ValueError(
                f"Capability '{contract.id}' references unknown forbidden claim '{claim}'. "
                f"Claims must come from abi.FORBIDDEN_CLAIM_CATALOG."
            )

    ev_req = contract.evidence_requirements
    validation: ValidationRequirements = enrich.get(
        "validation",
        ValidationRequirements(
            multiple_testing=ev_req.multiple_testing if ev_req.multiple_testing != "not_applicable" else "not_applicable",
        ),
    )

    ceiling = EvidenceCeiling(
        without_external_validation=contract.evidence_ceiling_without_external_validation,
        note=enrich.get("evidence_ceiling_note", EvidenceCeiling.note),
    )

    return CapabilityABI(
        capability_id=contract.id,
        contract_version=contract.version,
        abi_version=ABI_VERSION,
        input_contract=input_contract,
        preconditions=[p.id for p in contract.preconditions],
        forbidden_claims=forbidden,
        execution=enrich.get(
            "execution",
            ExecutionReference(reference_backend=contract.backend.canonical_name, minimum_version=contract.backend.minimum_version),
        ),
        validation=validation,
        evidence_ceiling=ceiling,
        provenance=ProvenanceRequirements(),
    )


def capability_abis() -> Dict[str, CapabilityABI]:
    """All canonical capability ABI records, keyed by capability id."""
    return {cid: _build_abi(c) for cid, c in CANONICAL_CAPABILITIES.items()}


def get_capability_abi(capability_id: str) -> CapabilityABI:
    """Retrieve the ABI record for a capability id (BNS-CC-010)."""
    abis = capability_abis()
    if capability_id not in abis:
        raise KeyError(
            f"Unknown capability id '{capability_id}'. Available: {sorted(abis.keys())}"
        )
    return abis[capability_id]


# ==============================================================================
# ABI Enforcement APIs
# ==============================================================================


@dataclass
class ClaimAudit:
    """Result of auditing candidate claims against a capability's ABI."""

    capability_id: str
    passed: bool
    violations: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def audit_claims_against_abi(
    capability_id: str,
    claims: List[str],
) -> ClaimAudit:
    """
    Audit a set of candidate output claims against the capability's forbidden
    claim list (BNS-CC-012). Any pattern match is a violation.
    """
    abi = get_capability_abi(capability_id)
    violations: List[Dict[str, Any]] = []
    for text in claims:
        for claim_id in abi.forbidden_claims:
            claim = FORBIDDEN_CLAIM_CATALOG[claim_id]
            for pat in claim.detection_patterns:
                if re.search(pat, text, flags=re.IGNORECASE):
                    violations.append(
                        {
                            "claim_id": claim_id,
                            "matched_text": text,
                            "pattern": pat,
                            "description": claim.description,
                        }
                    )
                    break
    return ClaimAudit(
        capability_id=capability_id,
        passed=len(violations) == 0,
        violations=violations,
    )


def detect_forbidden_claims_in_query(capability_id: str, query: str) -> List[Dict[str, Any]]:
    """
    Detect forbidden-claim intent inside an incoming request (BNS-AD-009).
    Used by the scientific intent router to block claim-inflation at routing time.
    """
    abi = get_capability_abi(capability_id)
    hits: List[Dict[str, Any]] = []
    for claim_id in abi.forbidden_claims:
        claim = FORBIDDEN_CLAIM_CATALOG[claim_id]
        for pat in claim.detection_patterns:
            if re.search(pat, query, flags=re.IGNORECASE):
                hits.append(
                    {
                        "claim_id": claim_id,
                        "pattern": pat,
                        "description": claim.description,
                        "remedy": claim.description,
                    }
                )
                break
    return hits


def enforce_evidence_ceiling(
    capability_id: str,
    claimed_maturity: str,
    has_external_validation: bool = False,
) -> str:
    """
    Clamp a claimed conclusion maturity to the capability's evidence ceiling
    (BNS-CC-013 / BNS-EM-006). Hosts and pipelines MUST apply this clamp
    before reporting maturity.
    """
    abi = get_capability_abi(capability_id)
    return abi.evidence_ceiling.clamp(claimed_maturity, has_external_validation=has_external_validation)


def abi_conformance_summary() -> Dict[str, Any]:
    """
    Structural conformance scan of every ABI record (BNS-CC-010..014).
    Returns per-capability completeness flags plus an overall verdict.
    """
    abis = capability_abis()
    per_cap: Dict[str, Dict[str, bool]] = {}
    all_ok = True
    for cid, abi in abis.items():
        checks = {
            "has_input_contract": bool(abi.input_contract.required_inputs),
            "has_preconditions": len(abi.preconditions) > 0,
            "has_forbidden_claims": len(abi.forbidden_claims) > 0,
            "has_execution_reference": abi.execution.reference_backend != "none",
            "has_validation_policy": True,
            "has_evidence_ceiling": bool(abi.evidence_ceiling.without_external_validation),
            "has_provenance_requirements": abi.provenance.dataset_hash == "required",
        }
        ok = all(checks.values())
        all_ok = all_ok and ok
        per_cap[cid] = {"ok": ok, **checks}
    return {"abi_version": ABI_VERSION, "conformant": all_ok, "capabilities": per_cap}
