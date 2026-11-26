"""Reconstruct the donor-level comparison supported by observed metadata."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from bionexus.de.conditions import contrast_diagnostics


def resolve_replicate_scope(*, table: pd.DataFrame | None, obs: pd.DataFrame | None,
                            ct_col: str | None, c_col: str | None, cell_type: str | None,
                            case: str | None, reference: str | None, contract: bool,
                            rgg: dict[str, Any] | None) -> tuple[dict[str, Any], pd.DataFrame | None]:
    """Identify the cell populations to which the supplied result can be attributed."""
    def labels(series: pd.Series) -> list[str]:
        return sorted({v for v in series.dropna().astype(str) if v.strip()})

    observed = labels(obs[ct_col]) if obs is not None and ct_col else []
    rows = table
    if rows is not None and case is not None:
        for col, target in (("numerator", case), ("denominator", reference)):
            if col in rows:
                rows = rows[rows[col].astype("string").eq(str(target)).fillna(False)]
    type_column = "cell_type" if rows is not None and "cell_type" in rows else ct_col
    table_has_types = rows is not None and type_column is not None and type_column in rows
    targets: list[str] = []
    incomplete_labels = False
    if cell_type is not None:
        targets = [cell_type]
        basis = "claim_contract" if contract else "explicit"
        if table_has_types and rows is not None:
            rows = rows[rows[type_column].astype("string").eq(cell_type).fillna(False)]
            incomplete_labels = rows.empty
    elif table_has_types and rows is not None:
        targets = labels(rows[type_column])
        incomplete_labels = rows.empty or rows[type_column].astype("string").str.strip().fillna("").eq("").any()
        basis = "inferred_from_de_table"
    elif (rgg and c_col and rgg.get("groupby") == c_col and len(observed) == 1 and rows is not None
          and obs is not None and ct_col and obs[ct_col].astype("string").str.strip().fillna("").ne("").all()):
        targets, basis = observed, "inferred_from_de_table"
    elif table is None and rgg is None and len(observed) == 1:
        targets, basis = observed, "single_metadata_cell_type"
    elif ct_col is None and obs is not None and not table_has_types:
        basis = "unstratified_metadata"
    else:
        basis = "unspecified"

    ambiguous_contrast = False
    if case is None and rows is not None and not rows.empty and {"numerator", "denominator"} <= set(rows):
        pairs = rows[["numerator", "denominator"]].astype("string").drop_duplicates()
        if len(pairs) == 1 and not pairs.isna().any().any():
            left, right = pairs.iloc[0]
            if left.strip() and right.strip() and left != right:
                case, reference = left, right
        ambiguous_contrast = case is None
    comparable_observed = observed
    if obs is not None and c_col and ct_col and case is not None:
        selected = obs[c_col].astype("string").isin([case, reference])
        comparable_observed = labels(obs.loc[selected, ct_col])
    missing = sorted(set(targets) - set(comparable_observed))
    return {"cell_type": targets[0] if len(targets) == 1 else None, "cell_types": targets,
            "case": case, "reference": reference, "basis": basis,
            "complete": bool((targets or basis == "unstratified_metadata")
                             and not (missing or incomplete_labels or ambiguous_contrast)),
            "ambiguous_contrast": ambiguous_contrast,
            "missing_cell_types": missing, "result_labels_incomplete": bool(incomplete_labels),
            "outside_cell_types": sorted(set(observed) - set(targets))}, rows


def _design(samples: pd.DataFrame, levels: list[str], d_col: str, c_col: str,
            b_col: str | None) -> dict[str, Any]:
    """Use distinct donor/condition/batch observations, never individual cells as replicates."""
    units = samples[[d_col, c_col]].drop_duplicates()
    repeated = units.groupby(d_col, observed=True).size()
    paired = list(repeated[repeated > 1].index)
    out: dict[str, Any] = dict(estimable=None, residual_df=None, batch_in_design=False,
                              paired_donors=paired, n_donor_condition_units=len(units),
                              cramer_v=None)
    if len(levels) < 2 or set(samples[c_col]) != set(levels):
        return out
    if b_col and samples[b_col].isna().any():
        return out

    samples = samples.drop_duplicates().reset_index(drop=True)
    indicators = pd.get_dummies(pd.Categorical(samples[c_col], categories=levels),
                                drop_first=True, dtype=float)
    blocks = [np.ones(len(samples)), indicators.to_numpy()]
    if b_col:
        tab = pd.crosstab(samples[c_col], samples[b_col])
        out["contingency_matrix"] = tab.to_dict()
        if len(tab.columns) > 1:
            freq = tab.to_numpy(dtype=float)
            expected = np.outer(freq.sum(axis=1), freq.sum(axis=0)) / freq.sum()
            chi_sq = np.sum((freq - expected)**2 / expected)
            out["cramer_v"] = float(np.sqrt(chi_sq / (freq.sum() * (min(freq.shape) - 1))))
            blocks.append(pd.get_dummies(samples[b_col], drop_first=True, dtype=float).to_numpy())
            out["batch_in_design"] = True
        else:
            out["cramer_v"] = 0.
    if paired:
        blocks.append(pd.get_dummies(samples[d_col], drop_first=True, dtype=float).to_numpy())
    matrix = np.column_stack(blocks)
    # Without a named comparison, all observed condition differences must be estimable.
    contrasts = np.zeros((len(levels) - 1, matrix.shape[1]))
    contrasts[:, 1:len(levels)] = np.eye(len(levels) - 1)
    diagnostics = [contrast_diagnostics(matrix, c) for c in contrasts]
    # Technical repeats of a donor/condition across batches do not add biological df.
    biological_rank = diagnostics[0]["rank"]
    if len(units) < len(samples):
        biological_matrix = pd.DataFrame(matrix).groupby([samples[d_col], samples[c_col]], observed=True).mean()
        biological_rank = contrast_diagnostics(biological_matrix.to_numpy(), contrasts[0])["rank"]
    biological_df = len(units) - biological_rank
    out.update(estimable=all(d["estimable"] for d in diagnostics), residual_df=biological_df,
               rank=diagnostics[0]["rank"], biological_rank=biological_rank, design_rows=len(matrix))
    return out


def measure_replicate_strata(obs: pd.DataFrame, d_col: str, c_col: str, ct_col: str | None,
                             b_col: str | None, *, min_cells_per_donor: int, rows_are_cells: bool | None,
                             case: str | None, reference: str | None, cell_type: str | None,
                             dominance_threshold: float, included_cell_types: list[str] | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return eligible donor counts, design diagnostics and within-condition dominance."""
    columns = [c for c in (d_col, c_col, ct_col, b_col) if c is not None]
    if rows_are_cells is None:
        # Sample sheets may include technical repeats with distinct sample identifiers.
        sample_ids = [c for c in ("sample_id", "sample") if c in obs and obs[c].notna().all()]
        if any(obs[c].is_unique for c in sample_ids):
            rows_are_cells = False
            basis = "unique_sample_identifiers"
        else:
            rows_are_cells = bool(obs.duplicated(list(dict.fromkeys(columns))).any())
            basis = "repeated_metadata_rows" if rows_are_cells else "one_row_per_sample_stratum"
    else:
        basis = "cell_observations" if rows_are_cells else "sample_sheet"
    # Normalise after retaining missingness so NaNs never become donors or levels named 'nan'.
    # Separate roles even if a metadata column was requested as both condition and batch.
    d_col, c_col, ct_col, b_col = "donor", "condition", "cell_type" if ct_col else None, "batch" if b_col else None
    roles = [c for c in (d_col, c_col, ct_col, b_col) if c is not None]
    obs = obs[columns].set_axis(roles, axis=1).astype("string").replace(r"^\s*$", pd.NA, regex=True)
    levels = list(obs[c_col].dropna().unique())
    if case is not None and reference is not None:
        levels = [str(reference), str(case)]
        obs = obs[obs[c_col].isin(levels)]
    if cell_type is not None and ct_col:
        obs = obs[obs[ct_col] == str(cell_type)]
    if included_cell_types is not None and ct_col:
        obs = obs[obs[ct_col].isin(included_cell_types)]
    strata = list(obs.groupby(ct_col, observed=True, sort=False)) if ct_col else [(None, obs)]
    results, imbalanced = [], []
    for name, frame in strata:
        frame = frame.dropna(subset=[d_col, c_col])
        sizes = frame.groupby([c_col, d_col], observed=True, sort=False).size()
        eligible = sizes[sizes >= min_cells_per_donor] if rows_are_cells else sizes
        counts = eligible.groupby(level=0).size().reindex(levels, fill_value=0).to_dict()
        excluded = [{"condition": condition, "donor": donor, "cells": int(n)}
                    for (condition, donor), n in sizes.drop(index=eligible.index).items()]
        sample_cols = [c for c in (c_col, d_col, b_col) if c is not None]
        samples = frame[sample_cols].drop_duplicates().merge(
            eligible.index.to_frame(index=False), on=[c_col, d_col], how="inner"
        )
        results.append(dict(cell_type=name, donors_by_condition=counts, min_donors=min(counts.values(), default=0),
                            min_cells_per_donor=min_cells_per_donor if rows_are_cells else None,
                            min_cells_per_eligible_sample=int(eligible.min()) if rows_are_cells and len(eligible) else None,
                            row_unit="cell" if rows_are_cells else "sample", row_unit_basis=basis,
                            eligible_donors=sorted(set(eligible.index.get_level_values(1))),
                            excluded_donors=excluded, design=_design(samples, levels, d_col, c_col, b_col)))
        if not ct_col or not rows_are_cells:
            continue
        for condition, donors in sizes.groupby(level=0):
            total = int(donors.sum())
            donor = donors.idxmax()[1]
            maximum = int(donors.max())
            if total >= 50 and maximum / total >= dominance_threshold:
                imbalanced.append(dict(cell_type=name, condition=condition, dominant_donor=donor,
                                       fraction=round(maximum / total, 3), donor_cells=maximum,
                                       total_cells=total))
    return results, imbalanced
