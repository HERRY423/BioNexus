"""
Unit tests for BioNexus Result Verification (BNS-013, firewall entry 3):
Claim–Evidence Ledger verification semantics.
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
from bionexus.contracts import ConclusionMaturity
from bionexus.ledger import ClaimLedger, ClaimRecord, EvidenceRef
from bionexus.verification import (
    locate_ledger,
    render_verification,
    verify_ledger,
    verify_results,
    write_example_ledger,
)


def _demo_ledger(tmp_path: Path) -> Path:
    return write_example_ledger(tmp_path / "results" / "bionexus.ledger.json")


def test_example_ledger_verifies_clean(tmp_path):
    """The CXCL13+ reference scenario verifies with exit code 0."""
    ledger_path = _demo_ledger(tmp_path)
    report = verify_results(tmp_path / "results")
    assert report.passed
    assert report.exit_code == 0
    claim = report.claims[0]
    assert claim.claim_id == "CLAIM-DEMO-017"
    assert claim.evidence_status == "SUPPORTED"  # min supporting maturity with cross-method
    symbols = [e["symbol"] for e in claim.evidence_lines]
    assert "[OK]" in symbols and "[~]" in symbols  # FRAGILE sensitivity shown honestly
    assert locate_ledger(tmp_path / "results") == ledger_path


def test_rendered_block_matches_contract(tmp_path):
    _demo_ledger(tmp_path)
    report = verify_results(tmp_path / "results")
    rendered = render_verification(report)
    for token in ("CLAIM", "Evidence:", "Warrant:", "Not warranted:", "OVERALL: VERIFIED"):
        assert token in rendered, token
    assert "CXCL13+ T cells are enriched in tumor" in rendered


def test_causal_language_fails_verification(tmp_path, capsys):
    ledger = ClaimLedger()
    ledger.add_evidence(EvidenceRef("E1", "method_run", "enrichment test", ConclusionMaturity.SUPPORTED.value))
    ledger.add_claim(
        ClaimRecord(
            claim_id="C1",
            statement="CXCL13+ T cells drive tumor progression",
            capability_id="scrna.pseudobulk_de",
            supported_by=["E1"],
        )
    )
    report = verify_ledger(ledger)
    assert not report.passed
    assert report.exit_code == 1
    claim = report.claims[0]
    assert any("causal" in nw.lower() for nw in claim.not_warranted)

    path = tmp_path / "bad.ledger.json"
    ledger.save(path)
    assert cli_main(["verify", str(path)]) == 1
    out = capsys.readouterr().out
    assert "VERIFICATION FAILED" in out


def test_unsupported_and_contradicted_claims_fail(tmp_path):
    ledger = ClaimLedger()
    ledger.add_evidence(EvidenceRef("E1", "dataset", "cohort A", ConclusionMaturity.SUPPORTED.value))
    ledger.add_evidence(EvidenceRef("E2", "database", "contradicting source", ConclusionMaturity.SUPPORTED.value))
    ledger.add_claim(ClaimRecord(claim_id="C-EMPTY", statement="an unevidenced claim"))
    ledger.add_claim(
        ClaimRecord(
            claim_id="C-CONTRA",
            statement="a contradicted claim",
            supported_by=["E1"],
            contradicted_by=["E2"],
        )
    )
    report = verify_ledger(ledger)
    assert not report.passed
    statuses = {c.claim_id: c.evidence_status for c in report.claims}
    assert statuses["C-EMPTY"] == "ABSTAIN"
    assert statuses["C-CONTRA"] == "CONFLICTED"
    empty = next(c for c in report.claims if c.claim_id == "C-EMPTY")
    assert any(e["symbol"] == "[X]" for e in empty.evidence_lines)


def test_forbidden_claim_catalog_surfaced(tmp_path):
    _demo_ledger(tmp_path)
    report = verify_results(tmp_path / "results")
    claim = report.claims[0]
    assert any("causal_interaction" in nw for nw in claim.not_warranted)


def test_verify_missing_ledger_errors(tmp_path, capsys):
    assert cli_main(["verify", str(tmp_path)]) == 1
    assert "No Claim–Evidence Ledger found" in capsys.readouterr().err


def test_verify_json_projection(tmp_path, capsys):
    _demo_ledger(tmp_path)
    assert cli_main(["verify", str(tmp_path / "results"), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["passed"] is True
    assert payload["claims"][0]["evidence_status"] == "SUPPORTED"
