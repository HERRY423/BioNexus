"""
BioNexus Scientific Integrity & Diagnostic Audit Engine.

Audits input data semantics, numerical stability, distribution assumptions,
and statistical support to prevent silent methodological distortions
(e.g., treating log-normalized floats as raw count matrices).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np


def audit_expression_matrix(
    X: Any,
    expected_type: str = "counts",
    sample_size: int = 2000
) -> Tuple[str, List[str], Dict[str, Any]]:
    """
    Audit expression matrix data semantics and numeric health.

    Parameters:
        X: Scipy sparse matrix, numpy array, or array-like.
        expected_type: "counts" (raw integer counts) or "normalized" (floats).
        sample_size: Number of elements to sample for fast inspection.

    Returns:
        (grade: "A" | "B" | "C", notes: List[str], stats: Dict[str, Any])
    """
    notes: List[str] = []
    stats: Dict[str, Any] = {
        "expected_type": expected_type,
        "is_sparse": False,
        "shape": None,
        "min": None,
        "max": None,
        "has_nans": False,
        "has_negs": False,
        "is_integer_like": False,
    }

    if X is None:
        return "C", ["Matrix is None"], stats

    # Shape detection
    if hasattr(X, "shape"):
        stats["shape"] = list(X.shape)
        if len(X.shape) != 2 or X.shape[0] == 0 or X.shape[1] == 0:
            return "C", ["Matrix has invalid empty shape"], stats

    # Fast sampling
    try:
        import scipy.sparse as sp
        if sp.issparse(X):
            stats["is_sparse"] = True
            data = X.data
        else:
            data = np.asarray(X).ravel()
    except Exception as e:
        return "C", [f"Unable to convert matrix to numeric array: {e}"], stats

    if len(data) == 0:
        return "B", ["Matrix is all zeros"], stats

    # Take subsample if large
    if len(data) > sample_size:
        indices = np.random.choice(len(data), size=sample_size, replace=False)
        sample = data[indices]
    else:
        sample = data

    # Check finite
    has_nans = not np.all(np.isfinite(sample))
    stats["has_nans"] = bool(has_nans)
    if has_nans:
        notes.append("Matrix contains NaN or Inf non-finite values.")
        return "C", notes, stats

    min_val = float(np.min(sample))
    max_val = float(np.max(sample))
    stats["min"] = min_val
    stats["max"] = max_val

    # Check negatives
    has_negs = min_val < 0.0
    stats["has_negs"] = bool(has_negs)
    if has_negs:
        notes.append(f"Matrix contains negative values (min: {min_val:.3f}).")
        return "C", notes, stats

    # Check integer nature
    # Non-zero entries should be very close to whole integers
    non_zero_sample = sample[sample > 0]
    if len(non_zero_sample) > 0:
        frac_part = np.abs(non_zero_sample - np.round(non_zero_sample))
        is_integer_like = bool(np.percentile(frac_part, 95) < 1e-4)
    else:
        is_integer_like = True
    stats["is_integer_like"] = is_integer_like

    if expected_type == "counts":
        if is_integer_like:
            notes.append("Verified raw integer count distribution.")
            return "A", notes, stats
        else:
            # Floating point numbers detected where raw counts were expected
            if max_val < 30.0:
                notes.append(
                    f"Continuous values detected (max={max_val:.2f}) where raw counts were expected. "
                    "Data appears to be already log-normalized or scaled."
                )
            else:
                notes.append("Continuous float values detected instead of integer counts.")
            return "B", notes, stats

    elif expected_type == "normalized":
        if not is_integer_like or max_val < 50.0:
            notes.append("Verified normalized continuous expression scale.")
            return "A", notes, stats
        else:
            notes.append(f"High-magnitude integer counts detected (max={max_val:.0f}) where normalized data expected.")
            return "B", notes, stats

    return "B", notes, stats


def audit_spatial_coordinates(
    coords: Any,
    min_spots: int = 5
) -> Tuple[str, List[str], Dict[str, Any]]:
    """
    Audit spatial coordinate matrix for geometric validity.

    Parameters:
        coords: 2D or 3D coordinate array (N x D).
        min_spots: Minimum required spots/cells.

    Returns:
        (grade: "A" | "B" | "C", notes: List[str], stats: Dict[str, Any])
    """
    notes: List[str] = []
    stats: Dict[str, Any] = {
        "n_points": 0,
        "n_dimensions": 0,
        "has_nans": False,
        "zero_variance": False,
    }

    if coords is None:
        return "C", ["Spatial coordinates are missing (None)."], stats

    try:
        arr = np.asarray(coords)
    except Exception as e:
        return "C", [f"Unable to parse spatial coordinates: {e}"], stats

    if arr.ndim != 2 or arr.shape[1] not in (2, 3):
        notes.append(f"Invalid coordinate dimensions: shape {arr.shape} (expected N x 2 or N x 3).")
        return "C", notes, stats

    stats["n_points"] = int(arr.shape[0])
    stats["n_dimensions"] = int(arr.shape[1])

    if arr.shape[0] < min_spots:
        notes.append(f"Insufficient spatial spots: found {arr.shape[0]}, minimum required {min_spots}.")
        return "C", notes, stats

    if not np.all(np.isfinite(arr)):
        stats["has_nans"] = True
        notes.append("Spatial coordinates contain NaN or Inf values.")
        return "C", notes, stats

    variances = np.var(arr, axis=0)
    if np.any(variances < 1e-8):
        stats["zero_variance"] = True
        notes.append("Degenerate spatial coordinates: variance along an axis is virtually zero.")
        return "C", notes, stats

    notes.append(f"Verified {arr.shape[0]} valid {arr.shape[1]}D spatial coordinates.")
    return "A", notes, stats


def audit_statistical_significance(
    pvals: Optional[np.ndarray | List[float]] = None,
    fdr_q: Optional[np.ndarray | List[float]] = None,
    effect_sizes: Optional[np.ndarray | List[float]] = None,
    alpha: float = 0.05
) -> Tuple[str, List[str], Dict[str, Any]]:
    """
    Audit statistical findings power and effect size significance.
    """
    notes: List[str] = []
    stats: Dict[str, Any] = {
        "n_tested": 0,
        "n_significant": 0,
        "fdr_applied": False,
    }

    test_vals = fdr_q if fdr_q is not None else pvals
    if test_vals is None:
        return "INSUFFICIENT", ["No statistical p-values or FDR q-values supplied."], stats

    arr = np.asarray(test_vals, dtype=float)
    arr = arr[np.isfinite(arr)]
    stats["n_tested"] = len(arr)
    stats["fdr_applied"] = fdr_q is not None

    if len(arr) == 0:
        return "INSUFFICIENT", ["No finite statistical values found."], stats

    sig_count = int(np.sum(arr < alpha))
    stats["n_significant"] = sig_count

    if sig_count > 0:
        if fdr_q is not None:
            notes.append(f"{sig_count}/{len(arr)} findings pass FDR q < {alpha:.2f}.")
            return "A", notes, stats
        else:
            notes.append(f"{sig_count}/{len(arr)} findings pass unadjusted p < {alpha:.2f}.")
            return "B", notes, stats
    else:
        notes.append(f"No findings reached statistical threshold (alpha = {alpha:.2f}).")
        return "C", notes, stats


def audit_parameter_stability(
    runs: List[Any],
    metric: str = "ari",
    tolerance_threshold: float = 0.70,
) -> Tuple[str, List[str], Dict[str, Any]]:
    """
    Audit parameter robustness across parameter sweeps, resolutions, or subsampling runs.

    Parameters:
        runs: List of clustering label arrays or top feature rank lists across parameter iterations.
        metric: "ari" (Adjusted Rand Index for clusterings) or "jaccard" (for feature rank lists).
        tolerance_threshold: Minimum mean pairwise similarity to earn Grade A robustness.

    Returns:
        (grade: "A" | "B" | "C" | "UNTESTED", notes: List[str], stats: Dict[str, Any])
    """
    notes: List[str] = []
    stats: Dict[str, Any] = {
        "n_runs": len(runs) if runs else 0,
        "metric": metric,
        "mean_similarity": 0.0,
        "min_similarity": 0.0,
    }

    if not runs or len(runs) < 2:
        return "UNTESTED", ["Fewer than 2 runs provided for parameter sweep."], stats

    pairwise_scores: List[float] = []

    if metric == "ari":
        try:
            from sklearn.metrics import adjusted_rand_score
            for i in range(len(runs)):
                for j in range(i + 1, len(runs)):
                    score = adjusted_rand_score(runs[i], runs[j])
                    pairwise_scores.append(float(score))
        except Exception as e:
            return "C", [f"Failed to compute Adjusted Rand Index: {e}"], stats

    elif metric == "jaccard":
        for i in range(len(runs)):
            for j in range(i + 1, len(runs)):
                set_i = set(runs[i])
                set_j = set(runs[j])
                union_len = len(set_i.union(set_j))
                score = len(set_i.intersection(set_j)) / union_len if union_len > 0 else 1.0
                pairwise_scores.append(float(score))
    else:
        return "C", [f"Unsupported parameter stability metric: {metric}"], stats

    if not pairwise_scores:
        return "UNTESTED", ["No pairwise comparisons could be formed."], stats

    mean_score = float(np.mean(pairwise_scores))
    min_score = float(np.min(pairwise_scores))
    stats["mean_similarity"] = mean_score
    stats["min_similarity"] = min_score

    if mean_score >= tolerance_threshold and min_score >= (tolerance_threshold - 0.15):
        notes.append(f"High parameter stability across {len(runs)} sweeps (mean {metric.upper()}={mean_score:.3f}).")
        return "A", notes, stats
    elif mean_score >= (tolerance_threshold - 0.25):
        notes.append(f"Moderate parameter sensitivity across {len(runs)} sweeps (mean {metric.upper()}={mean_score:.3f}).")
        return "B", notes, stats
    else:
        notes.append(f"Fragile parameter sensitivity across {len(runs)} sweeps (mean {metric.upper()}={mean_score:.3f} < {tolerance_threshold}).")
        return "C", notes, stats

