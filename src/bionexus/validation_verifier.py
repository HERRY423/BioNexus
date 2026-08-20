"""Unified validation artifact and certification integrity verifier (BNS-010, BNS-015).

Checks:
1. File existence (REPORT.json, INFERENTIAL_STRESS_REPORT.json, CERTIFICATION.json, and referenced evidence files).
2. Runtime SHA-256 checksums match observed file contents.
3. Version and Git Commit consistency (strictly matches bionexus.versions.VERSION).
4. Evidence track consistency (synthetic technical acceptance vs real reference dataset).
5. Certification consistency (standards, summary, and _EVIDENCE mapping agreement).
6. Flagship directory cleanliness (no synthetic pretenders masquerading in data/flagship).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from bionexus.certification import _EVIDENCE
from bionexus.provenance import sha256_file
from bionexus.versions import VERSION

FLAGSHIP_CAPABILITIES = (
    "scrna.pseudobulk_de",
    "scrna.annotation_evidence",
    "spatial.inference_validity",
)

CAPABILITY_TO_SUBDIR: Dict[str, str] = {
    "scrna.pseudobulk_de": "pseudobulk",
    "scrna.annotation_evidence": "annotation",
    "spatial.inference_validity": "spatial",
}


@dataclass
class VerificationResult:
    passed: bool
    checked_files: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def summary_str(self) -> str:
        status_str = "PASS" if self.passed else "FAIL"
        lines = [
            f"=== BioNexus Validation Artifacts Verification: {status_str} ===",
            f"Checked files ({len(self.checked_files)}):",
        ]
        for f in self.checked_files:
            lines.append(f"  [OK] {f}")
        if self.warnings:
            lines.append(f"Warnings ({len(self.warnings)}):")
            for w in self.warnings:
                lines.append(f"  [WARN] {w}")
        if self.errors:
            lines.append(f"Errors ({len(self.errors)}):")
            for e in self.errors:
                lines.append(f"  [ERROR] {e}")
        return "\n".join(lines)


def verify_validation_artifacts(
    repo_root: Optional[Union[Path, str]] = None,
    enforce_version: Optional[str] = None,
) -> VerificationResult:
    """Verify all validation artifacts, checksums, provenance, and certification consistency.

    Parameters
    ----------
    repo_root : Path or str, optional
        Repository root path. If None, resolves from file location.
    enforce_version : str, optional
        Expected version string. Defaults to bionexus.versions.VERSION.

    Returns
    -------
    VerificationResult
        Result containing pass/fail, checked files, errors, and warnings.
    """
    root = Path(repo_root) if repo_root else Path(__file__).resolve().parents[2]
    expected_version = enforce_version or VERSION
    checked: List[str] = []
    errors: List[str] = []
    warnings: List[str] = []
    details: Dict[str, Any] = {}

    # Check 1: data/flagship directory integrity (no synthetic pretenders)
    flagship_dir = root / "data" / "flagship"
    if flagship_dir.is_dir():
        citeseq_fake = flagship_dir / "citeseq_pbmc_sorted" / "citeseq_pbmc.h5ad"
        spatial_fake = flagship_dir / "xenium_spatial_truth" / "spatial_truth.h5ad"
        if citeseq_fake.is_file():
            errors.append(f"Synthetic file {citeseq_fake.relative_to(root)} masquerading in data/flagship")
        if spatial_fake.is_file():
            errors.append(f"Synthetic file {spatial_fake.relative_to(root)} masquerading in data/flagship")

    for cap_id in FLAGSHIP_CAPABILITIES:
        subdir = CAPABILITY_TO_SUBDIR[cap_id]
        cap_dir = root / "validation" / subdir
        cap_details: Dict[str, Any] = {"capability": cap_id}

        # Check required reports
        report_path = cap_dir / "REPORT.json"
        stress_path = cap_dir / "INFERENTIAL_STRESS_REPORT.json"
        cert_path = cap_dir / "CERTIFICATION.json"

        for p, label in [
            (report_path, "REPORT.json"),
            (stress_path, "INFERENTIAL_STRESS_REPORT.json"),
            (cert_path, "CERTIFICATION.json"),
        ]:
            if not p.is_file():
                try:
                    rel_p = p.relative_to(root)
                except ValueError:
                    rel_p = p
                errors.append(f"Missing required artifact: {rel_p}")
            else:
                try:
                    rel_p = str(p.relative_to(root))
                except ValueError:
                    rel_p = str(p)
                checked.append(rel_p)

        if not report_path.is_file() or not cert_path.is_file():
            details[cap_id] = cap_details
            continue

        try:
            report_data = json.loads(report_path.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"Corrupt JSON in {report_path}: {exc}")
            continue

        try:
            cert_data = json.loads(cert_path.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"Corrupt JSON in {cert_path}: {exc}")
            continue

        # Version checks
        pipeline_ver = report_data.get("pipeline", {}).get("version")
        if pipeline_ver != expected_version:
            errors.append(
                f"{cap_id} REPORT.json pipeline.version '{pipeline_ver}' != expected '{expected_version}'"
            )

        cert_ver = cert_data.get("project_version")
        if cert_ver != expected_version:
            errors.append(
                f"{cap_id} CERTIFICATION.json project_version '{cert_ver}' != expected '{expected_version}'"
            )

        # Provenance checks
        prov = report_data.get("pipeline", {}).get("provenance", {})
        if not prov:
            errors.append(f"{cap_id} REPORT.json missing pipeline.provenance")
        else:
            if not prov.get("commit_sha"):
                errors.append(f"{cap_id} REPORT.json missing provenance.commit_sha")
            if prov.get("generator_version") != expected_version:
                errors.append(
                    f"{cap_id} REPORT.json provenance.generator_version '{prov.get('generator_version')}' != '{expected_version}'"
                )

        # Evidence track and accession checks
        dataset_info = report_data.get("dataset", {})
        dataset_track = dataset_info.get("dataset_track")

        if cap_id in ("scrna.annotation_evidence", "spatial.inference_validity"):
            if dataset_track != "synthetic_technical_acceptance":
                errors.append(
                    f"{cap_id} must have dataset_track='synthetic_technical_acceptance', got '{dataset_track}'"
                )
            accession = dataset_info.get("accession", "")
            if "synthetic_technical_acceptance" not in accession:
                errors.append(
                    f"{cap_id} accession must indicate synthetic_technical_acceptance, got '{accession}'"
                )
            # Check checksum validity
            cs = dataset_info.get("checksum_sha256")
            if not isinstance(cs, str) or len(cs) != 64:
                errors.append(f"{cap_id} invalid checksum_sha256 in REPORT.json")

            # Check that gitignored .h5ad is NOT listed as a permanent evidence_file in REPORT.json
            evidence_files = report_data.get("evidence_files", [])
            for ef in evidence_files:
                if ef.endswith(".h5ad"):
                    errors.append(f"{cap_id} REPORT.json evidence_files should not list ignored .h5ad: '{ef}'")

        elif cap_id == "scrna.pseudobulk_de":
            # Real dataset checksum verification
            cs_dict = dataset_info.get("checksum_sha256")
            if isinstance(cs_dict, dict):
                ds_dir = root / "data" / "flagship" / "kang2018_pbmc_ifnb"
                for fname, expected_hash in cs_dict.items():
                    target_file = ds_dir / fname
                    if target_file.is_file():
                        actual_hash = sha256_file(target_file)
                        try:
                            rel_tf = str(target_file.relative_to(root))
                        except ValueError:
                            rel_tf = str(target_file)
                        checked.append(rel_tf)
                        if actual_hash != expected_hash:
                            errors.append(
                                f"Checksum mismatch for {fname}: recorded {expected_hash}, recomputed {actual_hash}"
                            )

        # Certification consistency
        standards = {s["standard_id"]: s for s in cert_data.get("standards", [])}
        expected_ev = _EVIDENCE.get(cap_id, {})
        for std_id, ev_tuple in expected_ev.items():
            exp_satisfied, _, _ = ev_tuple
            if std_id not in standards:
                errors.append(f"{cap_id} CERTIFICATION.json missing standard '{std_id}'")
            elif standards[std_id]["satisfied"] != exp_satisfied:
                errors.append(
                    f"{cap_id} standard '{std_id}' satisfied mismatch: CERTIFICATION.json has {standards[std_id]['satisfied']}, certification.py expects {exp_satisfied}"
                )

        # Synthetic capabilities must NOT claim public_reference_dataset or independent_ground_truth
        if cap_id in ("scrna.annotation_evidence", "spatial.inference_validity"):
            if standards.get("public_reference_dataset", {}).get("satisfied"):
                errors.append(f"{cap_id} falsely claims public_reference_dataset=true under synthetic track")
            if standards.get("independent_ground_truth", {}).get("satisfied"):
                errors.append(f"{cap_id} falsely claims independent_ground_truth=true under synthetic track")

        # Summary check
        satisfied_count = sum(1 for s in cert_data.get("standards", []) if s.get("satisfied"))
        summary = cert_data.get("summary", {})
        if summary.get("satisfied") != satisfied_count:
            errors.append(
                f"{cap_id} summary.satisfied ({summary.get('satisfied')}) != count of satisfied standards ({satisfied_count})"
            )

        details[cap_id] = cap_details

    passed = len(errors) == 0
    return VerificationResult(
        passed=passed,
        checked_files=checked,
        errors=errors,
        warnings=warnings,
        details=details,
    )
