#!/usr/bin/env python3
"""Execute preregistered donor/platform holdout validation for pseudobulk DE.

The analysis is intentionally fail-closed.  Missing cohorts, changed
preregistration hashes, invalid counts, failed endpoints, a documented
subsample, or absent independent blinding attestation are retained in the
report and cap/abstain the final claim.
"""

from __future__ import annotations

import argparse
import json
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
SKILL_SCRIPTS = REPO_ROOT / "skills" / "single-cell-rna-qc" / "scripts"
for candidate in (SRC, SKILL_SCRIPTS):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from scrna_deseq import run_pydeseq2  # noqa: E402

from bionexus.independent_pseudobulk import (  # noqa: E402
    aggregate_pseudobulk,
    direction_concordance,
    donor_log2_fold_changes,
    exact_sign_flip_empirical_p_value,
    file_sha256,
    independent_claim_status,
    sign_flip_empirical_p_value,
    validate_preaggregated_pseudobulk,
    validate_preregistration,
)
from bionexus.provenance import sidecar  # noqa: E402

DEFAULT_ROOT = REPO_ROOT / "validation" / "pseudobulk" / "studies" / "BN-PB-IV-003"
EXECUTION_WARNINGS: list[str] = []


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


def _normalise_de_table(table: pd.DataFrame) -> pd.DataFrame:
    required = {"gene", "log2FoldChange", "padj"}
    missing = required - set(table.columns)
    if missing:
        raise ValueError(f"PyDESeq2 result lacks required columns: {sorted(missing)}")
    out = table.copy()
    out["gene"] = out["gene"].astype(str).str.strip().str.upper()
    out["padj"] = pd.to_numeric(out["padj"], errors="coerce")
    out["log2FoldChange"] = pd.to_numeric(out["log2FoldChange"], errors="coerce")
    out = out.sort_values(["padj", "gene"], na_position="last").drop_duplicates("gene", keep="first")
    out = out.set_index("gene", drop=False)
    out.index.name = "gene_id"
    return out


def _run_de(counts: pd.DataFrame, design: pd.DataFrame) -> pd.DataFrame:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        table, _contract = run_pydeseq2(
            counts,
            design[["sample_id", "condition"]],
            condition="condition",
            reference="reference",
            contrast_level="contrast",
        )
    for item in caught:
        message = f"{item.category.__name__}: {item.message}"
        if message not in EXECUTION_WARNINGS:
            EXECUTION_WARNINGS.append(message)
    return _normalise_de_table(table)


def _cohort_data(spec: dict[str, Any], prereg: dict[str, Any]):
    import anndata as ad

    data_path = REPO_ROOT / spec["data_path"]
    if not data_path.is_file():
        raise FileNotFoundError(f"missing preregistered cohort file: {data_path}")
    adata = ad.read_h5ad(data_path)

    # Keep dataset-native labels at the I/O boundary, then replace them with
    # opaque analysis labels.  Outcome code sees only reference/contrast.
    extraction = adata.uns.get("bionexus_extraction", {})
    loader = (
        validate_preaggregated_pseudobulk
        if extraction.get("aggregation_level") == "donor_condition_pseudobulk"
        else aggregate_pseudobulk
    )
    counts, design, audit = loader(
        adata,
        donor_column=spec["donor_column"],
        condition_column=spec["condition_column"],
        cohort_id=spec["cohort_id"],
        reference_level=spec["reference_level"],
        contrast_level=spec["contrast_level"],
        minimum_paired_donors=int(spec["minimum_paired_donors"]),
        minimum_cells_per_sample=int(prereg["input_gates"]["minimum_cells_per_pseudobulk_sample"]),
    )
    if not design.empty:
        design["condition"] = design["condition"].map(
            {spec["reference_level"]: "reference", spec["contrast_level"]: "contrast"}
        )
    return data_path, counts, design, audit


def _top_signature(de: pd.DataFrame, top_n: int) -> tuple[list[str], pd.Series]:
    ranked = de.loc[np.isfinite(de["log2FoldChange"])].sort_values(["padj", "gene"], na_position="last")
    genes = ranked.head(top_n).index.astype(str).tolist()
    return genes, ranked["log2FoldChange"]


def _donor_holdout(
    counts: pd.DataFrame,
    design: pd.DataFrame,
    donor_effects: pd.DataFrame,
    endpoint: dict[str, Any],
    top_n: int,
) -> dict[str, Any]:
    fold_records: list[dict[str, Any]] = []
    for donor in sorted(design["donor"].astype(str).unique()):
        train_design = design.loc[design["donor"].astype(str) != donor].copy()
        train_counts = counts.loc[train_design["sample_id"]]
        try:
            train_de = _run_de(train_counts, train_design)
            genes, expected = _top_signature(train_de, top_n)
            concordance, n_evaluable = direction_concordance(donor_effects.loc[donor], expected, genes)
            passed = bool(
                concordance is not None
                and n_evaluable >= int(endpoint["minimum_evaluable_genes_per_fold"])
                and concordance >= float(endpoint["minimum_median_concordance"])
            )
            fold_records.append(
                {
                    "held_out_donor": donor,
                    "training_donors": int(train_design["donor"].nunique()),
                    "n_evaluable_genes": n_evaluable,
                    "direction_concordance": concordance,
                    "passed": passed,
                    "error": None,
                }
            )
        except Exception as exc:
            fold_records.append(
                {
                    "held_out_donor": donor,
                    "training_donors": int(train_design["donor"].nunique()),
                    "n_evaluable_genes": 0,
                    "direction_concordance": None,
                    "passed": False,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )

    valid = [float(record["direction_concordance"]) for record in fold_records if record["direction_concordance"] is not None]
    median = float(np.median(valid)) if valid else None
    passing_fraction = float(np.mean([record["passed"] for record in fold_records])) if fold_records else 0.0
    passed = bool(
        median is not None
        and median >= float(endpoint["minimum_median_concordance"])
        and passing_fraction >= float(endpoint["minimum_passing_fold_fraction"])
    )
    return {
        "metric": endpoint["metric"],
        "folds": fold_records,
        "median_direction_concordance": median,
        "passing_fold_fraction": passing_fraction,
        "thresholds": {
            "minimum_evaluable_genes_per_fold": endpoint["minimum_evaluable_genes_per_fold"],
            "minimum_median_concordance": endpoint["minimum_median_concordance"],
            "minimum_passing_fold_fraction": endpoint["minimum_passing_fold_fraction"],
        },
        "passed": passed,
    }


def _abstain_report(prereg: dict[str, Any], prereg_issues: list[str], errors: list[str]) -> dict[str, Any]:
    return {
        "schema_version": "bionexus.pseudobulk-independent-report.v1",
        "study_id": prereg.get("study_id", "unknown"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": {
            "run_status": "ABSTAIN",
            "conclusion_maturity": "ABSTAIN",
            "independent_biological_validation": "not_evaluated",
        },
        "preregistration_issues": prereg_issues,
        "errors": errors,
        "negative_results": [],
        "claim_boundary": prereg.get("claim_boundary", {}),
    }


def run(root: Path = DEFAULT_ROOT) -> dict[str, Any]:
    EXECUTION_WARNINGS.clear()
    freeze_path = root / "NEGATIVE_RESULT_FREEZE.json"
    if freeze_path.is_file():
        raise RuntimeError(
            f"refusing to overwrite frozen study at {root}; create a successor study directory"
        )
    prereg_path = root / "PREREGISTRATION.json"
    lock_path = root / "PREREGISTRATION_LOCK.json"
    prereg = _load_json(prereg_path)
    lock = _load_json(lock_path)
    prereg_issues = validate_preregistration(prereg, lock, prereg_path)
    report_path = root / "REPORT.json"
    if prereg_issues:
        report = _abstain_report(prereg, prereg_issues, [])
        _write_json(report_path, report)
        return report

    cohort_payloads: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    input_files: list[Path] = [prereg_path, lock_path]
    for spec in prereg["cohorts"]:
        try:
            data_path, counts, design, audit = _cohort_data(spec, prereg)
            input_files.append(data_path)
            cohort_payloads[spec["cohort_id"]] = {
                "spec": spec,
                "path": data_path,
                "counts": counts,
                "design": design,
                "audit": audit,
                "donor_effects": donor_log2_fold_changes(
                    counts,
                    design,
                    reference_level="reference",
                    contrast_level="contrast",
                ),
            }
            errors.extend(f"{spec['cohort_id']}: {issue}" for issue in audit.issues)
        except Exception as exc:
            errors.append(f"{spec['cohort_id']}: {type(exc).__name__}: {exc}")

    if errors or len(cohort_payloads) != len(prereg["cohorts"]):
        report = _abstain_report(prereg, [], errors)
        report["cohort_audits"] = {
            cohort_id: payload["audit"].to_dict() for cohort_id, payload in cohort_payloads.items()
        }
        _write_json(report_path, report)
        return report

    discovery = next(payload for payload in cohort_payloads.values() if payload["spec"]["role"] == "discovery_and_donor_holdout")
    platform = next(payload for payload in cohort_payloads.values() if payload["spec"]["role"] == "independent_platform_holdout")
    distinct_sources = discovery["spec"]["source"] != platform["spec"]["source"]
    distinct_platforms = discovery["spec"]["platform_family"] != platform["spec"]["platform_family"]

    discovery_de = _run_de(discovery["counts"], discovery["design"])
    platform_de = _run_de(platform["counts"], platform["design"])
    top_n = int(prereg["primary_endpoints"]["discovery_top_n"])
    signature_genes, signature_direction = _top_signature(discovery_de, top_n)

    donor_holdout = _donor_holdout(
        discovery["counts"],
        discovery["design"],
        discovery["donor_effects"],
        prereg["primary_endpoints"]["donor_leave_one_out"],
        top_n,
    )

    platform_endpoint = prereg["primary_endpoints"]["platform_holdout"]
    platform_concordance, platform_evaluable = direction_concordance(
        platform_de["log2FoldChange"], signature_direction, signature_genes
    )
    platform_passed = bool(
        platform_concordance is not None
        and platform_evaluable >= int(platform_endpoint["minimum_evaluable_genes"])
        and platform_concordance >= float(platform_endpoint["minimum_concordance"])
    )
    platform_holdout = {
        "metric": platform_endpoint["metric"],
        "n_evaluable_genes": platform_evaluable,
        "direction_concordance": platform_concordance,
        "thresholds": {
            "minimum_evaluable_genes": platform_endpoint["minimum_evaluable_genes"],
            "minimum_concordance": platform_endpoint["minimum_concordance"],
        },
        "passed": platform_passed,
    }

    multi_endpoint = prereg["primary_endpoints"]["multi_cohort"]
    discovery_median = discovery["donor_effects"].median(axis=0)
    platform_median = platform["donor_effects"].median(axis=0)
    multi_concordance, multi_evaluable = direction_concordance(platform_median, discovery_median, signature_genes)
    multi_passed = bool(
        multi_concordance is not None and multi_concordance >= float(multi_endpoint["minimum_fraction"])
    )
    multi_cohort = {
        "metric": multi_endpoint["metric"],
        "n_evaluable_genes": multi_evaluable,
        "consistent_direction_fraction": multi_concordance,
        "minimum_fraction": multi_endpoint["minimum_fraction"],
        "passed": multi_passed,
    }

    null_endpoint = prereg["primary_endpoints"]["negative_control"]
    if null_endpoint["method"] == "paired_donor_condition_label_exact_sign_flip":
        null_observed, empirical_p, null_scores = exact_sign_flip_empirical_p_value(
            platform["donor_effects"], signature_direction, signature_genes
        )
        expected_sign_flips = (2 ** platform["donor_effects"].shape[0]) - 1
        if len(null_scores) != expected_sign_flips:
            raise RuntimeError(
                f"exact sign-flip count mismatch: expected {expected_sign_flips}, observed {len(null_scores)}"
            )
    else:
        null_observed, empirical_p, null_scores = sign_flip_empirical_p_value(
            platform["donor_effects"],
            signature_direction,
            signature_genes,
            permutations=int(null_endpoint["permutations"]),
            seed=int(null_endpoint["seed"]),
        )
    null_passed = bool(empirical_p is not None and empirical_p <= float(null_endpoint["maximum_empirical_p_value"]))
    negative_control = {
        "method": null_endpoint["method"],
        "observed_direction_concordance": null_observed,
        "empirical_p_value": empirical_p,
        "permutations_executed": len(null_scores),
        "enumeration": "all_nonidentity_assignments" if null_endpoint["method"].endswith("exact_sign_flip") else "sampled",
        "null_median": float(np.median(null_scores)) if null_scores else None,
        "null_95th_percentile": float(np.quantile(null_scores, 0.95)) if null_scores else None,
        "maximum_empirical_p_value": null_endpoint["maximum_empirical_p_value"],
        "passed": null_passed,
    }

    endpoints = {
        "donor_leave_one_out": donor_holdout,
        "platform_holdout": platform_holdout,
        "multi_cohort": multi_cohort,
        "negative_control": negative_control,
    }
    endpoints_passed = all(endpoint["passed"] for endpoint in endpoints.values())
    attestation_path = REPO_ROOT / prereg["blinding"]["attestation_path"]
    independent_blinding_attested = attestation_path.is_file()
    full_cohorts_used = not any(payload["spec"]["is_documented_subsample"] for payload in cohort_payloads.values())
    status = independent_claim_status(
        input_gates_passed=distinct_sources and distinct_platforms,
        endpoints_passed=endpoints_passed,
        full_cohorts_used=full_cohorts_used,
        independent_blinding_attested=independent_blinding_attested,
    )

    evidence_dir = root / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    signature_table = discovery_de.loc[signature_genes, ["gene", "log2FoldChange", "pvalue", "padj"]].copy()
    signature_table["platform_log2FoldChange"] = platform_de.reindex(signature_genes)["log2FoldChange"]
    signature_table["direction_concordant"] = (
        np.sign(signature_table["log2FoldChange"]) == np.sign(signature_table["platform_log2FoldChange"])
    )
    signature_path = evidence_dir / "locked_discovery_signature_platform_holdout.csv"
    signature_table.to_csv(signature_path, index=False)
    folds_path = evidence_dir / "donor_leave_one_out_folds.csv"
    pd.DataFrame(donor_holdout["folds"]).to_csv(folds_path, index=False)
    null_path = evidence_dir / "negative_control_sign_flip_null.csv"
    pd.DataFrame(
        {
            "permutation_index": np.arange(1, len(null_scores) + 1),
            "direction_concordance": null_scores,
        }
    ).to_csv(null_path, index=False)

    provenance_path = root / "PROVENANCE.json"
    provenance = sidecar(
        activity_name="preregistered_pseudobulk_independent_validation",
        input_files=input_files
        + [REPO_ROOT / "evals" / "pseudobulk_independent_validation.py", REPO_ROOT / "src" / "bionexus" / "independent_pseudobulk.py"],
        output_files=[signature_path, folds_path, null_path],
        parameters=prereg["primary_endpoints"],
        method="donor-aware pseudobulk PyDESeq2 with leave-one-donor and platform holdout",
        backend="scanpy/anndata + pydeseq2",
    )
    _write_json(provenance_path, provenance)

    negative_results = [name for name, endpoint in endpoints.items() if not endpoint["passed"]]
    limitations = [
        "C01 uses IFN-beta at 6 h whereas C02 uses IFN-gamma at 24 h; the endpoint is shared interferon-response reproducibility, not identical ligand-specific biology.",
        "C02 is a documented 10K-cell subsample of the Parse 10M atlas; it is suitable for executable acceptance but caps maturity at PRELIMINARY.",
        "Opaque cohort IDs and locked thresholds provide workflow blinding only; no independent analyst attestation is present unless separately supplied.",
        "Donor overlap is excluded by independent study provenance, not by identity linkage across de-identified public cohorts.",
        "This evaluates technical-biological reproducibility, not clinical validity, causality, or method superiority.",
    ]
    report = {
        "schema_version": "bionexus.pseudobulk-independent-report.v1",
        "study_id": prereg["study_id"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "preregistration": {
            "path": str(prereg_path.relative_to(REPO_ROOT).as_posix()),
            "sha256": file_sha256(prereg_path),
            "lock_path": str(lock_path.relative_to(REPO_ROOT).as_posix()),
            "lock_strength": lock["lock_strength"],
            "thresholds_changed_after_lock": False,
        },
        "cohort_audits": {
            cohort_id: {
                **payload["audit"].to_dict(),
                "dataset_id": payload["spec"]["dataset_id"],
                "role": payload["spec"]["role"],
                "platform_family": payload["spec"]["platform_family"],
                "is_documented_subsample": payload["spec"]["is_documented_subsample"],
                "input_sha256": file_sha256(payload["path"]),
            }
            for cohort_id, payload in cohort_payloads.items()
        },
        "independence_gates": {
            "distinct_dataset_sources": distinct_sources,
            "distinct_platform_families": distinct_platforms,
            "declared_no_donor_overlap": distinct_sources,
            "full_cohorts_used": full_cohorts_used,
            "independent_blinding_attested": independent_blinding_attested,
        },
        "endpoints": endpoints,
        "status": status,
        "negative_results": negative_results,
        "abstentions": [
            reason
            for reason, active in (
                ("full independent biological validation abstained: platform cohort is a documented subsample", not full_cohorts_used),
                ("independent-blinded claim abstained: reviewer/analyst attestation is absent", not independent_blinding_attested),
            )
            if active
        ],
        "evidence_files": [
            str(signature_path.relative_to(REPO_ROOT).as_posix()),
            str(folds_path.relative_to(REPO_ROOT).as_posix()),
            str(null_path.relative_to(REPO_ROOT).as_posix()),
            str(provenance_path.relative_to(REPO_ROOT).as_posix()),
        ],
        "execution_warnings": list(EXECUTION_WARNINGS),
        "limitations": limitations,
        "claim_boundary": prereg["claim_boundary"],
    }
    _write_json(report_path, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    args = parser.parse_args()
    report = run(args.root)
    print(json.dumps(report["status"], indent=2))
    return 0 if report["status"]["run_status"] != "ABSTAIN" else 2


if __name__ == "__main__":
    raise SystemExit(main())
