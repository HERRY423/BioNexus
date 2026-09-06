"""BCTK Cross-Host Consistency development evaluator (BNS-HC-007)."""

from __future__ import annotations

import json
from pathlib import Path

from bionexus.bctk.spec import (
    BCTK_RULE_CATALOG,
    ConformanceDimension,
    DimensionResult,
    DimensionStatus,
    RuleEvaluation,
    RuleSeverity,
)
from bionexus.bctk.targets import TargetDescriptor

_LIVE_L2_PROVIDERS = frozenset({"openai", "anthropic", "gemini"})
_REPLAY_MODES = frozenset(
    {"replay", "offline", "offline_trace_replay", "headless", "simulated_trace_v1"}
)


def _is_live_l2_comparison(data: dict | None) -> bool:
    """Return True only for a live host-provider L2 matrix (BNS-HC-007).

    A headless ABSTAIN comparison between coding-agent harnesses is schema
    evidence, not live ``--provider openai|anthropic|gemini`` evaluation.
    """
    if not isinstance(data, dict):
        return False
    overall = data.get("overall") if isinstance(data.get("overall"), dict) else {}
    mode = str(data.get("execution_mode") or overall.get("execution_mode") or "").strip().casefold()
    if mode in _REPLAY_MODES:
        return False
    providers: list[str] = []
    for key in ("providers", "host_providers", "live_providers"):
        raw = data.get(key)
        if raw is None:
            raw = overall.get(key)
        if isinstance(raw, str):
            providers.append(raw)
        elif isinstance(raw, list):
            providers.extend(str(item) for item in raw)
    hosts = [str(host) for host in (data.get("hosts") or [])]
    names = {item.strip().casefold() for item in providers + hosts if str(item).strip()}
    return (
        bool(names & _LIVE_L2_PROVIDERS)
        and int(data.get("traps_compared") or 0) >= 2
        and len(data.get("hosts") or []) >= 2
    )


def evaluate_cross_host(target: TargetDescriptor, cross_host_dir: Path | None = None) -> DimensionResult:
    """
    Evaluate target conformance against cross-host evidence (BNS-HC-007).

    Evaluates:
    - BCTK-HST-001: host-native traces from >= 2 declared hosts with common traps
    - BCTK-HST-002: consistent execution under fixed seed (agreement >= 90%)
    - BCTK-HST-003: completed headless CI verification (valid comparison report schema)
    """
    if cross_host_dir is not None:
        comp_file = cross_host_dir / "COMPARISON.json"
    elif target.name.lower() in ("bionexus", "bionexus-reliability", "bionexus-plugin"):
        comp_file = target.root_path / "cross-host" / "COMPARISON.json"
    else:
        # Check target-specific cross-host directory for foreign targets
        target_comp = target.root_path / "cross-host" / target.name / "COMPARISON.json"
        comp_file = target_comp if target_comp.is_file() else (target.root_path / "cross_host_comparison.json")

    comparison_data = None
    if comp_file.is_file():
        try:
            comparison_data = json.loads(comp_file.read_text(encoding="utf-8"))
        except Exception:
            comparison_data = None

    evaluations: list[RuleEvaluation] = []
    has_live_l2 = _is_live_l2_comparison(comparison_data)
    not_live_details = {
        "target": target.name,
        "required_evidence": "live --provider openai|anthropic|gemini L2 matrix",
        "comparison_file": str(comp_file) if comp_file.is_file() else None,
    }

    # 1. BCTK-HST-001: traces from >= 2 declared hosts
    rule_001 = BCTK_RULE_CATALOG["BCTK-HST-001"]
    if has_live_l2:
        hosts_str = ", ".join(comparison_data.get("hosts", []))
        traps_n = comparison_data.get("traps_compared", 0)
        evaluations.append(
            RuleEvaluation(
                rule_id=rule_001.rule_id,
                dimension=ConformanceDimension.CROSS_HOST_CONSISTENCY,
                status=DimensionStatus.PASS,
                severity=rule_001.severity,
                message=f"Passed: verified multi-host traces from [{hosts_str}] across {traps_n} traps.",
                details={"target": target.name, "hosts": comparison_data.get("hosts", []), "traps_compared": traps_n},
            )
        )
    else:
        evaluations.append(
            RuleEvaluation(
                rule_id=rule_001.rule_id,
                dimension=ConformanceDimension.CROSS_HOST_CONSISTENCY,
                status=DimensionStatus.NOT_ASSESSED,
                severity=rule_001.severity,
                message="Not assessed: requires live host-provider traces from >= 2 of openai/anthropic/gemini. Headless coding-agent ABSTAIN comparisons do not satisfy BNS-HC-007.",
                details=not_live_details,
            )
        )

    # 2. BCTK-HST-002: repeated under fixed seed with agreement >= 90%
    rule_002 = BCTK_RULE_CATALOG["BCTK-HST-002"]
    if has_live_l2:
        agreement = comparison_data.get("overall", {}).get("agreement_rate")
        verdict = comparison_data.get("overall", {}).get("conformance_verdict")
        if agreement is not None and agreement >= 0.90 and verdict == "pass":
            evaluations.append(
                RuleEvaluation(
                    rule_id=rule_002.rule_id,
                    dimension=ConformanceDimension.CROSS_HOST_CONSISTENCY,
                    status=DimensionStatus.PASS,
                    severity=rule_002.severity,
                    message=f"Passed: cross-host agreement rate {agreement:.1%} >= 90% threshold under fixed seed.",
                    details={"target": target.name, "agreement_rate": agreement, "verdict": verdict},
                )
            )
        else:
            evaluations.append(
                RuleEvaluation(
                    rule_id=rule_002.rule_id,
                    dimension=ConformanceDimension.CROSS_HOST_CONSISTENCY,
                    status=DimensionStatus.FAIL,
                    severity=rule_002.severity,
                    message=f"Failed: agreement rate {agreement} below 90% threshold.",
                    details={"target": target.name, "agreement_rate": agreement, "verdict": verdict},
                )
            )
    else:
        evaluations.append(
            RuleEvaluation(
                rule_id=rule_002.rule_id,
                dimension=ConformanceDimension.CROSS_HOST_CONSISTENCY,
                status=DimensionStatus.NOT_ASSESSED,
                severity=rule_002.severity,
                message="Not assessed: requires a live host-provider L2 matrix with agreement >= 90%. Headless ABSTAIN comparisons are not that matrix.",
                details=not_live_details,
            )
        )

    # 3. BCTK-HST-003: completed live L2 run
    rule_003 = BCTK_RULE_CATALOG["BCTK-HST-003"]
    if has_live_l2 and comparison_data.get("per_trap"):
        evaluations.append(
            RuleEvaluation(
                rule_id=rule_003.rule_id,
                dimension=ConformanceDimension.CROSS_HOST_CONSISTENCY,
                status=DimensionStatus.PASS,
                severity=rule_003.severity,
                message="Passed: automated headless cross-host comparison report verified.",
                details={"target": target.name, "comparison_file": str(comp_file)},
            )
        )
    else:
        evaluations.append(
            RuleEvaluation(
                rule_id=rule_003.rule_id,
                dimension=ConformanceDimension.CROSS_HOST_CONSISTENCY,
                status=DimensionStatus.NOT_ASSESSED,
                severity=rule_003.severity,
                message="Not assessed: requires a completed live host-provider L2 run. Headless COMPARISON.json is not sufficient.",
                details=not_live_details,
            )
        )

    passed_count = sum(1 for e in evaluations if e.status == DimensionStatus.PASS)
    failed_count = sum(1 for e in evaluations if e.status == DimensionStatus.FAIL)
    not_assessed_count = sum(1 for e in evaluations if e.status == DimensionStatus.NOT_ASSESSED)
    critical_failures = sum(
        1 for e in evaluations if e.status == DimensionStatus.FAIL and e.severity == RuleSeverity.CRITICAL
    )

    if not_assessed_count == len(evaluations):
        overall_status = DimensionStatus.NOT_ASSESSED
    elif failed_count > 0:
        overall_status = DimensionStatus.FAIL
    elif passed_count == len(evaluations):
        overall_status = DimensionStatus.PASS
    else:
        overall_status = DimensionStatus.WARN

    score_pct = (passed_count / len(evaluations)) * 100.0 if evaluations else 0.0

    return DimensionResult(
        dimension=ConformanceDimension.CROSS_HOST_CONSISTENCY,
        status=overall_status,
        score_percentage=score_pct,
        passed_rules=passed_count,
        total_rules=len(evaluations),
        critical_failures=critical_failures,
        rule_evaluations=evaluations,
    )
