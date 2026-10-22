"""Enforce separate line and branch floors for the declared reliability core.

Consumes coverage.py JSON; it never runs tests or treats missing data as a pass.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


def check_coverage(report: dict[str, Any], baseline: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if report.get("meta", {}).get("branch_coverage") is not True:
        errors.append("Branch coverage was not collected")
    files = {name.replace("\\", "/"): data for name, data in report.get("files", {}).items()}
    floors = dict(baseline.get("files", {}))
    groups = baseline.get("groups", {})
    if not floors and not groups:
        return errors + ["Coverage baseline has no guarded files"]
    # A module split must retain its original weighted floor. Averaging file
    # percentages would let tiny facades dilute untested implementation code.
    for name, group in groups.items():
        members = group.get("members", [])
        if not members or len(members) != len(set(members)):
            errors.append(f"Invalid coverage group members for {name}")
            continue
        prefix = group.get("prefix", "")
        measured = {key for key in files if prefix and key.startswith(prefix)}
        if measured != set(members):
            errors.append(f"Coverage group inventory drift for {name}: {sorted(measured ^ set(members))}")
        summary = {key: 0 for key in ("covered_lines", "num_statements", "covered_branches", "num_branches")}
        valid = True
        for member in members:
            if member not in files:
                errors.append(f"Missing coverage for {member}")
                valid = False
                continue
            data = files[member].get("summary", {})
            for covered_key, total_key in (("covered_lines", "num_statements"), ("covered_branches", "num_branches")):
                covered, total = data.get(covered_key), data.get(total_key)
                if type(covered) is not int or type(total) is not int or not 0 <= covered <= total:
                    errors.append(f"Invalid group measurement for {member}: {covered_key}")
                    valid = False
                    continue
                summary[covered_key] += covered
                summary[total_key] += total
        if valid:
            files[name] = {"summary": summary}
            floors[name] = group
    for name, limits in floors.items():
        if name not in files:
            errors.append(f"Missing coverage for {name}")
            continue
        summary = files[name].get("summary", {})
        for label, covered_key, total_key in (
            ("line", "covered_lines", "num_statements"),
            ("branch", "covered_branches", "num_branches"),
        ):
            covered, total = summary.get(covered_key), summary.get(total_key)
            floor = limits.get(label)
            if (type(covered) is not int or type(total) is not int or total <= 0
                    or not 0 <= covered <= total):
                errors.append(f"Invalid or empty {label} measurement for {name}")
                continue
            if (type(floor) not in (int, float) or not math.isfinite(floor)
                    or not 0 <= floor <= 100):
                errors.append(f"Invalid {label} floor for {name}")
                continue
            actual = 100 * covered / total
            if actual + 1e-9 < floor:
                errors.append(f"{name}: {label} {actual:.2f}% < {floor:.2f}%")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--baseline", type=Path, default=Path("quality/coverage-baseline.json"))
    args = parser.parse_args(argv)
    try:
        errors = check_coverage(json.loads(args.report.read_text(encoding="utf-8")),
                                json.loads(args.baseline.read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        errors = [f"Cannot validate coverage: {exc}"]
    for error in errors:
        print(error)
    if not errors:
        print("Core line and branch coverage floors passed")
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
