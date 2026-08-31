"""
BioNexus Capability Certification Program (BNS-010).

A skill is documentation; a **Certified Scientific Capability** is an
executable contract that has survived a defined evidence program.

Tiers:
- CERTIFIED        all 14 criteria satisfied with recorded evidence
- VALIDATED        all core criteria (backend, contract, invariants,
                   failure modes, positive + negative tests) satisfied
- EXPERIMENTAL     formal contract exists with at least one passing test class
- CONNECTOR-ONLY   data-plane connector without scientific execution claims

Tier assignment is COMPUTED from evidence records, never asserted by hand:
a capability that lacks evidence for a criterion cannot reach the tier that
requires it (structural honesty, mirroring the frontier track philosophy).
The per-capability gap report is the certification roadmap.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List

from bionexus.abi import capability_abis
from bionexus.capabilities import CANONICAL_CAPABILITIES
from bionexus.failures import failure_modes_by_capability

# ==============================================================================
# The 14 Certification Criteria (BNS-010 §2)
# ==============================================================================

CERTIFICATION_CRITERIA: Dict[str, str] = {
    "reference_backend": "Canonical community backend declared, versioned, and probed at runtime.",
    "formal_input_contract": "Complete ABI input contract: allowed matrix states, coordinate types, required inputs.",
    "invariants": "Machine-checkable preconditions and deterministic refusal triggers.",
    "known_failure_modes": "Failure taxonomy modes (BN-Fxxx) linked, with detection rules.",
    "positive_test": "Verified execution producing the expected scientific result.",
    "negative_test": "Invalid inputs and invalid requests refused deterministically.",
    "adversarial_test": "Coercion / jailbreak attempts to bypass invariants blocked.",
    "public_reference_dataset": "Execution validated against a public dataset or truth set.",
    "independent_ground_truth": "Ground truth independent of the implementation under test.",
    "parameter_perturbation": "Stability audit across a declared parameter sweep.",
    "degradation_test": "Missing-backend behavior tested (refuse or disclose-degrade).",
    "provenance_test": "Provenance sidecar completeness and integrity tested.",
    "cross_host_test": "L2 claim audit executed across >= 2 host providers with agreement reported.",
    "external_reviewer": "Independent scientific review recorded (reviewer, date, findings).",
}

CORE_CRITERIA = [
    "reference_backend",
    "formal_input_contract",
    "invariants",
    "known_failure_modes",
    "positive_test",
    "negative_test",
]

# ==============================================================================
# Flagship Certification Track (BNS-015)
# ==============================================================================

# The flagship program concentrates certification effort on three capabilities
# with independent external validation rather than spreading self-tests across
# many. Three externally-validated CERTIFIED capabilities carry more scientific
# weight than ten self-defined, self-tested, self-certified ones (BNS-FC-001).
FLAGSHIP_CAPABILITIES: tuple = (
    "scrna.pseudobulk_de",           # A: scRNA differential expression / pseudoreplication
    "scrna.annotation_evidence",     # B: cell annotation evidence
    "spatial.inference_validity",    # C: spatial inference validity
)

# Criteria that cannot be satisfied by the implementer alone: the flagship
# program is, by construction, a program of *external* evidence.
EXTERNAL_CRITERIA = ("public_reference_dataset", "independent_ground_truth", "cross_host_test", "external_reviewer")

FLAGSHIP_PRINCIPLE = (
    "Three CERTIFIED capabilities with independent external validation outweigh "
    "ten self-tested certifications. The flagship track exists to make external "
    "evidence, not self-assertion, the path to CERTIFIED."
)


class CertificationTier(str, Enum):
    """Capability certification tiers (BNS-010 §1)."""

    CERTIFIED = "CERTIFIED"
    VALIDATED = "VALIDATED"
    EXPERIMENTAL = "EXPERIMENTAL"
    CONNECTOR_ONLY = "CONNECTOR-ONLY"


@dataclass
class CriterionEvidence:
    """Evidence for one certification criterion."""

    satisfied: bool
    evidence: str = ""  # pointer: test file, eval case id, dataset, review record
    note: str = ""


@dataclass
class CertificationRecord:
    """Computed certification state for one capability."""

    capability_id: str
    criteria: Dict[str, CriterionEvidence] = field(default_factory=dict)
    tier: CertificationTier = CertificationTier.EXPERIMENTAL
    satisfied_count: int = 0
    blocking_for_certified: List[str] = field(default_factory=list)
    blocking_for_validated: List[str] = field(default_factory=list)
    assessment_authority: str = "INTERNAL_EVIDENCE_ASSESSMENT"
    certification_effect: str = "NONE"
    independent_assurance_status: str = "NOT_ASSESSED"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "capability_id": self.capability_id,
            "tier": self.tier.value,
            "assessment_authority": self.assessment_authority,
            "certification_effect": self.certification_effect,
            "independent_assurance_status": self.independent_assurance_status,
            "satisfied_count": self.satisfied_count,
            "total_criteria": len(CERTIFICATION_CRITERIA),
            "blocking_for_certified": self.blocking_for_certified,
            "blocking_for_validated": self.blocking_for_validated,
            "criteria": {k: asdict(v) for k, v in self.criteria.items()},
        }


# ==============================================================================
# Evidence records (honest, pointer-backed; gaps are the roadmap)
# ==============================================================================

_EVIDENCE: Dict[str, Dict[str, tuple[bool, str, str]]] = {
    "scrna.pseudobulk_de": {
        "reference_backend": (True, "pydeseq2 >= 0.4.0 (bionexus-reliability[deseq])", "ABI execution reference"),
        "formal_input_contract": (True, "abi.get_capability_abi('scrna.pseudobulk_de')", "raw_counts only; sample_design required"),
        "invariants": (True, "preconditions: min_replicates, raw_integer_counts", ""),
        "known_failure_modes": (True, "BN-F001, BN-F002, BN-F006, BN-F011, BN-F012", ""),
        "positive_test": (True, "l3-outcome-pseudobulk-deseq-003 (planted DEG g0 recovered)", "full-extras CI matrix"),
        "negative_test": (True, "refuse-pseudorep-001/002, refuse-normalized-counts-001", ""),
        "adversarial_test": (True, "adv-force-pseudorep-001, adv-log-as-raw-001", ""),
        "public_reference_dataset": (True, "validation/pseudobulk/REPORT.json -> dataset.accession GSE96583 (Kang et al. 2018, Nat Biotechnol doi:10.1038/nbt.4042); executed: donor-aware pseudobulk DE on 13487 singlets / 8 donors, published-support overlap 0.66 >= 0.50 (PASS)", "Real-data external validation executed, not skipped"),
        "independent_ground_truth": (True, "Planted DEG with known fold change (truth independent of PyDESeq2); flagship truth = published-knowledge membership set (MSigDB Hallmark IFN + QuickGO curated GO), independent of the DE implementation", ""),
        "parameter_perturbation": (True, "l3-outcome-pseudobulk-stability-005 (declared leave-one-out sample-composition grid; significant-DEG call set Jaccard >= 0.80 via audit_parameter_stability)", ""),
        "degradation_test": (True, "backend-pydeseq2-missing-001 (deterministic backend-absence simulation: canonical refusal with pip-install remedy even under allow_degraded consent)", "Environment-independent eval case"),
        "provenance_test": (True, "tests/unit/test_provenance_tracker.py, test_artifacts.py", ""),
        "cross_host_test": (False, "cross-host/COMPARISON.json (framework: codex + claude-code; 0 traps compared, agreement_rate null)", "Cross-host framework established but no L2 claim audit executed; blocked: no provider API keys and no codex CLI in environment (only claude-code available), and consistency requires >= 2 hosts"),
        "external_reviewer": (False, "review/SCIENTIFIC_REVIEW.json (3 reviewer slots; all PENDING; status framework_created_pending_review)", "Scientific review framework established but no review conducted; requires human domain reviewers, not automatable"),
    },
    "scrna.exploratory_clustering": {
        "reference_backend": (True, "scanpy >= 1.10.0 (bionexus-reliability[goldchain])", ""),
        "formal_input_contract": (True, "abi.get_capability_abi('scrna.exploratory_clustering')", ""),
        "invariants": (True, "preconditions: min_cells_and_genes", ""),
        "known_failure_modes": (True, "BN-F001, BN-F003, BN-F005, BN-F007, BN-F011", ""),
        "positive_test": (True, "l3-outcome-marker-recovery-001 (CD3D/MS4A1/CD14 planted markers)", ""),
        "negative_test": (True, "refuse-forbidden-celltype-promotion-003 (claim-level refusal)", "no input-level refusal case for n_cells < 20 yet"),
        "adversarial_test": (True, "adv-guess-celltypes-001 (coercion; claims audited)", ""),
        "public_reference_dataset": (False, "", "Synthetic PBMC-like fixture; no vendored PBMC3K-class dataset"),
        "independent_ground_truth": (True, "Planted canonical marker genes", ""),
        "parameter_perturbation": (True, "l3-outcome-clustering-ari-stability-004 (resolution sweep, ARI >= 0.80)", ""),
        "degradation_test": (True, "tests/unit/test_backend_matrix.py goldchain-missing honesty paths", "covers stack absence, not a dedicated eval case"),
        "provenance_test": (True, "tests/unit/test_provenance_tracker.py", ""),
        "cross_host_test": (False, "", "Single-host replay only"),
        "external_reviewer": (False, "", "No independent scientific review recorded"),
    },
    "spatial.morans_svg": {
        "reference_backend": (True, "squidpy >= 1.3.0 (bionexus-reliability[spatial])", ""),
        "formal_input_contract": (True, "abi.get_capability_abi('spatial.morans_svg')", "coordinates required; physical | justified_spatial_embedding"),
        "invariants": (True, "preconditions: spatial_coords_present, non_degenerate_geometry", ""),
        "known_failure_modes": (True, "BN-F003, BN-F007, BN-F009, BN-F011", ""),
        "positive_test": (True, "l3-outcome-spatial-svg-002 (planted SVG_LEFT gradient recovered)", ""),
        "negative_test": (True, "refuse-spatial-degenerate-001, semantics-spatial-degenerate-coords-001", ""),
        "adversarial_test": (False, "", "No spatial adversarial/jailbreak case in the suites"),
        "public_reference_dataset": (False, "", "Synthetic coordinates only"),
        "independent_ground_truth": (True, "Planted spatial gradient genes", ""),
        "parameter_perturbation": (False, "", "No KNN-k sweep audit wired for Moran's I"),
        "degradation_test": (False, "", "No dedicated missing-squidpy behavior case"),
        "provenance_test": (True, "tests/unit/test_provenance_tracker.py", ""),
        "cross_host_test": (False, "", "Single-host replay only"),
        "external_reviewer": (False, "", "No independent scientific review recorded"),
    },
    "survival.kaplan_meier": {
        "reference_backend": (True, "lifelines >= 0.27.0 (bionexus-reliability[survival])", ""),
        "formal_input_contract": (True, "abi.get_capability_abi('survival.kaplan_meier')", ""),
        "invariants": (True, "preconditions: positive_durations, non_zero_events", ""),
        "known_failure_modes": (True, "BN-F006, BN-F010, BN-F011", ""),
        "positive_test": (True, "tests/unit/test_clinical_cohort.py (KM estimation on fixtures)", ""),
        "negative_test": (True, "refuse-survival-all-censored-001", ""),
        "adversarial_test": (False, "", "No survival adversarial case"),
        "public_reference_dataset": (False, "", "No public cohort vendored"),
        "independent_ground_truth": (False, "", "Fixture truth generated alongside the analyzer; no independent truth set"),
        "parameter_perturbation": (False, "", "Not applicable to non-parametric KM point estimation; no band-width/CI sensitivity audit"),
        "degradation_test": (True, "backend-lifelines-missing-001 (degraded advisory), backend-lifelines-strict-001 (strict refusal)", ""),
        "provenance_test": (True, "tests/unit/test_provenance_tracker.py", ""),
        "cross_host_test": (False, "", "Single-host replay only"),
        "external_reviewer": (False, "", "No independent scientific review recorded"),
    },
    "scvi.probabilistic_vae": {
        "reference_backend": (True, "scvi-tools >= 1.0.0 (bionexus-reliability[scverse])", ""),
        "formal_input_contract": (True, "abi.get_capability_abi('scvi.probabilistic_vae')", "raw_counts only"),
        "invariants": (True, "preconditions: raw_counts_only", ""),
        "known_failure_modes": (True, "BN-F001, BN-F003, BN-F007, BN-F011", ""),
        "positive_test": (True, "tests/unit/test_gold_wrappers.py scvi smoke paths (full-extras matrix)", ""),
        "negative_test": (True, "refuse-scvi-normalized-001", ""),
        "adversarial_test": (False, "", "No scVI adversarial case"),
        "public_reference_dataset": (False, "", "No public dataset vendored"),
        "independent_ground_truth": (False, "", "No independent integration-quality truth set"),
        "parameter_perturbation": (False, "", "No seed/architecture sweep audit"),
        "degradation_test": (False, "", "No dedicated missing-scvi behavior case"),
        "provenance_test": (True, "tests/unit/test_provenance_tracker.py", ""),
        "cross_host_test": (False, "", "Single-host replay only"),
        "external_reviewer": (False, "", "No independent scientific review recorded"),
    },
    "allotrope.format_conversion": {
        "reference_backend": (True, "allotropy >= 0.1.30 (bionexus-reliability[allotrope])", ""),
        "formal_input_contract": (True, "abi.get_capability_abi('allotrope.format_conversion')", ""),
        "invariants": (True, "preconditions: supported_instrument_or_mapping", ""),
        "known_failure_modes": (True, "BN-F010, BN-F011", ""),
        "positive_test": (True, "tests/unit/test_yaml_mapping_engine.py + instrument conversion suites", ""),
        "negative_test": (True, "claim-gxppart11-001 (compliance claim refused at routing)", "missing_mapping input-level case not in eval suites"),
        "adversarial_test": (False, "", "No allotrope adversarial case"),
        "public_reference_dataset": (False, "", "No public instrument record set vendored"),
        "independent_ground_truth": (False, "", "Round-trip checks are self-referential; no external ASM truth set"),
        "parameter_perturbation": (False, "", "Not applicable: deterministic syntactic mapping"),
        "degradation_test": (False, "", "No dedicated missing-allotropy behavior case"),
        "provenance_test": (True, "tests/unit/test_kernel_and_honesty.py::test_provenance_sidecar_disclaims_part11", ""),
        "cross_host_test": (False, "", "Single-host replay only"),
        "external_reviewer": (False, "", "No independent scientific review recorded"),
    },
    "nextflow.pipeline_launch": {
        "reference_backend": (True, "local deterministic generator (nf-core schema)", ""),
        "formal_input_contract": (True, "abi.get_capability_abi('nextflow.pipeline_launch')", ""),
        "invariants": (True, "preconditions: valid_paired_reads", ""),
        "known_failure_modes": (True, "BN-F004, BN-F011", ""),
        "positive_test": (True, "tests/unit/test_nextflow_preflight.py (samplesheet validation)", ""),
        "negative_test": (False, "Refusal trigger missing_fastq_files is contract-defined", "not exercised by any eval suite or unit test"),
        "adversarial_test": (False, "", "No nextflow adversarial case"),
        "public_reference_dataset": (False, "", "No public samplesheet corpus vendored"),
        "independent_ground_truth": (False, "", "Launch artifacts are not analytical outcomes; no truth set applies"),
        "parameter_perturbation": (False, "", "Not applicable: artifact generation"),
        "degradation_test": (False, "", "Not exercised"),
        "provenance_test": (True, "tests/unit/test_artifacts.py", ""),
        "cross_host_test": (False, "", "Single-host replay only"),
        "external_reviewer": (False, "", "No independent scientific review recorded"),
    },
    "variant.acmg_classification": {
        "reference_backend": (True, "local deterministic Bayesian combiner (bionexus)", ""),
        "formal_input_contract": (True, "abi.get_capability_abi('variant.acmg_classification')", ""),
        "invariants": (True, "preconditions: no_auto_pvs1_without_mechanism", ""),
        "known_failure_modes": (True, "BN-F004, BN-F006, BN-F008, BN-F011", ""),
        "positive_test": (True, "tests/unit/test_golden_biology.py + test_kernel_and_honesty.py ACMG paths", ""),
        "negative_test": (True, "claim-acmg-clinical-001 (clinical report request refused); PVS1 mechanism guard tests", ""),
        "adversarial_test": (False, "", "No variant adversarial case"),
        "public_reference_dataset": (True, "evals/datasets/benchmarks/clinvar_controls.json (vendored ClinVar-derived controls)", ""),
        "independent_ground_truth": (True, "ClinVar expert-reviewed classifications (independent of the combiner)", ""),
        "parameter_perturbation": (False, "", "Deterministic rule combination; no probabilistic sweep applicable"),
        "degradation_test": (False, "", "No dedicated behavior case"),
        "provenance_test": (True, "tests/unit/test_provenance_tracker.py", ""),
        "cross_host_test": (False, "", "Single-host replay only"),
        "external_reviewer": (False, "", "No independent scientific review recorded"),
    },
    "scrna.annotation_evidence": {
        "reference_backend": (True, "local deterministic evidence combiner (bionexus >= 0.9.0)", ""),
        "formal_input_contract": (True, "abi.get_capability_abi('scrna.annotation_evidence')", ""),
        "invariants": (True, "preconditions: annotation_source_recorded, negative_markers_evaluated", ""),
        "known_failure_modes": (True, "BN-F003, BN-F011", "router traps: no_annotation_evidence, open_set_population"),
        "positive_test": (True, "tests/unit/test_flagship_capabilities.py (SUPPORTED/TENTATIVE verdict ladder)", ""),
        "negative_test": (True, "BF-004 (no evidence source refused), BF-022 (open-set refused), test_flagship_capabilities", ""),
        "adversarial_test": (True, "evals/annotation_stress_test.py::test_dim10_claim_interception (coercion audit)", ""),
        "public_reference_dataset": (True, "BN-ANN-IV-001 executed two real public CITE-seq datasets; BN-ANN-IV-003 evaluated 148297 mapped cells against external Azimuth PBMC reference annotations", "BN-ANN-IV-003 met its locked endpoints but was not blinded to label distributions and is capped at CANDIDATE_EXTERNAL_REFERENCE_NONBLINDED"),
        "independent_ground_truth": (False, "BN-ANN-IV-003 uses externally authored reference annotations; BN-ANN-IV-001 uses paired ADT anchors", "Reference annotations and orthogonal ADT are not experimental biological ground truth; no warrant profile was activated"),
        "parameter_perturbation": (True, "evals/annotation_stress_test.py::test_dim9_resolution_perturbation (ARI stability >= 0.80)", ""),
        "degradation_test": (True, "evals/annotation_stress_test.py::test_dim7_open_set_gating (missing evidence -> ABSTAIN)", ""),
        "provenance_test": (True, "tests/unit/test_provenance_tracker.py, tests/unit/test_validation_artifacts.py", ""),
        "cross_host_test": (False, "cross-host/COMPARISON.json (framework: codex + claude-code; 0 traps compared)", "Cross-host framework established but no L2 claim audit executed"),
        "external_reviewer": (False, "review/SCIENTIFIC_REVIEW.json (reviewer-3 assigned; all PENDING; status framework_created_pending_review)", "Scientific review framework established but no review conducted"),
    },
    "spatial.inference_validity": {
        "reference_backend": (True, "local bounded alternative-explanation battery (bionexus >= 0.10.0)", ""),
        "formal_input_contract": (True, "abi.get_capability_abi('spatial.inference_validity')", ""),
        "invariants": (True, "preconditions: physical coordinates, state revisions, bounded graphs, profile-conditioned decisions", ""),
        "known_failure_modes": (True, "BN-F006, BN-F009, BN-F011", "router traps: embedding_substitution, no_controls_provided"),
        "positive_test": (True, "tests/unit/test_spatial_alternative_battery.py (executable synthetic contract fixture) + test_flagship_capabilities.py (verdict ladder)", "Synthetic approved profiles are software fixtures only"),
        "negative_test": (True, "test_spatial_alternative_battery.py (missing calibration/contact, nonphysical coordinates, graph bounds, unestimable baseline) + BF-011/BF-015", ""),
        "adversarial_test": (True, "evals/spatial_stress_test.py::test_dim11_executable_battery + test_dim2_segmentation_leakage", "Executable battery correctly remains FRAGILE without an approved real spatial profile"),
        "public_reference_dataset": (False, "validation/spatial/studies/BN-SP-IV-001/REPORT.json -> authentic official Xenium XOA v4 tiny output executed", "10x documents the tiny subset as format-testing material not intended for biological conclusions; it therefore does not satisfy the public scientific reference standard"),
        "independent_ground_truth": (False, "BN-SP-IV-001 manufactured artifact endpoints on authentic instrument bytes; one locked endpoint failed", "No independent pathology or segmentation ground truth was executed"),
        "parameter_perturbation": (True, "evals/spatial_stress_test.py::test_dim7_radius_sensitivity (neighborhood radius sweep 15-100um)", ""),
        "degradation_test": (True, "test_spatial_alternative_battery.py (FAILED -> CONFLICTED; missing approved profile -> FRAGILE; unestimable baseline -> ABSTAIN)", ""),
        "provenance_test": (True, "tests/unit/test_provenance_tracker.py, tests/unit/test_validation_artifacts.py", ""),
        "cross_host_test": (False, "cross-host/COMPARISON.json (framework: codex + claude-code; 0 traps compared)", "Cross-host framework established but no L2 claim audit executed"),
        "external_reviewer": (False, "review/SCIENTIFIC_REVIEW.json (reviewer-2 assigned; all PENDING; status framework_created_pending_review)", "Scientific review framework established but no review conducted"),
    },
}


# ==============================================================================
# Tier computation
# ==============================================================================


def compute_tier(criteria: Dict[str, CriterionEvidence | bool]) -> CertificationTier:
    """
    Compute the certification tier from criterion evidence (BNS-010 §3).

    CERTIFIED requires ALL criteria; VALIDATED requires all core criteria;
    EXPERIMENTAL requires a formal contract plus at least one passing test
    class. Tiers are never asserted past their evidence. Values may be
    CriterionEvidence records or plain booleans.
    """

    def ok(name: str) -> bool:
        ev = criteria.get(name)
        if isinstance(ev, bool):
            return ev
        return ev is not None and ev.satisfied

    if all(ok(name) for name in CERTIFICATION_CRITERIA):
        return CertificationTier.CERTIFIED

    if all(ok(c) for c in CORE_CRITERIA):
        return CertificationTier.VALIDATED

    if ok("formal_input_contract") and (ok("positive_test") or ok("negative_test")):
        return CertificationTier.EXPERIMENTAL

    return CertificationTier.CONNECTOR_ONLY


def _ivn_external_overrides(capability_id: str) -> Dict[str, tuple[bool, str, str]]:
    """IVN-derived evidence for the two external criteria of a flagship.

    The Independent Validation Network (BNS-023) can only ever *raise* a
    criterion above its static baseline: while the network quotas are unmet
    the static verdicts stand and this returns an empty dict, so certification
    output is unchanged until hash-verified external-lab studies or blinded
    non-author reviews actually exist in ``validation/ivn/REGISTRY.json``.
    """
    if capability_id not in FLAGSHIP_CAPABILITIES:
        return {}
    try:
        from pathlib import Path

        from bionexus import ivn as _ivn

        registry = _ivn.load_registry()
        assessment = _ivn.evaluate_capability(capability_id, registry, repo_root=Path.cwd())
    except Exception:  # no registry, unreadable, or unusable cwd: keep static evidence
        return {}
    checks = {check.requirement: check for check in assessment.checks}
    counted_ids = set(assessment.counted_lab_studies)
    counted_studies = [study for study in registry.lab_studies if study.study_id in counted_ids]
    distinct_hosts = {study.host.strip().casefold() for study in counted_studies if study.host.strip()}
    overrides: Dict[str, tuple[bool, str, str]] = {}
    labs = checks.get("external_labs")
    if labs and labs.satisfied and len(distinct_hosts) >= 2:
        overrides["cross_host_test"] = (
            True,
            "validation/ivn/REGISTRY.json (IVN external labs: "
            f"{labs.observed}; distinct hosts: {len(distinct_hosts)})",
            "Independent Validation Network external-lab quota satisfied with "
            "hash-verified studies executed on >= 2 distinct hosts",
        )
    reviewers = checks.get("non_author_reviewers")
    if reviewers and reviewers.satisfied:
        overrides["external_reviewer"] = (
            True,
            "validation/ivn/REGISTRY.json (IVN non-author reviewers: "
            f"{reviewers.observed})",
            "Independent Validation Network non-author reviewer quota satisfied "
            "with blinded, attested reviews by reviewers outside the author roster",
        )
    return overrides


def certify_capability(capability_id: str) -> CertificationRecord:
    """Compute the honest certification record for a capability."""
    if capability_id not in CANONICAL_CAPABILITIES:
        raise KeyError(f"Unknown capability '{capability_id}'. Available: {sorted(CANONICAL_CAPABILITIES)}")

    static = _EVIDENCE.get(capability_id)
    evidence = dict(static) if static else None
    if evidence is not None:
        evidence.update(_ivn_external_overrides(capability_id))
    criteria: Dict[str, CriterionEvidence]
    if evidence is None:
        # No recorded evidence at all: connector-grade only.
        criteria = {name: CriterionEvidence(satisfied=False, evidence="", note="no evidence recorded") for name in CERTIFICATION_CRITERIA}
    else:
        criteria = {
            name: CriterionEvidence(satisfied=sat, evidence=ptr, note=note)
            for name, (sat, ptr, note) in evidence.items()
        }
        # Structural cross-checks: contract-derived criteria cannot be claimed
        # without their live sources (mirrors the drift-guard philosophy).
        abis = capability_abis()
        if not abis[capability_id].input_contract.required_inputs:
            criteria["formal_input_contract"].satisfied = False
        if not CANONICAL_CAPABILITIES[capability_id].preconditions:
            criteria["invariants"].satisfied = False
        if not failure_modes_by_capability().get(capability_id):
            criteria["known_failure_modes"].satisfied = False

    tier = compute_tier(criteria)
    satisfied = [name for name, ev in criteria.items() if ev.satisfied]
    return CertificationRecord(
        capability_id=capability_id,
        criteria=criteria,
        tier=tier,
        satisfied_count=len(satisfied),
        blocking_for_certified=[n for n in CERTIFICATION_CRITERIA if n not in satisfied],
        blocking_for_validated=[c for c in CORE_CRITERIA if c not in satisfied],
    )


def flagship_program() -> Dict[str, Any]:
    """
    The flagship certification track (BNS-015): the three capabilities that
    will reach CERTIFIED through independent external evidence first.
    """
    records = {cid: certify_capability(cid) for cid in FLAGSHIP_CAPABILITIES}
    certified = [cid for cid, rec in records.items() if rec.tier is CertificationTier.CERTIFIED]
    return {
        "principle": FLAGSHIP_PRINCIPLE,
        "flagship_target_certified": 3,
        "certified": certified,
        "progress": f"{len(certified)}/{len(FLAGSHIP_CAPABILITIES)}",
        "external_criteria": list(EXTERNAL_CRITERIA),
        "capabilities": {
            cid: {
                "current_tier": rec.tier.value,
                "satisfied_count": rec.satisfied_count,
                "blocking_for_certified": rec.blocking_for_certified,
                "external_criteria_remaining": [c for c in EXTERNAL_CRITERIA if c in rec.blocking_for_certified],
            }
            for cid, rec in records.items()
        },
    }


def certification_report() -> Dict[str, Any]:
    """
    Full certification report: per-capability records, tier distribution,
    the flagship track (BNS-015), and the honest gap analysis that
    constitutes the certification roadmap.
    """
    records = {cid: certify_capability(cid) for cid in CANONICAL_CAPABILITIES}
    tiers: Dict[str, List[str]] = {t.value: [] for t in CertificationTier}
    for cid, rec in records.items():
        tiers[rec.tier.value].append(cid)

    certified_count = len(tiers[CertificationTier.CERTIFIED.value])
    return {
        "assessment_authority": "INTERNAL_EVIDENCE_ASSESSMENT",
        "certification_effect": "NONE",
        "independent_assurance_status": "NOT_ASSESSED",
        "tier_distribution": tiers,
        "certified_count": certified_count,
        "m4_target_certified": 10,
        "m4_gap": max(0, 10 - certified_count),
        "criteria_catalog": CERTIFICATION_CRITERIA,
        "core_criteria": CORE_CRITERIA,
        "flagship": flagship_program(),
        "records": {cid: rec.to_dict() for cid, rec in records.items()},
        "roadmap": {
            cid: {
                "current_tier": rec.tier.value,
                "blocking_for_certified": rec.blocking_for_certified,
            }
            for cid, rec in records.items()
        },
    }
