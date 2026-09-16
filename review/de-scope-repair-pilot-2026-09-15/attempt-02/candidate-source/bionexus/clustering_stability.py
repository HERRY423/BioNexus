"""Recompute descriptive stability from cell-aligned perturbation partitions.

No sample-size cutoff and no implicit acceptance threshold. Passing a caller's
declared criterion is an engineering result, not a validated cell identity.
"""

from __future__ import annotations

import itertools
import math
import re
from typing import Any


def assess_clustering_stability(packet: Any, *, dataset_sha256: str | None = None) -> dict:
    result = {
        "status": "NOT_ASSESSED",
        "criterion_met": False,
        "pairs": [],
        "evidence_class": "SUPPLIED_PARTITIONS_RECOMPUTED",
        "independent_validation": "NOT_ESTABLISHED",
        "biological_identity": "NOT_ASSESSED",
        "limitations": [],
    }
    if packet is None:
        result["limitations"] = ["No cell-aligned resampling/parameter-perturbation results supplied."]
        return result
    try:
        if not isinstance(packet, dict):
            raise ValueError("clustering_stability must be a mapping")
        if not isinstance(dataset_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", dataset_sha256):
            raise ValueError("current dataset_sha256 is required to bind the supplied partitions")
        if packet.get("dataset_sha256") != dataset_sha256:
            raise ValueError("stability evidence belongs to a different dataset")
        runs = packet.get("runs")
        if not isinstance(runs, list) or len(runs) < 2:
            raise ValueError("at least two perturbation runs are required")
        run_ids, perturbations, assignments = set(), set(), []
        for run in runs:
            if not isinstance(run, dict):
                raise ValueError("run must be a mapping")
            run_id, perturbation = run.get("run_id"), run.get("perturbation")
            if not isinstance(run_id, str) or not run_id or run_id in run_ids:
                raise ValueError("run ids must be nonempty and unique")
            if not isinstance(perturbation, str) or not perturbation:
                raise ValueError("each run must describe its perturbation")
            cells, labels = run.get("cell_ids"), run.get("labels")
            if not isinstance(cells, list) or not isinstance(labels, list) or len(cells) != len(labels):
                raise ValueError("cell_ids and labels must be aligned lists")
            if any(not isinstance(c, str) or not c for c in cells) or len(set(cells)) != len(cells):
                raise ValueError("cell ids must be nonempty and unique within each run")
            if any(not isinstance(label, str) or not label for label in labels):
                raise ValueError("labels must be nonempty strings")
            if len(set(labels)) < 2 or len(set(labels)) == len(labels):
                raise ValueError("trivial one-cluster or all-singleton partitions do not establish stability")
            run_ids.add(run_id)
            perturbations.add(perturbation)
            assignments.append((run_id, dict(zip(cells, labels))))
        if len(perturbations) < 2:
            raise ValueError("duplicate perturbation descriptions do not establish a perturbation grid")
        from sklearn.metrics import adjusted_rand_score

        for (left_id, left), (right_id, right) in itertools.combinations(assignments, 2):
            common = sorted(left.keys() & right.keys())
            if len(common) < 2:
                raise ValueError("insufficient shared cells to compare partitions")
            a, b = [left[c] for c in common], [right[c] for c in common]
            if any(len(set(x)) < 2 or len(set(x)) == len(x) for x in (a, b)):
                raise ValueError("shared-cell partition is degenerate; ARI would be misleading")
            score = float(adjusted_rand_score(a, b))
            if not math.isfinite(score):
                raise ValueError("non-finite ARI")
            result["pairs"].append(
                {
                    "left": left_id,
                    "right": right_id,
                    "n_shared": len(common),
                    "union_coverage": len(common) / len(left.keys() | right.keys()),
                    "ari": score,
                }
            )
        scores = [pair["ari"] for pair in result["pairs"]]
        result.update(
            status="MEASURED_NO_CRITERION", n_runs=len(runs), mean_ari=sum(scores) / len(scores), min_ari=min(scores)
        )
        threshold = packet.get("declared_min_ari")
        if threshold is not None:
            if isinstance(threshold, (bool, str)) or not math.isfinite(float(threshold)) or not -1 <= threshold <= 1:
                raise ValueError("declared_min_ari must be finite and in [-1, 1]")
            result["declared_min_ari"] = threshold
            result["criterion_met"] = min(scores) >= threshold
            result["status"] = "MEETS_DECLARED_CRITERION" if result["criterion_met"] else "BELOW_DECLARED_CRITERION"
        result["limitations"] = [
            "ARI describes only shared cells in the supplied perturbation grid; omitted cells/populations are not validated.",
            "The declared criterion is not an approved empirical threshold; passing does not establish biological identity or population generalization.",
            "Dataset hash binding and recomputation do not authenticate the supplier or independence of the runs.",
        ]
    except (ValueError, TypeError, KeyError) as exc:
        result.update(status="INVALID", criterion_met=False, limitations=[str(exc)])
    return result
