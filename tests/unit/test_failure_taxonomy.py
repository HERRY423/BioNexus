"""
Unit tests for the BioNexus Scientific Failure Taxonomy (BNS-011).

Validates:
1. Record completeness: every BN-Fxxx has definition/example/detection/behavior.
2. Required behaviors use the fail-closed vocabulary only.
3. Benchmark case references resolve to real eval cases.
4. Violation classification maps runtime text onto taxonomy IDs.
5. CLI surface.
"""

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SRC = _REPO_ROOT / "src"
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from bionexus.cli import main as cli_main
from bionexus.failures import (
    FAILURE_TAXONOMY,
    classify_violation,
    failure_modes_by_capability,
    failure_to_dict,
    get_failure_mode,
    list_failure_modes,
    taxonomy_summary,
)

FAIL_CLOSED_VOCAB = ("REFUSE", "ABSTAIN", "BLOCK CLAIM", "DEGRADE WITH DISCLOSURE", "CAP EVIDENCE LEVEL", "CONFLICTED")


def test_taxonomy_contains_core_twelve_modes():
    """The taxonomy MUST cover BN-F001..BN-F012 (BNS-FT-002)."""
    for i in range(1, 13):
        assert f"BN-F{i:03d}" in FAILURE_TAXONOMY
    expected_names = {
        "BN-F001": "Assay-state confusion",
        "BN-F002": "Pseudoreplication",
        "BN-F003": "Unsupported annotation",
        "BN-F004": "Identifier mismatch",
        "BN-F005": "Missing multiple-testing correction",
        "BN-F006": "Invalid model assumption",
        "BN-F007": "Parameter instability",
        "BN-F008": "Cross-database contradiction",
        "BN-F009": "Missing spatial provenance",
        "BN-F010": "Backend degradation masquerading",
        "BN-F011": "Claim inflation",
        "BN-F012": "Unexecuted maturity claim",
    }
    for fid, name in expected_names.items():
        assert FAILURE_TAXONOMY[fid].name == name


def test_every_failure_record_is_complete():
    """Every mode MUST be a complete record (BNS-FT-001)."""
    for fid, mode in FAILURE_TAXONOMY.items():
        assert mode.failure_id == fid
        assert len(mode.definition) > 40, fid
        assert mode.example
        assert len(mode.affected_capabilities) >= 1, fid
        assert mode.detection_rule
        assert mode.required_behavior
        assert mode.acceptable_degradation
        # Fail-closed vocabulary only (BNS-FT-003)
        assert any(v in mode.required_behavior for v in FAIL_CLOSED_VOCAB), fid


def test_benchmark_case_references_resolve():
    """Referenced benchmark cases MUST exist in the eval suites (BNS-FT-005)."""
    from evals.runner import load_eval_cases

    known_ids = {c.id for c in load_eval_cases()}
    for mode in FAILURE_TAXONOMY.values():
        for case_id in mode.benchmark_cases:
            assert case_id in known_ids, f"{mode.failure_id} -> unknown case {case_id}"


def test_open_gaps_are_flagged_not_hidden():
    """Modes without benchmark coverage MUST be flagged open_gap (BNS-FT-005).

    Honest state since BioFailureBench (BNS-014): every mode BN-F001..BN-F012
    carries at least one benchmark case, so the open-gap set is empty. If a new
    mode is added without coverage, this test fails until a trap is attached
    (suites grow by attaching cases to open gaps, BNS-FT-008).
    """
    summary = taxonomy_summary()
    assert set(summary["open_gaps"]) == set()
    covered = [m for m in FAILURE_TAXONOMY.values() if not m.open_gap]
    assert all(m.benchmark_cases for m in covered)
    # The three formerly-open gaps are now wired to deterministic detection
    for fid in ("BN-F004", "BN-F005", "BN-F008"):
        assert FAILURE_TAXONOMY[fid].benchmark_cases, fid
        assert FAILURE_TAXONOMY[fid].open_gap is False


def test_capability_index_and_queries():
    """Inverted index + query APIs MUST work for every capability."""
    index = failure_modes_by_capability()
    assert "BN-F002" in index["scrna.pseudobulk_de"]
    assert "BN-F009" in index["spatial.morans_svg"]
    assert "BN-F008" in index["variant.acmg_classification"]
    assert get_failure_mode("BN-F001").name == "Assay-state confusion"
    spatial_modes = list_failure_modes(capability_id="spatial.morans_svg")
    assert all("spatial.morans_svg" in m.affected_capabilities for m in spatial_modes)
    assert "affected_capabilities" in failure_to_dict(FAILURE_TAXONOMY["BN-F007"])


def test_classify_violation_signatures():
    """Runtime violation text MUST map onto taxonomy IDs (BNS-FT-006)."""
    assert "BN-F002" in classify_violation("Fewer than 2 biological replicates per experimental condition.")
    assert "BN-F001" in classify_violation("Normalized continuous matrix passed where raw counts required.")
    assert "BN-F011" in classify_violation("Forbidden claim 'causal_interaction' requested from capability.")
    assert "BN-F010" in classify_violation("Backend 'lifelines' is not installed; heuristic fallback used.")
    assert classify_violation("completely unrelated text about cats") == []


def test_failures_cli(capsys):
    """CLI exposes the taxonomy: list + show."""
    assert cli_main(["failures", "list"]) == 0
    out = capsys.readouterr().out
    assert "BN-F001" in out
    assert "Open gaps (no benchmark coverage yet):" in out  # honest even when empty
    assert cli_main(["failures", "show", "BN-F002"]) == 0
    out = capsys.readouterr().out
    assert "Pseudoreplication" in out and "Detection rule" in out
    assert cli_main(["failures", "show", "BN-F999"]) == 1
