"""A missing or weaker measurement must actually fail the CI gate."""
import copy

import pytest

from scripts.check_coverage import check_coverage


def measurement():
    return {"meta": {"branch_coverage": True}, "files": {
        "src/core.py": {"summary": {"covered_lines": 9, "num_statements": 10,
                                    "covered_branches": 3, "num_branches": 4}}}}


BASELINE = {"files": {"src/core.py": {"line": 90, "branch": 75}}}


def test_exact_floor_passes_and_windows_paths_are_portable():
    report = measurement()
    report["files"]["src\\core.py"] = report["files"].pop("src/core.py")
    assert check_coverage(report, BASELINE) == []


@pytest.mark.parametrize("field,value", [("covered_lines", 8), ("covered_branches", 2),
                                         ("num_statements", 0), ("num_branches", 0),
                                         ("covered_lines", True), ("covered_branches", 5)])
def test_regression_or_invalid_measurement_fails(field, value):
    report = measurement()
    report["files"]["src/core.py"]["summary"][field] = value
    assert check_coverage(report, BASELINE)


def test_missing_module_or_branch_measurement_fails():
    report = measurement()
    report["meta"]["branch_coverage"] = False
    assert check_coverage(report, BASELINE)
    report["files"] = {}
    assert any("Missing coverage" in e for e in check_coverage(report, BASELINE))


@pytest.mark.parametrize("floor", [None, float("nan"), -1, 101, True])
def test_invalid_floor_is_not_a_bypass(floor):
    baseline = copy.deepcopy(BASELINE)
    baseline["files"]["src/core.py"]["line"] = floor
    assert check_coverage(measurement(), baseline)


def test_empty_baseline_fails():
    assert check_coverage(measurement(), {"files": {}})


def test_split_core_uses_weighted_counts_and_retains_inventory():
    report = measurement()
    report["files"]["src/impl/large.py"] = report["files"].pop("src/core.py")
    report["files"]["src/impl/__init__.py"] = {"summary": {
        "covered_lines": 1, "num_statements": 1, "covered_branches": 0, "num_branches": 0,
    }}
    baseline = {"groups": {"core": {"prefix": "src/impl/",
        "members": ["src/impl/large.py", "src/impl/__init__.py"], "line": 90, "branch": 75}}}
    assert check_coverage(report, baseline) == []
    report["files"]["src/impl/large.py"]["summary"]["covered_branches"] = 2
    assert any("branch 50.00%" in e for e in check_coverage(report, baseline))
    report["files"]["src/impl/unlisted.py"] = report["files"]["src/impl/__init__.py"]
    assert any("inventory drift" in e for e in check_coverage(report, baseline))


def test_split_core_missing_or_fabricated_member_fails():
    baseline = {"groups": {"core": {"prefix": "src/", "members": ["src/core.py", "src/missing.py"],
                                    "line": 90, "branch": 75}}}
    assert any("Missing coverage" in e for e in check_coverage(measurement(), baseline))
    baseline["groups"]["core"]["members"] = ["src/core.py"]
    report = measurement()
    report["files"]["src/core.py"]["summary"]["num_branches"] = -1
    assert any("Invalid group" in e for e in check_coverage(report, baseline))
