"""
Unit tests for the BioNexus Scientific Preflight (BNS-013, firewall entry 1).

Validates the output contract (INTENT / DATA STATE / RISKS / DECISION /
ALLOWED / FORBIDDEN CLAIM / REMEDY), the fail-closed decision vocabulary,
exit-code semantics, and trap surfacing from real metadata.
"""

import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SRC = _REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from bionexus.cli import main as cli_main
from bionexus.preflight import (
    INTENT_ALIASES,
    PreflightReport,
    render_preflight,
    resolve_intent,
    run_preflight,
)


def test_intent_aliases_resolve_to_live_contracts():
    """Every intent alias MUST resolve to a live capability contract."""
    for alias, cap_id in INTENT_ALIASES.items():
        cap = resolve_intent(alias)
        assert cap is not None, alias
        assert cap.id == cap_id, (alias, cap.id)


def test_preflight_output_contract_blocked(tmp_path):
    """Confounded design produces the seven-section block and exit code 1."""
    report = run_preflight(
        intent="differential-expression",
        metadata={
            "min_replicates_per_condition": 2,
            "is_integer_like": True,
            "condition_confounded_with": "donor",
        },
    )
    assert isinstance(report, PreflightReport)
    assert report.capability_id == "scrna.pseudobulk_de"
    assert report.decision == "ABSTAIN"
    assert report.action == "REFUSE"
    assert report.exit_code == 1
    assert "BN-F006" in report.failure_mode_ids
    # ALLOWED comes from taxonomy acceptable_degradation only
    assert report.allowed and all(a.startswith("at most:") or a.startswith("nothing") for a in report.allowed)
    # FORBIDDEN CLAIM is mechanically derived from the catalog + ceiling
    assert any("causal_interaction" in f for f in report.forbidden_claims)
    assert any("maturity above" in f for f in report.forbidden_claims)
    assert report.remedies

    rendered = render_preflight(report)
    for section in ("INTENT", "DATA STATE", "RISKS", "DECISION", "ALLOWED", "FORBIDDEN CLAIM", "REMEDY"):
        assert section in rendered, section


def test_preflight_permits_clean_request_and_caps_maturity(canonical_backends_available):
    """A sound request passes with exit 0; REPLICATED is capped at the ceiling."""
    report = run_preflight(
        intent="differential-expression",
        metadata={
            "min_replicates_per_condition": 4,
            "is_integer_like": True,
            "multiple_testing_correction": True,
            "claimed_maturity": "REPLICATED",
        },
    )
    assert report.decision == "PERMITTED"
    assert report.exit_code == 0
    assert report.claimed_maturity == "REPLICATED"
    assert report.warranted_maturity == "SUPPORTED"  # pseudobulk ceiling
    assert any("REPLICATED" in f for f in report.forbidden_claims)


def test_preflight_missing_evidence_exits_two():
    """Replicate metadata absent -> NEEDS_DATA with exit code 2."""
    report = run_preflight(
        intent="differential-expression",
        query="differential expression between treatment and control please",
        metadata={"is_integer_like": True},
    )
    assert report.decision in ("NEEDS_DATA",)
    assert report.exit_code == 2


def test_preflight_unknown_intent_requests_data():
    report = run_preflight(intent="not-a-real-intent")
    assert report.capability_id is None
    assert report.exit_code == 2
    assert report.remedies


def test_preflight_metadata_path_json(tmp_path):
    """--metadata JSON file is loaded and drives the decision."""
    meta_file = tmp_path / "meta.json"
    meta_file.write_text(
        json.dumps(
            {
                "min_replicates_per_condition": 3,
                "is_integer_like": True,
                "identifier_namespace": "ensembl_v110",
                "reference_namespace": "ensembl_v92",
            }
        ),
        encoding="utf-8",
    )
    report = run_preflight(intent="differential-expression", metadata_path=meta_file)
    assert report.decision == "ABSTAIN"
    assert "BN-F004" in report.failure_mode_ids
    assert any(r.failure_id == "BN-F004" for r in report.risks)


def test_preflight_unverifiable_state_is_distinct(tmp_path):
    """A missing h5ad is a failed check, not an unverifiable pass (BNS-FW-008)."""
    report = run_preflight(data_path=tmp_path / "nope.h5ad", intent="clustering")
    marks = {c.name: c.passed for c in report.data_state}
    assert marks.get("input") is False

    report2 = run_preflight(intent="clustering")  # no data path at all
    assert any(c.passed is None for c in report2.data_state)


def test_preflight_cli_exit_codes(tmp_path, capsys, canonical_backends_available):
    """CLI wiring: exit 0 clean, exit 1 refused, JSON projection available."""
    meta_clean = tmp_path / "clean.json"
    meta_clean.write_text(
        json.dumps({"min_replicates_per_condition": 4, "is_integer_like": True}), encoding="utf-8"
    )
    assert cli_main(["preflight", "--intent", "differential-expression", "--metadata", str(meta_clean)]) == 0
    out = capsys.readouterr().out
    assert "DECISION" in out and "FORBIDDEN CLAIM" in out

    meta_bad = tmp_path / "bad.json"
    meta_bad.write_text(
        json.dumps({"min_replicates_per_condition": 1, "is_integer_like": True}), encoding="utf-8"
    )
    assert cli_main(["preflight", "--intent", "differential-expression", "--metadata", str(meta_bad)]) == 1
    capsys.readouterr()

    assert cli_main(
        ["preflight", "--intent", "differential-expression", "--metadata", str(meta_bad), "--json"]
    ) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["decision"] == "ABSTAIN"
    assert payload["capability_id"] == "scrna.pseudobulk_de"

    assert cli_main(["preflight"]) == 2  # no intent/query -> help
