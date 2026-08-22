"""
BCTK Development Diagnostic Reporting.

Renders:
1. Terminal Visual Dashboard (ANSI / ASCII)
2. Machine-Readable JSON Export
3. Markdown development report

Badge issuance is suspended during the Scientific Trust Reset.
"""

from __future__ import annotations

from bionexus.bctk.spec import ConformanceReport, ConformanceTier, DimensionStatus


class BadgeIssuanceSuspended(RuntimeError):
    """Raised whenever code attempts to issue a self-certified BCTK badge."""


def render_terminal_report(report: ConformanceReport, verbose: bool = False) -> str:
    """Render a visual terminal dashboard summarizing BCTK test results."""
    lines = []
    lines.append("=" * 80)
    lines.append("               BioNexus BCTK Development Diagnostic")
    lines.append("=" * 80)
    lines.append(f"Target:         {report.target_name} (Type: {report.target_type})")
    lines.append(f"Scientific ABI: v{report.abi_version} | BCTK Version: v{report.bctk_version}")
    lines.append(f"Timestamp:      {report.timestamp}")
    lines.append(f"Assessment:     {report.assessment_status}")
    lines.append(f"Trust decision: {report.trust_decision}")
    lines.append(f"Target digest:  sha256:{report.target_content_sha256 or 'UNAVAILABLE'}")
    lines.append(f"Report digest:  sha256:{report.cryptographic_fingerprint}")
    lines.append("-" * 80)
    lines.append(f"{'DIMENSION':<32} {'STATUS':<8} {'SCORE':<9} {'RULES':<14} {'CRIT FAILS'}")
    lines.append("-" * 80)

    for dim_name, res in report.dimension_results.items():
        status_str = f"[{res.status.value}]" if res.status == DimensionStatus.PASS else f"*{res.status.value}*"
        pass_ratio = f"{res.passed_rules}/{res.total_rules}"
        crit_str = str(res.critical_failures) if res.critical_failures > 0 else "-"
        lines.append(
            f"{dim_name:<32} {status_str:<8} {res.score_percentage:>5.1f}%   {pass_ratio:<14} {crit_str}"
        )
        if verbose:
            for ev in res.rule_evaluations:
                ev_mark = "  ✓" if ev.status == DimensionStatus.PASS else "  ✗"
                lines.append(f"  {ev_mark} {ev.rule_id}: {ev.message}")

    lines.append("-" * 80)
    lines.append(f"INTERNAL DIAGNOSTIC SCORE: {report.overall_score:.1f}%")
    lines.append(f"Certification state:       {report.conformance_tier.value}")
    lines.append(f"Unverified score mapping:  {report.diagnostic_tier.value}")
    if report.biofailurebench_score is not None:
        lines.append(f"BioFailureBench Defense:   {report.biofailurebench_score:.1f}%")

    if report.critical_violations:
        lines.append("\n[CRITICAL VIOLATIONS]")
        for cv in report.critical_violations:
            lines.append(f" - [{cv['rule_id']}] ({cv['dimension']}): {cv['message']}")

    lines.append("\n[BADGING SUSPENDED] Independent, target-bound evidence is required before badge issuance.")
    lines.append("=" * 80)
    return "\n".join(lines)


def render_markdown_report(report: ConformanceReport) -> str:
    """Render a non-certifying BCTK development diagnostic."""
    lines = []
    lines.append(f"# BioNexus BCTK Development Diagnostic: `{report.target_name}`\n")
    lines.append("> **Not a certificate or endorsement.** Badge issuance is suspended until independent, target-bound evidence is verified.\n")
    lines.append(f"**Assessment Status**: `{report.assessment_status}`  ")
    lines.append(f"**Certification State**: `{report.conformance_tier.value}`  ")
    lines.append(f"**Unverified Diagnostic Tier**: `{report.diagnostic_tier.value}`  ")
    lines.append(f"**Internal Diagnostic Score**: `{report.overall_score:.1f}%`  ")
    lines.append(f"**Scientific ABI**: `v{report.abi_version}`  ")
    lines.append(f"**Evaluation Timestamp**: `{report.timestamp}`  ")
    lines.append(f"**Target Content Digest**: `sha256:{report.target_content_sha256 or 'UNAVAILABLE'}`  ")
    lines.append(f"**Diagnostic Payload Digest (not a signature)**: `sha256:{report.cryptographic_fingerprint}`\n")

    lines.append("## 1. Conformance Dimension Breakdown\n")
    lines.append("| Dimension | Status | Score | Passed / Total | Critical Violations |")
    lines.append("| :--- | :---: | :---: | :---: | :---: |")

    for dim_name, res in report.dimension_results.items():
        lines.append(
            f"| **{dim_name}** | `{res.status.value}` | `{res.score_percentage:.1f}%` | "
            f"{res.passed_rules} / {res.total_rules} | {res.critical_failures} |"
        )

    lines.append("\n## 2. Normative Rule Audit Log\n")
    for dim_name, res in report.dimension_results.items():
        lines.append(f"### {dim_name}")
        for ev in res.rule_evaluations:
            status_icon = "✅" if ev.status == DimensionStatus.PASS else ("⚠️" if ev.status == DimensionStatus.WARN else "❌")
            lines.append(f"- {status_icon} **{ev.rule_id}** (`{ev.severity.value}`): {ev.message}")
        lines.append("")

    if report.critical_violations:
        lines.append("## 3. Critical Violations & Remediation Roadmap\n")
        for cv in report.critical_violations:
            lines.append(f"- **{cv['rule_id']}** ({cv['dimension']}): {cv['message']}")

    return "\n".join(lines)


def generate_svg_badge(tier: ConformanceTier) -> str:
    """Refuse badge issuance until independent certification governance exists."""
    raise BadgeIssuanceSuspended(
        f"BCTK badge issuance is suspended; requested tier {tier.value!r} is only an internal diagnostic mapping."
    )
