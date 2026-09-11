"""Require both evidence directions and complete pytest outcomes."""
from pathlib import Path
from types import SimpleNamespace

import yaml

from scripts.check_de_traceability import TestOutcomes as Outcomes
from scripts.check_de_traceability import validate_profile

ROOT = Path(__file__).resolve().parents[2]


def test_repository_profile_resolves_positive_negative_and_implementation_references():
    _, targets, errors = validate_profile(ROOT, ROOT / "spec/de-audit-traceability.yaml")
    assert not errors
    assert targets


def test_missing_negative_or_broken_symbol_is_rejected(tmp_path):
    raw = yaml.safe_load((ROOT / "spec/de-audit-traceability.yaml").read_text(encoding="utf-8"))
    entry = raw["requirements"]["BNS-II-001"]
    entry["negative_tests"] = []
    entry["evidence"][0]["target"] = "src/bionexus/integrity.py::missing_enforcement_point"
    path = tmp_path / "broken.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    _, _, errors = validate_profile(ROOT, path)
    assert any("negative_tests" in error for error in errors)
    assert any("missing_enforcement_point" in error for error in errors)


def test_all_parameter_cases_and_teardown_must_pass():
    outcomes = Outcomes()
    target = "tests/test_example.py::test_boundary"
    assert not outcomes.passed(target)
    for phase in ("setup", "call", "teardown"):
        outcomes.pytest_runtest_logreport(SimpleNamespace(nodeid=target + "[good]", when=phase, outcome="passed"))
    assert outcomes.passed(target)
    outcomes.pytest_runtest_logreport(SimpleNamespace(nodeid=target + "[bad]", when="setup", outcome="skipped"))
    assert not outcomes.passed(target)
    outcomes.pytest_runtest_logreport(SimpleNamespace(nodeid=target + "[bad]", when="setup", outcome="passed"))
    outcomes.pytest_runtest_logreport(SimpleNamespace(nodeid=target + "[bad]", when="call", outcome="passed"))
    assert not outcomes.passed(target)
    outcomes.pytest_runtest_logreport(SimpleNamespace(nodeid=target + "[bad]", when="teardown", outcome="failed"))
    assert not outcomes.passed(target)
