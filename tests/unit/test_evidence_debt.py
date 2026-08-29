"""
Unit tests for the BioNexus Evidence Debt Engine (BNS-021).

Tests:
1. Evidence Debt item taxonomy & severity weighting.
2. Epistemic DAG keystone bottleneck detection.
3. Payoff leverage score calculation & optimal repayment ranking.
4. Report rendering (Terminal, Markdown, Mermaid DAG).
5. CLI commands (`bionexus debt audit`, `payoff`, `graph`, `sample`).
"""

from __future__ import annotations

import json

from bionexus.contracts import ConclusionMaturity
from bionexus.debt import (
    DebtKind,
    EvidenceDebtEngine,
    create_sample_debt_ledger,
    render_markdown_debt_report,
    render_mermaid_debt_dag,
    render_terminal_debt_report,
)
from bionexus.ledger import ClaimLedger, ClaimRecord, EvidenceRef

# ==============================================================================
# 1. Evidence Debt Detection & Taxonomy Tests
# ==============================================================================


def test_detect_heuristic_annotation_debt():
    """Detects heuristic cell-type annotation shortcut on upstream transformation node."""
    ledger = ClaimLedger()
    ledger.add_evidence(
        EvidenceRef(
            ref_id="REF-ANNOTATION-TCELL",
            kind="transformation",
            summary="Manual gating for CD4/CD8 T-cells",
            maturity=ConclusionMaturity.FRAGILE.value,
            provenance={"heuristic_marker_gating": True},
        )
    )
    ledger.add_claim(
        ClaimRecord(
            claim_id="CLAIM-1",
            statement="CD8+ T-cells express PDCD1 under treatment",
            capability_id="scrna.pseudobulk_de",
            supported_by=["REF-ANNOTATION-TCELL"],
        )
    )

    report = EvidenceDebtEngine.audit_ledger(ledger)
    assert report.total_claims == 1
    assert report.total_debt_items >= 1

    kinds = [d.debt_kind for d in report.debt_items]
    assert DebtKind.HEURISTIC_DEPENDENCY in kinds


def test_detect_domain_mismatch_debt():
    """Detects atlas reference domain mismatch."""
    ledger = ClaimLedger()
    ledger.add_evidence(
        EvidenceRef(
            ref_id="REF-ATLAS-TRANSFER",
            kind="transformation",
            summary="PBMC reference atlas projected on lung tumor",
            maturity=ConclusionMaturity.FRAGILE.value,
            provenance={"domain_mismatch": True},
        )
    )
    ledger.add_claim(
        ClaimRecord(
            claim_id="CLAIM-2",
            statement="Tumor infiltrating lymphocytes match PBMC signatures",
            capability_id="scrna.pseudobulk_de",
            supported_by=["REF-ATLAS-TRANSFER"],
        )
    )

    report = EvidenceDebtEngine.audit_ledger(ledger)
    assert any(d.debt_kind == DebtKind.DOMAIN_MISMATCH for d in report.debt_items)


def test_detect_causal_identification_gap():
    """Detects unsupported causal claims from observational correlation."""
    ledger = ClaimLedger()
    ledger.add_evidence(
        EvidenceRef(
            ref_id="EVID-OBS-01",
            kind="statistical_result",
            summary="Correlational p-value < 0.01",
            maturity=ConclusionMaturity.SUPPORTED.value,
        )
    )
    ledger.add_claim(
        ClaimRecord(
            claim_id="CLAIM-CAUSAL",
            statement="Treatment causes downregulation of TP53",
            capability_id="scrna.pseudobulk_de",
            supported_by=["EVID-OBS-01"],
        )
    )

    report = EvidenceDebtEngine.audit_ledger(ledger)
    assert any(d.debt_kind == DebtKind.CAUSAL_IDENTIFICATION_GAP for d in report.debt_items)


# ==============================================================================
# 2. Keystone & Payoff Multiplier Tests
# ==============================================================================


def test_epistemic_keystone_payoff_multiplier():
    """Verifies that an upstream keystone affecting 7 claims earns a 70x payoff multiplier."""
    ledger = create_sample_debt_ledger()
    report = EvidenceDebtEngine.audit_ledger(ledger)

    assert report.total_claims == 20
    assert len(report.epistemic_keystones) >= 2

    # Check that TRANSFORM-ANNOTATION-X or TRANSFORM-SPATIAL-MAPPING is identified as top keystone
    keystone_ids = [k["root_node_id"] for k in report.epistemic_keystones]
    assert "TRANSFORM-ANNOTATION-X" in keystone_ids
    assert "TRANSFORM-SPATIAL-MAPPING" in keystone_ids

    # Top priority in repayment schedule should have high payoff multiplier
    top_pri = report.optimal_repayment_schedule[0]
    assert top_pri.payoff_multiplier >= 40.0
    assert len(top_pri.claims_unblocked) >= 7


# ==============================================================================
# 3. Report Rendering Tests
# ==============================================================================


def test_render_debt_reports():
    """Tests terminal, markdown, and Mermaid rendering of Evidence Debt."""
    ledger = create_sample_debt_ledger()
    report = EvidenceDebtEngine.audit_ledger(ledger)

    term = render_terminal_debt_report(report)
    assert "BioNexus Scientific Evidence Debt Report" in term
    assert "EPISTEMIC KEYSTONES" in term
    assert "OPTIMAL EVIDENCE REPAYMENT SCHEDULE" in term

    md = render_markdown_debt_report(report)
    assert "# 📑 BioNexus Scientific Evidence Debt Report" in md
    assert "Optimal Scientific Repayment Schedule" in md

    mermaid = render_mermaid_debt_dag(report, ledger)
    assert "```mermaid" in mermaid
    assert "graph TD" in mermaid
    assert "-->|degrades|" in mermaid


# ==============================================================================
# 4. CLI Execution Tests
# ==============================================================================


def test_cli_debt_sample(tmp_path, capsys):
    """Tests 'bionexus debt sample' CLI."""
    from bionexus.cli import main

    out_file = tmp_path / "test_ledger.json"
    exit_code = main(["debt", "sample", "-o", str(out_file), "--json"])
    assert exit_code == 0
    assert out_file.is_file()

    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["total_claims"] == 20
    assert data["total_debt_items"] >= 10
    assert "optimal_repayment_schedule" in data


def test_cli_debt_payoff(tmp_path, capsys):
    """Tests 'bionexus debt payoff' CLI."""
    from bionexus.cli import main

    out_file = tmp_path / "test_ledger.json"
    create_sample_debt_ledger().save(out_file)

    exit_code = main(["debt", "payoff", str(out_file), "--markdown"])
    assert exit_code == 0

    captured = capsys.readouterr()
    assert "Optimal Scientific Repayment Schedule" in captured.out


def test_cli_debt_graph(tmp_path, capsys):
    """Tests 'bionexus debt graph' CLI."""
    from bionexus.cli import main

    out_file = tmp_path / "test_ledger.json"
    create_sample_debt_ledger().save(out_file)

    exit_code = main(["debt", "graph", str(out_file)])
    assert exit_code == 0

    captured = capsys.readouterr()
    assert "graph TD" in captured.out
