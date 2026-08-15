"""
Unit tests for Scientific Epistemic Evidence Calibration Engine.

Validates:
1. Computation of Overconfidence Rate (Epistemic Hubris) when predicted rank > true rank.
2. Computation of Underconfidence Rate (Epistemic Timidity) when predicted rank < true rank.
3. Computation of Ordinal Calibration Error (OCE).
4. Generation of Maturity Confusion Matrix.
5. Macro-F1 across active maturity levels.
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

from evals.metrics import compute_epistemic_calibration
from evals.schema import EvalResult


def test_epistemic_calibration_perfect():
    """Verify perfect calibration results in 0% over/underconfidence and OCE = 0."""
    results = [
        EvalResult(
            case_id="c1",
            category="routing",
            passed=True,
            expected_status="PERMITTED",
            actual_status="PERMITTED",
            expected_maturity="UNASSESSED",
            level="L1",
        ),
        EvalResult(
            case_id="c2",
            category="refusal",
            passed=True,
            expected_status="ABSTAIN",
            actual_status="ABSTAIN",
            expected_maturity="ABSTAIN",
            level="L1",
        ),
        EvalResult(
            case_id="c3",
            category="scientific_outcome",
            passed=True,
            expected_status="PERMITTED",
            actual_status="PERMITTED",
            expected_maturity="SUPPORTED",
            level="L3",
        ),
    ]

    report = compute_epistemic_calibration(results)
    assert report.total_evaluated == 3
    assert report.exact_accuracy == 1.0
    assert report.overconfidence_rate == 0.0
    assert report.underconfidence_rate == 0.0
    assert report.ordinal_calibration_error == 0.0
    assert report.brier_calibration_score == 1.0
    assert report.macro_f1 == 1.0


def test_epistemic_calibration_detects_overconfidence():
    """Verify overconfidence (predicting SUPPORTED when expected is PRELIMINARY) is caught."""
    results = [
        EvalResult(
            case_id="c1",
            category="routing",
            passed=True,
            expected_status="PERMITTED",
            actual_status="PERMITTED",
            expected_maturity="PRELIMINARY",
            actual_maturity="SUPPORTED",  # Overconfident! Rank 3 vs Rank 1
            level="L1",
        ),
    ]

    report = compute_epistemic_calibration(results)
    assert report.overconfidence_count == 1
    assert report.overconfidence_rate == 1.0
    assert report.underconfidence_count == 0
    assert report.ordinal_calibration_error == 2.0  # Rank difference |3 - 1| = 2


def test_epistemic_calibration_detects_underconfidence():
    """Verify underconfidence (predicting PRELIMINARY when expected is REPLICATED) is caught."""
    results = [
        EvalResult(
            case_id="c1",
            category="scientific_outcome",
            passed=True,
            expected_status="PERMITTED",
            actual_status="PERMITTED",
            expected_maturity="REPLICATED",
            actual_maturity="PRELIMINARY",  # Underconfident! Rank 1 vs Rank 5
            level="L3",
        ),
    ]

    report = compute_epistemic_calibration(results)
    assert report.underconfidence_count == 1
    assert report.underconfidence_rate == 1.0
    assert report.overconfidence_count == 0
    assert report.ordinal_calibration_error == 4.0  # Rank difference |1 - 5| = 4
