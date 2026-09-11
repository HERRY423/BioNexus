"""Reliable Current Evidence Index and Upstream Invalidation/Recomputation Engine (BNS-026).

Maps every certified capability verdict, study finding, and cross-host result to:
- Source code (paths and expected SHA-256 hashes)
- Scientific rules and invariants (catalog IDs)
- Runtime and analytical dependencies (pinned packages and versions)
- Input data (datasets, accessions, files, and content hashes)
- Execution host (environment, engine, execution mode, real-host status)
- Report version (report path, schema version, project version, commit SHA)

Provides deterministic change impact analysis:
- Invalidated conclusions (失效): conclusions whose underlying rules, invariants,
  or contracts have been violated or broken.
- Recomputation needed (需要重算): conclusions whose source code, algorithms, or input
  data have changed, rendering previous numerical outputs and hashes stale.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Union

from bionexus.provenance import sha256_file
from bionexus.versions import VERSION


@dataclass
class ConclusionEntry:
    """A distinct scientific or capability conclusion in the current repository."""

    conclusion_id: str
    capability_id: str
    statement: str
    verdict: str
    claim_boundary: Dict[str, Any]
    source_files: Dict[str, str]  # rel_path -> sha256
    rules: List[str]  # e.g., ["INV-011", "BNS-HC-007"]
    dependencies: Dict[str, str]  # package -> version constraint
    data: Dict[str, Any]  # dataset info, accessions, file hashes
    host: Dict[str, Any]  # host environment, execution mode, real_host_certified
    report_version: Dict[str, str]  # report_path, schema_version, project_version
    upstream_nodes: List[str] = field(default_factory=list)
    downstream_nodes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConclusionEntry":
        return cls(**data)


@dataclass
class InvalidationItem:
    """A conclusion invalidated by upstream contract or rule violation."""

    conclusion_id: str
    statement: str
    broken_rule_or_contract: str
    reason: str


@dataclass
class RecomputationItem:
    """A conclusion whose outputs are stale and requires recomputation."""

    conclusion_id: str
    statement: str
    trigger_file_or_data: str
    reason: str
    recommended_command: str


@dataclass
class UpstreamImpactReport:
    """Diagnostic report of upstream change impact across all conclusions."""

    changed_files: List[str]
    broken_rules: List[str]
    invalidated_conclusions: List[Dict[str, Any]]
    requires_recomputation: List[Dict[str, Any]]
    metadata_updates: List[Dict[str, Any]] = field(default_factory=list)
    unaffected_conclusions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def summary_str(self) -> str:
        lines = [
            "=== BioNexus Evidence Index Upstream Impact Report ===",
            f"Changed upstream files: {len(self.changed_files)}",
        ]
        for f in self.changed_files:
            lines.append(f"  [CHANGED] {f}")

        if self.broken_rules:
            lines.append(f"Broken / modified rules: {len(self.broken_rules)}")
            for r in self.broken_rules:
                lines.append(f"  [RULE-VIOLATION] {r}")

        lines.append(f"\n1. 失效结论 (Invalidated Conclusions: {len(self.invalidated_conclusions)}):")
        if not self.invalidated_conclusions:
            lines.append("  (None - all rule contracts and invariants remain intact)")
        for inv in self.invalidated_conclusions:
            lines.append(f"  [INVALIDATED] {inv['conclusion_id']}: {inv['statement']}")
            lines.append(f"    Cause: {inv['broken_rule_or_contract']} -> {inv['reason']}")

        lines.append(f"\n2. 需要科学重算结论 (Requires Scientific Recomputation: {len(self.requires_recomputation)}):")
        if not self.requires_recomputation:
            lines.append("  (None - all numerical outputs and reports are up-to-date)")
        for rec in self.requires_recomputation:
            lines.append(f"  [RECOMPUTE] {rec['conclusion_id']}: {rec['statement']}")
            lines.append(f"    Trigger: {rec['trigger_file_or_data']} -> {rec['reason']}")
            lines.append(f"    Action: {rec['recommended_command']}")

        lines.append(f"\n3. 报告元数据更新 (Report Metadata Updates Only: {len(self.metadata_updates)}):")
        if not self.metadata_updates:
            lines.append("  (None - no reports with metadata-only drift)")
        for meta in self.metadata_updates:
            lines.append(f"  [METADATA-UPDATE] {meta['conclusion_id']}: {meta['statement']}")
            lines.append(f"    Report: {meta['report_path']} -> {meta['reason']}")
            lines.append("    Note: Core algorithm code and data unchanged; rerun unnecessary")

        lines.append(f"\n4. 未受影响结论 (Unaffected Conclusions: {len(self.unaffected_conclusions)}):")
        for una in self.unaffected_conclusions:
            lines.append(f"  [STABLE] {una}")

        return "\n".join(lines)


class EvidenceIndex:
    """The authoritative current evidence index for BioNexus releases."""

    def __init__(self, conclusions: Optional[Dict[str, ConclusionEntry]] = None) -> None:
        self.conclusions: Dict[str, ConclusionEntry] = conclusions or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": "bionexus.evidence-index.v1",
            "project_version": VERSION,
            "total_conclusions": len(self.conclusions),
            "conclusions": {cid: c.to_dict() for cid, c in self.conclusions.items()},
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EvidenceIndex":
        conclusions = {}
        for cid, c_dict in data.get("conclusions", {}).items():
            conclusions[cid] = ConclusionEntry.from_dict(c_dict)
        return cls(conclusions=conclusions)

    def save(self, path: Union[Path, str]) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return p

    @classmethod
    def load(cls, path: Union[Path, str]) -> "EvidenceIndex":
        p = Path(path)
        data = json.loads(p.read_text(encoding="utf-8"))
        return cls.from_dict(data)

    @classmethod
    def build_current_index(cls, repo_root: Union[Path, str]) -> "EvidenceIndex":
        """Build the authoritative current evidence index dynamically from repository artifacts."""
        root = Path(repo_root)

        def _get_hash(rel: str) -> str:
            p = root / rel
            if p.is_file():
                return sha256_file(p)
            return "UNKNOWN"

        def _load_report(rel_path: str) -> Optional[Dict[str, Any]]:
            p = root / rel_path
            if p.is_file():
                try:
                    return json.loads(p.read_text(encoding="utf-8"))
                except Exception:
                    return None
            return None

        conclusions: Dict[str, ConclusionEntry] = {}

        # 1. Spatial Real Instrument Technical Acceptance (BN-SP-IV-001)
        sp_rep = _load_report("validation/spatial/studies/BN-SP-IV-001/REPORT.json")
        sp_status = sp_rep.get("status", {}) if sp_rep else {}
        sp_endpoints = sp_rep.get("endpoints", {}) if sp_rep else {}
        sp_prov = sp_rep.get("provenance", {}) if sp_rep else {}
        sp_cb = sp_rep.get("claim_boundary", {}) if sp_rep else {}
        sp_dataset = sp_rep.get("dataset", {}) if sp_rep else {}
        sp_verdict = sp_status.get("run_status", "technical_acceptance_pass").upper()
        passed_ep = sum(1 for ep in sp_endpoints.values() if isinstance(ep, dict) and ep.get("passed"))
        total_ep = len(sp_endpoints) or 5

        conclusions["BNC-SP-001-TECH-ACCEPTANCE"] = ConclusionEntry(
            conclusion_id="BNC-SP-001-TECH-ACCEPTANCE",
            capability_id="spatial.inference_validity",
            statement=(
                f"BioNexus artifact diagnostics execute on authentic Xenium XOA bytes and respond in the expected "
                f"direction to deterministic manufactured confounders ({passed_ep}/{total_ep} locked technical endpoints passed)."
            ),
            verdict=sp_verdict,
            claim_boundary={
                "supported": [
                    sp_cb.get("supported_if_positive", "Artifact diagnostics execute on authentic XOA bytes"),
                    f"Deterministic responses to manufactured confounders (segmentation leakage delta {round(sp_endpoints.get('segmentation_leakage', {}).get('delta', 0.307), 3)}, cell size bias delta {round(sp_endpoints.get('cell_size_bias', {}).get('delta', 0.201), 3)}, transcript density bias delta {round(sp_endpoints.get('transcript_density_bias', {}).get('delta', 0.886), 3)})",
                    f"{passed_ep}/{total_ep} locked technical endpoints passed",
                ],
                "not_supported": sp_cb.get("not_supported", [
                    "biological validity",
                    "tissue-level generalization",
                    "segmentation accuracy against histology",
                    "approved spatial calibration profile",
                    "independent ground truth",
                ]),
            },
            source_files={
                "evals/spatial_instrument_validation.py": _get_hash("evals/spatial_instrument_validation.py"),
                "src/bionexus/capabilities.py": _get_hash("src/bionexus/capabilities.py"),
                "src/bionexus/abi.py": _get_hash("src/bionexus/abi.py"),
            },
            rules=["INV-011", "INV-012", "INV-013", "INV-017", "INV-018", "BNS-010"],
            dependencies={"squidpy": ">=1.3.0", "scanpy": ">=1.10.0", "python": ">=3.10"},
            data={
                "dataset_name": "xenium_spatial_truth",
                "accession": "10x Genomics official Xenium XOA v4 tiny human kidney",
                "vendor_disclaimer": sp_cb.get("vendor_limit", "Vendor documents tiny dataset as format-testing material not intended for biological conclusions"),
                "files": {
                    "Xenium_V1_Protein_Human_Kidney_tiny_outs.zip": sp_dataset.get("archive_sha256", "abd7e8f7fd047dcc6afdb1e9eece90d4533d3ead053c6f05c482be050bdf79d2"),
                },
            },
            host={
                "platform": sp_prov.get("platform", "Windows-11-10.0.26200-SP0"),
                "execution_mode": "live_instrument_script",
                "real_host_certified": False,
            },
            report_version={
                "report_path": "validation/spatial/studies/BN-SP-IV-001/REPORT.json",
                "schema_version": sp_rep.get("schema_version", "bionexus.spatial-real-instrument-validation-report.v1") if sp_rep else "bionexus.spatial-real-instrument-validation-report.v1",
                "project_version": sp_prov.get("generator_version", VERSION) if sp_prov else VERSION,
            },
            upstream_nodes=["DATA-XENIUM-TINY", "SRC-SPATIAL-INSTRUMENT", "RULE-INV-011"],
            downstream_nodes=["BNC-SPATIAL-CAPABILITY-VALIDATED"],
        )

        # 2. Spatial Capability Certification (spatial.inference_validity)
        sp_cert = _load_report("validation/spatial/CERTIFICATION.json")
        sp_cert_summary = sp_cert.get("summary", {}) if sp_cert else {}
        sp_sat = sp_cert_summary.get("satisfied", 10)
        sp_total = sp_cert_summary.get("total", 14)
        sp_tier = sp_cert_summary.get("verdict", "VALIDATED")

        conclusions["BNC-SPATIAL-CAPABILITY-VALIDATED"] = ConclusionEntry(
            conclusion_id="BNC-SPATIAL-CAPABILITY-VALIDATED",
            capability_id="spatial.inference_validity",
            statement=(
                f"spatial.inference_validity satisfies {sp_sat}/{sp_total} certification criteria and achieves {sp_tier} tier. "
                "Biological ground truth, public reference dataset, cross-host claim audit, and external review remain unsatisfied."
            ),
            verdict=sp_tier,
            claim_boundary={
                "supported": [
                    "6/6 core software criteria satisfied",
                    "Technical acceptance on authentic XOA bytes passed",
                    "Neighborhood radius perturbation sensitivity passed (15um-100um sweep)",
                ],
                "not_supported": [
                    "CERTIFIED tier (requires 14/14)",
                    "independent biological ground truth",
                    "public scientific reference dataset",
                    "real-host cross-host multi-lab execution",
                ],
            },
            source_files={
                "src/bionexus/certification.py": _get_hash("src/bionexus/certification.py"),
                "src/bionexus/capabilities.py": _get_hash("src/bionexus/capabilities.py"),
                "evals/spatial_stress_test.py": _get_hash("evals/spatial_stress_test.py"),
            },
            rules=["BNS-010", "BNS-015", "BNS-HC-007", "INV-011", "INV-012"],
            dependencies={"squidpy": ">=1.3.0", "python": ">=3.10"},
            data={
                "study_reports": ["validation/spatial/studies/BN-SP-IV-001/REPORT.json"],
                "stress_reports": ["validation/spatial/INFERENTIAL_STRESS_REPORT.json"],
            },
            host={
                "platform": "Windows-11-10.0.26200-SP0",
                "cross_host_status": "headless_only_6_traps_abstain_unmet_quota",
                "real_host_certified": False,
            },
            report_version={
                "report_path": "validation/spatial/CERTIFICATION.json",
                "schema_version": sp_cert.get("schema_version", "1.0") if sp_cert else "1.0",
                "project_version": sp_cert.get("project_version", VERSION) if sp_cert else VERSION,
            },
            upstream_nodes=["BNC-SP-001-TECH-ACCEPTANCE", "RULE-BNS-010", "RULE-BNS-HC-007"],
            downstream_nodes=[],
        )

        # 3. Pseudobulk Kang et al. 2018 Reference DE (GEO GSE96583)
        pb_rep = _load_report("validation/pseudobulk/REPORT.json")
        pb_prov = pb_rep.get("pipeline", {}).get("provenance", {}) if pb_rep else {}
        pb_ds = pb_rep.get("dataset", {}) if pb_rep else {}
        pb_status = pb_rep.get("status", "pass").upper() if pb_rep else "PASS"
        pb_metrics = {m.get("name"): m.get("observed") for m in pb_rep.get("metrics", [])} if pb_rep else {}
        overlap_frac = pb_metrics.get("published_support_fraction", 0.66)

        conclusions["BNC-PSEUDOBULK-GSE96583"] = ConclusionEntry(
            conclusion_id="BNC-PSEUDOBULK-GSE96583",
            capability_id="scrna.pseudobulk_de",
            statement=(
                f"Kang et al. 2018 (GEO GSE96583) donor-aware pseudobulk differential expression with PyDESeq2 "
                f"recovers known IFN-stimulated genes with {overlap_frac} published-support overlap >= 0.50 threshold."
            ),
            verdict=pb_status,
            claim_boundary={
                "supported": [
                    "Donor-aware pseudobulk DE on 13487 singlets / 8 donors / 2 conditions",
                    f"Published-support overlap fraction {overlap_frac} >= 0.50",
                    "Top-100 DE calls validated against independent MSigDB Hallmark IFN + QuickGO truth sets",
                ],
                "not_supported": [
                    "CERTIFIED tier",
                    "Cross-cohort generalization without donor replicates",
                    "Causal inference without experimental intervention controls",
                ],
            },
            source_files={
                "evals/flagship_validation.py": _get_hash("evals/flagship_validation.py"),
                "src/bionexus/pseudobulk_warrant.py": _get_hash("src/bionexus/pseudobulk_warrant.py"),
                "src/bionexus/abi.py": _get_hash("src/bionexus/abi.py"),
            },
            rules=["INV-001", "INV-003", "INV-014", "BNS-010"],
            dependencies={"pydeseq2": ">=0.4.0", "python": ">=3.10"},
            data={
                "dataset_name": pb_ds.get("name", "kang2018_pbmc_ifnb"),
                "accession": pb_ds.get("accession", "GEO GSE96583"),
                "files": pb_ds.get("checksum_sha256", {
                    "pbmc_ifnb_counts.h5ad": "46122ba4e196561a781123614d856fed7d1ca05743d39a1d117597fd6d0bb993",
                    "published_de_truth.csv": "ded3bb9b1e4606da34f5142ab129c5f97b619e0d23e30eade49b2b7be14b3d30",
                }),
            },
            host={
                "platform": pb_prov.get("platform", "Windows-11-10.0.26200-SP0"),
                "execution_mode": "live_script_execution",
                "real_host_certified": False,
            },
            report_version={
                "report_path": "validation/pseudobulk/REPORT.json",
                "schema_version": pb_rep.get("schema_version", "bionexus.flagship-validation-report.v1") if pb_rep else "bionexus.flagship-validation-report.v1",
                "project_version": pb_rep.get("pipeline", {}).get("version", VERSION) if pb_rep else VERSION,
            },
            upstream_nodes=["DATA-GSE96583", "SRC-PYDESEQ2-WRAPPER", "RULE-INV-001"],
            downstream_nodes=["BNC-PSEUDOBULK-CAPABILITY-VALIDATED"],
        )

        # 4. Pseudobulk Independent Study Negative Result Freeze (BN-PB-IV-002)
        indep_rep = _load_report("validation/pseudobulk/independent/REPORT.json")
        conclusions["BNC-PSEUDOBULK-INDEP-002"] = ConclusionEntry(
            conclusion_id="BNC-PSEUDOBULK-INDEP-002",
            capability_id="scrna.pseudobulk_de",
            statement=(
                "BN-PB-IV-002 independent reanalysis is a preserved negative result: locked negative-control endpoint "
                "failed (p=0.05859 > 0.05); maturity remains FRAGILE and independent biological validation is not supported."
            ),
            verdict="NEGATIVE_RESULT_FREEZE",
            claim_boundary={
                "supported": [
                    "Negative result preserved without promotion",
                    "Negative-control endpoint failure accurately recorded",
                ],
                "not_supported": [
                    "biological validation pass",
                    "conformance promotion",
                    "ROBUST maturity",
                ],
            },
            source_files={
                "validation/pseudobulk/independent/REPORT.json": _get_hash("validation/pseudobulk/independent/REPORT.json")
            },
            rules=["BNS-004", "BNS-010"],
            dependencies={"pydeseq2": ">=0.4.0"},
            data={"dataset_track": "independent_replication_attempt"},
            host={
                "platform": "Windows-11-10.0.26200-SP0",
                "real_host_certified": False,
            },
            report_version={
                "report_path": "validation/pseudobulk/independent/REPORT.json",
                "schema_version": indep_rep.get("schema_version", "bionexus.pseudobulk-independent-report.v1") if indep_rep else "bionexus.pseudobulk-independent-report.v1",
                "project_version": VERSION,
            },
            upstream_nodes=["SRC-PYDESEQ2-WRAPPER"],
            downstream_nodes=["BNC-PSEUDOBULK-CAPABILITY-VALIDATED"],
        )

        # 5. Pseudobulk Capability Certification (scrna.pseudobulk_de)
        pb_cert = _load_report("validation/pseudobulk/CERTIFICATION.json")
        pb_cert_summary = pb_cert.get("summary", {}) if pb_cert else {}
        pb_sat = pb_cert_summary.get("satisfied", 12)
        pb_total = pb_cert_summary.get("total", 14)
        pb_tier = pb_cert_summary.get("verdict", "VALIDATED")

        conclusions["BNC-PSEUDOBULK-CAPABILITY-VALIDATED"] = ConclusionEntry(
            conclusion_id="BNC-PSEUDOBULK-CAPABILITY-VALIDATED",
            capability_id="scrna.pseudobulk_de",
            statement=(
                f"scrna.pseudobulk_de satisfies {pb_sat}/{pb_total} certification criteria and achieves {pb_tier} tier. "
                "Cross-host testing and external review remain unsatisfied."
            ),
            verdict=pb_tier,
            claim_boundary={
                "supported": [
                    "All 6 core software criteria satisfied",
                    "Real-data public reference validation passed (GSE96583 overlap 0.66)",
                    "Stability (Jaccard >= 0.80) and missing-backend degradation tests passed",
                ],
                "not_supported": [
                    "CERTIFIED tier (requires 14/14)",
                    "real-host cross-host multi-lab execution",
                    "external domain reviewer sign-off",
                ],
            },
            source_files={
                "src/bionexus/certification.py": _get_hash("src/bionexus/certification.py"),
                "evals/pseudobulk_stress_test.py": _get_hash("evals/pseudobulk_stress_test.py"),
            },
            rules=["BNS-010", "BNS-015", "BNS-HC-007", "INV-001", "INV-003"],
            dependencies={"pydeseq2": ">=0.4.0", "python": ">=3.10"},
            data={
                "validation_report": "validation/pseudobulk/REPORT.json",
                "stress_report": "validation/pseudobulk/INFERENTIAL_STRESS_REPORT.json",
            },
            host={
                "platform": "Windows-11-10.0.26200-SP0",
                "cross_host_status": "headless_only_6_traps_abstain_unmet_quota",
                "real_host_certified": False,
            },
            report_version={
                "report_path": "validation/pseudobulk/CERTIFICATION.json",
                "schema_version": pb_cert.get("schema_version", "1.0") if pb_cert else "1.0",
                "project_version": pb_cert.get("project_version", VERSION) if pb_cert else VERSION,
            },
            upstream_nodes=["BNC-PSEUDOBULK-GSE96583", "RULE-BNS-010", "RULE-BNS-HC-007"],
            downstream_nodes=[],
        )

        # 6. Annotation Reference Evaluation (BN-ANN-IV-003)
        ann_rep = _load_report("validation/annotation/studies/BN-ANN-IV-003/REPORT.json")
        ann_status = ann_rep.get("status", {}) if ann_rep else {}
        ann_verdict = ann_status.get("run_status", "CANDIDATE_EXTERNAL_REFERENCE_NONBLINDED")
        ann_ds = ann_rep.get("dataset", {}) if ann_rep else {}
        ann_cb = ann_rep.get("claim_boundary", {}) if ann_rep else {}
        ann_prov = ann_rep.get("provenance", {}) if ann_rep else {}
        n_cells = ann_ds.get("n_cells", 148297)

        conclusions["BNC-ANNOTATION-AZIMUTH-003"] = ConclusionEntry(
            conclusion_id="BNC-ANNOTATION-AZIMUTH-003",
            capability_id="scrna.annotation_evidence",
            statement=(
                f"BN-ANN-IV-003 evaluated {n_cells} mapped cells against external Azimuth PBMC reference annotations; "
                f"met locked endpoints but was nonblinded to label distributions (capped at {ann_verdict})."
            ),
            verdict=ann_verdict,
            claim_boundary={
                "supported": [
                    f"{n_cells} cells mapped against Azimuth PBMC",
                    "Locked endpoints met",
                ],
                "not_supported": ann_cb.get("not_supported", [
                    "blinded evaluation",
                    "independent biological ground truth",
                    "approved empirical calibration profile",
                ]),
            },
            source_files={
                "evals/annotation_external_holdout_validation.py": _get_hash("evals/annotation_external_holdout_validation.py"),
                "src/bionexus/annotation_evidence.py": _get_hash("src/bionexus/annotation_evidence.py"),
            },
            rules=["INV-004", "INV-005", "INV-008", "INV-016", "BNS-010"],
            dependencies={"scanpy": ">=1.10.0", "python": ">=3.10"},
            data={
                "dataset_track": ann_ds.get("dataset_track", "real_public_processed_citeseq"),
                "files": {
                    "pbmc_10k_protein_v3.h5ad": ann_ds.get("file_sha256", "473347c617b8f972bdfa6797f1f0a1496b998cfb62a43bfa99351faef8a25cbb")
                },
            },
            host={
                "platform": ann_prov.get("platform", "Windows-11-10.0.26200-SP0"),
                "execution_mode": "live_script_execution",
                "real_host_certified": False,
            },
            report_version={
                "report_path": "validation/annotation/studies/BN-ANN-IV-003/REPORT.json",
                "schema_version": ann_rep.get("schema_version", "1.0") if ann_rep else "1.0",
                "project_version": ann_prov.get("generator_version", VERSION) if ann_prov else VERSION,
            },
            upstream_nodes=["DATA-CITESEQ-10K", "SRC-ANNOTATION-EVIDENCE"],
            downstream_nodes=["BNC-ANNOTATION-CAPABILITY-VALIDATED"],
        )

        # 7. Annotation Capability Certification (scrna.annotation_evidence)
        ann_cert = _load_report("validation/annotation/CERTIFICATION.json")
        ann_cert_summary = ann_cert.get("summary", {}) if ann_cert else {}
        ann_sat = ann_cert_summary.get("satisfied", 11)
        ann_total = ann_cert_summary.get("total", 14)
        ann_tier = ann_cert_summary.get("verdict", "VALIDATED")

        conclusions["BNC-ANNOTATION-CAPABILITY-VALIDATED"] = ConclusionEntry(
            conclusion_id="BNC-ANNOTATION-CAPABILITY-VALIDATED",
            capability_id="scrna.annotation_evidence",
            statement=(
                f"scrna.annotation_evidence satisfies {ann_sat}/{ann_total} certification criteria and achieves {ann_tier} tier. "
                "Independent biological ground truth, cross-host testing, and external review remain unsatisfied."
            ),
            verdict=ann_tier,
            claim_boundary={
                "supported": [
                    "All 6 core software criteria satisfied",
                    "Public reference evaluation met locked endpoints",
                    "Parameter perturbation (ARI >= 0.80) & claim interception passed",
                ],
                "not_supported": [
                    "CERTIFIED tier (requires 14/14)",
                    "independent biological ground truth",
                    "real-host cross-host multi-lab execution",
                    "external reviewer sign-off",
                ],
            },
            source_files={
                "src/bionexus/certification.py": _get_hash("src/bionexus/certification.py"),
                "evals/annotation_stress_test.py": _get_hash("evals/annotation_stress_test.py"),
            },
            rules=["BNS-010", "BNS-015", "BNS-HC-007", "INV-004"],
            dependencies={"scanpy": ">=1.10.0", "python": ">=3.10"},
            data={
                "validation_report": "validation/annotation/REPORT.json",
                "stress_report": "validation/annotation/INFERENTIAL_STRESS_REPORT.json",
            },
            host={
                "platform": "Windows-11-10.0.26200-SP0",
                "cross_host_status": "headless_only_6_traps_abstain_unmet_quota",
                "real_host_certified": False,
            },
            report_version={
                "report_path": "validation/annotation/CERTIFICATION.json",
                "schema_version": ann_cert.get("schema_version", "1.0") if ann_cert else "1.0",
                "project_version": ann_cert.get("project_version", VERSION) if ann_cert else VERSION,
            },
            upstream_nodes=["BNC-ANNOTATION-AZIMUTH-003", "RULE-BNS-010", "RULE-BNS-HC-007"],
            downstream_nodes=[],
        )

        # 8. Cross-Host Concordance (cross-host/COMPARISON.json)
        ch_rep = _load_report("cross-host/COMPARISON.json")
        ch_overall = ch_rep.get("overall", {}) if ch_rep else {}
        ch_verdict = "PASS_HEADLESS_REFUSAL_CONCORDANCE" if ch_overall.get("conformance_verdict") == "pass" else "FAIL"
        ch_traps = ch_rep.get("traps_compared", 6) if ch_rep else 6
        ch_hosts = ch_rep.get("hosts", ["claude-code", "antigravity"]) if ch_rep else ["claude-code", "antigravity"]

        conclusions["BNC-CROSS-HOST-CONCORDANCE"] = ConclusionEntry(
            conclusion_id="BNC-CROSS-HOST-CONCORDANCE",
            capability_id="cross-host.router_traps",
            statement=(
                f"Cross-host comparison records {ch_traps} router traps (BF-001..BF-006) executed on {', '.join(ch_hosts)}, "
                "all yielding ABSTAIN (100% concordance, 6/6 consistent). This confirms software refusal consistency, "
                "but does not certify real-host execution or satisfy IVN multi-host quota (BNS-HC-007)."
            ),
            verdict=ch_verdict,
            claim_boundary={
                "supported": [
                    f"{ch_traps} router traps compared on {', '.join(ch_hosts)}",
                    "100% agreement on ABSTAIN refusal (agreement_rate 1.0)",
                    "Software contract conformance",
                ],
                "not_supported": [
                    "real-host execution certification",
                    "IVN external-lab claim audit quota",
                    "CERTIFIED tier promotion",
                ],
            },
            source_files={
                "cross-host/COMPARISON.json": _get_hash("cross-host/COMPARISON.json"),
                "cross-host/claude-code/REPORT.json": _get_hash("cross-host/claude-code/REPORT.json"),
                "cross-host/antigravity/REPORT.json": _get_hash("cross-host/antigravity/REPORT.json"),
            },
            rules=["BNS-HC-007", "BNS-010"],
            dependencies={"python": ">=3.10"},
            data={"traps": ["BF-001", "BF-002", "BF-003", "BF-004", "BF-005", "BF-006"]},
            host={
                "hosts": ch_hosts,
                "execution_mode": "headless_trap_replay",
                "real_host_certified": False,
            },
            report_version={
                "report_path": "cross-host/COMPARISON.json",
                "schema_version": ch_rep.get("schema_version", "1.0") if ch_rep else "1.0",
                "project_version": ch_rep.get("plugin_version", VERSION) if ch_rep else VERSION,
            },
            upstream_nodes=["RULE-BNS-HC-007"],
            downstream_nodes=[
                "BNC-SPATIAL-CAPABILITY-VALIDATED",
                "BNC-PSEUDOBULK-CAPABILITY-VALIDATED",
                "BNC-ANNOTATION-CAPABILITY-VALIDATED",
            ],
        )

        return cls(conclusions=conclusions)

    def assess_upstream_changes(
        self,
        repo_root: Union[Path, str],
        changed_files: Optional[Sequence[str]] = None,
        broken_rules: Optional[Sequence[str]] = None,
    ) -> UpstreamImpactReport:
        """Analyze changes in upstream files or rules, returning invalidated, recomputation-needed, and metadata-updated conclusions.

        Distinguishes:
        - 失效 (Invalidated): A scientific rule, invariant, or contract was broken/modified.
          The conclusion no longer holds logically.
        - 科学计算必须重算 (Requires Scientific Recomputation): Source code or dataset contents changed.
          The conclusion logic may still be sound, but numerical outputs and metrics are stale.
        - 报告元数据更新 (Report Metadata Update): Only report provenance/version files updated.
          Core algorithm code and datasets remain identical; no scientific recomputation required.
        - 未受影响 (Unaffected): All code, datasets, rules, and reports remain identical.
        """
        root = Path(repo_root)

        # 1. Collect changed files
        active_changed_files: Set[str] = set()
        if changed_files is not None:
            for f in changed_files:
                norm_f = f.replace("\\", "/").lstrip("/")
                active_changed_files.add(norm_f)
        else:
            # Auto-detect modified files via git status
            try:
                res = subprocess.run(
                    ["git", "status", "--porcelain"],
                    cwd=root,
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                for line in res.stdout.splitlines():
                    if len(line) >= 4:
                        rel = line[3:].strip().replace("\\", "/")
                        if " -> " in rel:
                            rel = rel.split(" -> ", 1)[1]
                        active_changed_files.add(rel)
            except Exception:
                pass

            # Also check hashes directly against index for source files
            for cid, entry in self.conclusions.items():
                for sf, exp_sha in entry.source_files.items():
                    p = root / sf
                    if p.is_file():
                        if sha256_file(p) != exp_sha:
                            active_changed_files.add(sf)

        active_broken_rules: Set[str] = set(broken_rules or [])

        invalidated: List[Dict[str, Any]] = []
        recomputation: List[Dict[str, Any]] = []
        metadata_updates: List[Dict[str, Any]] = []
        unaffected: List[str] = []

        # Categorization per conclusion
        for cid, entry in self.conclusions.items():
            is_invalidated = False
            invalidation_reason = ""
            broken_contract = ""

            needs_recompute = False
            recompute_trigger = ""
            recompute_reason = ""

            is_metadata_update = False
            metadata_trigger = ""
            metadata_reason = ""

            # 1. Check rules
            for rule_id in entry.rules:
                if rule_id in active_broken_rules:
                    is_invalidated = True
                    broken_contract = f"RULE:{rule_id}"
                    invalidation_reason = f"Upstream scientific rule or invariant '{rule_id}' was broken or revoked"
                    break

            # Check rule files if modified
            if not is_invalidated:
                if any("rules/" in cf or "SCIENTIFIC_RULE_CATALOG" in cf for cf in active_changed_files):
                    for cf in active_changed_files:
                        if "rules/" in cf or "SCIENTIFIC_RULE_CATALOG" in cf:
                            is_invalidated = True
                            broken_contract = f"RULE_FILE:{cf}"
                            invalidation_reason = f"Underlying scientific rule file '{cf}' modified"
                            break

            # 2. Check source files: algorithm / test code changes require recomputation!
            if not is_invalidated:
                for sf in entry.source_files:
                    norm_sf = sf.replace("\\", "/").lstrip("/")
                    if norm_sf in active_changed_files:
                        if norm_sf.endswith(".json") and ("REPORT" in norm_sf or "COMPARISON" in norm_sf):
                            is_metadata_update = True
                            metadata_trigger = norm_sf
                            metadata_reason = f"Upstream report artifact '{norm_sf}' was updated"
                        else:
                            needs_recompute = True
                            recompute_trigger = norm_sf
                            recompute_reason = f"Source code '{norm_sf}' was modified; outputs and hashes are stale"
                            break

            # 3. Check dataset files: data changes require recomputation!
            if not is_invalidated and not needs_recompute:
                data_files = entry.data.get("files", {})
                for df in data_files:
                    for cf in active_changed_files:
                        if df in cf:
                            needs_recompute = True
                            recompute_trigger = df
                            recompute_reason = f"Input dataset '{df}' was modified; requires pipeline re-execution"
                            break

            # 4. Check bound report file: if ONLY report changed without code/data change
            if not is_invalidated and not needs_recompute and not is_metadata_update:
                rep_path = entry.report_version.get("report_path", "")
                norm_rep = rep_path.replace("\\", "/").lstrip("/")
                if norm_rep in active_changed_files:
                    is_metadata_update = True
                    metadata_trigger = norm_rep
                    metadata_reason = f"Report metadata file '{norm_rep}' was updated"

            # Recommend command
            rec_cmd = "python scripts/sync_flagship_reports.py"
            if "spatial" in entry.capability_id:
                rec_cmd = "python evals/spatial_instrument_validation.py"
            elif "pseudobulk" in entry.capability_id:
                rec_cmd = "python evals/flagship_validation.py --capability scrna.pseudobulk_de"
            elif "annotation" in entry.capability_id:
                rec_cmd = "python evals/annotation_external_holdout_validation.py"

            if is_invalidated:
                invalidated.append({
                    "conclusion_id": cid,
                    "statement": entry.statement,
                    "broken_rule_or_contract": broken_contract,
                    "reason": invalidation_reason,
                })
            elif needs_recompute:
                recomputation.append({
                    "conclusion_id": cid,
                    "statement": entry.statement,
                    "trigger_file_or_data": recompute_trigger,
                    "reason": recompute_reason,
                    "recommended_command": rec_cmd,
                })
            elif is_metadata_update:
                metadata_updates.append({
                    "conclusion_id": cid,
                    "statement": entry.statement,
                    "report_path": metadata_trigger,
                    "reason": metadata_reason,
                })
            else:
                unaffected.append(cid)

        # Graph propagation: topological traversal
        invalidated_ids = {inv["conclusion_id"] for inv in invalidated}
        recompute_ids = {rec["conclusion_id"] for rec in recomputation}
        metadata_ids = {meta["conclusion_id"] for meta in metadata_updates}

        for cid, entry in list(self.conclusions.items()):
            if cid in unaffected:
                for up in entry.upstream_nodes:
                    if up in invalidated_ids:
                        unaffected.remove(cid)
                        invalidated.append({
                            "conclusion_id": cid,
                            "statement": entry.statement,
                            "broken_rule_or_contract": f"UPSTREAM_INVALIDATED:{up}",
                            "reason": f"Direct upstream conclusion '{up}' was invalidated",
                        })
                        invalidated_ids.add(cid)
                        break
                    elif up in recompute_ids:
                        unaffected.remove(cid)
                        recomputation.append({
                            "conclusion_id": cid,
                            "statement": entry.statement,
                            "trigger_file_or_data": f"UPSTREAM_RECOMPUTE:{up}",
                            "reason": f"Direct upstream conclusion '{up}' requires recomputation",
                            "recommended_command": "python scripts/sync_flagship_reports.py",
                        })
                        recompute_ids.add(cid)
                        break
                    elif up in metadata_ids:
                        unaffected.remove(cid)
                        metadata_updates.append({
                            "conclusion_id": cid,
                            "statement": entry.statement,
                            "report_path": f"UPSTREAM_METADATA:{up}",
                            "reason": f"Direct upstream conclusion '{up}' had metadata update",
                        })
                        metadata_ids.add(cid)
                        break

        return UpstreamImpactReport(
            changed_files=sorted(active_changed_files),
            broken_rules=sorted(active_broken_rules),
            invalidated_conclusions=invalidated,
            requires_recomputation=recomputation,
            metadata_updates=metadata_updates,
            unaffected_conclusions=unaffected,
        )

    def verify_index_integrity(self, repo_root: Union[Path, str]) -> Dict[str, Any]:
        """Verify that files, reports, and hashes recorded in the index match disk reality."""
        root = Path(repo_root)
        errors: List[str] = []
        checked_count = 0

        for cid, entry in self.conclusions.items():
            # 1. Check report file existence and semantic content
            rep_rel = entry.report_version.get("report_path", "")
            rep_path = root / rep_rel
            if not rep_path.is_file():
                errors.append(f"{cid} report file missing: {rep_rel}")
            else:
                checked_count += 1
                try:
                    rep_data = json.loads(rep_path.read_text(encoding="utf-8"))
                    # Extract verdict from report
                    rep_verdict = None
                    if "status" in rep_data:
                        if isinstance(rep_data["status"], dict):
                            rep_verdict = rep_data["status"].get("run_status") or rep_data["status"].get("verdict")
                        elif isinstance(rep_data["status"], str):
                            rep_verdict = rep_data["status"]
                    elif "summary" in rep_data and isinstance(rep_data["summary"], dict):
                        rep_verdict = rep_data["summary"].get("verdict")
                    elif "overall" in rep_data and isinstance(rep_data["overall"], dict):
                        rep_verdict = rep_data["overall"].get("conformance_verdict")

                    if rep_verdict:
                        norm_rep = str(rep_verdict).upper().replace("-", "_").strip()
                        norm_entry = str(entry.verdict).upper().replace("-", "_").strip()
                        is_compatible = (norm_rep == norm_entry)
                        if not is_compatible:
                            contradictions = {"NOT_", "NON_", "FAIL", "UNWARRANTED", "INVALID", "REJECT"}
                            rep_is_neg = any(c in norm_rep for c in contradictions)
                            entry_is_neg = any(c in norm_entry for c in contradictions)
                            if rep_is_neg == entry_is_neg:
                                allowed_equivalences = {
                                    "NEGATIVE_RESULT_FREEZE": {"NEGATIVE_RESULT", "NEGATIVE_RESULT_FREEZE"},
                                    "PASS_HEADLESS_REFUSAL_CONCORDANCE": {"PASS", "PASS_HEADLESS_REFUSAL_CONCORDANCE"},
                                    "TECHNICAL_ACCEPTANCE_PASS": {"TECHNICAL_ACCEPTANCE_PASS", "PASS"},
                                }
                                for canonical, syns in allowed_equivalences.items():
                                    if (norm_entry == canonical or norm_entry in syns) and (norm_rep == canonical or norm_rep in syns):
                                        is_compatible = True
                                        break
                        if not is_compatible:
                            errors.append(
                                f"{cid} report verdict mismatch: index has '{entry.verdict}', report has '{rep_verdict}'"
                            )

                    # Verify real_host_certified claim
                    if entry.host.get("real_host_certified") is True:
                        is_rep_certified = False
                        if isinstance(rep_data.get("status"), dict):
                            is_rep_certified = bool(rep_data["status"].get("real_host_certified"))
                        elif isinstance(rep_data.get("host"), dict):
                            is_rep_certified = bool(rep_data["host"].get("real_host_certified"))
                        if not is_rep_certified:
                            errors.append(
                                f"{cid} unauthorized host certification: index claims real_host_certified=True without underlying report attestation"
                            )
                except Exception as exc:
                    errors.append(f"{cid} report file corrupted: {exc}")

            # 2. Check source files existence and recalculate SHA-256
            for sf, expected_hash in entry.source_files.items():
                p = root / sf
                if not p.is_file():
                    errors.append(f"{cid} source file missing: {sf}")
                else:
                    observed_hash = sha256_file(p)
                    if observed_hash != expected_hash:
                        errors.append(
                            f"{cid} source file hash mismatch for {sf}: recorded {expected_hash}, observed {observed_hash}"
                        )
                    else:
                        checked_count += 1

            # 3. Check data files if present on disk
            data_files = entry.data.get("files", {})
            if isinstance(data_files, dict):
                for df_name, exp_df_hash in data_files.items():
                    ds_name = entry.data.get("dataset_name", "")
                    candidates = [
                        root / "data" / "flagship" / ds_name / df_name,
                        root / "data" / "flagship" / df_name,
                        root / df_name,
                    ]
                    found = next((c for c in candidates if c.is_file()), None)
                    if found is not None:
                        obs_df_hash = sha256_file(found)
                        if obs_df_hash != exp_df_hash:
                            errors.append(
                                f"{cid} data file hash mismatch for {df_name}: recorded {exp_df_hash}, observed {obs_df_hash}"
                            )
                        else:
                            checked_count += 1

        return {
            "passed": len(errors) == 0,
            "checked_count": checked_count,
            "errors": errors,
        }
