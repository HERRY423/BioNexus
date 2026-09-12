"""Descriptive, paired person-minute accounting; missing costs are never zero."""
from __future__ import annotations

import math
from typing import Any

COST_FIELDS = ("installation", "review", "false_alarm_handling", "repair", "communication")
ARMS = ("baseline", "assisted")


def empty_costs() -> dict[str, Any]:
    return {"unit": "person_minutes", "comparison": None,
            "allocation_note": None,
            **{arm: dict.fromkeys(COST_FIELDS) for arm in ARMS}}


def summarize_costs(costs: dict[str, Any] | None) -> dict[str, Any]:
    """Both arms, disjoint categories, installation charged to the observed cohort.

    Allocation and timing are declarations, not authenticated measurements.
    Money, compute and scientific harm are not converted to person-minutes.
    """
    if costs is None:
        return {"status": "NOT_ASSESSED", "minutes_saved": None}
    if not isinstance(costs, dict) or costs.get("unit") != "person_minutes":
        raise ValueError("costs must declare person_minutes")
    if costs.get("comparison") not in (None, "PAIRED_SAME_CASE"):
        raise ValueError("costs comparison must be null or PAIRED_SAME_CASE")
    totals: dict[str, float | None] = {}
    missing: list[str] = []
    for arm in ARMS:
        entries = costs.get(arm)
        if not isinstance(entries, dict) or set(entries) != set(COST_FIELDS):
            raise ValueError(f"{arm} costs require exactly {COST_FIELDS}")
        for field, value in entries.items():
            if value is None:
                missing.append(f"{arm}.{field}")
            elif type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                raise ValueError(f"{arm}.{field} must be null or finite nonnegative minutes")
        total = None if any(v is None for v in entries.values()) else sum(entries.values())
        if total is not None and not math.isfinite(total):
            raise ValueError("cost total is not finite")
        totals[arm] = total
    note = costs.get("allocation_note")
    complete = not missing and costs.get("comparison") == "PAIRED_SAME_CASE"
    if complete and (not isinstance(note, str) or not note.strip()):
        raise ValueError("complete costs require an installation allocation and no-double-counting note")
    baseline, assisted = totals["baseline"], totals["assisted"]
    saved = baseline - assisted if complete and baseline is not None and assisted is not None else None
    return {"status": "REPORTED_COMPLETE" if complete else "INCOMPLETE",
            "minutes_saved": saved,
            "totals": totals, "missing": missing, "allocation_note": note,
            "measurement_authentication": "NOT_ESTABLISHED"}
