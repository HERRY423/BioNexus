#!/usr/bin/env python3
"""Fail-closed gate and freeze for the BN-PB-IV-004 blinded packet."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import anndata as ad
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from bionexus.independent_pseudobulk import (  # noqa: E402
    file_sha256,
    validate_preregistration,
    verify_negative_result_freeze,
)

STUDY_ROOT = REPO_ROOT / "validation" / "pseudobulk" / "studies" / "BN-PB-IV-004"
DEFAULT_INPUT_ROOT = REPO_ROOT / "data" / "independent" / "BN-PB-IV-004_blinded_inputs"
FORBIDDEN_BLINDED_TOKENS = ("ifn", "pbs", "vehicle", "control", "stim", "cytokine", "condition")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.incomplete")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _blinded_adata_issues(path: Path, *, expected_cells: int | None) -> list[str]:
    if not path.is_file():
        return [f"missing blinded AnnData: {path}"]
    issues: list[str] = []
    try:
        adata = ad.read_h5ad(path)
    except Exception as exc:
        return [f"unreadable blinded AnnData {path}: {type(exc).__name__}: {exc}"]
    required = {"opaque_subject_id", "opaque_arm_id", "n_cells"}
    missing = sorted(required - set(adata.obs.columns))
    if missing:
        issues.append(f"{path.name} missing opaque obs columns: {missing}")
        return issues
    obs = adata.obs[list(required)].astype(str)
    if adata.n_obs != 24:
        issues.append(f"{path.name} must contain 24 donor-arm pseudobulk rows, observed {adata.n_obs}")
    pairs = obs.groupby("opaque_subject_id")["opaque_arm_id"].nunique()
    if len(pairs) != 12 or not (pairs == 2).all():
        issues.append(f"{path.name} does not contain exactly 12 complete opaque subject pairs")
    if obs["opaque_arm_id"].nunique() != 2:
        issues.append(f"{path.name} must contain exactly two opaque arms")
    n_cells = pd.to_numeric(adata.obs["n_cells"], errors="coerce")
    if n_cells.isna().any() or (n_cells < 1).any():
        issues.append(f"{path.name} contains invalid n_cells")
    elif expected_cells is not None and int(n_cells.sum()) != expected_cells:
        issues.append(f"{path.name} source-cell total is {int(n_cells.sum())}, expected {expected_cells}")
    searchable = " ".join(map(str, adata.obs.columns)) + " " + " ".join(obs.to_numpy().ravel())
    leaked = sorted(token for token in FORBIDDEN_BLINDED_TOKENS if token in searchable.lower())
    if leaked:
        issues.append(f"{path.name} leaks condition semantics in blinded labels: {leaked}")
    return issues


def assess_gates(input_root: Path) -> tuple[list[str], dict[str, Any]]:
    issues: list[str] = []
    prereg_path = STUDY_ROOT / "PREREGISTRATION.json"
    lock_path = STUDY_ROOT / "PREREGISTRATION_LOCK.json"
    prereg = _load_json(prereg_path)
    lock = _load_json(lock_path)
    issues.extend(validate_preregistration(prereg, lock, prereg_path))

    negative_freeze = REPO_ROOT / "validation" / "pseudobulk" / "independent" / "NEGATIVE_RESULT_FREEZE.json"
    issues.extend(verify_negative_result_freeze(negative_freeze))

    parse_manifest_path = (
        REPO_ROOT / "data" / "independent" / "parse10m_pbmc_ifnb_natural_v1" / "EXTRACTION_MANIFEST.json"
    )
    if not parse_manifest_path.is_file():
        issues.append("C02 extraction manifest is missing")
    else:
        parse_manifest = _load_json(parse_manifest_path)
        parse_output = REPO_ROOT / str(parse_manifest.get("output_path", ""))
        if parse_manifest.get("schema_version") != "bionexus.parse-natural-extraction.v2":
            issues.append("C02 extraction manifest schema is not the resume-safe v2 contract")
        if int(parse_manifest.get("n_cells", -1)) != 725_031:
            issues.append("C02 extraction does not cover exactly 725,031 cells")
        if parse_manifest.get("balancing_or_stratified_sampling") is not False:
            issues.append("C02 extraction used or failed to exclude balancing/subsampling")
        if not parse_output.is_file() or file_sha256(parse_output) != parse_manifest.get("output_sha256"):
            issues.append("C02 pseudobulk output is missing or hash-invalid")

    c02_blinded = input_root / "C02_BLINDED_PSEUDOBULK.h5ad"
    c04_blinded = input_root / "C04_BLINDED_PSEUDOBULK.h5ad"
    blinded_manifest = input_root / "C04_BLINDED_SAMPLE_MANIFEST.csv"
    attestation_path = input_root / "CUSTODIAN_DATA_GATE_ATTESTATION.json"
    issues.extend(_blinded_adata_issues(c02_blinded, expected_cells=725_031))
    issues.extend(_blinded_adata_issues(c04_blinded, expected_cells=None))

    if not blinded_manifest.is_file():
        issues.append(f"missing C04 blinded sample manifest: {blinded_manifest}")
    else:
        manifest = pd.read_csv(blinded_manifest, dtype=str)
        required = {"opaque_subject_id", "opaque_arm_id", "aliquot_id", "library_id"}
        missing = sorted(required - set(manifest.columns))
        if missing:
            issues.append(f"C04 blinded sample manifest missing columns: {missing}")
        elif len(manifest) != 24:
            issues.append(f"C04 blinded sample manifest must have 24 rows, observed {len(manifest)}")
        leaked_columns = sorted(
            column for column in manifest.columns if any(token in column.lower() for token in FORBIDDEN_BLINDED_TOKENS)
        )
        if leaked_columns:
            issues.append(f"C04 blinded manifest leaks condition columns: {leaked_columns}")

    if not attestation_path.is_file():
        issues.append(f"missing signed custodian data-gate attestation: {attestation_path}")
    else:
        attestation = _load_json(attestation_path)
        if attestation.get("status") != "SIGNED_COMPLETE":
            issues.append("custodian data-gate attestation is not SIGNED_COMPLETE")
        required_true = (
            "authoritative_lims_pairing_verified",
            "no_pair_inferred_from_accession_or_file_order",
            "exactly_12_complete_donor_pairs",
            "ifn_beta_1a_identity_and_lot_verified",
            "six_hour_timing_within_five_minutes_verified",
            "arm_key_held_outside_packet",
        )
        for field in required_true:
            if attestation.get("gates", {}).get(field) is not True:
                issues.append(f"custodian did not attest gate: {field}")
        expected_hashes = {
            "preregistration_sha256": file_sha256(prereg_path),
            "C02_blinded_pseudobulk_sha256": file_sha256(c02_blinded) if c02_blinded.is_file() else None,
            "C04_blinded_pseudobulk_sha256": file_sha256(c04_blinded) if c04_blinded.is_file() else None,
            "C04_blinded_sample_manifest_sha256": file_sha256(blinded_manifest) if blinded_manifest.is_file() else None,
        }
        for field, expected in expected_hashes.items():
            if expected is not None and attestation.get("materials", {}).get(field) != expected:
                issues.append(f"custodian attestation hash mismatch: {field}")
        signature = attestation.get("signature", {})
        if not signature.get("signed_at_utc") or not signature.get("signature_value_or_detached_sha256"):
            issues.append("custodian attestation signature is incomplete")

    materials = {
        "preregistration": prereg_path,
        "preregistration_lock": lock_path,
        "negative_result_freeze": negative_freeze,
        "frozen_signature": REPO_ROOT
        / "validation"
        / "pseudobulk"
        / "independent"
        / "evidence"
        / "locked_discovery_signature_platform_holdout.csv",
        "C02_blinded_pseudobulk": c02_blinded,
        "C04_blinded_pseudobulk": c04_blinded,
        "C04_blinded_sample_manifest": blinded_manifest,
        "custodian_attestation": attestation_path,
        "analysis_code": REPO_ROOT / "evals" / "pseudobulk_independent_validation.py",
    }
    return list(dict.fromkeys(issues)), materials


def freeze(input_root: Path, output_root: Path) -> dict[str, Any]:
    issues, materials = assess_gates(input_root)
    gate_report = {
        "schema_version": "bionexus.blinded-packet-gate.v1",
        "study_id": "BN-PB-IV-004",
        "assessed_at": _utc_now(),
        "status": "PASS" if not issues else "ABSTAIN_BLOCKED",
        "packet_frozen": False,
        "issues": issues,
    }
    gate_path = STUDY_ROOT / "BLINDED_PACKET_GATE.json"
    if issues:
        _write_json(gate_path, gate_report)
        return gate_report
    if output_root.exists():
        raise RuntimeError(f"refusing to overwrite an existing blinded packet: {output_root}")
    output_root.mkdir(parents=True)
    artifact_records: list[dict[str, str]] = []
    for role, source in materials.items():
        destination = output_root / source.name
        shutil.copy2(source, destination)
        artifact_records.append({"role": role, "file": destination.name, "sha256": file_sha256(destination)})
    packet_manifest = {
        "schema_version": "bionexus.blinded-packet.v1",
        "study_id": "BN-PB-IV-004",
        "frozen_at": _utc_now(),
        "condition_key_included": False,
        "artifacts": artifact_records,
    }
    _write_json(output_root / "BLINDED_PACKET_MANIFEST.json", packet_manifest)
    packet_hash = hashlib.sha256(
        json.dumps(packet_manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    gate_report.update({"packet_frozen": True, "packet_manifest_sha256": packet_hash})
    _write_json(gate_path, gate_report)
    return gate_report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", type=Path, default=DEFAULT_INPUT_ROOT)
    parser.add_argument("--output-root", type=Path, default=STUDY_ROOT / "blinded_packet")
    args = parser.parse_args()
    report = freeze(args.input_root, args.output_root)
    print(json.dumps(report, indent=2), flush=True)
    return 0 if report["packet_frozen"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
