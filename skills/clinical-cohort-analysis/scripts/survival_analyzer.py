#!/usr/bin/env python3
"""
Clinical Multi-Cohort Survival & Prognostic Risk Analyzer.
Computes vectorized Kaplan-Meier survival curves, Log-rank test statistics,
and Cox Proportional Hazards Hazard Ratios (HR, 95% CI) for patient stratification.
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import Any, Dict, Tuple

import numpy as np
import pandas as pd
from scipy.stats import chi2

_SRC = Path(__file__).resolve().parents[3] / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from bionexus.contracts import EvidenceCard  # noqa: E402

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s")
logger = logging.getLogger("SurvivalAnalyzer")


def compute_kaplan_meier(times: np.ndarray, events: np.ndarray) -> Tuple[np.ndarray, np.ndarray, float]:
    """
    Compute Kaplan-Meier survival probability curve S(t) = prod(1 - d_i / n_i).
    Returns (unique_times, survival_probabilities, median_survival_time).
    """
    order = np.argsort(times)
    sorted_times = times[order]
    sorted_events = events[order]

    unique_times = np.unique(sorted_times)
    len(times)
    survival_prob = 1.0

    km_times = [0.0]
    km_probs = [1.0]

    for t in unique_times:
        d_i = np.sum(sorted_events[sorted_times == t])
        n_i = np.sum(sorted_times >= t)
        if n_i > 0:
            survival_prob *= 1.0 - (d_i / n_i)
        km_times.append(t)
        km_probs.append(survival_prob)

    # Median survival (first time S(t) <= 0.50)
    km_probs_arr = np.array(km_probs)
    km_times_arr = np.array(km_times)
    median_idx = np.where(km_probs_arr <= 0.50)[0]
    median_os = float(km_times_arr[median_idx[0]]) if len(median_idx) > 0 else float(np.max(unique_times))

    return km_times_arr, km_probs_arr, median_os


def log_rank_test(
    times_a: np.ndarray, events_a: np.ndarray, times_b: np.ndarray, events_b: np.ndarray
) -> Tuple[float, float]:
    """
    Perform 2-sample Log-Rank test for comparing survival distributions.
    Returns (chi2_statistic, p_value).
    """
    all_times = np.unique(np.concatenate([times_a, times_b]))
    all_times = all_times[all_times > 0]

    obs_a = 0.0
    exp_a = 0.0
    var_a = 0.0

    for t in all_times:
        d_a = np.sum((times_a == t) & (events_a == 1))
        d_b = np.sum((times_b == t) & (events_b == 1))
        d_total = d_a + d_b

        n_a = np.sum(times_a >= t)
        n_b = np.sum(times_b >= t)
        n_total = n_a + n_b

        if n_total > 1 and d_total > 0:
            e_a = (n_a * d_total) / n_total
            v = (n_a * n_b * d_total * (n_total - d_total)) / (n_total**2 * (n_total - 1))

            obs_a += d_a
            exp_a += e_a
            var_a += v

    if var_a > 0:
        z = (obs_a - exp_a) / np.sqrt(var_a)
        chi2_stat = float(z**2)
        p_val = float(1.0 - chi2.cdf(chi2_stat, df=1))
    else:
        chi2_stat = 0.0
        p_val = 1.0

    return chi2_stat, p_val


def calculate_cox_hazard_ratio(times: np.ndarray, events: np.ndarray, group_labels: np.ndarray) -> Dict[str, Any]:
    """
    Compute Cox Proportional Hazards regression coefficient (beta) and Hazard Ratio (HR = exp(beta)).
    group_labels: binary array (1 = High Risk / Biomarker Positive, 0 = Control).
    """
    # Analytical approximation using weighted log-rank statistics
    mask_1 = group_labels == 1
    mask_0 = group_labels == 0

    times_1, events_1 = times[mask_1], events[mask_1]
    times_0, events_0 = times[mask_0], events[mask_0]

    _, km_1, med_1 = compute_kaplan_meier(times_1, events_1)
    _, km_0, med_0 = compute_kaplan_meier(times_0, events_0)

    chi2_stat, p_val = log_rank_test(times_1, events_1, times_0, events_0)

    method = "event_rate_ratio_not_cox"
    backend = "local_km_logrank"
    evidence_grade = "C"
    try:
        from lifelines import CoxPHFitter

        frame = pd.DataFrame({"T": times, "E": events, "g": group_labels.astype(float)})
        cph = CoxPHFitter()
        cph.fit(frame, duration_col="T", event_col="E")
        hr = float(np.exp(cph.params_["g"]))
        ci = cph.confidence_intervals_.loc["g"]
        hr_lower = float(np.exp(ci.iloc[0]))
        hr_upper = float(np.exp(ci.iloc[1]))
        method = "lifelines_coxph"
        backend = "lifelines"
        evidence_grade = "A"
    except Exception:
        rate_1 = np.sum(events_1) / (np.sum(times_1) + 1e-6)
        rate_0 = np.sum(events_0) / (np.sum(times_0) + 1e-6)
        hr = rate_1 / (rate_0 + 1e-6)
        beta = np.log(max(1e-4, hr))
        se_beta = np.sqrt(1.0 / (np.sum(events_1) + 1e-6) + 1.0 / (np.sum(events_0) + 1e-6))
        hr_lower = float(np.exp(beta - 1.96 * se_beta))
        hr_upper = float(np.exp(beta + 1.96 * se_beta))

    if p_val <= 0.05 and hr > 1.25:
        prognosis = "Group 1 has worse survival (log-rank p<=0.05)"
    elif p_val <= 0.05 and hr < 0.80:
        prognosis = "Group 1 has better survival (log-rank p<=0.05)"
    else:
        prognosis = "No significant two-group survival difference at p<=0.05"

    stat_grade = "A" if p_val <= 0.05 and (hr > 1.5 or hr < 0.67) else ("B" if p_val <= 0.05 else "C")
    sample_grade = "A" if (len(events_1) >= 20 and len(events_0) >= 20) else "B"

    card = EvidenceCard(
        execution_fidelity=evidence_grade,
        input_integrity="A" if (np.all(times >= 0) and np.all(np.isin(events, [0, 1]))) else "C",
        assumption_validity="A" if method == "lifelines_coxph" else "C",
        statistical_support=stat_grade,
        parameter_robustness="B",
        details={
            "method": method,
            "sample_size_group1": int(len(events_1)),
            "sample_size_group0": int(len(events_0)),
            "events_group1": int(np.sum(events_1)),
            "events_group0": int(np.sum(events_0)),
            "sample_grade": sample_grade,
        },
    )

    try:
        from bionexus.contracts import attach_meta

        return attach_meta(
            {
                "hazard_ratio": round(float(hr), 3) if method == "lifelines_coxph" else None,
                "event_rate_ratio": None if method == "lifelines_coxph" else round(float(hr), 3),
                "hazard_ratio_95_ci": [round(hr_lower, 3), round(hr_upper, 3)],
                "log_rank_p_value": float(p_val),
                "log_rank_chi2": round(float(chi2_stat), 2),
                "median_survival_months_high": round(float(med_1), 1),
                "median_survival_months_low": round(float(med_0), 1),
                "clinical_prognosis_verdict": prognosis,
            },
            method=method,
            backend=backend,
            evidence_grade=evidence_grade,
            limitations=[
                "Cox PH requires lifelines; otherwise this is an event-rate ratio, not a partial-likelihood Cox model.",
                "Research-use only.",
            ],
            evidence_card=card,
        )
    except ImportError:
        return {
            "hazard_ratio": round(float(hr), 3) if method == "lifelines_coxph" else None,
            "event_rate_ratio": None if method == "lifelines_coxph" else round(float(hr), 3),
            "hazard_ratio_95_ci": [round(hr_lower, 3), round(hr_upper, 3)],
            "log_rank_p_value": float(p_val),
            "log_rank_chi2": round(float(chi2_stat), 2),
            "median_survival_months_high": round(float(med_1), 1),
            "median_survival_months_low": round(float(med_0), 1),
            "clinical_prognosis_verdict": prognosis,
            "method": method,
            "backend": backend,
            "evidence_grade": evidence_grade,
            "evidence_card": card.to_dict(),
            "conclusion_status": card.synthesize_status(),
            "limitations": [
                "Cox PH requires lifelines; otherwise this is an event-rate ratio, not a partial-likelihood Cox model.",
                "Research-use only.",
            ],
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Kaplan-Meier / log-rank / optional Cox")
    parser.add_argument("--table", required=True, help="CSV with columns time, event, group")
    parser.add_argument("--time-col", default="time")
    parser.add_argument("--event-col", default="event")
    parser.add_argument("--group-col", default="group")
    args = parser.parse_args()
    frame = pd.read_csv(args.table)
    times = frame[args.time_col].to_numpy(dtype=float)
    events = frame[args.event_col].to_numpy(dtype=int)
    groups = frame[args.group_col].to_numpy(dtype=int)
    result = calculate_cox_hazard_ratio(times, events, groups)
    import json

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
