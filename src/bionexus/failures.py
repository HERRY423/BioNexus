"""
BioNexus Scientific Failure Taxonomy (BNS-011).

An ontology of the ways agentic computational biology actually goes wrong.
Each failure mode is a first-class record with: definition, canonical example,
affected capabilities, detection rule, required behavior, acceptable
degradation, category, severity, and benchmark cases that exercise it.

BioNexus is not "providing bioinformatics knowledge" — it is building the
failure ontology for agentic computational biology. Every refusal, ceiling
clamp, and degraded advisory in the runtime traces back to one of these IDs.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional

from bionexus.capabilities import CANONICAL_CAPABILITIES

TAXONOMY_SCHEMA_VERSION = "bionexus.failure_taxonomy.v1"


@dataclass(frozen=True)
class FailureMode:
    """One normative failure mode in the BioNexus taxonomy (BN-Fxxx)."""

    failure_id: str
    name: str
    definition: str
    example: str
    affected_capabilities: tuple[str, ...]
    detection_rule: str
    required_behavior: str
    acceptable_degradation: str
    benchmark_cases: tuple[str, ...] = ()
    open_gap: bool = False  # True when no benchmark case exercises this mode yet
    category: str = "INFERENTIAL_DESIGN"  # DATA_INTEGRITY, INFERENTIAL_DESIGN, SEMANTIC_CLAIM, SYSTEM_DEGRADATION
    severity: str = "HIGH"  # CRITICAL, HIGH, MEDIUM


FAILURE_TAXONOMY: Dict[str, FailureMode] = {
    f.failure_id: f
    for f in [
        FailureMode(
            failure_id="BN-F001",
            name="Assay-state confusion",
            category="DATA_INTEGRITY",
            severity="CRITICAL",
            definition=(
                "An analysis is executed on a matrix whose semantic assay state (raw integer counts "
                "vs log/CPM-normalized vs z-scored expression) does not match the model's likelihood "
                "assumption."
            ),
            example=(
                "A negative-binomial GLM (PyDESeq2) fitted on log1p-normalized floats; scVI trained "
                "on scaled expression instead of raw counts."
            ),
            affected_capabilities=("scrna.pseudobulk_de", "scvi.probabilistic_vae", "scrna.exploratory_clustering"),
            detection_rule="integrity.audit_expression_matrix integer-likeness + ABI input_contract matrix_state_allowed",
            required_behavior="REFUSE (BNS-II-002); deterministic refusal triggers normalized_matrix_only / normalized_input",
            acceptable_degradation="None for count-model inputs. Scale-insensitive methods MAY accept normalized input per ABI contract.",
            benchmark_cases=(
                "refuse-normalized-counts-001",
                "refuse-scvi-normalized-001",
                "semantics-raw-vs-log-001",
                "adv-log-as-raw-001",
                "frontier-boundary-normalized-to-spatial-010",
                "BF-001",
                "BF-019",
                "BF-031",
            ),
        ),
        FailureMode(
            failure_id="BN-F002",
            name="Pseudoreplication",
            category="INFERENTIAL_DESIGN",
            severity="CRITICAL",
            definition=(
                "Condition-level inference performed on cell-level observations without biological "
                "replicate aggregation, treating thousands of cells from one sample as independent "
                "biological replicates."
            ),
            example=(
                "Differential expression 'treatment vs control' with n=1 donor per condition, tested "
                "across 8,000 single cells."
            ),
            affected_capabilities=("scrna.pseudobulk_de",),
            detection_rule="router stage 3: min_replicates_per_condition < 2 -> refusal trigger missing_replicates",
            required_behavior="REFUSE with pseudobulk remedy (BNS-II-010)",
            acceptable_degradation="Exploratory within-sample marker ranking MAY be offered, explicitly not labeled condition DE.",
            benchmark_cases=(
                "refuse-pseudorep-001",
                "refuse-pseudorep-002",
                "refuse-needs-data-001",
                "adv-force-pseudorep-001",
                "semantics-marker-vs-de-001",
                "frontier-boundary-exactly-two-replicates-009",
                "BF-002",
                "BF-010",
                "BF-029",
                "BF-032",
            ),
        ),
        FailureMode(
            failure_id="BN-F003",
            name="Unsupported annotation",
            category="SEMANTIC_CLAIM",
            severity="HIGH",
            definition=(
                "Unsupervised computational structures (clusters, latent embeddings, neighborhoods) "
                "promoted to biological identities (cell types, lineages) without an explicit "
                "annotation evidence source."
            ),
            example="'Cluster 0 are cytotoxic T cells' asserted from Leiden output alone.",
            affected_capabilities=(
                "scrna.exploratory_clustering",
                "spatial.morans_svg",
                "scvi.probabilistic_vae",
                "scrna.annotation_evidence",
            ),
            detection_rule="claim_checker cell-type assertion patterns + ABI forbidden_claims cell_type_identity_without_reference + router trap screen (annotation_evidence_available / open_set_detected)",
            required_behavior="BLOCK CLAIM: labels stay numeric until a reference atlas / curated marker panel is attached (BNS-II-008)",
            acceptable_degradation="Putative/candidate phrasing with mandatory external-validation caveat.",
            benchmark_cases=(
                "claim-celltype-hallucination-001",
                "adv-guess-celltypes-001",
                "l2-claim-celltype-hallucination-001",
                "l2-claim-celltype-qualified-002",
                "refuse-forbidden-celltype-promotion-003",
                "BF-004",
                "BF-006",
                "BF-014",
                "BF-022",
            ),
        ),
        FailureMode(
            failure_id="BN-F004",
            name="Identifier mismatch",
            category="DATA_INTEGRITY",
            severity="CRITICAL",
            definition=(
                "Entity identifiers from different namespaces are conflated or silently mapped "
                "(gene symbols vs ENSEMBL/Entrez, HGVS vs rsID/dbSNP, sample vs patient IDs), "
                "corrupting joins against knowledge sources."
            ),
            example="Annotating a DE table keyed on HGNC symbols against a pathway database keyed on Entrez IDs without a recorded mapping.",
            affected_capabilities=(
                "scrna.pseudobulk_de",
                "variant.acmg_classification",
                "nextflow.pipeline_launch",
            ),
            detection_rule=(
                "Router stage 3.5 trap screen: identifier_namespace vs reference_namespace mismatch -> refusal "
                "(wired since BioFailureBench, BF-008/BF-025); output-table namespace audit pending"
            ),
            required_behavior="REFUSE the join and request the identifier namespace, or record the mapping table in provenance",
            acceptable_degradation="None: silent cross-namespace joins are never acceptable.",
            benchmark_cases=(
                "BF-008",
                "BF-025",
            ),
        ),
        FailureMode(
            failure_id="BN-F005",
            name="Missing multiple-testing correction",
            category="INFERENTIAL_DESIGN",
            severity="HIGH",
            definition=(
                "Genome-scale scan statistics reported without false-discovery control (uncorrected "
                "p-values across thousands of genes presented as findings)."
            ),
            example="Reporting 800 'significant' marker genes at raw p < 0.05 from rank_genes_groups with no BH/FDR correction.",
            affected_capabilities=(
                "scrna.exploratory_clustering",
                "spatial.morans_svg",
                "scrna.pseudobulk_de",
            ),
            detection_rule=(
                "abi.enforce_statistical_warrant: multiple_testing == required and has_fdr_correction is False -> "
                "warrant capped at PRELIMINARY (wired since BioFailureBench, BF-005); static audit rule BFA-003"
            ),
            required_behavior="CAP EVIDENCE LEVEL: cap conclusion maturity at PRELIMINARY until corrected values are reported alongside any finding (BNS-CC-009)",
            acceptable_degradation="Exploratory ranking tables without inferential labels.",
            benchmark_cases=(
                "BF-005",
            ),
        ),
        FailureMode(
            failure_id="BN-F006",
            name="Invalid model assumption",
            category="INFERENTIAL_DESIGN",
            severity="CRITICAL",
            definition=(
                "A structural statistical assumption of the chosen method is violated beyond assay "
                "state: proportional hazards for Cox/log-rank, independence of censoring, "
                "linearity of the linear predictor, dispersion-mean trend in NB GLMs."
            ),
            example="Interpreting a log-rank p-value as a hazard-ratio effect under strongly crossing survival curves.",
            affected_capabilities=("survival.kaplan_meier", "scrna.pseudobulk_de", "spatial.inference_validity"),
            detection_rule="Capability preconditions (no_auto_pvs1_without_mechanism, positive_durations, non_zero_events) + assumption-specific audits (PLANNED: PH residual tests)",
            required_behavior="BLOCK CLAIM: downgrade to association language; REFUSE where the estimator is undefined (BNS-II-011..013)",
            acceptable_degradation="Descriptive statistics without inferential claims.",
            benchmark_cases=(
                "refuse-survival-all-censored-001",
                "BF-003",
                "BF-011",
                "BF-013",
                "BF-015",
                "BF-021",
                "BF-028",
            ),
        ),
        FailureMode(
            failure_id="BN-F007",
            name="Parameter instability",
            category="INFERENTIAL_DESIGN",
            severity="MEDIUM",
            definition=(
                "Reported findings are not stable under defensible perturbations of tunable "
                "parameters (clustering resolution, KNN graph k, number of HVGs, seeds)."
            ),
            example="A 'novel cell population' that disappears when Leiden resolution moves from 0.5 to 0.8 (ARI < 0.5).",
            affected_capabilities=(
                "scrna.exploratory_clustering",
                "spatial.morans_svg",
                "scvi.probabilistic_vae",
            ),
            detection_rule="integrity.audit_parameter_stability across the declared sweep; ARI below capability threshold",
            required_behavior="CAP EVIDENCE LEVEL: cap conclusion maturity at FRAGILE (BNS-XM-003)",
            acceptable_degradation="Findings reported as parameter-sensitive with the sweep attached in provenance.",
            benchmark_cases=(
                "l3-outcome-clustering-ari-stability-004",
                "BF-018",
                "BF-038",
            ),
        ),
        FailureMode(
            failure_id="BN-F008",
            name="Cross-database contradiction",
            category="DATA_INTEGRITY",
            severity="HIGH",
            definition=(
                "Independent knowledge sources disagree about the same entity (ClinVar classifications "
                "without concordance, conflicting pathway memberships, mismatched gene mappings across "
                "release versions)."
            ),
            example="An ACMG classification contradicted by newer ClinVar expert-reviewed status not present in the vendored truth set.",
            affected_capabilities=("variant.acmg_classification",),
            detection_rule=(
                "Router stage 3.5 trap screen: cross_database_contradiction metadata -> refusal with CONFLICTED "
                "guidance (wired since BioFailureBench, BF-016); ledger resolution marks claims CONFLICTED (BNS-CL-005)"
            ),
            required_behavior="Mark conclusion maturity CONFLICTED and surface both sources with identifiers and access dates (BNS-XM-006)",
            acceptable_degradation="Reported as discordant pending expert review; never silently resolved by preference order.",
            benchmark_cases=(
                "BF-016",
            ),
        ),
        FailureMode(
            failure_id="BN-F009",
            name="Missing spatial provenance",
            category="DATA_INTEGRITY",
            severity="CRITICAL",
            definition=(
                "Spatial statistics computed on coordinates whose origin is unrecorded or "
                "illegitimately substituted (a UMAP/PCA embedding passed off as physical tissue "
                "coordinates)."
            ),
            example="Moran's I 'spatially variable genes' computed over obsm['X_umap'] because obsm['spatial'] was absent.",
            affected_capabilities=("spatial.morans_svg", "spatial.inference_validity"),
            detection_rule=(
                "ABI input_contract coordinate_type_allowed; router stage 3.5 inspects coordinate_type metadata "
                "(wired since BioFailureBench: embedding substitutions refused, BF-007/BF-020)"
            ),
            required_behavior="REFUSE substitution, or DEGRADED advisory only when the capability explicitly allows justified_spatial_embedding (BNS-II-005/006)",
            acceptable_degradation="Analysis on a justified embedding with the substitution named in the evidence card and maturity capped FRAGILE.",
            benchmark_cases=(
                "refuse-spatial-degenerate-001",
                "frontier-coordinate-umap-substitution-001",
                "semantics-spatial-degenerate-coords-001",
                "BF-007",
                "BF-020",
                "BF-027",
                "BF-033",
            ),
        ),
        FailureMode(
            failure_id="BN-F010",
            name="Backend degradation masquerading",
            category="SYSTEM_DEGRADATION",
            severity="CRITICAL",
            definition=(
                "Output of a heuristic fallback or partial stack presented as if the canonical "
                "gold-standard backend had executed."
            ),
            example="A correlation-based local heuristic reported as 'PyDESeq2 Wald test results' because pydeseq2 was not installed.",
            affected_capabilities=tuple(CANONICAL_CAPABILITIES.keys()),
            detection_rule="contracts.ExecutionState.DEGRADED vs claimed backend; claim_checker model_substitution patterns",
            required_behavior="DEGRADE WITH DISCLOSURE: name the missing backend in the evidence card, cap maturity at FRAGILE (BNS-EF-002, BNS-AD-007)",
            acceptable_degradation="Heuristic output clearly labeled Grade C with the canonical backend named as unavailable.",
            benchmark_cases=(
                "backend-lifelines-missing-001",
                "backend-lifelines-strict-001",
                "backend-pydeseq2-missing-001",
                "backend-frontier-fallback-001",
                "backend-frontier-nofallback-001",
                "route-survival-km-001",
                "l2-claim-regulatory-honest-006",
                "BF-017",
                "BF-034",
                "BF-035",
            ),
        ),
        FailureMode(
            failure_id="BN-F011",
            name="Claim inflation",
            category="SEMANTIC_CLAIM",
            severity="CRITICAL",
            definition=(
                "A scientific claim asserted beyond the warrant of the underlying evidence class: "
                "causation from correlation, mechanism from autocorrelation, clinical action from "
                "research-grade output, regulatory certification from tooling."
            ),
            example="'Moran's I proves ligand-receptor-mediated cell-cell communication.'",
            affected_capabilities=tuple(CANONICAL_CAPABILITIES.keys()),
            detection_rule="abi.FORBIDDEN_CLAIM_CATALOG detection patterns at routing time and claim audit time (BNS-CC-012)",
            required_behavior="BLOCK CLAIM at routing; audit host responses at L2; RUO limitation mandatory (BNS-AD-009/010)",
            acceptable_degradation="Hedged formulation naming the actual evidence class ('consistent with', 'spatially autocorrelated').",
            benchmark_cases=(
                "refuse-forbidden-causal-communication-001",
                "refuse-forbidden-clinical-diagnosis-002",
                "refuse-forbidden-celltype-promotion-003",
                "claim-gxppart11-001",
                "claim-acmg-clinical-001",
                "l2-claim-causal-de-overclaim-003",
                "l2-claim-causal-de-honest-004",
                "l2-claim-regulatory-overclaim-005",
                "BF-009",
                "BF-023",
                "BF-026",
                "BF-030",
            ),
        ),
        FailureMode(
            failure_id="BN-F012",
            name="Unexecuted maturity claim",
            category="SEMANTIC_CLAIM",
            severity="HIGH",
            definition=(
                "Evidence maturity asserted for an analysis that did not execute, or above the "
                "capability's evidence ceiling: calibration claims without executions inflate "
                "epistemic warrant."
            ),
            example="L3 benchmark cases counted toward SUPPORTED calibration in an environment where the gold backend was never installed.",
            affected_capabilities=tuple(CANONICAL_CAPABILITIES.keys()),
            detection_rule="ExecutionState not in (EXECUTED,) while claimed maturity > UNASSESSED; abi.enforce_evidence_ceiling clamp (BNS-EM-006)",
            required_behavior="CAP EVIDENCE LEVEL: exclude from calibration accounting with disclosed skip counts; clamp claims to ceiling (BNS-EM-009)",
            acceptable_degradation="None: unexecuted analyses carry no maturity claim.",
            benchmark_cases=(
                "frontier-ceiling-spatial-supported-claim-005",
                "frontier-ceiling-pseudobulk-replicated-claim-006",
                "frontier-ceiling-acmg-clinvar-replicated-007",
                "frontier-ceiling-clustering-robust-claim-008",
                "BF-012",
                "BF-036",
                "BF-037",
            ),
        ),
    ]
}


# ==============================================================================
# Query APIs
# ==============================================================================


def get_failure_mode(failure_id: str) -> FailureMode:
    """Retrieve a failure mode by ID (BN-Fxxx)."""
    if failure_id not in FAILURE_TAXONOMY:
        raise KeyError(
            f"Unknown failure mode '{failure_id}'. Available: {sorted(FAILURE_TAXONOMY.keys())}"
        )
    return FAILURE_TAXONOMY[failure_id]


def list_failure_modes(
    capability_id: Optional[str] = None,
    category: Optional[str] = None,
    severity: Optional[str] = None,
) -> List[FailureMode]:
    """List failure modes, optionally filtered by capability, category, or severity."""
    modes = list(FAILURE_TAXONOMY.values())
    if capability_id:
        modes = [m for m in modes if capability_id in m.affected_capabilities]
    if category:
        modes = [m for m in modes if m.category.upper() == category.upper()]
    if severity:
        modes = [m for m in modes if m.severity.upper() == severity.upper()]
    return modes


def failure_modes_by_capability() -> Dict[str, List[str]]:
    """Inverted index: capability id -> failure mode IDs that affect it."""
    index: Dict[str, List[str]] = {cid: [] for cid in CANONICAL_CAPABILITIES}
    for mode in FAILURE_TAXONOMY.values():
        for cap in mode.affected_capabilities:
            index.setdefault(cap, []).append(mode.failure_id)
    return index


def classify_violation(violation_text: str) -> List[str]:
    """
    Map a runtime violation string onto taxonomy failure IDs via keyword
    signatures. Used to tag refusal payloads with their failure ontology IDs.
    """
    text = violation_text.lower()
    hits: List[str] = []
    signatures: List[tuple[str, tuple[str, ...]]] = [
        ("BN-F001", ("normalized", "integer", "count model", "log-normalized")),
        ("BN-F002", ("replicat", "pseudoreplication")),
        ("BN-F003", ("cell-type", "cell type", "cluster identity", "annotation")),
        ("BN-F004", ("identifier", "namespace", "mapping")),
        ("BN-F005", ("multiple testing", "fdr", "correction")),
        ("BN-F006", ("assumption", "censor", "duration", "pvs1", "mechanism")),
        ("BN-F007", ("parameter", "stability", "resolution", "perturbation")),
        ("BN-F008", ("contradiction", "discordant", "clinvar", "database")),
        ("BN-F009", ("spatial", "coordinate", "embedding", "spot")),
        ("BN-F010", ("backend", "degrad", "heuristic", "fallback")),
        ("BN-F011", ("forbidden claim", "causal", "communication", "diagnos", "compliant")),
        ("BN-F012", ("maturity", "ceiling", "calibration", "executed")),
    ]
    for failure_id, keywords in signatures:
        if any(k in text for k in keywords):
            hits.append(failure_id)
    return hits


def get_taxonomy_v1() -> Dict[str, Any]:
    """Return the full Failure Taxonomy v1 specification dictionary."""
    modes = list(FAILURE_TAXONOMY.values())
    return {
        "schema_version": TAXONOMY_SCHEMA_VERSION,
        "total_modes": len(modes),
        "categories": {
            "DATA_INTEGRITY": [m.failure_id for m in modes if m.category == "DATA_INTEGRITY"],
            "INFERENTIAL_DESIGN": [m.failure_id for m in modes if m.category == "INFERENTIAL_DESIGN"],
            "SEMANTIC_CLAIM": [m.failure_id for m in modes if m.category == "SEMANTIC_CLAIM"],
            "SYSTEM_DEGRADATION": [m.failure_id for m in modes if m.category == "SYSTEM_DEGRADATION"],
        },
        "severities": {
            "CRITICAL": [m.failure_id for m in modes if m.severity == "CRITICAL"],
            "HIGH": [m.failure_id for m in modes if m.severity == "HIGH"],
            "MEDIUM": [m.failure_id for m in modes if m.severity == "MEDIUM"],
        },
        "summary": taxonomy_summary(),
        "modes": [failure_to_dict(m) for m in modes],
    }


def failure_modes_matrix() -> Dict[str, Dict[str, Any]]:
    """Return a mapping matrix between capabilities and failure modes."""
    by_cap = failure_modes_by_capability()
    matrix = {}
    for cid, fids in by_cap.items():
        matrix[cid] = {
            "capability_id": cid,
            "failure_mode_count": len(fids),
            "failure_mode_ids": sorted(fids),
            "critical_count": sum(1 for fid in fids if FAILURE_TAXONOMY[fid].severity == "CRITICAL"),
        }
    return matrix


def taxonomy_summary() -> Dict[str, Any]:
    """Structural summary: counts, per-capability index, open gaps."""
    modes = list(FAILURE_TAXONOMY.values())
    total_cases = sum(len(m.benchmark_cases) for m in modes)
    return {
        "schema_version": TAXONOMY_SCHEMA_VERSION,
        "total_modes": len(modes),
        "modes_with_benchmark_coverage": sum(1 for m in modes if not m.open_gap and m.benchmark_cases),
        "open_gaps": [m.failure_id for m in modes if m.open_gap],
        "total_benchmark_case_links": total_cases,
        "by_capability": failure_modes_by_capability(),
    }


def failure_to_dict(mode: FailureMode) -> Dict[str, Any]:
    """Serialize a failure mode record."""
    return asdict(mode)
