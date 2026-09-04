"""
Unit tests for the BioNexus Conformance Test Kit (BCTK).

Tests:
1. Target discovery across all target types (plugin, python module, script, artifact).
2. All 8 Conformance Dimension Evaluators.
3. Legacy diagnostic tier calculation and global NOT_ASSESSED gate.
4. Target-bound diagnostic fingerprint generation.
5. Reporting rendering and badge refusal.
6. CLI commands (`bctk test`, `bctk inspect`, `bctk badge`, `bctk rules`, `bctk init`).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from bionexus.bctk.dimensions import (
    evaluate_abstention,
    evaluate_backend_identity,
    evaluate_biological_semantics,
    evaluate_claim_warrant,
    evaluate_cross_host,
    evaluate_failure_handling,
    evaluate_input_honesty,
    evaluate_provenance,
)
from bionexus.bctk.engine import run_conformance_test
from bionexus.bctk.reporters import (
    BadgeIssuanceSuspended,
    generate_svg_badge,
    render_markdown_report,
    render_terminal_report,
)
from bionexus.bctk.spec import (
    ConformanceDimension,
    ConformanceTier,
    DimensionResult,
    DimensionStatus,
    calculate_conformance_tier,
)
from bionexus.bctk.targets import TargetDescriptor, TargetType, detect_target

# ==============================================================================
# 1. Target Discovery Tests
# ==============================================================================


def test_detect_target_plugin_dir():
    """Detects plugin / skill directories properly."""
    repo_root = Path(__file__).resolve().parents[2]
    plugin_path = repo_root / "plugins" / "bionexus"
    target = detect_target(plugin_path)
    assert target.target_type in (TargetType.PLUGIN, TargetType.SKILL, TargetType.REPO_ROOT)
    assert target.root_path.exists()


def test_detect_target_python_callable():
    """Detects python module:function callable targets."""
    target = detect_target("bionexus.contracts:refuse")
    assert target.target_type == TargetType.PYTHON_MODULE
    assert target.callable_func is not None
    assert callable(target.callable_func)


def test_detect_target_script_file(tmp_path):
    """Detects standalone script files."""
    script_file = tmp_path / "my_pipeline.py"
    script_file.write_text("print('hello')", encoding="utf-8")
    target = detect_target(script_file)
    assert target.target_type == TargetType.CLI_SCRIPT
    assert len(target.script_paths) == 1


def test_detect_target_artifact_bundle(tmp_path):
    """Detects artifact bundle json files."""
    art_file = tmp_path / "run.json"
    art_file.write_text("{}", encoding="utf-8")
    target = detect_target(art_file)
    assert target.target_type == TargetType.ARTIFACT_BUNDLE


# ==============================================================================
# 2. Conformance Dimension Evaluator Tests
# ==============================================================================


def test_biological_semantics_evaluator():
    """Biological semantics must not self-award PASS without target fixtures."""
    target = TargetDescriptor(name="test_target", target_type=TargetType.SKILL, root_path=Path("."))
    res = evaluate_biological_semantics(target)
    assert res.dimension == ConformanceDimension.BIOLOGICAL_SEMANTICS
    assert res.status == DimensionStatus.NOT_ASSESSED
    assert res.score_percentage == 0.0
    assert len(res.rule_evaluations) >= 4


def test_input_honesty_evaluator():
    """Input honesty requires target-bound fixtures."""
    target = TargetDescriptor(name="test_target", target_type=TargetType.SKILL, root_path=Path("."))
    res = evaluate_input_honesty(target)
    assert res.dimension == ConformanceDimension.INPUT_STATE_HONESTY
    assert res.status == DimensionStatus.NOT_ASSESSED
    assert res.score_percentage == 0.0
    assert res.critical_failures == 0


def test_backend_identity_evaluator():
    """Backend identity cannot be inferred from BioNexus's own environment."""
    target = TargetDescriptor(name="test_target", target_type=TargetType.SKILL, root_path=Path("."))
    res = evaluate_backend_identity(target)
    assert res.dimension == ConformanceDimension.BACKEND_IDENTITY
    assert res.status == DimensionStatus.NOT_ASSESSED
    assert res.score_percentage == 0.0
    assert res.critical_failures == 0


def test_provenance_evaluator():
    """Provenance requires target-produced artifacts."""
    target = TargetDescriptor(name="test_target", target_type=TargetType.SKILL, root_path=Path("."))
    res = evaluate_provenance(target)
    assert res.dimension == ConformanceDimension.PROVENANCE
    assert res.status == DimensionStatus.NOT_ASSESSED
    assert res.score_percentage == 0.0


def test_claim_warrant_evaluator():
    """Claim-warrant checks require target output fixtures."""
    target = TargetDescriptor(name="test_target", target_type=TargetType.SKILL, root_path=Path("."))
    res = evaluate_claim_warrant(target)
    assert res.dimension == ConformanceDimension.CLAIM_WARRANT
    assert res.status == DimensionStatus.NOT_ASSESSED
    assert res.score_percentage == 0.0


def test_abstention_evaluator():
    """Abstention requires a target-native refusal trace."""
    target = TargetDescriptor(name="test_target", target_type=TargetType.SKILL, root_path=Path("."))
    res = evaluate_abstention(target)
    assert res.dimension == ConformanceDimension.ABSTENTION
    assert res.status == DimensionStatus.NOT_ASSESSED
    assert res.score_percentage == 0.0


def test_failure_handling_evaluator():
    """A BioFailureBench corpus check is not target failure-handling evidence."""
    target = TargetDescriptor(name="test_target", target_type=TargetType.SKILL, root_path=Path("."))
    res = evaluate_failure_handling(target)
    assert res.dimension == ConformanceDimension.FAILURE_HANDLING
    assert res.status == DimensionStatus.NOT_ASSESSED
    assert res.score_percentage == 0.0


def test_cross_host_evaluator():
    """Cross-host claims require actual host-native evidence."""
    target = TargetDescriptor(name="test_target", target_type=TargetType.SKILL, root_path=Path("."))
    res = evaluate_cross_host(target)
    assert res.dimension == ConformanceDimension.CROSS_HOST_CONSISTENCY
    assert res.status == DimensionStatus.NOT_ASSESSED
    assert res.score_percentage == 0.0


def test_cross_host_headless_repo_comparison_is_not_live_l2():
    """The committed 6-trap ABSTAIN comparison is not a BNS-HC-007 live matrix."""
    repo = Path(__file__).resolve().parents[2]
    target = TargetDescriptor(name="bionexus", target_type=TargetType.PLUGIN, root_path=repo)
    res = evaluate_cross_host(target)
    assert res.status == DimensionStatus.NOT_ASSESSED
    assert res.score_percentage == 0.0
    assert all(item.status == DimensionStatus.NOT_ASSESSED for item in res.rule_evaluations)


def test_cross_host_live_provider_matrix_can_pass(tmp_path):
    """A live openai/anthropic matrix with agreement still may PASS."""
    payload = {
        "hosts": ["openai", "anthropic"],
        "providers": ["openai", "anthropic"],
        "execution_mode": "live",
        "traps_compared": 6,
        "per_trap": [{"trap_id": "BF-001", "consistent": True}],
        "overall": {"agreement_rate": 1.0, "conformance_verdict": "pass"},
    }
    (tmp_path / "COMPARISON.json").write_text(json.dumps(payload), encoding="utf-8")
    target = TargetDescriptor(name="fixture", target_type=TargetType.PLUGIN, root_path=tmp_path)
    res = evaluate_cross_host(target, cross_host_dir=tmp_path)
    assert res.status == DimensionStatus.PASS
    assert res.passed_rules == 3


# ==============================================================================
# 3. Tier Calculation & Cryptographic Fingerprinting Tests
# ==============================================================================


def test_calculate_conformance_tier_gold():
    """Tests GOLD tier calculation when all dimensions pass."""
    dummy_results = {
        ConformanceDimension.BACKEND_IDENTITY.value: DimensionResult(
            dimension=ConformanceDimension.BACKEND_IDENTITY,
            status=DimensionStatus.PASS,
            score_percentage=100.0,
            passed_rules=4,
            total_rules=4,
            critical_failures=0,
        ),
        ConformanceDimension.ABSTENTION.value: DimensionResult(
            dimension=ConformanceDimension.ABSTENTION,
            status=DimensionStatus.PASS,
            score_percentage=100.0,
            passed_rules=3,
            total_rules=3,
            critical_failures=0,
        ),
    }
    tier = calculate_conformance_tier(98.0, dummy_results, critical_failures=0)
    assert tier == ConformanceTier.GOLD


def test_calculate_conformance_tier_blocked_by_critical_failure():
    """Critical failures disqualify from conformance."""
    dummy_results = {}
    tier = calculate_conformance_tier(98.0, dummy_results, critical_failures=1)
    assert tier == ConformanceTier.NON_CONFORMANT


def test_full_engine_run_and_fingerprint():
    """Engine is target-bound but cannot certify during the trust reset."""
    report = run_conformance_test(".")
    assert report.conformance_tier == ConformanceTier.NOT_ASSESSED
    assert report.badge_eligible is False
    assert report.trust_decision == "NOT_ASSESSED"
    assert len(report.target_content_sha256) == 64
    assert report.target_file_count > 0
    assert len(report.dimension_results) == 8
    assert report.profile_results["BNS-Core"]["status"] == "NOT_ASSESSED"
    assert report.profile_results["BNS-Full"]["status"] == "NOT_ASSESSED"
    assert report.profile_results["BNS-Full"]["certification_effect"] == "NONE"
    assert len(report.cryptographic_fingerprint) == 64

    # Verify deterministic fingerprint
    fp2 = report.compute_fingerprint()
    assert report.cryptographic_fingerprint == fp2


def test_target_content_change_invalidates_report_binding(tmp_path):
    target = tmp_path / "target.py"
    target.write_text("VALUE = 1\n", encoding="utf-8")
    first = run_conformance_test(target)
    target.write_text("VALUE = 2\n", encoding="utf-8")
    second = run_conformance_test(target)
    assert first.target_content_sha256 != second.target_content_sha256
    assert first.cryptographic_fingerprint != second.cryptographic_fingerprint


def test_target_snapshot_ignores_local_codex_workspaces(tmp_path):
    target = tmp_path / "target.py"
    target.write_text("VALUE = 1\n", encoding="utf-8")
    baseline = run_conformance_test(tmp_path)
    local_runtime = tmp_path / ".codex-review-probe"
    local_runtime.mkdir()
    (local_runtime / "generated.py").write_text("LOCAL = True\n", encoding="utf-8")
    after = run_conformance_test(tmp_path)
    assert after.target_content_sha256 == baseline.target_content_sha256


# ==============================================================================
# 4. Reporter Tests
# ==============================================================================


def test_reporters_render():
    """Reports disclose diagnostic status and badge generation refuses."""
    report = run_conformance_test(".")
    term = render_terminal_report(report, verbose=True)
    assert "BCTK Development Diagnostic" in term
    assert "BIOLOGICAL SEMANTICS" in term
    assert "BACKEND IDENTITY" in term

    md = render_markdown_report(report)
    assert "# BioNexus BCTK Development Diagnostic" in md
    assert "Not a certificate or endorsement" in md
    assert "sha256:" in md

    with pytest.raises(BadgeIssuanceSuspended):
        generate_svg_badge(ConformanceTier.GOLD)


def test_bctk_cli_test_and_badge_fail_closed(capsys, tmp_path):
    from bionexus.bctk.cli import main as bctk_main

    target = tmp_path / "target.py"
    target.write_text("print('diagnostic')\n", encoding="utf-8")
    assert bctk_main(["test", str(target), "--json"]) == 2
    report = json.loads(capsys.readouterr().out)
    assert report["conformance_tier"] == "NOT_ASSESSED"
    assert report["badge_eligible"] is False
    assert bctk_main(["badge", "--tier", "GOLD"]) == 2
    assert "suspended" in capsys.readouterr().err.lower()
    assert not (tmp_path / "bionexus-conformance-badge.svg").exists()


# ==============================================================================
# 5. CLI Interface Tests
# ==============================================================================


def test_bctk_cli_rules(capsys):
    """Tests 'bctk rules' CLI execution."""
    from bionexus.bctk.cli import main as bctk_main

    exit_code = bctk_main(["rules", "--json"])
    assert exit_code == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert "BCTK-SEM-001" in data
    assert "BCTK-BAK-001" in data


def test_bctk_cli_inspect(capsys):
    """Tests 'bctk inspect' CLI execution."""
    from bionexus.bctk.cli import main as bctk_main

    exit_code = bctk_main(["inspect", "plugins/bionexus", "--json"])
    assert exit_code == 0
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert "name" in data
    assert "type" in data


def test_bctk_cli_init(tmp_path):
    """Tests 'bctk init' configuration scaffolding."""
    from bionexus.bctk.cli import main as bctk_main

    cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        exit_code = bctk_main(["init"])
        assert exit_code == 0
        assert (tmp_path / ".bctk.yaml").is_file()
    finally:
        os.chdir(cwd)
