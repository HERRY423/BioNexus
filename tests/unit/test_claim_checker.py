"""
Unit tests for BioNexus Prohibited Claims and Hallucination Auditor.

Validates:
1. Detection of unverified cell-type assertions (Cluster X is CellType Y).
2. Allow-list for exploratory / putative / candidate qualifiers.
3. Detection of causal DE overclaims from rank_genes_groups.
4. Detection of regulatory / FDA Part 11 overclaims without RUO.
5. Detection of model substitutions (BLOSUM heuristic labeled as ESM-2).
6. Detection of hazard ratio claims without Cox model.
7. CLI 'bionexus audit-claims' command.
"""

import sys
from pathlib import Path

# Ensure src is on sys.path
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SRC = _REPO_ROOT / "src"
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from bionexus.claim_checker import ClaimViolationType, audit_prohibited_claims
from bionexus.cli import main as cli_main


def test_cell_type_hallucination_detection():
    """Verify unverified cell-type claims are flagged."""
    bad_text = "The analysis finished. Cluster 0 is CD8+ T cell, Cluster 1 is B cell."
    res = audit_prohibited_claims(bad_text)
    assert res.passed is False
    assert res.violation_count == 2
    types = [v.violation_type for v in res.violations]
    assert ClaimViolationType.CELL_TYPE_HALLUCINATION in types

    # Good text with exploratory qualifiers
    good_text = "Cluster 0 shows high CD3D expression, representing candidate T-cell markers (exploratory)."
    res_good = audit_prohibited_claims(good_text)
    assert res_good.passed is True


def test_causal_de_overclaim_detection():
    """Verify rank_genes_groups causal claims are flagged."""
    bad_text = "Scanpy rank_genes_groups marker p-values prove that drug treatment caused 200 DEGs."
    res = audit_prohibited_claims(bad_text)
    assert res.passed is False
    assert any(v.violation_type == ClaimViolationType.CAUSAL_TREATMENT_DE_OVERCLAIM for v in res.violations)

    # Good text stating cannot prove
    good_text = (
        "Marker p-values from rank_genes_groups cannot prove causal treatment effects without biological replicates."
    )
    res_good = audit_prohibited_claims(good_text)
    assert res_good.passed is True


def test_regulatory_overclaim_detection():
    """Verify Part 11 / GxP overclaims without RUO disclaimer are flagged."""
    bad_text = "BioNexus audit logs are FDA 21 CFR Part 11 compliant and certified for clinical diagnosis."
    res = audit_prohibited_claims(bad_text)
    assert res.passed is False
    assert any(v.violation_type == ClaimViolationType.REGULATORY_COMPLIANCE_OVERCLAIM for v in res.violations)

    # Good text with RUO disclaimer
    good_text = "Research Use Only. BioNexus is not certified under FDA 21 CFR Part 11 or CLIA/CAP."
    res_good = audit_prohibited_claims(good_text)
    assert res_good.passed is True


def test_cli_audit_claims(capsys):
    """Verify CLI audit-claims subcommand."""
    # Bad text returns 1
    rc_bad = cli_main(["audit-claims", "Cluster 0 is CD8+ T cell"])
    assert rc_bad == 1
    captured_bad = capsys.readouterr()
    assert "[FAIL]" in captured_bad.out
    assert "CELL_TYPE_HALLUCINATION" in captured_bad.out

    # Good text returns 0
    rc_good = cli_main(["audit-claims", "Cluster 0 is an exploratory candidate cluster. Research Use Only."])
    assert rc_good == 0
    captured_good = capsys.readouterr()
    assert "[PASS]" in captured_good.out


def test_structured_ir_causal_mechanism_audit():
    """Verify BNS-017 structured IR catches unbacked causal assertions with actionable remedies."""
    bad_causal = "We conclude that IFNG directly causes STAT1 phosphorylation and drives cell differentiation."
    res = audit_prohibited_claims(bad_causal)
    assert res.passed is False
    assert any(
        v.violation_type in (ClaimViolationType.UNWARRANTED_CAUSAL_MECHANISM, ClaimViolationType.CAUSAL_TREATMENT_DE_OVERCLAIM)
        for v in res.violations
    )
    causal_v = [v for v in res.violations if v.violation_type == ClaimViolationType.UNWARRANTED_CAUSAL_MECHANISM]
    if causal_v:
        assert "perturbation" in causal_v[0].remedy.lower() or "downgrade" in causal_v[0].remedy.lower()


def test_structured_ir_cleared_by_verified_factors():
    """Supplying verified perturbation and confound controls factors warrants causal claims."""
    causal_text = "We conclude that IFNG drives STAT1 activation in the analyzed cohort."
    # Without factors -> fails
    res_unbacked = audit_prohibited_claims(causal_text)
    assert res_unbacked.passed is False

    # With verified perturbation & confound factors -> passes
    res_backed = audit_prohibited_claims(
        causal_text,
        evidence_factors=["perturbation", "confound_controls", "sample_design"],
    )
    assert res_backed.passed is True


def test_structured_ir_cleared_by_tool_receipt():
    """Supplying a verified tool execution receipt certifying perturbation clears causal claim."""
    from bionexus.tool_receipt import create_tool_receipt

    receipt = create_tool_receipt(
        plugin_id="bionexus-gold",
        plugin_version="1.0.0-rc.3",
        tool_name="functional.crispr_perturbation",
        request_payload={"target": "IFNG"},
        response_payload={"knockout_validated": True},
        execution_status="SUCCESS",
        metadata={"perturbation": True, "confound_controls": True, "sample_design": True},
    )

    causal_text = "We conclude that IFNG drives STAT1 activation in the analyzed cohort."
    res = audit_prohibited_claims(causal_text, tool_receipts=[receipt])
    assert res.passed is True

