"""
Unit tests for the Frontier Calibration Track and honest calibration metrics.

Validates (BNS-LC-004..007, BNS-EM-007..010):
1. Frontier cases load with known_limitation flags and stay out of gating counts.
2. Gating metrics remain 100% while frontier failures are reported honestly.
3. Union accuracy is below 1.0 while known limitations remain open.
4. Calibration diagnostics expose adjacent-error, per-class F1, and verdict.
5. Cross-host consistency reports single-host runs as not evaluated.
"""

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SRC = _REPO_ROOT / "src"
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


import pytest

pytest.importorskip("squidpy", reason="SKIPPED_NO_BACKEND: canonical backend squidpy not installed (runs in the Canonical Scientific Stack matrix)")
from evals.metrics import (
    compute_cross_host_consistency,
    compute_epistemic_calibration,
    compute_frontier_metrics,
)
from evals.runner import format_benchmark_markdown, load_eval_cases, run_benchmark
from evals.schema import EvalResult


def test_frontier_track_loads():
    """Frontier calibration suite MUST load with known_limitation flags (BNS-LC-004)."""
    cases = load_eval_cases()
    frontier = [c for c in cases if c.known_limitation]
    assert len(frontier) >= 8, "frontier calibration suite must contain >= 8 probes"
    assert all(c.description for c in frontier)
    known_open = [c for c in frontier if c.description.startswith("KNOWN LIMITATION")]
    assert len(known_open) == 4, "exactly four documented open limitations"
    ids = {c.id for c in frontier}
    # The four documented open limitations
    assert "frontier-coordinate-umap-substitution-001" in ids
    assert "frontier-insufficient-power-clustering-002" in ids
    assert "frontier-ambiguous-spatial-marker-003" in ids
    assert "frontier-cluster-vs-condition-de-conflation-004" in ids


def test_gating_and_frontier_separation():
    """Gating track MUST stay clean; frontier failures MUST NOT gate but MUST be visible."""
    report = run_benchmark()

    # Gating: guaranteed behavior only
    assert report.total_cases >= 42
    assert report.failed_cases == 0
    assert report.overall_accuracy == 1.0
    assert report.metrics["composite_reliability_index"] >= 0.99

    # Frontier: executed, honestly counted, not gating
    fm = report.frontier_metrics
    assert fm["total"] >= 8
    assert report.union_total == report.total_cases + fm["total"]
    assert report.union_passed == report.passed_cases + fm["passed"]

    # While known limitations remain open, union accuracy MUST be < 1.0
    # (a hard benchmark with honest misses beats an easy one at 100%, BNS-LC-006)
    assert 0.80 <= report.union_accuracy < 1.0
    assert fm["failed"] >= 1
    assert fm["failed_cases"], "open known limitations must be listed with failure reasons"
    assert all(fc["failure_reasons"] for fc in fm["failed_cases"])


def test_ceiling_clamp_frontier_cases_pass_via_abi():
    """ABI evidence-ceiling frontier cases are graduation-eligible (BNS-LC-005)."""
    report = run_benchmark()
    eligible = set(report.frontier_metrics["graduation_eligible"])
    assert "frontier-ceiling-spatial-supported-claim-005" in eligible
    assert "frontier-ceiling-pseudobulk-replicated-claim-006" in eligible
    assert "frontier-ceiling-clustering-robust-claim-008" in eligible


def test_calibration_diagnostics_present():
    """Calibration report MUST expose adjacent-error, per-class F1, verdict, skipped count."""
    report = run_benchmark()
    c = report.calibration
    assert c["verdict"] in ("CALIBRATED", "OVERCONFIDENT", "UNDERCONFIDENT", "MISALIGNED")
    assert 0.0 <= c["adjacent_error_rate"] <= 1.0
    assert 0.0 <= c["within_one_accuracy"] <= 1.0
    assert isinstance(c["per_class"], dict) and len(c["per_class"]) >= 3
    assert c["total_evaluated"] > 0

    union_cal = report.frontier_metrics["union_calibration"]
    # Honest current state: the union now contains BOTH an overconfidence
    # frontier trap (BF-026: SUPPORTED labels without negative markers) and
    # the underconfidence frontier probes -> MISALIGNED, not one-directional.
    assert union_cal["verdict"] in ("MISALIGNED", "UNDERCONFIDENT")
    assert union_cal["macro_f1"] < 1.0
    assert union_cal["total_evaluated"] == c["total_evaluated"] + (
        report.frontier_metrics["total"] - report.frontier_metrics["calibration"]["skipped_no_backend"]
    )


def test_no_backend_cases_do_not_inflate_calibration():
    """Unexecuted L3 cases MUST be excluded from calibration, never guessed (BNS-EM-009)."""
    cases = load_eval_cases()
    from evals.runner import run_single_case

    l3 = [c for c in cases if c.level.value == "L3"]
    results = [run_single_case(c) for c in l3]
    calib = compute_epistemic_calibration(results)
    # In minimal environments all four L3 cases are skipped and nothing is claimed
    assert calib.total_evaluated + calib.skipped_no_backend == len(results)


def test_cross_host_consistency_single_host_not_evaluated():
    """Single-host runs MUST report cross-host consistency as not evaluated (BNS-HC-007)."""
    r1 = EvalResult(
        case_id="x",
        category="host_agent_claim",
        passed=True,
        expected_status="PERMITTED",
        actual_status="PERMITTED",
        level="L2",
        provider="replay",
    )
    out = compute_cross_host_consistency([r1])
    assert out["evaluated"] is False
    assert "agreement_rate" == None or out["agreement_rate"] is None

    r2 = EvalResult(
        case_id="x",
        category="host_agent_claim",
        passed=False,
        expected_status="PERMITTED",
        actual_status="ABSTAIN",
        level="L2",
        provider="openai",
    )
    out2 = compute_cross_host_consistency([r1, r2])
    assert out2["evaluated"] is True
    assert out2["agreement_rate"] == 0.0  # hosts disagree on the same case


def test_frontier_metrics_shape():
    results = [
        EvalResult(case_id="a", category="routing", passed=True, expected_status="PERMITTED", actual_status="PERMITTED"),
        EvalResult(case_id="b", category="routing", passed=False, expected_status="ABSTAIN", actual_status="PERMITTED"),
    ]
    fm = compute_frontier_metrics(results)
    assert fm["total"] == 2
    assert fm["passed"] == 1
    assert fm["pass_rate"] == 0.5
    assert fm["graduation_eligible"] == ["a"]
    assert len(fm["failed_cases"]) == 1


def test_markdown_report_renders_honest_numbers():
    """The rendered report MUST show gating, frontier, and union distinctly (BNS-LC-006)."""
    report = run_benchmark()
    md = format_benchmark_markdown(report)
    assert "Gating Cases" in md
    assert "Union Accuracy" in md
    assert "Frontier Calibration Track" in md
    assert "Open Known Limitations" in md
    assert "Graduation-eligible" in md
    assert "Cross-Host Consistency" in md
    assert "Adjacent-Rank Error Rate" in md
    assert "NOT a calibration claim" in md
    assert "frontier-coordinate-umap-substitution-001" in md
