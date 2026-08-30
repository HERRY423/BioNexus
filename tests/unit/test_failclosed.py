"""
Unit tests for the fail-closed execution gate (BNS-005 §6, BNS-AD-013..015).

Validates every row of the closed-by-default table:
    missing evidence            -> ABSTAIN (request data)
    invalid input               -> REFUSE
    backend unavailable         -> REFUSE (canonical); DEGRADE WITH DISCLOSURE only
                                   for frontier capabilities under opt-in + explicit fallback
    assumption violated         -> BLOCK CLAIM
    claim beyond warrant        -> BLOCK CLAIM
    external validation absent  -> CAP EVIDENCE LEVEL
plus frontier execution isolation (refused without opt-in), the clean
RUN PERMITTED exit and the CLI surface.
"""

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SRC = _REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


import pytest

pytest.importorskip("squidpy", reason="SKIPPED_NO_BACKEND: canonical backend squidpy not installed (runs in the Canonical Scientific Stack matrix)")
from bionexus.cli import main as cli_main
from bionexus.failclosed import FAIL_CLOSED_TABLE, prevent_invalid_run


def test_missing_evidence_abstains():
    d = prevent_invalid_run("Help me compare treatment and control condition DE in my scRNA data")
    assert d.prevented is True
    assert d.prevention_kind == "MISSING_EVIDENCE"
    assert d.action == "ABSTAIN (request data)"
    assert d.missing_data_requests


def test_invalid_input_refuses():
    d = prevent_invalid_run(
        "Run PyDESeq2 DE on my log-normalized matrix",
        data_metadata={"min_replicates_per_condition": 3, "is_normalized": True, "is_integer_like": False},
    )
    assert d.prevented is True
    assert d.prevention_kind == "INVALID_INPUT"
    assert d.action == "REFUSE"
    assert "BN-F001" in d.failure_mode_ids


def test_assumption_violated_blocks_claim():
    d = prevent_invalid_run(
        "Run condition DE comparing treatment vs control in 1 sample per condition",
        data_metadata={"min_replicates_per_condition": 1, "is_integer_like": True},
    )
    assert d.prevented is True
    assert d.prevention_kind == "ASSUMPTION_VIOLATED"
    assert d.action in ("REFUSE", "BLOCK CLAIM")
    assert "BN-F002" in d.failure_mode_ids


def test_claim_beyond_warrant_blocks_claim():
    d = prevent_invalid_run(
        "Use Moran's I spatial autocorrelation to prove cell-cell communication",
        data_metadata={"n_spatial_spots": 100},
    )
    assert d.prevented is True
    assert d.prevention_kind == "CLAIM_BEYOND_WARRANT"
    assert d.action == "BLOCK CLAIM"
    assert "BN-F011" in d.failure_mode_ids


def test_backend_unavailable_refuses_canonical():
    """A missing canonical backend is a strict refusal, even with degradation consent."""
    d = prevent_invalid_run(
        "Fit Kaplan-Meier survival curve for clinical cohort",
        allow_degraded=True,
    )
    assert d.prevented is True
    assert d.prevention_kind == "BACKEND_UNAVAILABLE"
    assert d.action == "REFUSE"
    assert "BN-F010" in d.failure_mode_ids


def test_backend_unavailable_degrades_only_for_opted_in_frontier():
    """DEGRADE WITH DISCLOSURE is reachable only via frontier opt-in + explicit fallback."""
    from bionexus.backends import is_available

    if is_available("gears"):
        return  # nothing to degrade when the canonical backend is present

    # No opt-in: the frontier capability is not even evaluated.
    d = prevent_invalid_run("use GEARS to predict TP53 perturbation", allow_degraded=True)
    assert d.prevented is True
    assert d.action == "REFUSE"

    # Opt-in + explicit fallback: disclosed degradation, never silent.
    d2 = prevent_invalid_run(
        "use GEARS to predict TP53 perturbation",
        allow_frontier=True,
        allow_degraded=True,
    )
    assert d2.prevented is True
    assert d2.prevention_kind == "BACKEND_UNAVAILABLE"
    assert d2.action == "DEGRADE WITH DISCLOSURE"
    assert "BN-F010" in d2.failure_mode_ids


def test_external_validation_absent_caps_evidence():
    d = prevent_invalid_run(
        "Compute Moran's I spatial autocorrelation on my Visium data",
        data_metadata={"n_spatial_spots": 100},
        claimed_maturity="SUPPORTED",
    )
    assert d.prevented is False  # run itself is fine; the claim is capped
    assert d.prevention_kind == "EXTERNAL_VALIDATION_ABSENT"
    assert d.action == "CAP EVIDENCE LEVEL"
    assert d.claimed_maturity == "SUPPORTED"
    assert d.warranted_maturity == "FRAGILE"
    assert d.failure_mode_ids == ["BN-F012"]


def test_clean_run_permitted():
    d = prevent_invalid_run(
        "Cluster my single cells and find marker genes",
        data_metadata={"is_integer_like": True},
    )
    assert d.prevented is False
    assert d.prevention_kind is None
    assert d.action == "RUN PERMITTED"


def test_external_validation_unlocks_claim():
    d = prevent_invalid_run(
        "ACMG classification complete; ClinVar expert-reviewed concordance verified",
        claimed_maturity="REPLICATED",
        has_external_validation=True,
    )
    assert d.action == "RUN PERMITTED"
    assert d.warranted_maturity == "REPLICATED"


def test_fail_closed_table_is_complete():
    """The table MUST have exactly the six prevention rows (BNS-AD-014/015)."""
    kinds = [row["prevention_kind"] for row in FAIL_CLOSED_TABLE]
    assert kinds == [
        "MISSING_EVIDENCE",
        "INVALID_INPUT",
        "BACKEND_UNAVAILABLE",
        "ASSUMPTION_VIOLATED",
        "CLAIM_BEYOND_WARRANT",
        "EXTERNAL_VALIDATION_ABSENT",
    ]
    # No row may resolve to silent execution
    for row in FAIL_CLOSED_TABLE:
        assert "SILENT" not in row["action"].upper()
        assert row["action"] != "RUN"


def test_prevent_cli(capsys):
    rc = cli_main(["prevent", "Run condition DE comparing treatment vs control with 1 replicate", "--min-replicates", "1"])
    assert rc == 1
    out = capsys.readouterr().out
    assert "prevent_invalid_run" in out
    assert "ASSUMPTION_VIOLATED" in out

    cli_main(["prevent", "Cluster my single cells", "--claim-maturity", "ROBUST"])
    out2 = capsys.readouterr().out
    assert "CAP EVIDENCE LEVEL" in out2 or "RUN PERMITTED" in out2
