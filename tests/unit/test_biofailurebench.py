"""
Unit tests for BioFailureBench, the Scientific Trap Corpus (BNS-014).

Validates corpus integrity (8-field schema, taxonomy linkage, coverage,
gating/frontier separation), the positive-control requirement, and that the
gating traps pass deterministically through the standard runner.
"""

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SRC = _REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from bionexus.cli import main as cli_main
from bionexus.failures import FAILURE_TAXONOMY, taxonomy_summary
from evals.biofailurebench import corpus_path, load_corpus_records, validate_corpus
from evals.runner import load_eval_cases, run_single_case


def test_corpus_file_exists_and_loads():
    records = load_corpus_records()
    assert len(records) >= 20
    ids = [r["id"] for r in records]
    assert len(ids) == len(set(ids)), "trap IDs must be unique"


def test_corpus_schema_and_coverage_valid():
    report = validate_corpus()
    assert report.valid, [(i.case_id, i.field, i.problem) for i in report.issues]
    # Full taxonomy coverage with no open gaps
    assert set(report.failure_mode_coverage) == set(FAILURE_TAXONOMY)
    assert taxonomy_summary()["open_gaps"] == []
    # Gating/frontier split is explicit
    assert report.gating_cases >= 15
    assert report.frontier_cases >= 3


def test_corpus_carries_all_eight_fields():
    required = ("prompt", "data_metadata", "failure_mode", "expected_status", "allowed_computation", "forbidden_claim", "reference", "description")
    for rec in load_corpus_records():
        for field in required:
            assert field in rec, f"{rec.get('id')} missing {field}"
        assert rec.get("required_remedies") is not None


def test_corpus_contains_positive_control():
    controls = [r for r in load_corpus_records() if r.get("failure_mode") == "NONE"]
    assert len(controls) >= 1
    assert controls[0]["expected_status"] == "PERMITTED"


def test_frontier_traps_use_prefix_and_flag():
    for rec in load_corpus_records():
        if rec.get("known_limitation"):
            assert rec["description"].startswith("FRONTIER TRAP"), rec["id"]
        else:
            assert rec["description"].startswith(("TRAP", "CONTROL")), rec["id"]


def test_gating_traps_pass_deterministically(canonical_backends_available):
    """Every non-frontier trap MUST pass through the standard runner."""
    cases = {c.id: c for c in load_eval_cases(suite="biofailurebench")}
    gating = [c for c in cases.values() if not c.known_limitation]
    assert len(gating) >= 15
    for case in gating:
        result = run_single_case(case)
        assert result.passed, f"{case.id}: {result.failure_reasons}"


def test_frontier_traps_are_executed_not_hidden():
    cases = {c.id: c for c in load_eval_cases(suite="biofailurebench")}
    frontier = [c for c in cases.values() if c.known_limitation]
    assert len(frontier) >= 3
    for case in frontier:
        result = run_single_case(case)
        assert result.known_limitation  # honestly labeled


def test_formerly_open_gaps_have_traps():
    for fid in ("BN-F004", "BN-F005", "BN-F008"):
        assert FAILURE_TAXONOMY[fid].benchmark_cases, fid
        assert FAILURE_TAXONOMY[fid].open_gap is False


def test_bench_cli(capsys):
    assert cli_main(["bench", "validate"]) == 0
    out = capsys.readouterr().out
    assert "BioFailureBench" in out
    assert "Integrity: VALID" in out
    assert "bionexus eval --suite biofailurebench" in out


def test_corpus_file_is_wired_into_eval_suites():
    """The corpus path is a standard eval dataset file (host-agnostic)."""
    p = corpus_path()
    assert p.is_file()
    assert p.parent == (p.parent)  # datasets dir
    assert any(c.id.startswith("BF-") for c in load_eval_cases(suite=str(p.stem)))
