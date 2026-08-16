"""
Unit tests for the BioNexus Eval Benchmark Harness and Metric Aggregator.

Validates:
1. Loading all YAML benchmark datasets across 6 categories.
2. Evaluating single cases and full benchmark suites.
3. Accurate computation of the 8 Core Scientific Reliability Metrics.
4. CLI 'bionexus eval' execution and report formatting.
"""

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
from evals.runner import format_benchmark_markdown, load_eval_cases, run_benchmark


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


def test_run_benchmark_harness():
    """Verify gating track passes with high Composite Reliability Index; frontier reported honestly."""
    report = run_benchmark()
    assert report.total_cases >= 35
    assert report.failed_cases == 0
    assert report.overall_accuracy >= 0.95

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


def test_format_benchmark_markdown():
    """Verify Markdown report generation."""
    report = run_benchmark()
    md = format_benchmark_markdown(report)
    assert "[BioNexus Eval 2.0]" in md
    assert "Multi-Tier Benchmark Levels" in md
    assert "Core Scientific Reliability Metrics" in md
    assert "Category Breakdown" in md
    assert "Composite Reliability Index" in md


def test_cli_eval_subcommand(capsys):
    """Verify CLI 'bionexus eval' command with --level."""
    rc = cli_main(["eval", "--level", "L2"])
    assert rc == 0
    captured = capsys.readouterr()
    assert "[BioNexus Eval 2.0]" in captured.out
    assert "Gating Accuracy" in captured.out or "Overall Accuracy" in captured.out
