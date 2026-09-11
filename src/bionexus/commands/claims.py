"""Claims command handlers, extracted without changing command semantics."""


from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from bionexus.intent_router import RoutingStatus, route_scientific_intent


def handle_failures(args: argparse.Namespace) -> int:
    """Handle the 'failures' command (BNS-011): scientific failure taxonomy."""
    from bionexus.failures import (
        failure_modes_matrix,
        failure_to_dict,
        get_failure_mode,
        get_taxonomy_v1,
        list_failure_modes,
        taxonomy_summary,
    )

    action = getattr(args, "failures_action", "list")
    if action == "list":
        if args.json:
            print(json.dumps([failure_to_dict(m) for m in list_failure_modes()], indent=2))
            return 0
        summary = taxonomy_summary()
        print(f"\n=== BioNexus Scientific Failure Taxonomy (BNS-011): {summary['total_modes']} modes ===\n")
        print("| ID | Failure Mode | Category | Severity | Required Behavior | Benchmark Cases | Open Gap |")
        print("|---|---|---|---|---|---|---|")
        for m in list_failure_modes():
            gap = "**OPEN**" if m.open_gap else ""
            print(f"| `{m.failure_id}` | {m.name} | `{m.category}` | `{m.severity}` | {m.required_behavior.split(';')[0]} | {len(m.benchmark_cases)} | {gap} |")
        print(f"\nOpen gaps (no benchmark coverage yet): {', '.join(summary['open_gaps'])}\n")
        return 0

    elif action == "matrix":
        mat = failure_modes_matrix()
        if getattr(args, "json", False):
            print(json.dumps(mat, indent=2))
            return 0
        print("\n=== BioNexus Failure Taxonomy v1: Capability Mapping Matrix ===\n")
        print("| Capability | Total Modes | Critical Modes | Associated Failure Modes |")
        print("|---|---|---|---|")
        for cid, info in sorted(mat.items()):
            modes_str = ", ".join(f"`{fid}`" for fid in info["failure_mode_ids"])
            print(f"| `{cid}` | {info['failure_mode_count']} | {info['critical_count']} | {modes_str} |")
        print()
        return 0

    elif action == "taxonomy":
        tax = get_taxonomy_v1()
        if getattr(args, "json", False):
            print(json.dumps(tax, indent=2))
            return 0
        print(f"\n=== BioNexus Scientific Failure Taxonomy v1 ({tax['schema_version']}) ===\n")
        print(f"Total Modes: {tax['total_modes']}")
        for cat, fids in tax["categories"].items():
            print(f"  * Category `{cat}`: {', '.join(fids)}")
        print()
        return 0

    elif action == "show":
        try:
            mode = get_failure_mode(args.id)
        except KeyError as e:
            print(f"[ERROR] {e}", file=sys.stderr)
            return 1
        if args.json:
            print(json.dumps(failure_to_dict(mode), indent=2))
            return 0
        print(f"\n### {mode.failure_id}: {mode.name}\n")
        print(f"**Category**: `{mode.category}` | **Severity**: `{mode.severity}`\n")
        print(f"**Definition**: {mode.definition}\n")
        print(f"**Example**: {mode.example}\n")
        print(f"**Affected capabilities**: {', '.join(f'`{c}`' for c in mode.affected_capabilities)}\n")
        print(f"**Detection rule**: {mode.detection_rule}\n")
        print(f"**Required behavior**: {mode.required_behavior}\n")
        print(f"**Acceptable degradation**: {mode.acceptable_degradation}\n")
        print(f"**Benchmark cases**: {', '.join(f'`{c}`' for c in mode.benchmark_cases) or '*none (open gap)*'}\n")
        return 0
    return 0


def handle_ledger(args: argparse.Namespace) -> int:
    """Handle the 'ledger' command (BNS-012): claim-evidence ledger inspection."""
    from bionexus.ledger import ClaimLedger

    action = getattr(args, "ledger_action", "show")
    ledger = ClaimLedger.load(args.path)
    if action == "show":
        if args.json:
            print(json.dumps(ledger.to_dict(), indent=2))
            return 0
        print(f"\n=== Claim–Evidence Ledger: {args.path} ===\n")
        print(f"**Evidence refs**: {len(ledger.evidence)} | **Claims**: {len(ledger.claims)}\n")
        for cid, claim in ledger.claims.items():
            print(f"- **`{cid}`** [{claim.evidence_status}] {claim.statement}")
            if claim.supported_by:
                print(f"  - supported_by: {', '.join(claim.supported_by)}")
            if claim.contradicted_by:
                print(f"  - contradicted_by: {', '.join(claim.contradicted_by)}")
            if claim.depends_on:
                print(f"  - depends_on: {', '.join(claim.depends_on)}")
        print()
        return 0
    elif action == "jsonld":
        print(json.dumps(ledger.to_jsonld(), indent=2))
        return 0
    return 0


def handle_route(args: argparse.Namespace) -> int:
    """Handle the 'route' command for scientific intent routing."""
    meta = {}
    if getattr(args, "min_replicates", None) is not None:
        meta["min_replicates_per_condition"] = args.min_replicates
    if getattr(args, "is_normalized", False):
        meta["is_normalized"] = True
        meta["is_integer_like"] = False

    raw_factors = getattr(args, "factors", None)
    factors_list = [f.strip() for f in raw_factors.split(",") if f.strip()] if raw_factors else None

    raw_extras = getattr(args, "documented_extras", None)
    extras_list = [e.strip() for e in raw_extras.split(",") if e.strip()] if raw_extras else None

    decision = route_scientific_intent(
        query=args.query,
        data_path=args.data,
        data_metadata=meta,
        allow_degraded=args.allow_degraded,
        allow_frontier=getattr(args, "allow_frontier", False),
        research_purpose=getattr(args, "purpose", None),
        override_justification=getattr(args, "override_justification", ""),
        lab_policy=getattr(args, "lab_policy", None),
        evidence_factors=factors_list,
        claim_context=getattr(args, "claim_class", None),
        documented_extras=extras_list,
    )

    if args.json:
        print(json.dumps(decision.to_dict(), indent=2))
        return 0 if decision.status == RoutingStatus.PERMITTED else 1

    print("\n=== BioNexus Scientific Intent Routing Decision ===")
    print(f'**Query**: "{args.query}"')
    print(f"**Routing Status**: `{decision.status.value}`")
    if decision.matched_capability:
        print(
            f"**Matched Capability**: `{decision.matched_capability.id}` ({decision.matched_capability.display_name})"
        )
        print(f"**Target Skill**: `{decision.target_skill}`")
    print(f"**Rationale**: {decision.rationale}\n")

    if decision.status == RoutingStatus.PERMITTED:
        print("[PERMITTED] Analysis is scientifically valid.")
        if decision.recommended_script:
            print(f"  - Recommended Script: `{decision.recommended_script}`")
        if decision.recommended_command:
            print(f"  - Recommended Command: `{decision.recommended_command}`")
        return 0

    elif decision.status == RoutingStatus.NEEDS_DATA:
        print("[NEEDS DATA] Additional scientific metadata or inputs required:")
        for req in decision.missing_data_requests:
            print(f"  * {req}")
        return 2

    elif decision.status == RoutingStatus.ABSTAIN:
        print("[ABSTAIN / REFUSED] Analysis is scientifically invalid or prohibited:")
        for v in decision.violations:
            print(f"  - {v}")
        print("\nActionable Scientific Remedies:")
        for r in decision.remedies:
            print(f"  * {r}")
        return 1

    elif decision.status == RoutingStatus.EXPERIMENTAL_CAPABILITY_REQUIRES_OPT_IN:
        print("[FRONTIER] Frontier capability detected — execution requires explicit opt-in:")
        for v in decision.violations:
            print(f"  - {v}")
        print("\nRemedy:")
        for r in decision.remedies:
            print(f"  * {r}")
        return 1

    elif decision.status == RoutingStatus.DEGRADED_ADVISORY:
        print("[DEGRADED ADVISORY] Execution permitted via Grade C heuristic fallback:")
        for v in decision.violations:
            print(f"  - {v}")
        return 0

    return 0


def handle_audit_claims(args: argparse.Namespace) -> int:
    """Audit text or report artifact for prohibited scientific claims."""
    from bionexus.claim_checker import audit_prohibited_claims

    target = args.target
    p = Path(target)
    if p.exists() and p.is_file():
        content = p.read_text(encoding="utf-8")
    else:
        content = target

    res = audit_prohibited_claims(
        content,
        capability_id=getattr(args, "capability", None),
    )

    if getattr(args, "json", False):
        print(json.dumps(res.to_dict(), indent=2))
        return 0 if res.passed else 1

    print("\n=== BioNexus Prohibited Claims Audit ===")
    if res.passed:
        print("[PASS] Zero prohibited scientific claims detected.")
        return 0
    else:
        print(f"[FAIL] Detected {res.violation_count} prohibited claim violation(s):")
        for i, v in enumerate(res.violations, start=1):
            print(f'  {i}. [{v.violation_type.value}] Matched: "{v.matched_text}"')
            print(f"     Rule: {v.rule_description}")
            print(f"     Remedy: {v.remedy}")
        return 1


def handle_parse_claim(args: argparse.Namespace) -> int:
    """Parse natural language scientific claim into canonical ScientificClaimIR (BNS-017)."""
    from bionexus.claim_semantics import DeterministicClaimParser

    target = args.claim
    p = Path(target)
    if p.exists() and p.is_file():
        content = p.read_text(encoding="utf-8")
    else:
        content = target

    sentences = [s.strip() for s in re.split(r"[.\n\r]+", content) if len(s.strip()) > 3]
    parsed_claims = [DeterministicClaimParser.parse(s).to_dict() for s in sentences]

    if getattr(args, "json", False) or len(parsed_claims) > 1:
        print(json.dumps(parsed_claims if len(parsed_claims) > 1 else parsed_claims[0], indent=2))
        return 0

    ir = parsed_claims[0]
    print("\n=== BioNexus Scientific Claim IR (BNS-017) ===")
    print(f"Claim ID:          {ir['claim_id']}")
    print(f"Source Text:       \"{ir['source_text']}\"")
    print(f"Subject Entity:    {ir['subject_entity']['name']} (Features: {ir['subject_entity']['features']})")
    print(f"Object Entity:     {ir['object_entity']['name'] if ir['object_entity'] else 'None'}")
    print(f"Relationship:      {ir['relationship']}")
    print(f"Directionality:    {ir['direction']}")
    print(f"Population Scope:  {ir['population_scope'] or 'unspecified'} ({ir['generalization_scope']})")
    print(f"Association Type:  {ir['association_type']}")
    print(f"Causal Strength:   {ir['causal_strength']}")
    print(f"Mechanism Depth:   {ir['mechanism_depth']}")
    print(f"Claim Class:       {ir['claim_class']}")
    print(f"Qualifiers:        {ir['qualifiers'] or 'none'}")
    print(f"Negated:           {ir['negated']}")
    return 0


def handle_warrant_claim(args: argparse.Namespace) -> int:
    """Evaluate scientific claim against EvidenceProfile using Deterministic Warrant Engine (BNS-017)."""
    from bionexus.claim_semantics import DeterministicClaimParser, DeterministicWarrantEngine, EvidenceProfile

    target = args.claim
    p = Path(target)
    if p.exists() and p.is_file():
        content = p.read_text(encoding="utf-8")
    else:
        content = target

    ev_profile = EvidenceProfile()
    if getattr(args, "evidence_json", None):
        ep = Path(args.evidence_json)
        if ep.exists():
            data = json.loads(ep.read_text(encoding="utf-8"))
            ev_profile = EvidenceProfile(**data)

    if getattr(args, "spatial", False):
        ev_profile.spatial_colocalization = True
    if getattr(args, "ligand_receptor", False):
        ev_profile.ligand_receptor_inference = True
    if getattr(args, "perturbation", False):
        ev_profile.perturbation = True
    if getattr(args, "replicates", 0) > 0:
        ev_profile.biological_replicates_count = args.replicates
        ev_profile.pseudobulk_aggregated = True

    claim_ir = DeterministicClaimParser.parse(content)
    res = DeterministicWarrantEngine.evaluate(claim_ir, ev_profile)

    if getattr(args, "json", False):
        print(json.dumps(res.to_dict(), indent=2))
        return 0 if res.is_fully_warranted else 1

    print("\n=== BioNexus Deterministic Warrant Engine (BNS-017) ===")
    print(f"Claim:             \"{claim_ir.source_text}\"")
    print(f"Requested Class:   {res.requested_claim_class}")
    print(f"Warranted Class:   {res.warranted_claim_class}")
    print(f"Evidence Ceiling:  {res.evidence_ceiling}")
    print(f"Overall Status:    {'[WARRANTED]' if res.is_fully_warranted else '[NOT FULLY WARRANTED]'}")
    print("\nTier-by-Tier Evaluation:")
    for tier_name, tier_verdict in res.tier_verdicts.items():
        status_tag = f"[{tier_verdict.status.value}]"
        print(f"  - {tier_name:<22} {status_tag:<20} {tier_verdict.rationale}")

    if res.evidence_gaps:
        print("\nMissing Evidence Gaps:")
        for gap in res.evidence_gaps:
            print(f"  [!] {gap}")

    if res.remedies:
        print("\nActionable Remedies:")
        for rem in res.remedies:
            print(f"  -> {rem}")

    return 0 if res.is_fully_warranted else 1


def handle_rule(args: argparse.Namespace) -> int:
    """Handle 'rule' subcommands (show, list, challenge, list-challenges) for BNS-018."""
    from bionexus.rule_calibration import ChallengeNetwork

    network = ChallengeNetwork()
    action = getattr(args, "rule_action", None)

    if action == "list":
        if getattr(args, "json", False):
            print(json.dumps([r.to_dict() for r in network.rules.values()], indent=2))
            return 0

        print("\n=== BioNexus Development Rule Registry (BNS-018) ===")
        print(f"Registry Status: {network.registry_metadata.get('registry_status', 'NOT_ASSESSED')}")
        print(f"Rule Propositions: {len(network.rules)}\n")
        print(f"{'Rule ID':<35} {'Epistemic Kind':<24} {'Consensus':<14} {'Platforms / Regimes'}")
        print("-" * 90)
        for rid, rule in network.rules.items():
            platforms = []
            for reg in rule.applicable_regimes:
                platforms.extend(reg.target_platforms)
            plat_str = ", ".join(platforms[:3]) or "universal"
            print(f"{rid:<35} {rule.epistemic_kind.value:<24} {rule.consensus.value:<14} {plat_str}")
        print("\nNo packaged rule carries verified external calibration or endorsement.\n")
        return 0

    elif action == "show":
        rule = network.get_rule(args.rule_id)
        if not rule:
            print(f"[ERROR] Rule '{args.rule_id}' not found in registry.")
            return 1

        if getattr(args, "json", False):
            print(json.dumps(rule.to_dict(), indent=2))
            return 0

        print("\n============================================================")
        print(f"=== BioNexus Rule Proposition: {rule.rule_id} ===")
        print("============================================================")
        print(f"* Epistemic Kind:       {rule.epistemic_kind.value}")
        print(f"* Category:             {rule.category.value} ({rule.enforcement_level.value})")
        print(f"* Consensus State:      {rule.consensus.value}")
        print(f"* Source Citation:      {rule.source_citation}")
        print(f"* Evidence Status:      {rule.metadata.get('evidence_status', 'NOT_ASSESSED')}")
        print(f"* Review Status:        {rule.metadata.get('review_status', 'NOT_ASSESSED')}")

        if rule.proposition.statement:
            print("\n[Scientific Proposition]")
            print(f"  Statement:  {rule.proposition.statement}")
            if rule.proposition.formal_predicate:
                print(f"  Predicate:  {rule.proposition.formal_predicate}")
            if rule.proposition.underlying_assumptions:
                print(f"  Assumptions: {'; '.join(rule.proposition.underlying_assumptions)}")

        if rule.applicable_regimes:
            print(f"\n[Applicable Regimes] ({len(rule.applicable_regimes)}):")
            for reg in rule.applicable_regimes:
                print(f"  - [{reg.regime_id}] {reg.description}")
                print(f"    Platforms: {', '.join(reg.target_platforms)}, Min Samples: {reg.min_samples}")

        if rule.platform_calibrations:
            print(f"\n[Platform Calibrations] ({len(rule.platform_calibrations)}):")
            for pcal in rule.platform_calibrations:
                print(f"  - {pcal.platform_name}: recommended threshold = {pcal.recommended_threshold}, safe range = {pcal.safe_operating_range}")
                if pcal.calibration_notes:
                    print(f"    Notes: {pcal.calibration_notes}")

        if rule.dataset_calibrations:
            print(f"\n[Benchmark Dataset Calibrations] ({len(rule.dataset_calibrations)}):")
            for dcal in rule.dataset_calibrations:
                print(f"  - {dcal.dataset_name} (n={dcal.sample_size}): {dcal.empirical_metric_name} = {dcal.empirical_metric_value} (95% CI: {dcal.confidence_interval})")

        if rule.sensitivity_analysis:
            print("\n[Sensitivity Analysis]")
            for sens in rule.sensitivity_analysis:
                cliff = " [!] CLIFF-EDGE RISK" if sens.cliff_edge_risk else ""
                print(f"  - Parameter '{sens.parameter_name}' (nominal={sens.nominal_value}){cliff}: Elasticity={sens.elasticity_score}")
                print(f"    Summary: {sens.risk_summary}")

        if rule.known_counterexamples:
            print(f"\n[Known Counterexamples] ({len(rule.known_counterexamples)}):")
            for ce in rule.known_counterexamples:
                print(f"  - [{ce.counterexample_id}] {ce.description}")
                print(f"    Mitigation: {ce.mitigation_strategy}")

        if rule.reviewers:
            print(f"\n[Peer Reviewer Attestations] ({len(rule.reviewers)}):")
            for rev in rule.reviewers:
                print(f"  - {rev.reviewer_name} ({rev.institution}) [{rev.verdict}]: \"{rev.review_comments}\" ({rev.attestation_date})")
        else:
            print("\n[Verified External Attestations] 0 — NOT_ASSESSED")

        print()
        return 0

    elif action == "challenge":
        try:
            ch = network.submit_challenge(
                target_rule_id=args.rule_id,
                challenger_identity=args.challenger,
                challenge_type=args.type,
                title=args.title,
                description=args.description,
                empirical_evidence_refs=[args.dataset] if getattr(args, "dataset", None) else [],
            )
            network.save()
            print("\n[OK] Formal Challenge submitted successfully!")
            print(f"Challenge ID: {ch.challenge_id}")
            print(f"Target Rule:  {ch.target_rule_id}")
            print(f"Type:         {ch.challenge_type.value}")
            print(f"Status:       {ch.status.value}")
            print("The challenge is recorded as PROPOSED. It cannot change consensus without verified signed review attestations.\n")
            return 0
        except Exception as e:
            print(f"[ERROR] Failed to submit challenge: {e}")
            return 1

    elif action == "list-challenges":
        if getattr(args, "json", False):
            print(json.dumps([c.to_dict() for c in network.challenges.values()], indent=2))
            return 0

        print("\n=== BioNexus Scientific Challenge Network Ledger ===")
        print(f"Total Challenges: {len(network.challenges)}\n")
        print(f"{'Challenge ID':<35} {'Target Rule':<25} {'Type':<25} {'Status'}")
        print("-" * 95)
        for cid, ch in network.challenges.items():
            print(f"{cid:<35} {ch.target_rule_id:<25} {ch.challenge_type.value:<25} {ch.status.value}")
        print()
        return 0

    return 0

