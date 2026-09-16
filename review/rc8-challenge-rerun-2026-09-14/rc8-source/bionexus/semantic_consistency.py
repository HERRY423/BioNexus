"""Semantic consistency verification between reports, evidence records, and certifications.

Enforces:
1. Cross-host semantic consistency:
   - Verifies cross-host/COMPARISON.json data (traps_compared, hosts, verdict)
     is accurately described in CERTIFICATION.json and certification._EVIDENCE.
   - Prevents stale claims of "0 traps compared" when cases exist.
   - Enforces the policy that headless trap comparisons cannot mechanically certify
     real-host execution (cross_host_test must remain unsatisfied without live multi-host IVN studies).
2. Study report endpoint vs. Certification notes consistency:
   - Verifies that endpoint pass/fail statuses in underlying study reports
     (e.g., BN-SP-IV-001/REPORT.json, BN-PB-IV-002, etc.) are faithfully reflected
     in CERTIFICATION.json notes.
   - Prevents certification notes from falsely claiming an endpoint failed when the
     study report recorded all_locked_endpoints_passed=true, or vice-versa.
3. Ground truth and maturity claim boundaries:
   - Prevents technical acceptance on manufactured confounders from masquerading as
     independent biological ground truth.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import List, Optional, Union

from bionexus.certification import _EVIDENCE, FLAGSHIP_CAPABILITIES


def verify_cross_host_consistency(root: Path) -> List[str]:
    """Verify semantic consistency between cross-host/COMPARISON.json and certifications."""
    errors: List[str] = []
    comp_path = root / "cross-host" / "COMPARISON.json"
    if not comp_path.is_file():
        errors.append("cross-host/COMPARISON.json missing")
        return errors

    try:
        comp_data = json.loads(comp_path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"Corrupt JSON in cross-host/COMPARISON.json: {exc}")
        return errors

    traps_compared = comp_data.get("traps_compared", 0)

    for cap_id in FLAGSHIP_CAPABILITIES:
        subdir = cap_id.split(".")[-1]
        if cap_id == "scrna.pseudobulk_de":
            subdir = "pseudobulk"
        elif cap_id == "scrna.annotation_evidence":
            subdir = "annotation"
        elif cap_id == "spatial.inference_validity":
            subdir = "spatial"

        cert_path = root / "validation" / subdir / "CERTIFICATION.json"
        if not cert_path.is_file():
            continue

        try:
            cert_data = json.loads(cert_path.read_text(encoding="utf-8"))
        except Exception:
            continue

        standards = {s["standard_id"]: s for s in cert_data.get("standards", [])}
        ch_std = standards.get("cross_host_test")
        if not ch_std:
            errors.append(f"{cap_id} CERTIFICATION.json missing cross_host_test standard")
            continue

        evidence_str = ch_std.get("evidence", "")
        notes_str = ch_std.get("notes", "")

        # 1. Check for stale "0 traps compared" contradiction
        if traps_compared > 0:
            if "0 traps compared" in evidence_str or "0 traps compared" in notes_str:
                errors.append(
                    f"{cap_id} CERTIFICATION.json claims '0 traps compared' but cross-host/COMPARISON.json "
                    f"records {traps_compared} traps compared"
                )

            # If evidence asserts a trap count, check for exact match
            match = re.search(r"(\d+)\s+traps\s+compared", evidence_str)
            if match:
                asserted_count = int(match.group(1))
                if asserted_count != traps_compared:
                    errors.append(
                        f"{cap_id} CERTIFICATION.json asserts {asserted_count} traps compared, "
                        f"but cross-host/COMPARISON.json has {traps_compared}"
                    )

        # 2. Check policy: headless trap comparison cannot satisfy real-host execution
        if ch_std.get("satisfied") is True:
            # If hosts are only headless/simulator or no IVN external lab quota
            errors.append(
                f"{cap_id} CERTIFICATION.json cross_host_test falsely marked satisfied: "
                "headless trap comparison does not certify real-host execution (BNS-HC-007)"
            )

        # 3. Check consistency with _EVIDENCE tuple in certification.py
        cap_static = _EVIDENCE.get(cap_id, {})
        if "cross_host_test" in cap_static:
            sat, ptr, note = cap_static["cross_host_test"]
            if traps_compared > 0 and ("0 traps compared" in ptr or "0 traps compared" in note):
                errors.append(
                    f"src/bionexus/certification.py _EVIDENCE['{cap_id}']['cross_host_test'] "
                    f"contains stale '0 traps compared' while COMPARISON.json has {traps_compared}"
                )

    return errors


def verify_study_endpoints_consistency(root: Path) -> List[str]:
    """Verify that study report endpoint outcomes match descriptions in certification standards."""
    errors: List[str] = []

    # Check BN-SP-IV-001 (Spatial real instrument technical acceptance)
    spatial_study = root / "validation" / "spatial" / "studies" / "BN-SP-IV-001" / "REPORT.json"
    spatial_cert = root / "validation" / "spatial" / "CERTIFICATION.json"

    if spatial_study.is_file() and spatial_cert.is_file():
        try:
            s_study_data = json.loads(spatial_study.read_text(encoding="utf-8"))
            s_cert_data = json.loads(spatial_cert.read_text(encoding="utf-8"))
        except Exception:
            return errors

        endpoints = s_study_data.get("endpoints", {})
        cell_size_passed = endpoints.get("cell_size_bias", {}).get("passed", False)
        all_passed = s_study_data.get("status", {}).get("all_locked_endpoints_passed", False)

        standards = {s["standard_id"]: s for s in s_cert_data.get("standards", [])}
        igt = standards.get("independent_ground_truth", {})
        igt_notes = igt.get("notes", "")

        # If cell_size_bias passed in the study report, certification must not claim it failed
        if cell_size_passed and all_passed:
            if re.search(r"one locked (cell-size-bias|cell_size_bias) endpoint failed", igt_notes, re.IGNORECASE):
                errors.append(
                    "spatial CERTIFICATION.json independent_ground_truth notes claim 'cell-size-bias endpoint failed', "
                    "but BN-SP-IV-001/REPORT.json records cell_size_bias.passed=true and all_locked_endpoints_passed=true"
                )
            if "endpoint failed" in igt_notes.lower() and "cell_size_bias" in igt_notes.lower():
                errors.append(
                    "spatial CERTIFICATION.json claims cell_size_bias failed when BN-SP-IV-001 recorded passed"
                )

        # Ground truth check: technical acceptance pass does NOT mean independent_ground_truth is satisfied
        if igt.get("satisfied") is True:
            errors.append(
                "spatial CERTIFICATION.json falsely claims independent_ground_truth=true: "
                "BN-SP-IV-001 technical acceptance does not constitute independent ground truth"
            )

        # Check certification.py static evidence for spatial
        spatial_static = _EVIDENCE.get("spatial.inference_validity", {})
        if "independent_ground_truth" in spatial_static:
            sat, ptr, note = spatial_static["independent_ground_truth"]
            if "one locked endpoint failed" in ptr or "one locked endpoint failed" in note:
                errors.append(
                    "src/bionexus/certification.py _EVIDENCE['spatial.inference_validity'] "
                    "claims 'one locked endpoint failed', but BN-SP-IV-001 passed all locked endpoints"
                )

    # Check BN-PB-IV-002 (Pseudobulk independent study negative result freeze)
    pb_indep_report = root / "validation" / "pseudobulk" / "independent" / "REPORT.json"
    pb_cert = root / "validation" / "pseudobulk" / "CERTIFICATION.json"

    if pb_indep_report.is_file() and pb_cert.is_file():
        try:
            pb_study_data = json.loads(pb_indep_report.read_text(encoding="utf-8"))
            pb_cert_data = json.loads(pb_cert.read_text(encoding="utf-8"))
        except Exception:
            return errors

        pb_all_passed = pb_study_data.get("status", {}).get("all_locked_endpoints_passed", True)
        if pb_all_passed is False:
            summary_rationale = pb_cert_data.get("summary", {}).get("verdict_rationale", "")
            if "independent study fully passed" in summary_rationale.lower():
                errors.append(
                    "pseudobulk CERTIFICATION.json falsely claims independent study fully passed "
                    "when BN-PB-IV-002 is a frozen negative result"
                )

    return errors


def verify_semantic_consistency(repo_root: Optional[Union[Path, str]] = None) -> List[str]:
    """Run all semantic consistency checks between reports, certifications, and comparisons.

    Returns a list of error strings. Empty list indicates full semantic consistency.
    """
    root = Path(repo_root) if repo_root else Path.cwd()
    errors: List[str] = []
    errors.extend(verify_cross_host_consistency(root))
    errors.extend(verify_study_endpoints_consistency(root))
    return errors
