"""
BioNexus Scientific Preflight (BNS-013, firewall entry point 1).

Runs BEFORE any analysis:

    bionexus preflight sample.h5ad --intent differential-expression

The preflight resolves the declared intent onto a capability contract, inspects
the actual data state (matrix semantics, biological replicates, condition
confounding, spatial provenance), screens the deterministic trap set, and
returns a fail-closed decision block:

    INTENT / DATA STATE / RISKS / DECISION / ALLOWED / FORBIDDEN CLAIM / REMEDY

The decision vocabulary is the fail-closed table (BNS-AD-014), re-used
verbatim: ABSTAIN (request data), REFUSE, DEGRADE WITH DISCLOSURE,
BLOCK CLAIM, CAP EVIDENCE LEVEL, RUN PERMITTED. Preflight never executes the
analysis; it decides whether the analysis should be run at all.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from bionexus.abi import FORBIDDEN_CLAIM_CATALOG, get_capability_abi
from bionexus.capabilities import CANONICAL_CAPABILITIES, CapabilityContract
from bionexus.failclosed import PreventionDecision, prevent_invalid_run
from bionexus.failures import get_failure_mode
from bionexus.integrity import audit_expression_matrix

# Intent aliases -> capability contract IDs (the CLI-facing intent vocabulary).
INTENT_ALIASES: Dict[str, str] = {
    "differential-expression": "scrna.pseudobulk_de",
    "de": "scrna.pseudobulk_de",
    "pseudobulk-de": "scrna.pseudobulk_de",
    "condition-de": "scrna.pseudobulk_de",
    "clustering": "scrna.exploratory_clustering",
    "exploratory-clustering": "scrna.exploratory_clustering",
    "markers": "scrna.exploratory_clustering",
    "spatial-svg": "spatial.morans_svg",
    "spatial": "spatial.morans_svg",
    "spatially-variable-genes": "spatial.morans_svg",
    "annotation-evidence": "scrna.annotation_evidence",
    "annotation": "scrna.annotation_evidence",
    "cell-annotation": "scrna.annotation_evidence",
    "spatial-inference-validity": "spatial.inference_validity",
    "spatial-inference": "spatial.inference_validity",
    "survival": "survival.kaplan_meier",
    "survival-analysis": "survival.kaplan_meier",
    "scvi": "scvi.probabilistic_vae",
    "integration": "scvi.probabilistic_vae",
    "variant-interpretation": "variant.acmg_classification",
    "acmg": "variant.acmg_classification",
    "instrument-conversion": "allotrope.format_conversion",
    "allotrope": "allotrope.format_conversion",
    "pipeline-launch": "nextflow.pipeline_launch",
    "nextflow": "nextflow.pipeline_launch",
}

# Canonical router-matching query per capability (used when the caller passes
# only an intent alias, no free-text query).
_CANONICAL_QUERIES: Dict[str, str] = {
    "scrna.pseudobulk_de": "differential expression between treatment and control conditions",
    "scrna.exploratory_clustering": "cluster the single cells and identify marker genes",
    "spatial.morans_svg": "spatial transcriptomics spatially variable genes analysis",
    "scrna.annotation_evidence": "assess the annotation evidence support for the candidate cell-type labels",
    "spatial.inference_validity": "test whether the spatial conclusion holds against alternative explanations",
    "survival.kaplan_meier": "survival analysis kaplan-meier estimation for the cohort",
    "scvi.probabilistic_vae": "train an scvi model for latent embedding",
    "variant.acmg_classification": "variant pathogenicity interpretation",
    "allotrope.format_conversion": "standardize the instrument data format conversion",
    "nextflow.pipeline_launch": "nextflow pipeline launch preparation",
}

_DONOR_COLUMNS = ("donor_id", "donor", "sample_id", "sample", "patient_id", "mouse_id", "replicate")
_CONDITION_COLUMNS = ("condition", "treatment", "group", "disease", "genotype", "stim")


@dataclass
class PreflightCheck:
    """One DATA STATE line: what was verified about the input."""

    name: str
    passed: Optional[bool]  # None = unverifiable in this environment
    detail: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PreflightRisk:
    """One RISKS line, tagged with its taxonomy failure ID."""

    failure_id: str
    message: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PreflightReport:
    """The complete preflight verdict (BNS-013 output contract)."""

    intent: str
    capability_id: Optional[str]
    decision: str  # RoutingStatus value
    action: str  # fail-closed table action
    prevented: bool
    exit_code: int  # 0 proceed, 1 refused/blocked, 2 needs data
    rationale: str
    data_state: List[PreflightCheck] = field(default_factory=list)
    risks: List[PreflightRisk] = field(default_factory=list)
    allowed: List[str] = field(default_factory=list)
    forbidden_claims: List[str] = field(default_factory=list)
    remedies: List[str] = field(default_factory=list)
    missing_data_requests: List[str] = field(default_factory=list)
    failure_mode_ids: List[str] = field(default_factory=list)
    claimed_maturity: Optional[str] = None
    warranted_maturity: Optional[str] = None
    prevention: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        out = asdict(self)
        out["data_state"] = [c.to_dict() for c in self.data_state]
        out["risks"] = [r.to_dict() for r in self.risks]
        return out


def resolve_intent(intent: Optional[str]) -> Optional[CapabilityContract]:
    """Map a CLI intent alias (or free-text intent) onto a capability contract."""
    if not intent:
        return None
    cap_id = INTENT_ALIASES.get(intent.strip().lower()) or INTENT_ALIASES.get(
        intent.strip().lower().replace("_", "-")
    )
    if cap_id:
        return CANONICAL_CAPABILITIES[cap_id]
    # Fall back to contract-declared intents
    for cap in CANONICAL_CAPABILITIES.values():
        if intent.strip().lower() in cap.intent:
            return cap
    return None


def inspect_data_state(
    data_path: Optional[str | Path] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Tuple[List[PreflightCheck], Dict[str, Any]]:
    """
    Inspect the actual input data and derive router-consumable metadata.

    Returns the DATA STATE check list and the metadata dict (h5ad-derived facts
    merged under caller-provided metadata, which wins on conflicts).
    """
    checks: List[PreflightCheck] = []
    meta: Dict[str, Any] = dict(metadata or {})

    if data_path is None:
        checks.append(PreflightCheck(name="input", passed=None, detail="no data path supplied; metadata-only preflight"))
    elif not Path(data_path).is_file():
        checks.append(PreflightCheck(name="input", passed=False, detail=f"data file not found: {data_path}"))
    elif Path(data_path).suffix != ".h5ad":
        checks.append(
            PreflightCheck(name="input", passed=None, detail=f"'{Path(data_path).suffix}' files are not auto-inspected; supply --metadata")
        )
    else:
        try:
            import anndata as ad  # noqa: PLC0415

            adata = ad.read_h5ad(Path(data_path), backed="r")
        except ImportError:
            checks.append(
                PreflightCheck(
                    name="input", passed=None, detail="anndata not installed; matrix state not verified (install bionexus-reliability[goldchain] or supply --metadata)"
                )
            )
        except Exception as exc:  # unreadable h5ad
            checks.append(PreflightCheck(name="input", passed=False, detail=f"could not read .h5ad: {exc}"))
        else:
            grade, notes, stats = audit_expression_matrix(adata.X, expected_type="counts")
            is_integer = bool(stats.get("is_integer_like", False))
            meta.setdefault("is_integer_like", is_integer)
            meta.setdefault("is_normalized", not is_integer)
            checks.append(
                PreflightCheck(
                    name="matrix state",
                    passed=True if is_integer else None,
                    detail="raw integer-like counts present" if is_integer else "continuous (normalized/log) matrix detected",
                )
            )
            checks.append(
                PreflightCheck(name="cells", passed=True, detail=f"{adata.n_obs} cells x {adata.n_vars} features")
            )

            obs_cols = list(adata.obs.columns)
            donor_col = next((c for c in _DONOR_COLUMNS if c in obs_cols), None)
            condition_col = next((c for c in _CONDITION_COLUMNS if c in obs_cols), None)
            checks.append(
                PreflightCheck(
                    name="condition metadata",
                    passed=True if condition_col else False,
                    detail=f"condition column '{condition_col}' present" if condition_col else "no condition/treatment column found in .obs",
                )
            )
            if condition_col and donor_col:
                donors_per_condition: Dict[str, set] = {}
                cond_per_donor: Dict[Any, set] = {}
                for donor, cond in zip(adata.obs[donor_col], adata.obs[condition_col]):
                    donors_per_condition.setdefault(str(cond), set()).add(str(donor))
                    cond_per_donor.setdefault(str(donor), set()).add(str(cond))
                n_conditions = len(donors_per_condition)
                min_donors = min(len(v) for v in donors_per_condition.values()) if donors_per_condition else 0
                checks.append(
                    PreflightCheck(
                        name="biological samples",
                        passed=min_donors >= 2,
                        detail=f"{len(cond_per_donor)} unique donors across {n_conditions} conditions; minimum {min_donors} donors in a group",
                    )
                )
                meta.setdefault("min_replicates_per_condition", min_donors)
                fully_nested = n_conditions >= 2 and all(len(v) == 1 for v in cond_per_donor.values())
                if fully_nested:
                    meta.setdefault("condition_confounded_with", donor_col)
            elif donor_col:
                checks.append(
                    PreflightCheck(name="biological samples", passed=True, detail=f"replicate column '{donor_col}' present")
                )
            else:
                checks.append(
                    PreflightCheck(
                        name="biological samples",
                        passed=False,
                        detail="no donor/sample replicate column found in .obs; replicate structure unverified",
                    )
                )

            if "spatial" in getattr(adata, "obsm", {}):
                meta.setdefault("n_spatial_spots", int(adata.obsm["spatial"].shape[0]))
                checks.append(
                    PreflightCheck(name="spatial coordinates", passed=True, detail=f"{adata.obsm['spatial'].shape[0]} spatial coordinates present")
                )

    # Caller-provided explicit flags win over inferred values.
    if metadata:
        if metadata.get("is_normalized") is True or metadata.get("is_integer_like") is False:
            meta["is_normalized"] = True
            meta["is_integer_like"] = False
    return checks, meta


def run_preflight(
    *,
    intent: Optional[str] = None,
    query: Optional[str] = None,
    data_path: Optional[str | Path] = None,
    metadata: Optional[Dict[str, Any]] = None,
    metadata_path: Optional[str | Path] = None,
    claimed_maturity: Optional[str] = None,
    has_external_validation: bool = False,
    allow_degraded: bool = False,
    allow_frontier: bool = False,
) -> PreflightReport:
    """
    Execute the full preflight (BNS-013): intent -> data state -> risks ->
    fail-closed decision -> ALLOWED / FORBIDDEN CLAIM / REMEDY.
    """
    if metadata_path is not None:
        loaded = json.loads(Path(metadata_path).read_text(encoding="utf-8"))
        metadata = {**(metadata or {}), **loaded}

    # Maturity intent may be declared inline in the metadata file (eval-style).
    if claimed_maturity is None and metadata:
        claimed_maturity = metadata.get("claimed_maturity")
    if metadata and not has_external_validation:
        has_external_validation = bool(metadata.get("external_validation", False))

    contract = resolve_intent(intent)
    if contract is None:
        return PreflightReport(
            intent=intent or query or "",
            capability_id=None,
            decision="NEEDS_DATA",
            action="ABSTAIN (request data)",
            prevented=True,
            exit_code=2,
            rationale="Unknown intent: no capability contract matches the declared analytical intent.",
            data_state=[PreflightCheck(name="intent", passed=False, detail=f"unknown intent '{intent}'")],
            remedies=["Choose an intent from: " + ", ".join(sorted(INTENT_ALIASES))],
        )

    checks, meta = inspect_data_state(data_path=data_path, metadata=metadata)

    effective_query = query or _CANONICAL_QUERIES.get(contract.id, contract.display_name)

    # Preflight-visible risks (surfaced even when the router permits the run).
    risks: List[PreflightRisk] = []
    if meta.get("condition_confounded_with"):
        risks.append(
            PreflightRisk(
                failure_id="BN-F006",
                message=f"condition strongly confounded with '{meta['condition_confounded_with']}' (1:1 design)",
            )
        )
    min_reps = meta.get("min_replicates_per_condition")
    if min_reps is not None and min_reps < 2:
        risks.append(PreflightRisk(failure_id="BN-F002", message=f"one group contains only {min_reps} biological replicate(s)"))
    if meta.get("is_normalized") is True and contract.id in ("scrna.pseudobulk_de", "scvi.probabilistic_vae"):
        risks.append(PreflightRisk(failure_id="BN-F001", message="normalized/log matrix where raw counts are required"))
    if meta.get("identifier_namespace") and meta.get("reference_namespace"):
        if str(meta["identifier_namespace"]).lower() != str(meta["reference_namespace"]).lower():
            risks.append(
                PreflightRisk(
                    failure_id="BN-F004",
                    message=f"join across identifier namespaces ({meta['identifier_namespace']} vs {meta['reference_namespace']})",
                )
            )

    verdict: PreventionDecision = prevent_invalid_run(
        effective_query,
        data_metadata=meta,
        claimed_maturity=claimed_maturity,
        has_external_validation=has_external_validation,
        allow_degraded=allow_degraded,
        allow_frontier=allow_frontier,
    )
    routing = verdict.routing or {}
    decision = str(routing.get("status", "NEEDS_DATA"))
    failure_ids = sorted(set(verdict.failure_mode_ids) | {r.failure_id for r in risks})

    # ALLOWED: what may still be computed under this verdict.
    allowed: List[str] = []
    if not verdict.prevented:
        allowed.append(f"{contract.display_name} under its capability contract ({contract.id})")
        if verdict.action == "CAP EVIDENCE LEVEL" and verdict.warranted_maturity:
            allowed.append(f"report conclusions at most at maturity '{verdict.warranted_maturity}'")
    else:
        for fid in failure_ids:
            try:
                degradation = get_failure_mode(fid).acceptable_degradation
            except KeyError:
                continue
            if degradation and not degradation.lower().startswith("none"):
                allowed.append(f"at most: {degradation}")
        if not allowed:
            allowed.append("nothing: no acceptable degradation exists for this failure class")

    # FORBIDDEN CLAIM: the capability's forbidden-claim catalog, verbatim.
    forbidden: List[str] = []
    try:
        abi = get_capability_abi(contract.id)
        for claim_id in abi.forbidden_claims:
            entry = FORBIDDEN_CLAIM_CATALOG[claim_id]
            forbidden.append(f"{claim_id}: {entry.description}")
        forbidden.append(
            f"maturity above '{abi.evidence_ceiling.without_external_validation}' without external validation"
        )
    except KeyError:
        pass
    if claimed_maturity and verdict.warranted_maturity and claimed_maturity.upper() != verdict.warranted_maturity.upper():
        forbidden.append(f"claimed maturity '{claimed_maturity.upper()}' (warranted: '{verdict.warranted_maturity}')")

    exit_code = 0
    if verdict.prevented:
        exit_code = 2 if verdict.prevention_kind == "MISSING_EVIDENCE" else 1

    return PreflightReport(
        intent=contract.display_name,
        capability_id=contract.id,
        decision=decision,
        action=verdict.action,
        prevented=verdict.prevented,
        exit_code=exit_code,
        rationale=verdict.reason,
        data_state=checks,
        risks=risks,
        allowed=sorted(dict.fromkeys(allowed)),
        forbidden_claims=forbidden,
        remedies=list(verdict.remedies),
        missing_data_requests=list(verdict.missing_data_requests),
        failure_mode_ids=failure_ids,
        claimed_maturity=str(claimed_maturity).upper() if claimed_maturity else None,
        warranted_maturity=verdict.warranted_maturity,
        prevention=verdict.to_dict(),
    )


def render_preflight(report: PreflightReport) -> str:
    """Render the preflight block in the BNS-013 output contract (ASCII markers)."""

    def mark(passed: Optional[bool]) -> str:
        return "[OK]" if passed else ("[!!]" if passed is False else "[??]")

    lines: List[str] = []
    lines.append("=== BioNexus Preflight ===")
    lines.append("")
    lines.append("INTENT")
    cap = f"  ({report.capability_id})" if report.capability_id else ""
    lines.append(f"{report.intent}{cap}")
    lines.append("")
    lines.append("DATA STATE")
    if report.data_state:
        for check in report.data_state:
            lines.append(f"{mark(check.passed)} {check.name}: {check.detail}")
    else:
        lines.append("[??] no data state inspected")
    lines.append("")
    lines.append("RISKS")
    if report.risks:
        for risk in report.risks:
            lines.append(f"[!!] {risk.failure_id}: {risk.message}")
    else:
        lines.append("(none detected by the deterministic trap screen)")
    lines.append("")
    lines.append("DECISION")
    lines.append(f"{report.decision} -> {report.action}")
    lines.append(f"  {report.rationale}")
    if report.claimed_maturity and report.warranted_maturity:
        lines.append(f"  maturity: claimed '{report.claimed_maturity}' -> warranted '{report.warranted_maturity}'")
    if report.failure_mode_ids:
        lines.append(f"  failure modes: {', '.join(report.failure_mode_ids)}")
    lines.append("")
    lines.append("ALLOWED")
    for item in report.allowed:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("FORBIDDEN CLAIM")
    for item in report.forbidden_claims:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("REMEDY")
    remedies = report.remedies + report.missing_data_requests
    if remedies:
        for item in remedies:
            lines.append(f"- {item}")
    else:
        lines.append("- none: proceed under the capability contract")
    lines.append("")
    return "\n".join(lines)
