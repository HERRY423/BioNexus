#!/usr/bin/env python3
"""Run BN-PB-IV-004 endpoints without opening the condition key.

This produces a tamper-evident, opaque-orientation analysis artifact. It does
not decide IFN-beta versus vehicle direction and it never writes or reads the
custodian-held key. Final biological decisions remain blocked until an
independent biostatistician signs and the custodian performs the authorized
unblinding step.
"""

from __future__ import annotations

import argparse
import json
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
    direction_concordance,
    donor_log2_fold_changes,
    exact_sign_flip_empirical_p_value,
    file_sha256,
    validate_preaggregated_pseudobulk,
)

DEFAULT_PACKET = REPO_ROOT / "validation" / "pseudobulk" / "studies" / "BN-PB-IV-004" / "blinded_packet"
DEFAULT_OUTPUT = REPO_ROOT / "validation" / "pseudobulk" / "studies" / "BN-PB-IV-004" / "blinded_analysis"
FORBIDDEN_TOKENS = ("ifn", "pbs", "vehicle", "control", "stim", "cytokine", "condition")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.incomplete")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    temporary.replace(path)


def _opaque_issues(adata: ad.AnnData) -> list[str]:
    required = {"opaque_subject_id", "opaque_arm_id", "n_cells"}
    issues = [f"missing opaque columns: {sorted(required - set(adata.obs.columns))}"] if required - set(adata.obs.columns) else []
    if issues:
        return issues
    if adata.n_obs != 24:
        issues.append(f"expected 24 donor-arm rows, observed {adata.n_obs}")
    obs = adata.obs[["opaque_subject_id", "opaque_arm_id", "n_cells"]].astype(str)
    pairs = obs.groupby("opaque_subject_id")["opaque_arm_id"].nunique()
    if len(pairs) != 12 or not (pairs == 2).all():
        issues.append("expected exactly 12 complete opaque subject pairs")
    if obs["opaque_arm_id"].nunique() != 2:
        issues.append("expected exactly two opaque arms")
    searchable = " ".join(map(str, adata.obs.columns)) + " " + " ".join(obs.to_numpy().ravel())
    leaked = sorted(token for token in FORBIDDEN_TOKENS if token in searchable.lower())
    if leaked:
        issues.append(f"condition semantics leaked in opaque labels: {leaked}")
    return issues


def _validate_packet(packet: Path) -> tuple[list[str], dict[str, Any]]:
    manifest_path = packet / "BLINDED_PACKET_MANIFEST.json"
    if not manifest_path.is_file():
        return [f"missing frozen packet manifest: {manifest_path}"], {}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    issues: list[str] = []
    if manifest.get("condition_key_included") is not False:
        issues.append("frozen packet condition_key_included is not false")
    for artifact in manifest.get("artifacts", []):
        path = packet / str(artifact.get("file", ""))
        expected = str(artifact.get("sha256", "")).lower()
        if not path.is_file():
            issues.append(f"missing packet artifact: {path.name}")
        elif file_sha256(path).lower() != expected:
            issues.append(f"packet artifact hash mismatch: {path.name}")
    return issues, manifest


def _cohort(packet: Path, filename: str, cohort_id: str) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any], pd.DataFrame]:
    path = packet / filename
    adata = ad.read_h5ad(path)
    issues = _opaque_issues(adata)
    counts, design, audit = validate_preaggregated_pseudobulk(
        adata,
        donor_column="opaque_subject_id",
        condition_column="opaque_arm_id",
        cohort_id=cohort_id,
        reference_level="ARM_A",
        contrast_level="ARM_B",
        minimum_paired_donors=12,
        minimum_cells_per_sample=500,
    )
    issues.extend(audit.issues)
    return counts, design, {"audit": audit.to_dict(), "issues": issues, "source_sha256": file_sha256(path)}, adata.obs.copy()


def run(packet: Path = DEFAULT_PACKET, output: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    issues, packet_manifest = _validate_packet(packet)
    signature_path = packet / "locked_discovery_signature_platform_holdout.csv"
    if not signature_path.is_file():
        issues.append("missing frozen discovery signature")
        signature = pd.DataFrame()
    else:
        signature = pd.read_csv(signature_path)
        required = {"gene", "log2FoldChange"}
        if required - set(signature.columns):
            issues.append(f"frozen signature missing columns: {sorted(required - set(signature.columns))}")

    cohort_results: dict[str, Any] = {}
    effects: dict[str, pd.DataFrame] = {}
    designs: dict[str, pd.DataFrame] = {}
    for cohort_id, filename in (("C02", "C02_BLINDED_PSEUDOBULK.h5ad"), ("C04", "C04_BLINDED_PSEUDOBULK.h5ad")):
        try:
            counts, design, audit, _obs = _cohort(packet, filename, cohort_id)
            cohort_results[cohort_id] = audit
            designs[cohort_id] = design
            effects[cohort_id] = donor_log2_fold_changes(
                counts, design, reference_level="ARM_A", contrast_level="ARM_B"
            )
        except Exception as exc:  # retain fail-closed report rather than partial claims
            issues.append(f"{cohort_id} analysis input failure: {type(exc).__name__}: {exc}")

    endpoint_results: dict[str, Any] = {}
    if not signature.empty and not any(cohort_id not in effects for cohort_id in ("C02", "C04")):
        signature["gene"] = signature["gene"].astype(str).str.upper()
        expected = signature.set_index("gene")["log2FoldChange"]
        genes = signature["gene"].head(100).tolist()
        for cohort_id in ("C02", "C04"):
            median_effect = effects[cohort_id].median(axis=0)
            concordance, n_evaluable = direction_concordance(median_effect, expected, genes)
            observed, empirical_p, null_scores = exact_sign_flip_empirical_p_value(effects[cohort_id], expected, genes)
            endpoint_results[cohort_id] = {
                "opaque_orientation": "ARM_B_minus_ARM_A",
                "n_evaluable_genes": n_evaluable,
                "opaque_direction_concordance": concordance,
                "reverse_opaque_direction_concordance": None if concordance is None else 1.0 - concordance,
                "minimum_concordance": 0.65,
                "orientation_invariant_nonpass": bool(
                    concordance is not None and max(concordance, 1.0 - concordance) < 0.65
                ),
                "opaque_sign_flip_observed": observed,
                "opaque_sign_flip_empirical_p_value": empirical_p,
                "exact_sign_flips_executed": len(null_scores),
                "expected_exact_sign_flips": 4095,
                "decision": "PENDING_UNBLIND",
            }

    report = {
        "schema_version": "bionexus.bn-pb-iv-004-blinded-analysis.v1",
        "study_id": "BN-PB-IV-004",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "ABSTAIN_PENDING_UNBLIND_AND_INDEPENDENT_BIOSTATISTICIAN",
        "condition_key_accessed": False,
        "condition_key_included": False,
        "opaque_orientation": "ARM_B_minus_ARM_A; biological arm meaning intentionally unknown",
        "packet_manifest_sha256": file_sha256(packet / "BLINDED_PACKET_MANIFEST.json") if packet_manifest else None,
        "analysis_code_sha256": file_sha256(Path(__file__)),
        "cohort_audits": cohort_results,
        "endpoints": endpoint_results,
        "issues": issues,
        "unblinding_required": True,
        "independent_biostatistician_signature_required": True,
        "claim_boundary": "No biological pass/fail decision is made while ARM_A/ARM_B meaning is withheld.",
    }
    _write_json(output / "BLINDED_ANALYSIS_REPORT.json", report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--packet", type=Path, default=DEFAULT_PACKET)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    report = run(args.packet, args.output)
    print(json.dumps({"status": report["status"], "issues": report["issues"], "endpoints": report["endpoints"]}, indent=2))
    return 0 if not report["issues"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
