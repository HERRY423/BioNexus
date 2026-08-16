"""
Unit tests for the BioNexus Standards Alignment Registry (BNS-016):
honest statuses, verbatim disclaimer, closed vocabulary, CLI surface.
"""

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SRC = _REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import pytest

from bionexus.cli import main as cli_main
from bionexus.standards import (
    ALIGNMENTS,
    STANDARDS_DISCLAIMER,
    STATUSES,
    StandardAlignment,
    alignments_report,
    render_alignments,
)


def test_disclaimer_is_verbatim_and_honest():
    """BNS-IO-008: the disclaimer MUST be published verbatim, no endorsement claims."""
    assert "not an industry standard" in STANDARDS_DISCLAIMER
    assert "never declared" in STANDARDS_DISCLAIMER
    report = alignments_report()
    assert report["disclaimer"] == STANDARDS_DISCLAIMER


def test_status_vocabulary_is_closed():
    assert STATUSES == ("implemented", "aligned", "proposal", "tracked")
    with pytest.raises(ValueError):
        StandardAlignment(key="x", name="X", url="https://x", status="certified-by-ga4gh", role="nope")


def test_registry_covers_required_alignments():
    """The four alignment families from BNS-016 MUST be present."""
    keys = set(ALIGNMENTS)
    assert {"prov-o", "ro-crate", "workflow-run-crate", "bco"} <= keys          # data standards
    assert {"bioschemas", "nf-core"} <= keys                                    # aligned ecosystems
    assert "ga4gh-ai-workstream" in keys                                        # proposal venue
    assert {"elixir", "scverse", "bioconductor", "workflowhub"} <= keys         # tracked venues


def test_statuses_reflect_reality():
    """Implemented entries point at shipped modules; proposal never claims adoption."""
    implemented = [a for a in ALIGNMENTS.values() if a.status == "implemented"]
    assert len(implemented) >= 4
    # RO-Crate / BCO / Workflow Run Crate / PROV-O are implemented only because
    # the interop layer exists and is tested
    assert ALIGNMENTS["ro-crate"].status == "implemented"
    assert ALIGNMENTS["bco"].status == "implemented"
    assert ALIGNMENTS["workflow-run-crate"].status == "implemented"
    # GA4GH is a proposal, never an endorsement or membership claim
    ga4gh = ALIGNMENTS["ga4gh-ai-workstream"]
    assert ga4gh.status == "proposal"
    assert "implementation proposal" in ga4gh.role


def test_alignment_report_counts():
    report = alignments_report()
    counts = report["status_counts"]
    assert sum(counts.values()) == len(ALIGNMENTS)
    assert counts["implemented"] >= 4
    assert counts["proposal"] >= 1


def test_render_includes_disclaimer_and_table():
    rendered = render_alignments()
    assert STANDARDS_DISCLAIMER in rendered
    assert "| Standard | Status | Role in BioNexus | Since |" in rendered
    for key in ("ro-crate", "bco", "ga4gh-ai-workstream"):
        assert ALIGNMENTS[key].name in rendered


def test_standards_cli(capsys):
    assert cli_main(["standards"]) == 0
    out = capsys.readouterr().out
    assert "Standards Alignment" in out
    assert "not an industry standard" in out
    assert "GA4GH" in out and "`proposal`" in out

    assert cli_main(["standards", "--json"]) == 0
    import json

    payload = json.loads(capsys.readouterr().out)
    assert payload["disclaimer"] == STANDARDS_DISCLAIMER
    assert "alignments" in payload
