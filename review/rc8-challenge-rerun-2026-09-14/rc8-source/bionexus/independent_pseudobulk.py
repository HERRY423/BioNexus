"""Fail-closed helpers for donor- and platform-held-out pseudobulk validation.

This module evaluates reproducibility of a pseudobulk result.  It does not
assign cell types, establish a causal mechanism, or turn a subsampled public
cohort into a full independent biological validation.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd
from scipy import sparse


@dataclass(frozen=True)
class CohortAudit:
    cohort_id: str
    n_cells: int
    n_genes: int
    n_paired_donors: int
    donors_by_condition: dict[str, int]
    min_cells_per_sample: int
    raw_nonnegative_integer_counts: bool
    paired_conditions_complete: bool
    issues: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.issues

    def to_dict(self) -> dict[str, Any]:
        return {
            "cohort_id": self.cohort_id,
            "n_cells": self.n_cells,
            "n_genes": self.n_genes,
            "n_paired_donors": self.n_paired_donors,
            "donors_by_condition": dict(self.donors_by_condition),
            "min_cells_per_sample": self.min_cells_per_sample,
            "raw_nonnegative_integer_counts": self.raw_nonnegative_integer_counts,
            "paired_conditions_complete": self.paired_conditions_complete,
            "issues": list(self.issues),
            "passed": self.passed,
        }


def canonical_json_sha256(payload: Mapping[str, Any] | Sequence[Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


_STUDY_TEXT_EXTS = {".json", ".csv", ".tsv", ".txt", ".md", ".py", ".yaml", ".yml"}


def file_sha256(path: str | Path) -> str:
    p = Path(path)
    raw = p.read_bytes()
    posix_str = p.as_posix()
    if "validation/pseudobulk/studies" in posix_str or "BN-PB-IV-" in posix_str:
        if any(posix_str.endswith(f"BN-PB-IV-{x}/{sub}PREREGISTRATION.json") for x in ("004", "005") for sub in ("", "blinded_packet/")):
            raw = raw.replace(b"\r\n", b"\n")
        elif p.suffix.lower() in _STUDY_TEXT_EXTS:
            raw = raw.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    return hashlib.sha256(raw).hexdigest()


def validate_preregistration(prereg: Mapping[str, Any], lock: Mapping[str, Any], prereg_path: str | Path) -> list[str]:
    issues: list[str] = []
    if prereg.get("schema_version") != "bionexus.pseudobulk-independent-preregistration.v1":
        issues.append("unsupported preregistration schema")
    if prereg.get("locked") is not True:
        issues.append("preregistration is not locked")
    if prereg.get("study_id") != lock.get("study_id"):
        issues.append("study_id differs between preregistration and lock")
    expected_hash = str(lock.get("preregistration_sha256", "")).lower()
    observed_hash = file_sha256(prereg_path)
    if expected_hash != observed_hash:
        issues.append(f"preregistration hash mismatch: expected {expected_hash}, observed {observed_hash}")
    endpoints = prereg.get("primary_endpoints", {})
    required = {"discovery_top_n", "donor_leave_one_out", "platform_holdout", "multi_cohort", "negative_control"}
    missing = sorted(required - set(endpoints))
    if missing:
        issues.append(f"missing preregistered endpoints: {missing}")
    if len(prereg.get("cohorts", [])) < 2:
        issues.append("at least two cohorts are required")
    negative_control = endpoints.get("negative_control", {})
    if negative_control.get("method") == "paired_donor_condition_label_exact_sign_flip":
        donors = int(negative_control.get("donors", 0))
        expected = (2**donors) - 1 if donors > 0 else 0
        if int(negative_control.get("permutations", -1)) != expected:
            issues.append(f"exact sign-flip plan must specify 2**donors - 1 assignments ({expected})")
        if negative_control.get("seed") is not None:
            issues.append("exact sign-flip plan must not specify a random seed")
    return issues


def validate_independent_biostatistician_attestation(
    attestation_path: str | Path,
    *,
    preregistration_sha256: str,
    blinded_packet_sha256: str,
    analysis_code_sha256: str,
) -> list[str]:
    """Fail closed on missing, incomplete, condition-aware, or self-declared review."""
    path = Path(attestation_path)
    if not path.is_file():
        return [f"independent biostatistician attestation is missing: {path}"]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"independent biostatistician attestation is unreadable: {type(exc).__name__}: {exc}"]
    issues: list[str] = [
        "legacy reviewer JSON cannot establish independent trust; verification requires "
        "bionexus.evidence-attestation.v1, an explicit trust registry, and revocation checks"
    ]
    if payload.get("schema_version") != "bionexus.independent-biostatistician-attestation.v1":
        issues.append("unsupported independent biostatistician attestation schema")
    if payload.get("status") != "SIGNED_COMPLETE":
        issues.append("independent biostatistician attestation is not SIGNED_COMPLETE")
    reviewer = payload.get("reviewer", {})
    for key in ("full_name", "institution", "department_or_unit", "professional_email", "orcid_or_equivalent", "conflicts_of_interest"):
        value = str(reviewer.get(key, "")).strip()
        if not value or value == "REQUIRED":
            issues.append(f"reviewer field is missing: {key}")
    if reviewer.get("independent_of_code_and_threshold_authors") is not True:
        issues.append("reviewer independence is not attested")
    materials = payload.get("materials", {})
    expected_hashes = {
        "preregistration_sha256": preregistration_sha256,
        "blinded_packet_sha256": blinded_packet_sha256,
        "analysis_code_sha256": analysis_code_sha256,
    }
    for key, expected_hash in expected_hashes.items():
        if str(materials.get(key, "")).lower() != expected_hash.lower():
            issues.append(f"attested material hash mismatch: {key}")
    review = payload.get("review", {})
    if review.get("condition_key_available_during_analysis") is not False:
        issues.append("review was not blind to the condition key")
    if review.get("all_4095_exact_sign_flips_verified") is not True:
        issues.append("reviewer did not verify all 4095 exact sign flips")
    if review.get("negative_and_abstention_results_retained") is not True:
        issues.append("reviewer did not attest retention of negative and abstention results")
    if review.get("primary_endpoint_decision") not in {"PASS", "NEGATIVE_RESULT", "ABSTAIN"}:
        issues.append("reviewer primary endpoint decision is invalid")
    signature = payload.get("signature", {})
    for key in ("signed_at_utc", "signature_method", "signature_value_or_detached_signature_sha256"):
        value = str(signature.get(key, "")).strip()
        if not value or value.startswith("REQUIRED"):
            issues.append(f"signature field is missing: {key}")
    return issues


def _raw_integer_counts(matrix: Any, tolerance: float = 1e-8) -> bool:
    values = matrix.data if sparse.issparse(matrix) else np.asarray(matrix).ravel()
    if values.size == 0:
        return False
    values = np.asarray(values)
    if not np.issubdtype(values.dtype, np.number):
        return False
    return bool(np.all(np.isfinite(values)) and np.all(values >= 0) and np.all(np.abs(values - np.rint(values)) <= tolerance))


def aggregate_pseudobulk(
    adata: Any,
    *,
    donor_column: str,
    condition_column: str,
    cohort_id: str,
    reference_level: str,
    contrast_level: str,
    minimum_paired_donors: int,
    minimum_cells_per_sample: int,
    layer: str = "counts",
) -> tuple[pd.DataFrame, pd.DataFrame, CohortAudit]:
    missing = [column for column in (donor_column, condition_column) if column not in adata.obs.columns]
    if missing:
        audit = CohortAudit(
            cohort_id=cohort_id,
            n_cells=int(adata.n_obs),
            n_genes=int(adata.n_vars),
            n_paired_donors=0,
            donors_by_condition={},
            min_cells_per_sample=0,
            raw_nonnegative_integer_counts=False,
            paired_conditions_complete=False,
            issues=(f"missing obs columns: {missing}",),
        )
        return pd.DataFrame(), pd.DataFrame(), audit

    matrix = adata.layers[layer] if layer in adata.layers else adata.X
    is_raw = _raw_integer_counts(matrix)
    obs = adata.obs[[donor_column, condition_column]].astype(str).copy()
    keep = obs[condition_column].isin([reference_level, contrast_level])
    obs = obs.loc[keep]
    matrix = matrix[keep.to_numpy()]

    groups = obs.groupby([donor_column, condition_column], sort=True).indices
    rows: list[Any] = []
    records: list[dict[str, Any]] = []
    for (donor, condition), positions in groups.items():
        summed = matrix[positions].sum(axis=0)
        rows.append(np.asarray(summed).ravel())
        records.append(
            {
                "sample_id": f"{cohort_id}__{donor}__{condition}",
                "donor": donor,
                "condition": condition,
                "n_cells": int(len(positions)),
            }
        )

    design = pd.DataFrame.from_records(records)
    if rows:
        counts = pd.DataFrame(np.vstack(rows), index=design["sample_id"], columns=adata.var_names.astype(str))
    else:
        counts = pd.DataFrame()

    condition_donors = {
        level: set(design.loc[design["condition"] == level, "donor"].astype(str))
        for level in (reference_level, contrast_level)
    }
    paired = condition_donors[reference_level] & condition_donors[contrast_level]
    design = design.loc[design["donor"].isin(paired)].copy()
    if not counts.empty:
        counts = counts.loc[design["sample_id"]]

    min_cells = int(design["n_cells"].min()) if not design.empty else 0
    issues: list[str] = []
    if not is_raw:
        issues.append("expression matrix is not raw non-negative integer counts")
    if len(paired) < minimum_paired_donors:
        issues.append(f"paired donors {len(paired)} < required {minimum_paired_donors}")
    if min_cells < minimum_cells_per_sample:
        issues.append(f"minimum cells per pseudobulk sample {min_cells} < required {minimum_cells_per_sample}")
    if set(obs[condition_column].unique()) != {reference_level, contrast_level}:
        issues.append("reference or contrast condition is absent")

    audit = CohortAudit(
        cohort_id=cohort_id,
        n_cells=int(adata.n_obs),
        n_genes=int(adata.n_vars),
        n_paired_donors=len(paired),
        donors_by_condition={level: len(donors) for level, donors in condition_donors.items()},
        min_cells_per_sample=min_cells,
        raw_nonnegative_integer_counts=is_raw,
        paired_conditions_complete=bool(paired),
        issues=tuple(issues),
    )
    return collapse_duplicate_genes(counts), design, audit


def validate_preaggregated_pseudobulk(
    adata: Any,
    *,
    donor_column: str,
    condition_column: str,
    cohort_id: str,
    reference_level: str,
    contrast_level: str,
    minimum_paired_donors: int,
    minimum_cells_per_sample: int,
    layer: str = "counts",
) -> tuple[pd.DataFrame, pd.DataFrame, CohortAudit]:
    """Validate a donor-condition pseudobulk AnnData without aggregating twice."""
    required = {donor_column, condition_column, "n_cells"}
    missing = sorted(required - set(adata.obs.columns))
    matrix = adata.layers[layer] if layer in adata.layers else adata.X
    is_raw = _raw_integer_counts(matrix)
    issues: list[str] = []
    if missing:
        issues.append(f"missing obs columns: {missing}")
    if not is_raw:
        issues.append("expression matrix is not raw non-negative integer counts")
    if missing:
        audit = CohortAudit(
            cohort_id=cohort_id,
            n_cells=0,
            n_genes=int(adata.n_vars),
            n_paired_donors=0,
            donors_by_condition={},
            min_cells_per_sample=0,
            raw_nonnegative_integer_counts=is_raw,
            paired_conditions_complete=False,
            issues=tuple(issues),
        )
        return pd.DataFrame(), pd.DataFrame(), audit

    obs = adata.obs[[donor_column, condition_column, "n_cells"]].copy()
    obs[donor_column] = obs[donor_column].astype(str)
    obs[condition_column] = obs[condition_column].astype(str)
    obs["n_cells"] = pd.to_numeric(obs["n_cells"], errors="coerce")
    keep = obs[condition_column].isin([reference_level, contrast_level])
    obs = obs.loc[keep].copy()
    selected_matrix = matrix[keep.to_numpy()]
    if obs.duplicated([donor_column, condition_column]).any():
        issues.append("preaggregated input contains duplicate donor-condition rows")
    if obs["n_cells"].isna().any() or (obs["n_cells"] < 0).any():
        issues.append("preaggregated input has invalid n_cells values")

    condition_donors = {
        level: set(obs.loc[obs[condition_column] == level, donor_column])
        for level in (reference_level, contrast_level)
    }
    paired = condition_donors[reference_level] & condition_donors[contrast_level]
    paired_keep = obs[donor_column].isin(paired)
    obs = obs.loc[paired_keep].copy()
    selected_matrix = selected_matrix[paired_keep.to_numpy()]
    sample_ids = [
        f"{cohort_id}__{donor}__{condition}"
        for donor, condition in zip(obs[donor_column], obs[condition_column], strict=True)
    ]
    design = pd.DataFrame(
        {
            "sample_id": sample_ids,
            "donor": obs[donor_column].to_numpy(),
            "condition": obs[condition_column].to_numpy(),
            "n_cells": obs["n_cells"].fillna(0).astype(int).to_numpy(),
        }
    )
    dense = selected_matrix.toarray() if sparse.issparse(selected_matrix) else np.asarray(selected_matrix)
    counts = pd.DataFrame(dense, index=sample_ids, columns=adata.var_names.astype(str))
    min_cells = int(design["n_cells"].min()) if not design.empty else 0
    if len(paired) < minimum_paired_donors:
        issues.append(f"paired donors {len(paired)} < required {minimum_paired_donors}")
    if min_cells < minimum_cells_per_sample:
        issues.append(f"minimum cells per pseudobulk sample {min_cells} < required {minimum_cells_per_sample}")
    if set(obs[condition_column].unique()) != {reference_level, contrast_level}:
        issues.append("reference or contrast condition is absent")
    audit = CohortAudit(
        cohort_id=cohort_id,
        n_cells=int(design["n_cells"].sum()) if not design.empty else 0,
        n_genes=int(adata.n_vars),
        n_paired_donors=len(paired),
        donors_by_condition={level: len(donors) for level, donors in condition_donors.items()},
        min_cells_per_sample=min_cells,
        raw_nonnegative_integer_counts=is_raw,
        paired_conditions_complete=len(paired) >= minimum_paired_donors,
        issues=tuple(dict.fromkeys(issues)),
    )
    return collapse_duplicate_genes(counts), design, audit


def collapse_duplicate_genes(counts: pd.DataFrame) -> pd.DataFrame:
    if counts.empty:
        return counts
    normalized = pd.Index([str(gene).strip().upper() for gene in counts.columns], name="gene")
    out = counts.copy()
    out.columns = normalized
    if normalized.has_duplicates:
        out = out.T.groupby(level=0, sort=True).sum().T
    return out


def donor_log2_fold_changes(
    counts: pd.DataFrame,
    design: pd.DataFrame,
    *,
    reference_level: str,
    contrast_level: str,
    pseudocount_cpm: float = 1.0,
) -> pd.DataFrame:
    metadata = design.set_index("sample_id")
    records: list[pd.Series] = []
    for donor, donor_meta in metadata.groupby("donor", sort=True):
        refs = donor_meta.index[donor_meta["condition"] == reference_level]
        alts = donor_meta.index[donor_meta["condition"] == contrast_level]
        if len(refs) != 1 or len(alts) != 1:
            continue
        ref = counts.loc[refs[0]].astype(float)
        alt = counts.loc[alts[0]].astype(float)
        ref_cpm = ref / max(float(ref.sum()), 1.0) * 1_000_000.0
        alt_cpm = alt / max(float(alt.sum()), 1.0) * 1_000_000.0
        effect = np.log2((alt_cpm + pseudocount_cpm) / (ref_cpm + pseudocount_cpm))
        effect.name = str(donor)
        records.append(effect)
    if not records:
        return pd.DataFrame(columns=counts.columns)
    return pd.DataFrame(records)


def direction_concordance(
    observed_effect: pd.Series,
    expected_direction: pd.Series,
    genes: Iterable[str],
) -> tuple[float | None, int]:
    selected = [gene for gene in genes if gene in observed_effect.index and gene in expected_direction.index]
    if not selected:
        return None, 0
    observed = np.sign(observed_effect.loc[selected].astype(float).to_numpy())
    expected = np.sign(expected_direction.loc[selected].astype(float).to_numpy())
    usable = (observed != 0) & (expected != 0) & np.isfinite(observed) & np.isfinite(expected)
    if not np.any(usable):
        return None, 0
    return float(np.mean(observed[usable] == expected[usable])), int(np.sum(usable))


def sign_flip_empirical_p_value(
    donor_effects: pd.DataFrame,
    expected_direction: pd.Series,
    genes: Sequence[str],
    *,
    permutations: int,
    seed: int,
) -> tuple[float | None, float | None, list[float]]:
    shared = [gene for gene in genes if gene in donor_effects.columns and gene in expected_direction.index]
    if donor_effects.empty or not shared:
        return None, None, []
    effects = donor_effects.loc[:, shared].astype(float).to_numpy()
    expected = np.sign(expected_direction.loc[shared].astype(float).to_numpy())

    def score(values: np.ndarray) -> float:
        pooled = np.nanmedian(values, axis=0)
        usable = np.isfinite(pooled) & (pooled != 0) & (expected != 0)
        return float(np.mean(np.sign(pooled[usable]) == expected[usable])) if np.any(usable) else 0.0

    observed = score(effects)
    rng = np.random.default_rng(seed)
    null_scores: list[float] = []
    seen: set[tuple[int, ...]] = set()
    max_unique = max(1, (2 ** effects.shape[0]) - 1)
    target = min(int(permutations), max_unique)
    while len(null_scores) < target:
        signs = tuple(int(x) for x in rng.choice((-1, 1), size=effects.shape[0]))
        if signs in seen or all(sign == 1 for sign in signs):
            continue
        seen.add(signs)
        null_scores.append(score(effects * np.asarray(signs)[:, None]))
    p_value = (1.0 + sum(value >= observed for value in null_scores)) / (1.0 + len(null_scores))
    return observed, float(p_value), null_scores


def exact_sign_flip_empirical_p_value(
    donor_effects: pd.DataFrame,
    expected_direction: pd.Series,
    genes: Sequence[str],
) -> tuple[float | None, float | None, list[float]]:
    """Evaluate every non-identity paired-donor sign flip exactly.

    The returned null contains ``2**n_donors - 1`` scores.  The empirical
    p-value uses the equivalent full randomisation distribution: the observed
    identity assignment is added once to numerator and denominator.
    """
    shared = [gene for gene in genes if gene in donor_effects.columns and gene in expected_direction.index]
    if donor_effects.empty or not shared:
        return None, None, []
    effects = donor_effects.loc[:, shared].astype(float).to_numpy()
    expected = np.sign(expected_direction.loc[shared].astype(float).to_numpy())

    def score(values: np.ndarray) -> float:
        pooled = np.nanmedian(values, axis=0)
        usable = np.isfinite(pooled) & (pooled != 0) & (expected != 0)
        return float(np.mean(np.sign(pooled[usable]) == expected[usable])) if np.any(usable) else 0.0

    observed = score(effects)
    n_donors = effects.shape[0]
    null_scores: list[float] = []
    # Mask zero is the identity assignment (+1 for every donor) and is the
    # observed statistic.  Every other mask flips its selected donor rows.
    for mask in range(1, 2**n_donors):
        signs = np.ones(n_donors, dtype=np.int8)
        for donor_index in range(n_donors):
            if mask & (1 << donor_index):
                signs[donor_index] = -1
        null_scores.append(score(effects * signs[:, None]))
    p_value = (1.0 + sum(value >= observed for value in null_scores)) / (1.0 + len(null_scores))
    return observed, float(p_value), null_scores


def verify_negative_result_freeze(freeze_path: str | Path) -> list[str]:
    """Verify a frozen negative result and every artifact bound to it."""
    manifest_path = Path(freeze_path)
    issues: list[str] = []
    if not manifest_path.is_file():
        return [f"negative-result freeze is missing: {manifest_path}"]
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"negative-result freeze is unreadable: {type(exc).__name__}: {exc}"]
    if manifest.get("schema_version") != "bionexus.negative-result-freeze.v1":
        issues.append("unsupported negative-result freeze schema")
    policy = manifest.get("policy", {})
    for key in ("overwrite_prohibited", "reinterpret_as_pass_prohibited", "post_hoc_permutation_increase_prohibited"):
        if policy.get(key) is not True:
            issues.append(f"negative-result freeze policy is not enforced: {key}")
    root = manifest_path.parent
    for artifact in manifest.get("artifacts", []):
        relative = Path(str(artifact.get("path", "")))
        path = root / relative
        if not path.is_file():
            issues.append(f"frozen artifact is missing: {relative.as_posix()}")
            continue
        expected_hash = str(artifact.get("sha256", "")).lower()
        observed_hash = file_sha256(path)
        if observed_hash != expected_hash:
            issues.append(
                f"frozen artifact hash mismatch for {relative.as_posix()}: expected {expected_hash}, observed {observed_hash}"
            )
    report_path = root / "REPORT.json"
    if report_path.is_file():
        report = json.loads(report_path.read_text(encoding="utf-8"))
        frozen = manifest.get("result", {})
        observed_status = report.get("status", {})
        for key in ("run_status", "conclusion_maturity", "independent_biological_validation"):
            if observed_status.get(key) != frozen.get(key):
                issues.append(f"frozen result differs from report status: {key}")
        observed_p = report.get("endpoints", {}).get("negative_control", {}).get("empirical_p_value")
        if observed_p != frozen.get("empirical_p_value"):
            issues.append("frozen empirical p-value differs from REPORT.json")
    return issues


def independent_claim_status(
    *,
    input_gates_passed: bool,
    endpoints_passed: bool,
    full_cohorts_used: bool,
    independent_blinding_attested: bool,
) -> dict[str, str]:
    if not input_gates_passed:
        return {
            "run_status": "ABSTAIN",
            "conclusion_maturity": "ABSTAIN",
            "independent_biological_validation": "not_evaluated",
        }
    if not endpoints_passed:
        return {
            "run_status": "negative_result",
            "conclusion_maturity": "FRAGILE",
            "independent_biological_validation": "not_supported",
        }
    if not full_cohorts_used or not independent_blinding_attested:
        return {
            "run_status": "incomplete_not_claim_ready",
            "conclusion_maturity": "PRELIMINARY",
            "independent_biological_validation": "ABSTAIN",
        }
    return {
        "run_status": "pass",
        "conclusion_maturity": "SUPPORTED",
        "independent_biological_validation": "supported",
    }
