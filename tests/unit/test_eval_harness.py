"""
Unit tests for the BioNexus Eval Benchmark Harness and Metric Aggregator.

Validates:
1. Loading all YAML benchmark datasets across L1, L2, L3 categories.
2. Fail-closed accounting: a case skipped for a missing backend is NEVER
   counted as passed, is reported separately, and fails the run in strict mode.
3. Unknown L3 planted signals cannot silently auto-pass.
4. CLI 'bionexus eval' execution, report formatting, and the --strict flag.
"""

import builtins
import sys
from pathlib import Path

# Ensure src and repo root are on sys.path
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SRC = _REPO_ROOT / "src"
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from bionexus.cli import main as cli_main
from evals.runner import format_benchmark_markdown, load_eval_cases, run_benchmark, run_single_case
from evals.schema import EvalCase, EvalCategory, EvalLevel, EvalResult, ExpectedStatus

# Modules whose import failure must degrade an L3 case to SKIPPED_NO_BACKEND
_L3_BACKEND_MODULES = {
    "anndata",
    "scanpy",
    "squidpy",
    "pydeseq2",
    "make_tiny",
    "scrna_pipeline",
    "spatial_pipeline",
    "scrna_deseq",
    "scrna_preprocess",
    "scrna_reduce_cluster",
}


def test_load_eval_cases():
    """Verify all YAML benchmark suites load properly across L1, L2, L3."""
    cases = load_eval_cases()
    assert len(cases) >= 35

    categories = {c.category.value for c in cases}
    assert "routing" in categories
    assert "refusal" in categories
    assert "capability_claim" in categories
    assert "host_agent_claim" in categories
    assert "scientific_outcome" in categories

    levels = {c.level.value for c in cases}
    assert "L1" in levels
    assert "L2" in levels
    assert "L3" in levels


def test_run_benchmark_accounting_integrity(canonical_backends_available):
    """Verify gating track passes with high Composite Reliability Index; frontier reported honestly."""
    report = run_benchmark()
    assert report.total_cases >= 35

    for r in report.detailed_results:
        assert r.passed == (not r.skipped and not r.failure_reasons)
        if r.skipped:
            assert r.actual_status == "SKIPPED_NO_BACKEND"
            assert r.skip_reason, "skipped cases must carry a skip reason"

    skipped = sum(1 for r in report.detailed_results if r.skipped)
    assert report.skipped_cases == skipped

    attempted = report.total_cases - (skipped if not report.strict_mode else 0)
    expected_failed = sum(1 for r in report.detailed_results if not r.passed and not (r.skipped and not report.strict_mode))
    assert report.failed_cases == expected_failed
    assert report.overall_accuracy == report.passed_cases / attempted
    assert 0.0 <= report.overall_accuracy <= 1.0

    assert "L1" in report.level_scores
    assert "L2" in report.level_scores
    assert "L3" in report.level_scores

    m = report.metrics
    assert m["unsafe_invocation_rate"] == 0.0
    assert m["capability_hallucination_rate"] == 0.0
    assert m["scientific_semantic_error_rate"] == 0.0
    assert m["composite_reliability_index"] >= 0.90

    # Frontier track (BNS-LC-004..006): executed honestly, never gating
    assert report.frontier_metrics["total"] >= 8
    assert report.union_total == report.total_cases + report.frontier_metrics["total"]


def test_l3_missing_backend_never_counts_as_pass(monkeypatch):
    """A missing scientific backend must yield SKIPPED_NO_BACKEND, never PERMITTED.

    Regression guard for the unfalsifiable-score defect: previously every L3
    case auto-passed on machines without scanpy/squidpy/pydeseq2.
    """
    cases = [c for c in load_eval_cases() if c.level == EvalLevel.L3_OUTCOME]
    assert len(cases) >= 4

    real_import = builtins.__import__

    def _block_backends(name, *args, **kwargs):
        root_name = name.split(".")[0]
        if root_name in _L3_BACKEND_MODULES or name in _L3_BACKEND_MODULES or name.startswith(("evals.flagship", "evals.annotation", "evals.spatial")):
            raise ImportError(f"blocked for test: {name}")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _block_backends)

    for case in cases:
        result = run_single_case(case)
        assert not result.passed, f"{case.id} must not pass without a backend"
        assert result.actual_status == "SKIPPED_NO_BACKEND"
        assert result.skipped is True
        # The skip reason must disclose why: either the scientific backend is
        # unavailable, or (flagship real-data track) the external dataset is
        # absent. Both are honest refusal territory (BNS-EM-009).
        is_backend_skip = "backend unavailable" in (result.skip_reason or "")
        is_flagship_skip = "Flagship suite" in (result.skip_reason or "") and "Dataset absent" in (result.skip_reason or "")
        assert is_backend_skip or is_flagship_skip


def test_unknown_planted_signal_cannot_auto_pass():
    """An L3 case with an unrecognized planted_signal must fail loudly."""
    case = EvalCase(
        id="l3-unknown-signal",
        prompt="Run the planted outcome verification.",
        category=EvalCategory.SCIENTIFIC_OUTCOME,
        expected_status=ExpectedStatus.PERMITTED,
        level=EvalLevel.L3_OUTCOME,
        data_metadata={"planted_signal": "nonexistent_signal"},
    )
    result = run_single_case(case)
    assert not result.passed
    assert result.actual_status == "OUTCOME_MISMATCH"
    assert any("Unknown planted_signal" in fr for fr in result.failure_reasons)


def _patch_all_cases_skipped(monkeypatch):
    """Force every case to be backend-unavailable via a stubbed runner."""

    def _fake_run_single_case(case, provider=None, model=None):
        return EvalResult(
            case_id=case.id,
            category=case.category.value,
            passed=False,
            expected_status=case.expected_status.value,
            actual_status="SKIPPED_NO_BACKEND",
            level=case.level.value,
            skipped=True,
            skip_reason="backend unavailable (stub)",
        )

    from evals import runner as runner_module

    monkeypatch.setattr(runner_module, "run_single_case", _fake_run_single_case)


def test_strict_mode_promotes_skips_to_failures(monkeypatch):
    """Strict mode: backend-unavailable skips become failures (non-zero exit semantics)."""
    _patch_all_cases_skipped(monkeypatch)
    from evals import runner as runner_module

    report = runner_module.run_benchmark(strict=True)
    assert report.strict_mode is True
    assert report.skipped_cases == report.total_cases
    assert report.failed_cases == report.total_cases
    assert report.passed_cases == 0
    assert report.overall_accuracy == 0.0
    assert all(any("[STRICT MODE]" in fr for fr in r.failure_reasons) for r in report.detailed_results)


def test_non_strict_skip_excluded_from_denominator(monkeypatch):
    """Non-strict mode: skips are visible but excluded from accuracy, never silently passed."""
    _patch_all_cases_skipped(monkeypatch)
    from evals import runner as runner_module

    report = runner_module.run_benchmark(strict=False)
    assert report.strict_mode is False
    assert report.skipped_cases == report.total_cases
    assert report.failed_cases == 0
    assert report.passed_cases == 0
    assert report.overall_accuracy == 0.0  # attempted == 0 must not default to a free 100%


def test_format_benchmark_markdown():
    """Verify Markdown report generation surfaces skips and replay disclaimers."""
    report = run_benchmark()
    md = format_benchmark_markdown(report)
    assert "[BioNexus Eval 2.0]" in md
    assert "Multi-Tier Benchmark Levels" in md
    assert "Core Scientific Reliability Metrics" in md
    assert "Category Breakdown" in md
    assert "Composite Reliability Index" in md
    assert "Skipped (backend unavailable)" in md
    assert "Accuracy (attempted)" in md
    assert "Strict Mode" in md
    if not report.is_live:
        assert "REPLAY DISCLAIMER" in md
    if report.skipped_cases > 0:
        assert "VERIFICATION GAP" in md
        assert "Skipped Benchmark Cases" in md


def test_cli_eval_subcommand(capsys):
    """Verify CLI 'bionexus eval' command with --level."""
    rc = cli_main(["eval", "--level", "L2"])
    assert rc == 0
    captured = capsys.readouterr()
    assert "[BioNexus Eval 2.0]" in captured.out
    assert "Gating Accuracy" in captured.out or "Overall Accuracy" in captured.out


def test_cli_eval_strict_flag(capsys, canonical_backends_available):
    """Verify the --strict flag is wired through to the benchmark runner."""
    rc = cli_main(["eval", "--level", "L1", "--strict"])
    assert rc == 0  # L1 never depends on scientific backends
    captured = capsys.readouterr()
    assert "Strict Mode" in captured.out
    assert "`ON`" in captured.out
