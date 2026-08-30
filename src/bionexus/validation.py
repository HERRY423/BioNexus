"""
Orthogonal-evidence validation for BioNexus EvidenceCard dimensions 6 & 7.

Closes the "UNTESTED evidence" gap: the two most valuable EvidenceCard dimensions —
**Cross-Method Concordance** (dimension 6) and **External Validation** (dimension 7) —
were almost always left `UNTESTED` because no automated orthogonal-method runners
existed. This module provides deterministic, dependency-light auditing for both:

- ``rank_concordance``: agreement between two ranked result sets (e.g. Wilcoxon vs
  pseudobulk DE rankings) via Spearman rank correlation + top-k Jaccard overlap.
- ``external_validation``: agreement between predicted calls and an independent
  ground-truth set (e.g. ClinVar controls, planted truth sets) via precision / recall /
  F1 / Jaccard.

Grading is threshold-based and documented; thresholds are conservative and identical
across callers. Every payload is a standard BioNexus contract payload. These audits
quantify *statistical agreement* only — they cannot establish biological correctness.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence

from bionexus.contracts import (
    GRADE_A,
    GRADE_B,
    GRADE_C,
    DimensionGrade,
    EvidenceCard,
    attach_meta,
    refuse,
)

CONFLICTED = DimensionGrade.CONFLICTED.value

# Documented grading thresholds (identical for all callers).
CONCORDANCE_THRESHOLDS = {"A": 0.90, "B": 0.70, "C": 0.50}
EXTERNAL_THRESHOLDS = {"precision_min": 0.80, "recall_min": 0.80}
DEFAULT_TOP_K = 20


# --------------------------------------------------------------------- helpers


def _read_scored_table(path: str | Path) -> Dict[str, float]:
    """Read a two-column CSV/TSV (gene/score) into an ordered {name: score} mapping."""
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"Scored table not found: {p}")
    import csv

    delimiter = "\t" if p.suffix.lower() in (".tsv", ".txt") else ","
    with p.open(newline="", encoding="utf-8") as handle:
        rows = [row for row in csv.reader(handle, delimiter=delimiter) if row]
    if len(rows) < 2:
        raise ValueError(f"Scored table must have a header and at least one data row: {p}")
    header = [h.strip().lower() for h in rows[0]]
    name_col = next((i for i, h in enumerate(header) if h in ("gene", "name", "names", "id", "feature")), 0)
    score_col = next(
        (i for i, h in enumerate(header) if h in ("score", "value", "stat", "log2fc", "pvalue", "padj")),
        1 if len(header) > 1 else 0,
    )
    scored: Dict[str, float] = {}
    for row in rows[1:]:
        if len(row) <= max(name_col, score_col):
            continue
        try:
            scored[row[name_col].strip()] = float(row[score_col])
        except ValueError:
            continue
    if not scored:
        raise ValueError(f"No parsable (name, score) rows in {p}")
    return scored


def _rank_values(values: Sequence[float]) -> Sequence[float]:
    """Average ranks (1-based), ties get the mean of their positions."""
    n = len(values)
    order = sorted(range(n), key=lambda i: values[i])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def _spearman(x: Sequence[float], y: Sequence[float]) -> float:
    """Spearman rank correlation over paired values."""
    n = len(x)
    if n < 2:
        return 0.0
    rx, ry = _rank_values(list(x)), _rank_values(list(y))
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    dx = sum((a - mx) ** 2 for a in rx) ** 0.5
    dy = sum((b - my) ** 2 for b in ry) ** 0.5
    if dx == 0 or dy == 0:
        return 0.0
    return num / (dx * dy)


def _grade_concordance(rho: float, overlap: float) -> str:
    """Worst-case grade across the two agreement statistics (conservative)."""
    stats = (rho, overlap)
    if all(s >= CONCORDANCE_THRESHOLDS["A"] for s in stats):
        return GRADE_A
    if all(s >= CONCORDANCE_THRESHOLDS["B"] for s in stats):
        return GRADE_B
    if all(s >= CONCORDANCE_THRESHOLDS["C"] for s in stats):
        return GRADE_C
    return CONFLICTED


# ------------------------------------------------------- dimension 6: concordance


def rank_concordance(
    primary: Mapping[str, float] | str | Path,
    orthogonal: Mapping[str, float] | str | Path,
    *,
    top_k: int = DEFAULT_TOP_K,
    higher_is_better: bool = True,
) -> Dict[str, Any]:
    """
    Cross-method concordance (EvidenceCard dimension 6) between two ranked results.

    Agreement is measured on the genes common to both rankings:
    - Spearman rank correlation of scores, and
    - Jaccard overlap of the top-``k`` sets.

    Returns a standard contract payload; refusal when overlap is degenerate
    (fewer than 2 shared items cannot support a concordance claim).
    """
    if isinstance(primary, (str, Path)):
        primary = _read_scored_table(primary)
    if isinstance(orthogonal, (str, Path)):
        orthogonal = _read_scored_table(orthogonal)

    shared = [g for g in primary if g in orthogonal]
    if len(shared) < 2:
        return refuse(
            method="bionexus.validation.rank_concordance",
            reason=(
                f"Only {len(shared)} shared item(s) between the two rankings; concordance cannot be "
                "claimed from a degenerate overlap."
            ),
            extra={"primary_size": len(primary), "orthogonal_size": len(orthogonal), "shared": len(shared)},
        )

    sign = 1.0 if higher_is_better else -1.0
    rho = _spearman([sign * primary[g] for g in shared], [sign * orthogonal[g] for g in shared])

    k = max(1, min(top_k, len(shared)))
    top_primary = set(sorted(shared, key=lambda g: sign * primary[g], reverse=True)[:k])
    top_orthogonal = set(sorted(shared, key=lambda g: sign * orthogonal[g], reverse=True)[:k])
    overlap_jaccard = len(top_primary & top_orthogonal) / len(top_primary | top_orthogonal)

    grade = _grade_concordance(max(rho, 0.0), overlap_jaccard)
    result = {
        "refused": False,
        "audit": {
            "dimension": "cross_method_concordance",
            "spearman_rho": round(rho, 4),
            "top_k": k,
            "top_k_jaccard": round(overlap_jaccard, 4),
            "shared_items": len(shared),
            "grade": grade,
            "thresholds": CONCORDANCE_THRESHOLDS,
        },
    }
    return attach_meta(
        result,
        method="bionexus.validation.rank_concordance",
        backend="bionexus.validation",
        evidence_grade=grade if grade != CONFLICTED else GRADE_C,
        limitations=[
            "Concordance quantifies statistical agreement between two methods; it cannot establish "
            "which method is biologically correct.",
        ],
        conclusion_maturity=(
            "PRELIMINARY" if grade in (GRADE_A, GRADE_B, GRADE_C) else "CONFLICTED"
        ),
    )


def apply_cross_method_concordance(card: EvidenceCard, concordance_payload: Mapping[str, Any]) -> EvidenceCard:
    """Write a rank_concordance audit result into an EvidenceCard's dimension 6."""
    if concordance_payload.get("refused"):
        card.details["concordance_notes"] = concordance_payload.get("abstain_reason", "Concordance refused.")
        return card
    audit = concordance_payload["audit"]
    card.cross_method_concordance = audit["grade"]
    card.details["concordance_notes"] = (
        f"Spearman rho={audit['spearman_rho']}, top-{audit['top_k']} Jaccard={audit['top_k_jaccard']} "
        f"over {audit['shared_items']} shared items."
    )
    return card


# ------------------------------------------------- dimension 7: external validation


def external_validation(
    predicted: Iterable[str] | Mapping[str, Any] | str | Path,
    truth: Iterable[str] | Mapping[str, Any] | str | Path,
    *,
    truth_key: Optional[str] = None,
) -> Dict[str, Any]:
    """
    External validation (EvidenceCard dimension 7) of predicted calls against an
    independent ground-truth set.

    ``predicted`` and ``truth`` may be an iterable of names, a scored mapping (mapping
    form uses its keys), or a CSV/TSV path (all row names of the name column). For JSON
    truth sets, ``truth_key`` selects the array of true positives.

    Grades: A when precision AND recall >= 0.80, B when F1 >= 0.80 with one of them
    below 0.80, C when F1 >= 0.50, otherwise CONFLICTED.
    """
    def _as_names(source: Any) -> set[str]:
        if isinstance(source, (str, Path)):
            p = Path(source)
            if p.suffix.lower() == ".json":
                data = json.loads(p.read_text(encoding="utf-8"))
                if truth_key:
                    data = data[truth_key]
                if isinstance(data, dict):
                    return {str(k) for k in data}
                return {str(v) for v in data}
            return set(_read_scored_table(p))
        if isinstance(source, Mapping):
            return {str(k) for k in source}
        return {str(v) for v in source}

    predicted_set = _as_names(predicted)
    truth_set = _as_names(truth)
    if not truth_set:
        return refuse(
            method="bionexus.validation.external_validation",
            reason="Ground-truth set is empty; external validation cannot be claimed.",
        )
    if not predicted_set:
        return refuse(
            method="bionexus.validation.external_validation",
            reason="Predicted set is empty; external validation cannot be claimed.",
        )

    tp = len(predicted_set & truth_set)
    precision = tp / len(predicted_set)
    recall = tp / len(truth_set)
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    jaccard = tp / len(predicted_set | truth_set)

    if precision >= EXTERNAL_THRESHOLDS["precision_min"] and recall >= EXTERNAL_THRESHOLDS["recall_min"]:
        grade: str = GRADE_A
    elif f1 >= 0.80:
        grade = GRADE_B
    elif f1 >= 0.50:
        grade = GRADE_C
    else:
        grade = CONFLICTED

    result = {
        "refused": False,
        "audit": {
            "dimension": "external_validation",
            "true_positives": tp,
            "predicted_size": len(predicted_set),
            "truth_size": len(truth_set),
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "jaccard": round(jaccard, 4),
            "grade": grade,
            "thresholds": EXTERNAL_THRESHOLDS,
        },
    }
    return attach_meta(
        result,
        method="bionexus.validation.external_validation",
        backend="bionexus.validation",
        evidence_grade=grade if grade != CONFLICTED else GRADE_C,
        limitations=[
            "Validation is only as independent and complete as the supplied ground truth.",
            "Agreement with a truth set does not by itself certify the analysis pipeline.",
        ],
        conclusion_maturity=("REPLICATED" if grade == GRADE_A else "PRELIMINARY" if grade != CONFLICTED else "CONFLICTED"),
    )


def apply_external_validation(card: EvidenceCard, validation_payload: Mapping[str, Any]) -> EvidenceCard:
    """Write an external_validation audit result into an EvidenceCard's dimension 7."""
    if validation_payload.get("refused"):
        card.details["validation_notes"] = validation_payload.get("abstain_reason", "Validation refused.")
        return card
    audit = validation_payload["audit"]
    card.external_validation = audit["grade"]
    card.details["validation_notes"] = (
        f"Precision={audit['precision']}, recall={audit['recall']} against an independent truth set "
        f"({audit['truth_size']} items)."
    )
    return card
