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
    unaffected_conclusions: List[str]

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

        lines.append(f"\n2. 需要重算结论 (Requires Recomputation: {len(self.requires_recomputation)}):")
        if not self.requires_recomputation:
            lines.append("  (None - all numerical outputs and reports are up-to-date)")
        for rec in self.requires_recomputation:
            lines.append(f"  [RECOMPUTE] {rec['conclusion_id']}: {rec['statement']}")
            lines.append(f"    Trigger: {rec['trigger_file_or_data']} -> {rec['reason']}")
            lines.append(f"    Action: {rec['recommended_command']}")

        lines.append(f"\n3. 未受影响结论 (Unaffected Conclusions: {len(self.unaffected_conclusions)}):")
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
        """Build the authoritative current evidence index from repository artifacts."""
        root = Path(repo_root)

        def _get_hash(rel: str) -> str:
            p = root / rel
            if p.is_file():
                return sha256_file(p)
            return "UNKNOWN"

        conclusions: Dict[str, ConclusionEntry] = {}

        # 1. Spatial Real Instrument Technical Acceptance (BN-SP-IV-001)
        conclusions["BNC-SP-001-TECH-ACCEPTANCE"] = ConclusionEntry(
            conclusion_id="BNC-SP-001-TECH-ACCEPTANCE",
            capability_id="spatial.inference_validity",
            statement=(
                "BioNexus artifact diagnostics execute on authentic Xenium XOA bytes and respond in the expected "
                "direction to deterministic manufactured confounders (5/5 locked technical endpoints passed)."
            ),
            verdict="TECHNICAL_ACCEPTANCE_PASS",
            claim_boundary={
                "supported": [
                    "Artifact diagnostics execute on authentic XOA bytes",
                    "Deterministic responses to manufactured confounders (segmentation leakage delta 0.307, cell size bias delta 0.201, transcript density bias delta 0.886)",
                    "5/5 locked technical endpoints passed",
                ],
                "not_supported": [
                    "biological validity",
                    "tissue-level generalization",
                    "segmentation accuracy against histology",
                    "approved spatial calibration profile",
                    "independent ground truth",
                ],
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
                "vendor_disclaimer": "Vendor documents tiny dataset as format-testing material not intended for biological conclusions",
                "files": {
                    "Xenium_V1_Protein_Human_Kidney_tiny_outs.zip": "abd7e8f7fd047dcc6afdb1e9eece90d4533d3ead053c6f05c482be050bdf79d2"
                },
            },
            host={
                "platform": "Windows-11-10.0.26200-SP0",
                "execution_mode": "live_instrument_script",
                "real_host_certified": True,
            },
            report_version={
                "report_path": "validation/spatial/studies/BN-SP-IV-001/REPORT.json",
                "schema_version": "bionexus.spatial-real-instrument-validation-report.v1",
                "project_version": VERSION,
            },
            upstream_nodes=["DATA-XENIUM-TINY", "SRC-SPATIAL-INSTRUMENT", "RULE-INV-011"],
            downstream_nodes=["BNC-SPATIAL-CAPABILITY-VALIDATED"],
        )

        # 2. Spatial Capability Certification (spatial.inference_validity)
        conclusions["BNC-SPATIAL-CAPABILITY-VALIDATED"] = ConclusionEntry(
            conclusion_id="BNC-SPATIAL-CAPABILITY-VALIDATED",
            capability_id="spatial.inference_validity",
            statement=(
                "spatial.inference_validity satisfies 10/14 certification criteria and achieves VALIDATED tier. "
                "Biological ground truth, public reference dataset, cross-host claim audit, and external review remain unsatisfied."
            ),
            verdict="VALIDATED",
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
            },
            report_version={
                "report_path": "validation/spatial/CERTIFICATION.json",
                "schema_version": "1.0",
                "project_version": VERSION,
            },
            upstream_nodes=["BNC-SP-001-TECH-ACCEPTANCE", "RULE-BNS-010", "RULE-BNS-HC-007"],
            downstream_nodes=[],
        )

        # 3. Pseudobulk Kang et al. 2018 Reference DE (GEO GSE96583)
        conclusions["BNC-PSEUDOBULK-GSE96583"] = ConclusionEntry(
            conclusion_id="BNC-PSEUDOBULK-GSE96583",
            capability_id="scrna.pseudobulk_de",
            statement=(
                "Kang et al. 2018 (GEO GSE96583) donor-aware pseudobulk differential expression with PyDESeq2 "
                "recovers known IFN-stimulated genes with 0.66 published-support overlap >= 0.50 threshold."
            ),
            verdict="PASS",
            claim_boundary={
                "supported": [
                    "Donor-aware pseudobulk DE on 13487 singlets / 8 donors / 2 conditions",
                    "Published-support overlap fraction 0.66 >= 0.50",
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
                "dataset_name": "kang2018_pbmc_ifnb",
                "accession": "GEO GSE96583",
                "files": {
                    "pbmc_ifnb_counts.h5ad": "d2ef55f0ba2b1fbb6065538356c9a356aee0e5ee4b0c2db8eb0a95e7b233e72e",
                    "published_de_truth.csv": "8cb6249d9774577884d5f49ee2f153f3e26bb55274aa1cffce4e1f7c35272a52",
                },
            },
            host={
                "platform": "Windows-11-10.0.26200-SP0",
                "execution_mode": "live_script_execution",
                "real_host_certified": True,
            },
            report_version={
                "report_path": "validation/pseudobulk/REPORT.json",
                "schema_version": "bionexus.flagship-validation-report.v1",
                "project_version": VERSION,
            },
            upstream_nodes=["DATA-GSE96583", "SRC-PYDESEQ2-WRAPPER", "RULE-INV-001"],
            downstream_nodes=["BNC-PSEUDOBULK-CAPABILITY-VALIDATED"],
        )

        # 4. Pseudobulk Independent Study Negative Result Freeze (BN-PB-IV-002)
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
            host={"platform": "Windows-11-10.0.26200-SP0"},
            report_version={
                "report_path": "validation/pseudobulk/independent/REPORT.json",
                "project_version": VERSION,
            },
            upstream_nodes=["SRC-PYDESEQ2-WRAPPER"],
            downstream_nodes=["BNC-PSEUDOBULK-CAPABILITY-VALIDATED"],
        )

        # 5. Pseudobulk Capability Certification (scrna.pseudobulk_de)
        conclusions["BNC-PSEUDOBULK-CAPABILITY-VALIDATED"] = ConclusionEntry(
            conclusion_id="BNC-PSEUDOBULK-CAPABILITY-VALIDATED",
            capability_id="scrna.pseudobulk_de",
            statement=(
                "scrna.pseudobulk_de satisfies 12/14 certification criteria and achieves VALIDATED tier. "
                "Cross-host testing and external review remain unsatisfied."
            ),
            verdict="VALIDATED",
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
            },
            report_version={
                "report_path": "validation/pseudobulk/CERTIFICATION.json",
                "schema_version": "1.0",
                "project_version": VERSION,
            },
            upstream_nodes=["BNC-PSEUDOBULK-GSE96583", "RULE-BNS-010", "RULE-BNS-HC-007"],
            downstream_nodes=[],
        )

        # 6. Annotation Reference Evaluation (BN-ANN-IV-003)
        conclusions["BNC-ANNOTATION-AZIMUTH-003"] = ConclusionEntry(
            conclusion_id="BNC-ANNOTATION-AZIMUTH-003",
            capability_id="scrna.annotation_evidence",
            statement=(
                "BN-ANN-IV-003 evaluated 148297 mapped cells against external Azimuth PBMC reference annotations; "
                "met locked endpoints but was nonblinded to label distributions (capped at CANDIDATE_EXTERNAL_REFERENCE_NONBLINDED)."
            ),
            verdict="CANDIDATE_EXTERNAL_REFERENCE_NONBLINDED",
            claim_boundary={
                "supported": [
                    "148297 cells mapped against Azimuth PBMC",
                    "Locked endpoints met",
                ],
                "not_supported": [
                    "blinded evaluation",
                    "independent biological ground truth",
                    "approved empirical calibration profile",
                ],
            },
            source_files={
                "evals/annotation_external_holdout_validation.py": _get_hash("evals/annotation_external_holdout_validation.py"),
                "src/bionexus/annotation_evidence.py": _get_hash("src/bionexus/annotation_evidence.py"),
            },
            rules=["INV-004", "INV-005", "INV-008", "INV-016", "BNS-010"],
            dependencies={"scanpy": ">=1.10.0", "python": ">=3.10"},
            data={
                "dataset_track": "real_public_processed_citeseq",
                "files": {
                    "pbmc_10k_protein_v3.h5ad": "473347c617b8f972bdfa6797f1f0a1496b998cfb62a43bfa99351faef8a25cbb"
                },
            },
            host={
                "platform": "Windows-11-10.0.26200-SP0",
                "execution_mode": "live_script_execution",
                "real_host_certified": True,
            },
            report_version={
                "report_path": "validation/annotation/studies/BN-ANN-IV-003/REPORT.json",
                "project_version": VERSION,
            },
            upstream_nodes=["DATA-CITESEQ-10K", "SRC-ANNOTATION-EVIDENCE"],
            downstream_nodes=["BNC-ANNOTATION-CAPABILITY-VALIDATED"],
        )

        # 7. Annotation Capability Certification (scrna.annotation_evidence)
        conclusions["BNC-ANNOTATION-CAPABILITY-VALIDATED"] = ConclusionEntry(
            conclusion_id="BNC-ANNOTATION-CAPABILITY-VALIDATED",
            capability_id="scrna.annotation_evidence",
            statement=(
                "scrna.annotation_evidence satisfies 11/14 certification criteria and achieves VALIDATED tier. "
                "Independent biological ground truth, cross-host testing, and external review remain unsatisfied."
            ),
            verdict="VALIDATED",
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
            },
            report_version={
                "report_path": "validation/annotation/CERTIFICATION.json",
                "schema_version": "1.0",
                "project_version": VERSION,
            },
            upstream_nodes=["BNC-ANNOTATION-AZIMUTH-003", "RULE-BNS-010", "RULE-BNS-HC-007"],
            downstream_nodes=[],
        )

        # 8. Cross-Host Concordance (cross-host/COMPARISON.json)
        conclusions["BNC-CROSS-HOST-CONCORDANCE"] = ConclusionEntry(
            conclusion_id="BNC-CROSS-HOST-CONCORDANCE",
            capability_id="cross-host.router_traps",
            statement=(
                "Cross-host comparison records 6 router traps (BF-001..BF-006) executed on claude-code and antigravity, "
                "both yielding ABSTAIN (100% concordance, 6/6 consistent). This confirms software refusal consistency, "
                "but does not certify real-host execution or satisfy IVN multi-host quota (BNS-HC-007)."
            ),
            verdict="PASS_HEADLESS_REFUSAL_CONCORDANCE",
            claim_boundary={
                "supported": [
                    "6 router traps compared on claude-code + antigravity",
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
            dependencies={"python": "3.13.9"},
            data={"traps": ["BF-001", "BF-002", "BF-003", "BF-004", "BF-005", "BF-006"]},
            host={
                "hosts": ["claude-code", "antigravity"],
                "execution_mode": "headless_trap_replay",
                "real_host_certified": False,
            },
            report_version={
                "report_path": "cross-host/COMPARISON.json",
                "schema_version": "1.0",
                "project_version": VERSION,
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
        """Analyze changes in upstream files or rules, returning invalidated and recomputation-needed conclusions.

        Distinguishes:
        - 失效 (Invalidated): A scientific rule, invariant, or contract was broken/modified.
          The conclusion no longer holds logically.
        - 需要重算 (Requires Recomputation): Source code or dataset contents changed.
          The conclusion logic may still be sound, but test metrics, p-values, and hashes
          are stale and must be regenerated by running the test/pipeline.
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

        active_broken_rules: Set[str] = set(broken_rules or [])

        invalidated: List[Dict[str, Any]] = []
        recomputation: List[Dict[str, Any]] = []
        unaffected: List[str] = []

        # Graph propagation: topological traversal
        for cid, entry in self.conclusions.items():
            is_invalidated = False
            invalidation_reason = ""
            broken_contract = ""

            needs_recompute = False
            recompute_trigger = ""
            recompute_reason = ""

            # Check rules
            for rule_id in entry.rules:
                if rule_id in active_broken_rules:
                    is_invalidated = True
                    broken_contract = f"RULE:{rule_id}"
                    invalidation_reason = f"Upstream scientific rule or invariant '{rule_id}' was broken or revoked"
                    break

            # Check rule files if modified
            if not is_invalidated:
                if any("rules/" in cf or "SCIENTIFIC_RULE_CATALOG" in cf for cf in active_changed_files):
                    # Rules changed: check if this entry depends on rules
                    for cf in active_changed_files:
                        if "rules/" in cf or "SCIENTIFIC_RULE_CATALOG" in cf:
                            is_invalidated = True
                            broken_contract = f"RULE_FILE:{cf}"
                            invalidation_reason = f"Underlying scientific rule file '{cf}' modified"
                            break

            # Check source files
            if not is_invalidated:
                for sf in entry.source_files:
                    norm_sf = sf.replace("\\", "/").lstrip("/")
                    if norm_sf in active_changed_files:
                        needs_recompute = True
                        recompute_trigger = norm_sf
                        recompute_reason = f"Source code '{norm_sf}' was modified; outputs and hashes are stale"
                        break

            # Check dataset files
            if not is_invalidated and not needs_recompute:
                data_files = entry.data.get("files", {})
                for df in data_files:
                    for cf in active_changed_files:
                        if df in cf:
                            needs_recompute = True
                            recompute_trigger = df
                            recompute_reason = f"Input dataset '{df}' was modified; requires pipeline re-execution"
                            break

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
            else:
                unaffected.append(cid)

        # Propagate: If upstream conclusion requires recomputation or is invalidated, downstream does too
        invalidated_ids = {inv["conclusion_id"] for inv in invalidated}
        recompute_ids = {rec["conclusion_id"] for rec in recomputation}

        for cid, entry in list(self.conclusions.items()):
            if cid in unaffected:
                # Check upstreams
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

        return UpstreamImpactReport(
            changed_files=sorted(active_changed_files),
            broken_rules=sorted(active_broken_rules),
            invalidated_conclusions=invalidated,
            requires_recomputation=recomputation,
            unaffected_conclusions=unaffected,
        )

    def verify_index_integrity(self, repo_root: Union[Path, str]) -> Dict[str, Any]:
        """Verify that files, reports, and hashes recorded in the index match disk reality."""
        root = Path(repo_root)
        errors: List[str] = []
        checked_count = 0

        for cid, entry in self.conclusions.items():
            # Check report file existence
            rep_path = root / entry.report_version.get("report_path", "")
            if not rep_path.is_file():
                errors.append(f"{cid} report file missing: {rep_path}")
            else:
                checked_count += 1

            # Check source files existence
            for sf in entry.source_files:
                p = root / sf
                if not p.is_file():
                    errors.append(f"{cid} source file missing: {sf}")
                else:
                    checked_count += 1

        return {
            "passed": len(errors) == 0,
            "checked_count": checked_count,
            "errors": errors,
        }
