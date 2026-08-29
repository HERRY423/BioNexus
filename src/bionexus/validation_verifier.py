"""Unified validation artifact and certification integrity verifier (BNS-010, BNS-015).

Checks:
1. File existence (REPORT.json, INFERENTIAL_STRESS_REPORT.json, CERTIFICATION.json, declared data files, and referenced evidence files).
2. Runtime SHA-256 checksums match observed file contents (fail-closed on missing or tampered files).
3. Version and Git Commit consistency (strictly matches bionexus.versions.VERSION and verified commit SHA).
4. Git dirty policy enforcement (release evidence cannot silently accept dirty provenance).
5. Evidence track consistency (synthetic technical acceptance vs real reference dataset).
6. Certification consistency (standards, summary, tier, verdict, and _EVIDENCE mapping agreement).
7. Stress test deep verification (JSON integrity, overall PASS, and all dimension gates passed).
8. Flagship directory cleanliness (no synthetic pretenders masquerading in data/flagship).
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from bionexus.certification import _EVIDENCE, certify_capability
from bionexus.provenance import get_git_info, sha256_file
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

_VALIDATION_SOURCE_DIRS = (
    "src/bionexus",
    "skills/single-cell-rna-qc",
    "skills/spatial-transcriptomics",
)
_VALIDATION_SOURCE_FILES = (
    "evals/pseudobulk_stress_test.py",
    "evals/annotation_stress_test.py",
    "evals/annotation_external_validation.py",
    "evals/annotation_external_holdout_validation.py",
    "evals/spatial_stress_test.py",
    "evals/spatial_instrument_validation.py",
    "evals/flagship_validation.py",
    "scripts/run_flagship_validation.py",
    "pyproject.toml",
    "requirements.txt",
    "requirements-dev.txt",
)
_SOURCE_IGNORED_PARTS = {"__pycache__", ".pytest_cache", ".ruff_cache"}


_SNAPSHOT_TEXT_EXTS = {".py", ".json", ".yaml", ".yml", ".md", ".txt", ".csv", ".toml", ".cfg", ".ini", ".rst"}


def compute_validation_source_snapshot(repo_root: Union[Path, str]) -> str:
    """Hash the code that would execute now, excluding self-referential reports.

    Text line endings are normalized for cross-platform stability.  Reading
    the working tree (rather than ``git show HEAD``) is intentional: local
    source modifications must invalidate previously generated evidence.
    """
    root = Path(repo_root)
    paths = _validation_source_paths(root)

    digest = hashlib.sha256()
    for path in paths:
        rel = path.relative_to(root).as_posix()
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        raw = path.read_bytes()
        if path.suffix.lower() in _SNAPSHOT_TEXT_EXTS:
            raw = raw.replace(b"\r\n", b"\n")
        digest.update(hashlib.sha256(raw).digest())
        digest.update(b"\n")
    return digest.hexdigest()


def _validation_source_paths(root: Path) -> List[Path]:
    paths: List[Path] = []
    for rel_dir in _VALIDATION_SOURCE_DIRS:
        directory = root / rel_dir
        if directory.is_dir():
            paths.extend(
                path
                for path in directory.rglob("*")
                if path.is_file() and not any(part in _SOURCE_IGNORED_PARTS for part in path.parts)
            )
    for rel_file in _VALIDATION_SOURCE_FILES:
        path = root / rel_file
        if path.is_file():
            paths.append(path)

    return sorted(set(paths), key=lambda item: item.relative_to(root).as_posix())


def compute_validation_source_dirty(repo_root: Union[Path, str]) -> Optional[bool]:
    """Return whether validation-relevant sources differ from HEAD."""
    root = Path(repo_root)
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    for raw_line in result.stdout.splitlines():
        rel = raw_line[3:].strip().replace("\\", "/")
        if " -> " in rel:
            rel = rel.split(" -> ", 1)[1]
        if rel in _VALIDATION_SOURCE_FILES or any(
            rel == prefix or rel.startswith(prefix + "/") for prefix in _VALIDATION_SOURCE_DIRS
        ):
            return True
    return False


def bind_validation_source_provenance(provenance: Dict[str, Any], repo_root: Union[Path, str]) -> Dict[str, Any]:
    """Attach stable source identity while retaining whole-repository dirtiness."""
    repository_dirty = provenance.get("git_dirty")
    source_dirty = compute_validation_source_dirty(repo_root)
    provenance["repository_dirty_at_execution"] = repository_dirty
    provenance["validation_source_dirty"] = source_dirty
    provenance["git_dirty"] = source_dirty if source_dirty is not None else repository_dirty
    provenance["source_snapshot_sha256"] = compute_validation_source_snapshot(repo_root)
    return provenance


def _git_is_ancestor(root: Path, ancestor: str, descendant: str) -> Optional[bool]:
    """Return whether ancestor is reachable from descendant, or None without Git."""
    try:
        result = subprocess.run(
            ["git", "merge-base", "--is-ancestor", ancestor, descendant],
            cwd=root,
            capture_output=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode == 0:
        return True
    if result.returncode == 1:
        return False
    return None


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
    enforce_commit: Optional[str] = None,
    allow_dirty: bool = False,
) -> VerificationResult:
    """Verify all validation artifacts, checksums, provenance, and certification consistency.

    Parameters
    ----------
    repo_root : Path or str, optional
        Repository root path. If None, resolves from file location.
    enforce_version : str, optional
        Expected version string. Defaults to bionexus.versions.VERSION.
    enforce_commit : str, optional
        Expected commit SHA string. If provided, strictly verified.
    allow_dirty : bool, default False
        Whether to allow git_dirty=True in provenance records.

    Returns
    -------
    VerificationResult
        Result containing pass/fail, checked files, errors, and warnings.
    """
    root = Path(repo_root) if repo_root else Path(__file__).resolve().parents[2]
    expected_version = enforce_version or VERSION
    git_info = get_git_info(root)
    current_commit = enforce_commit or git_info.get("commit_sha")
    if current_commit == "unknown":
        current_commit = None

    checked: List[str] = []
    errors: List[str] = []
    warnings: List[str] = []
    details: Dict[str, Any] = {}
    current_source_snapshot = compute_validation_source_snapshot(root)
    details["validation_source_snapshot_sha256"] = current_source_snapshot

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

        # Preregistration locks are part of the evidence boundary, not merely
        # attachments.  Recompute each hash so post-outcome edits fail closed.
        studies_dir = cap_dir / "studies"
        if studies_dir.is_dir():
            resolved_root = root.resolve()
            for lock_path in sorted(studies_dir.rglob("PREREGISTRATION_LOCK.json")):
                try:
                    lock_data = json.loads(lock_path.read_text(encoding="utf-8"))
                    target_rel = lock_data.get("locked_path") or lock_data.get("preregistration_path")
                    if not target_rel:
                        errors.append(f"Invalid preregistration lock {lock_path}: missing target path")
                        continue
                    locked_path = (root / str(target_rel)).resolve()
                    locked_path.relative_to(resolved_root)
                    if not locked_path.is_file():
                        errors.append(f"Preregistration lock target missing: {locked_path}")
                        continue
                    observed_hash = sha256_file(locked_path)
                    expected_hash = lock_data.get("sha256") or lock_data.get("preregistration_sha256")
                    if observed_hash != expected_hash:
                        errors.append(
                            f"Preregistration hash mismatch for {locked_path.relative_to(root)}: "
                            f"recorded {expected_hash}, recomputed {observed_hash}"
                        )
                    checked.extend(
                        [str(lock_path.relative_to(root)), str(locked_path.relative_to(root))]
                    )
                except (KeyError, OSError, ValueError, json.JSONDecodeError) as exc:
                    errors.append(f"Invalid preregistration lock {lock_path}: {exc}")

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

        stress_data = None
        if stress_path.is_file():
            try:
                stress_data = json.loads(stress_path.read_text(encoding="utf-8"))
            except Exception as exc:
                errors.append(f"Corrupt JSON in {stress_path}: {exc}")
        else:
            errors.append(f"Missing required artifact: {cap_id} INFERENTIAL_STRESS_REPORT.json")

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
            prov_commit = prov.get("commit_sha")
            if not prov_commit:
                errors.append(f"{cap_id} REPORT.json missing provenance.commit_sha")
            elif current_commit and prov_commit != current_commit:
                if enforce_commit:
                    errors.append(
                        f"{cap_id} REPORT.json provenance.commit_sha '{prov_commit}' != enforced commit '{current_commit}'"
                    )
                else:
                    is_ancestor = _git_is_ancestor(root, prov_commit, current_commit)
                    if is_ancestor is not True:
                        errors.append(
                            f"{cap_id} REPORT.json provenance.commit_sha '{prov_commit}' is not a verified ancestor of current commit '{current_commit}'"
                        )
            recorded_snapshot = prov.get("source_snapshot_sha256")
            if recorded_snapshot != current_source_snapshot:
                errors.append(
                    f"{cap_id} REPORT.json source_snapshot_sha256 '{recorded_snapshot}' != current validation source snapshot '{current_source_snapshot}'"
                )
            if prov.get("generator_version") != expected_version:
                errors.append(
                    f"{cap_id} REPORT.json provenance.generator_version '{prov.get('generator_version')}' != '{expected_version}'"
                )
            if not allow_dirty and prov.get("git_dirty") is True:
                errors.append(
                    f"{cap_id} REPORT.json provenance has git_dirty=True (dirty provenance rejected)"
                )

        # Stress report deep checks
        if stress_data is not None:
            stress_cap = stress_data.get("capability_id")
            if stress_cap != cap_id:
                errors.append(
                    f"{cap_id} INFERENTIAL_STRESS_REPORT.json capability_id '{stress_cap}' != expected '{cap_id}'"
                )
            if stress_data.get("overall_status") != "PASS":
                errors.append(
                    f"{cap_id} INFERENTIAL_STRESS_REPORT.json overall_status is '{stress_data.get('overall_status')}', expected 'PASS'"
                )
            dims = stress_data.get("dimensions")
            if not isinstance(dims, dict) or len(dims) == 0:
                errors.append(
                    f"{cap_id} INFERENTIAL_STRESS_REPORT.json has empty or missing dimensions"
                )
            else:
                for d_key, d_val in dims.items():
                    if isinstance(d_val, dict):
                        if not d_val.get("passed", False):
                            errors.append(
                                f"{cap_id} INFERENTIAL_STRESS_REPORT.json dimension '{d_val.get('dimension', d_key)}' did not pass"
                            )
                    else:
                        errors.append(
                            f"{cap_id} INFERENTIAL_STRESS_REPORT.json dimension '{d_key}' is not a valid dict"
                        )

            stress_prov = stress_data.get("provenance", {})
            if not stress_prov:
                errors.append(f"{cap_id} INFERENTIAL_STRESS_REPORT.json missing provenance")
            else:
                if stress_prov.get("generator_version") != expected_version:
                    errors.append(
                        f"{cap_id} INFERENTIAL_STRESS_REPORT.json generator_version '{stress_prov.get('generator_version')}' != '{expected_version}'"
                    )
                stress_commit = stress_prov.get("commit_sha")
                if current_commit and stress_commit and stress_commit != current_commit:
                    if enforce_commit:
                        errors.append(
                            f"{cap_id} INFERENTIAL_STRESS_REPORT.json commit_sha '{stress_commit}' != enforced commit '{current_commit}'"
                        )
                    else:
                        is_ancestor = _git_is_ancestor(root, stress_commit, current_commit)
                        if is_ancestor is not True:
                            errors.append(
                                f"{cap_id} INFERENTIAL_STRESS_REPORT.json commit_sha '{stress_commit}' is not a verified ancestor of current commit '{current_commit}'"
                            )
                stress_snapshot = stress_prov.get("source_snapshot_sha256")
                if stress_snapshot != current_source_snapshot:
                    errors.append(
                        f"{cap_id} INFERENTIAL_STRESS_REPORT.json source_snapshot_sha256 '{stress_snapshot}' != current validation source snapshot '{current_source_snapshot}'"
                    )
                if not allow_dirty and stress_prov.get("git_dirty") is True:
                    errors.append(
                        f"{cap_id} INFERENTIAL_STRESS_REPORT.json provenance has git_dirty=True (dirty provenance rejected)"
                    )

        # Evidence track and accession checks
        dataset_info = report_data.get("dataset", {})
        dataset_track = dataset_info.get("dataset_track")

        if cap_id in ("scrna.annotation_evidence", "spatial.inference_validity"):
            expected_track = {
                "scrna.annotation_evidence": "real_public_processed_citeseq",
                "spatial.inference_validity": "real_instrument_technical_acceptance",
            }[cap_id]
            if dataset_track != expected_track:
                errors.append(f"{cap_id} must have dataset_track='{expected_track}', got '{dataset_track}'")
            cs_dict = dataset_info.get("checksum_sha256")
            if not isinstance(cs_dict, dict) or not cs_dict:
                errors.append(f"{cap_id} missing or invalid dataset.checksum_sha256 dictionary")
            else:
                ds_dir = root / "data" / "flagship" / dataset_info.get("name", "")
                for fname, expected_hash in cs_dict.items():
                    target_file = ds_dir / fname
                    if not target_file.is_file():
                        errors.append(f"{cap_id} declared real data file missing: {target_file}")
                        continue
                    actual_hash = sha256_file(target_file)
                    checked.append(str(target_file.relative_to(root)))
                    if actual_hash != expected_hash:
                        errors.append(
                            f"Checksum mismatch for {fname}: recorded {expected_hash}, recomputed {actual_hash}"
                        )

            # Large raw inputs are hash-bound datasets, not permanent report evidence attachments.
            evidence_files = report_data.get("evidence_files", [])
            for ef in evidence_files:
                if ef.endswith(".h5ad") or ef.endswith(".zarr"):
                    errors.append(f"{cap_id} REPORT.json evidence_files should not list ignored artifact: '{ef}'")

        elif cap_id == "scrna.pseudobulk_de":
            # Real dataset checksum verification (fail-closed on missing files)
            cs_dict = dataset_info.get("checksum_sha256")
            if not isinstance(cs_dict, dict) or not cs_dict:
                errors.append(f"{cap_id} missing or invalid dataset.checksum_sha256 dictionary")
            else:
                ds_dir = root / "data" / "flagship" / dataset_info.get("name", "kang2018_pbmc_ifnb")
                for fname, expected_hash in cs_dict.items():
                    target_file = ds_dir / fname
                    if not target_file.is_file():
                        try:
                            rel_tf = str(target_file.relative_to(root))
                        except ValueError:
                            rel_tf = str(target_file)
                        errors.append(
                            f"{cap_id} declared real data file missing: {rel_tf}"
                        )
                    else:
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

            # Check supplementary_data if present
            supp = dataset_info.get("supplementary_data")
            if isinstance(supp, dict) and "file" in supp and "checksum_sha256" in supp:
                supp_file = root / supp["file"]
                if supp_file.is_file():
                    actual_supp_hash = sha256_file(supp_file)
                    checked.append(str(supp_file.relative_to(root)))
                    if actual_supp_hash != supp["checksum_sha256"]:
                        errors.append(
                            f"Checksum mismatch for supplementary file {supp['file']}: recorded {supp['checksum_sha256']}, recomputed {actual_supp_hash}"
                        )

        # Check all evidence_files exist, are within repository, and not missing
        evidence_files = report_data.get("evidence_files", [])
        for ef in evidence_files:
            ef_clean = ef.replace("\\", "/")  # normalize to posix for display
            ef_path = root / Path(*ef_clean.split("/"))  # cross-platform path resolution
            if not ef_path.is_file():
                errors.append(f"{cap_id} REPORT.json evidence_files references missing file: '{ef_clean}'")
            else:
                try:
                    rel_ef = str(ef_path.relative_to(root))
                    checked.append(rel_ef)
                except ValueError:
                    errors.append(f"{cap_id} evidence_file '{ef_clean}' is outside repository root")

        # Certification consistency
        rec = certify_capability(cap_id)
        if cert_data.get("certification_level") != rec.tier.value:
            errors.append(
                f"{cap_id} CERTIFICATION.json certification_level '{cert_data.get('certification_level')}' != computed tier '{rec.tier.value}'"
            )

        standards = {s["standard_id"]: s for s in cert_data.get("standards", [])}
        for std_id, ev_tuple in _EVIDENCE.get(cap_id, {}).items():
            exp_satisfied, _, _ = ev_tuple
            if std_id not in standards:
                errors.append(f"{cap_id} CERTIFICATION.json missing standard '{std_id}'")
            elif standards[std_id]["satisfied"] != exp_satisfied:
                errors.append(
                    f"{cap_id} standard '{std_id}' satisfied mismatch: CERTIFICATION.json has {standards[std_id]['satisfied']}, certification.py expects {exp_satisfied}"
                )

        # External biological ground truth remains unsatisfied for these two
        # capabilities. Public-reference status is capability-specific and is
        # already bound to the canonical certification evidence above.
        if cap_id in ("scrna.annotation_evidence", "spatial.inference_validity"):
            if standards.get("independent_ground_truth", {}).get("satisfied"):
                errors.append(f"{cap_id} falsely claims independent_ground_truth=true")

        # Summary check
        satisfied_count = sum(1 for s in cert_data.get("standards", []) if s.get("satisfied"))
        summary = cert_data.get("summary", {})
        if summary.get("satisfied") != satisfied_count:
            errors.append(
                f"{cap_id} summary.satisfied ({summary.get('satisfied')}) != count of satisfied standards ({satisfied_count})"
            )
        if summary.get("satisfied") != rec.satisfied_count:
            errors.append(
                f"{cap_id} summary.satisfied ({summary.get('satisfied')}) != computed satisfied count ({rec.satisfied_count})"
            )
        if summary.get("verdict") != rec.tier.value:
            errors.append(
                f"{cap_id} summary.verdict ({summary.get('verdict')}) != computed tier ({rec.tier.value})"
            )
        if set(summary.get("unsatisfied_list", [])) != set(rec.blocking_for_certified):
            errors.append(
                f"{cap_id} summary.unsatisfied_list mismatch: {summary.get('unsatisfied_list')} != computed blocking {rec.blocking_for_certified}"
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
