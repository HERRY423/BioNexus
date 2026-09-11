"""Standards command handlers, extracted without changing command semantics."""


from __future__ import annotations

import argparse
import json
import sys

from bionexus.capabilities import (
    get_capability,
    list_capabilities,
)


def handle_interop(args: argparse.Namespace) -> int:
    """Handle the 'interop' command (BNS-016): standards-based exports."""
    from bionexus.interop import (
        export_bco,
        export_ro_crate,
        export_workflow_run_crate,
        ledger_to_ro_crate,
        load_adjacent_ledger,
        load_interop_source,
        run_bundle_to_bco,
        run_bundle_to_ro_crate,
        run_bundle_to_workflow_run_crate,
        validate_bco,
        validate_ro_crate,
        validate_workflow_run_crate,
    )
    from bionexus.ledger import ClaimLedger

    action = getattr(args, "interop_action", "ro-crate")
    out = getattr(args, "out", None)

    try:
        if action in ("ro-crate", "bco"):
            if out is None:
                kind, manifest, siblings = load_interop_source(args.path)
                if action == "ro-crate":
                    doc = (
                        ledger_to_ro_crate(ClaimLedger.from_dict(manifest))
                        if kind == "ledger"
                        else run_bundle_to_ro_crate(manifest, siblings)
                    )
                    errors = validate_ro_crate(doc)
                else:
                    if kind != "run":
                        print(
                            "[ERROR] BioCompute Objects describe computations: export a run capsule "
                            "(run.json); ledgers export as RO-Crate / PROV-O.",
                            file=sys.stderr,
                        )
                        return 1
                    doc = run_bundle_to_bco(manifest, siblings)
                    errors = validate_bco(doc)
                print(json.dumps(doc, indent=2))
                return 0 if not errors else 1

            target, _errors = (
                export_ro_crate(args.path, out) if action == "ro-crate" else export_bco(args.path, out)
            )
            print(f"[OK] {'RO-Crate' if action == 'ro-crate' else 'BioCompute Object'} written to: {target}")
            return 0

        elif action == "wfrun-crate":
            if out is None:
                kind, manifest, siblings = load_interop_source(args.path)
                if kind != "run":
                    print(
                        "[ERROR] Workflow Run Crates describe computations: export a run capsule "
                        "(run.json). A ledger embeds via --ledger or exports via 'interop ro-crate'.",
                        file=sys.stderr,
                    )
                    return 1
                ledger_doc = load_adjacent_ledger(args.path)
                doc = run_bundle_to_workflow_run_crate(
                    manifest, siblings, steps=manifest.get("steps") or [], ledger=ledger_doc
                )
                errors = validate_workflow_run_crate(doc)
                print(json.dumps(doc, indent=2))
                return 0 if not errors else 1

            result = export_workflow_run_crate(
                args.path,
                out,
                ledger_path=getattr(args, "ledger", None),
                zip_archive=bool(getattr(args, "zip", False)),
            )
            report = result.to_dict()
            print(f"[OK] Workflow Run RO-Crate written to: {result.crate_dir}")
            print(f"     files copied: {report['files_copied']}; steps projected: {report['steps_projected']}; ledger embedded: {report['ledger_included']}")
            print(f"     post-write verification: {'PASS' if report['verified'] else 'FAIL'}")
            if result.zip_path:
                print(f"     zip archive: {result.zip_path}")
            return 0 if report["verified"] else 1

        elif action == "de-crate":
            from bionexus.interop import export_de_audit_to_rocrate

            result = export_de_audit_to_rocrate(
                audit_report=args.report,
                output_dir=args.out,
                zip_archive=bool(getattr(args, "zip", False)),
            )
            report = result.to_dict()
            print(f"[OK] Differential Expression Audit RO-Crate written to: {result.crate_dir}")
            print(f"     files copied: {report['files_copied']}; post-write verification: {'PASS' if report['verified'] else 'FAIL'}")
            if result.zip_path:
                print(f"     zip archive: {result.zip_path}")
            return 0 if report["verified"] else 1

        elif action == "check":
            kind, manifest, siblings = load_interop_source(args.path)
            crate = (
                ledger_to_ro_crate(ClaimLedger.from_dict(manifest))
                if kind == "ledger"
                else run_bundle_to_ro_crate(manifest, siblings)
            )
            crate_errors = validate_ro_crate(crate)
            bco_errors: list = ["n/a: ledgers do not project to BCO"]
            wfrun_errors: list = ["n/a: ledgers do not project to Workflow Run Crates"]
            wfrun_doc = None
            if kind == "run":
                bco_errors = validate_bco(run_bundle_to_bco(manifest, siblings))
                ledger_doc = load_adjacent_ledger(args.path)
                wfrun_doc = run_bundle_to_workflow_run_crate(
                    manifest, siblings, steps=manifest.get("steps") or [], ledger=ledger_doc
                )
                wfrun_errors = validate_workflow_run_crate(wfrun_doc)
            print(f"=== Interop check: {args.path} (source kind: {kind}) ===")
            print(f"RO-Crate 1.1 structural validation: {'PASS' if not crate_errors else 'FAIL'}")
            for e in crate_errors:
                print(f"  - {e}")
            print(f"IEEE 2791-2020 BCO structural validation: {'PASS' if not bco_errors else 'FAIL'}")
            for e in bco_errors:
                print(f"  - {e}")
            print(
                "Workflow Run RO-Crate (bundle projection): "
                f"{'PASS' if not wfrun_errors else 'FAIL'}"
            )
            for e in wfrun_errors:
                print(f"  - {e}")
            return (
                0
                if not crate_errors
                and not (kind == "run" and (bco_errors or wfrun_errors))
                else 1
            )
    except (FileNotFoundError, ValueError) as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return 1
    return 0


def handle_standards(args: argparse.Namespace) -> int:
    """Handle the 'standards' command (BNS-016): alignment registry."""
    from bionexus.standards import alignments_report, render_alignments

    if args.json:
        print(json.dumps(alignments_report(), indent=2))
        return 0
    print(render_alignments())
    return 0


def handle_capability(args: argparse.Namespace) -> int:
    """Handle the 'capability' command."""
    action = getattr(args, "capability_action", "list")

    if action == "list":
        caps = list_capabilities(intent=args.intent, skill_name=args.skill)
        if args.json:
            print(json.dumps([c.to_dict() for c in caps], indent=2))
            return 0

        print(f"\n=== BioNexus Scientific Capabilities ({len(caps)} Registered) ===\n")
        print("| Capability ID | Display Name | Skill | Canonical Backend | Intents |")
        print("|---|---|---|---|---|")
        for c in caps:
            intents_str = ", ".join(c.intent[:3])
            print(
                f"| `{c.id}` | **{c.display_name}** | `{c.skill_name}` | `{c.backend.canonical_name}` | {intents_str} |"
            )
        print()
        return 0

    elif action == "show":
        try:
            contract = get_capability(args.id)
            if args.json:
                print(json.dumps(contract.to_dict(), indent=2))
                return 0

            print(f"\n### Capability Contract: `{contract.id}` (v{contract.version})")
            print(f"**{contract.display_name}** (`{contract.skill_name}`)\n")
            print(f"> {contract.summary}\n")
            print(f"- **Intents**: {', '.join(contract.intent)}")
            print(
                f"- **Canonical Backend**: `{contract.backend.canonical_name}` (min version: {contract.backend.minimum_version or 'any'})"
            )
            print("\n#### Input Semantic Specifications:")
            for name, spec in contract.inputs.items():
                print(f"- `{name}` ({spec.semantic_type}, required={spec.required}): {spec.description}")
            print("\n#### Scientific Preconditions:")
            for p in contract.preconditions:
                print(f"- `{p.id}`: `{p.rule}` ({p.description})")
            print("\n#### Deterministic Refusal Triggers:")
            for r in contract.refusal_conditions:
                print(f"- **`{r.condition_id}`**: {r.description}")
                print(f"  *Remedy*: {r.remedy}")
            print("\n#### Expected Outputs:")
            for out in contract.outputs:
                print(f"- {out}")
            print()
            return 0
        except KeyError as e:
            print(f"[ERROR] {e}", file=sys.stderr)
            return 1

    elif action == "check":
        try:
            contract = get_capability(args.id)
            meta = {}
            if getattr(args, "meta_json", None):
                with open(args.meta_json, "r", encoding="utf-8") as f:
                    meta = json.load(f)

            if getattr(args, "min_replicates", None) is not None:
                meta["min_replicates_per_condition"] = args.min_replicates
            if getattr(args, "is_normalized", False):
                meta["is_normalized"] = True
                meta["is_integer_like"] = False

            result = contract.evaluate_viability(input_metadata=meta)
            if args.json:
                print(json.dumps(result.to_dict(), indent=2))
                return 0 if result.permitted else 1

            print(f"\n=== Capability Precondition Evaluation: `{contract.id}` ===")
            print(f"**Status**: `{result.status}` | **Conclusion Maturity**: `{result.conclusion_maturity}`\n")
            if result.permitted:
                print("[OK] All scientific preconditions satisfied. Analysis is scientifically valid.")
                return 0
            else:
                print("[REFUSED] Analysis cannot be validly executed due to scientific violations:")
                for v in result.violations:
                    print(f"  - {v}")
                print("\nActionable Remedies:")
                for r in result.remedies:
                    print(f"  * {r}")
                print()
                return 1
        except KeyError as e:
            print(f"[ERROR] {e}", file=sys.stderr)
            return 1

    return 0


def handle_abi(args: argparse.Namespace) -> int:
    """Handle the 'abi' command: inspect the Biological Capability ABI (BNS-001 §5)."""
    from bionexus.abi import (
        abi_conformance_summary,
        audit_claims_against_abi,
        capability_abis,
        get_capability_abi,
    )

    action = getattr(args, "abi_action", "list")

    if action == "list":
        abis = capability_abis()
        if args.json:
            print(json.dumps([a.to_dict() for a in abis.values()], indent=2))
            return 0
        print(f"\n=== Biological Capability ABI v1.0 ({len(abis)} Capabilities) ===\n")
        print("| Capability | ABI Ceiling (no ext. validation) | Forbidden Claims | Reference Backend |")
        print("|---|---|---|---|")
        for a in abis.values():
            forbidden = ", ".join(a.forbidden_claims)
            print(
                f"| `{a.capability_id}` | `{a.evidence_ceiling.without_external_validation}` | {forbidden} | `{a.execution.reference_backend}` |"
            )
        print()
        return 0

    elif action == "show":
        try:
            abi = get_capability_abi(args.id)
            if args.json:
                print(json.dumps(abi.to_dict(), indent=2))
                return 0
            print(f"\n### Biological Capability ABI: `{abi.capability_id}` (ABI v{abi.abi_version})\n")
            ic = abi.input_contract
            print(f"- **Matrix states allowed**: `{', '.join(ic.matrix_state_allowed)}`")
            if ic.coordinates_required:
                print(f"- **Coordinates**: required (`{', '.join(ic.coordinate_type_allowed)}`)")
            print(f"- **Preconditions**: `{', '.join(abi.preconditions)}`")
            print(f"- **Forbidden claims**: `{', '.join(abi.forbidden_claims)}`")
            print(
                f"- **Execution reference**: `{abi.execution.reference_backend}` / `{abi.execution.reference_algorithm}`"
            )
            v = abi.validation
            print(
                f"- **Validation policy**: multiple_testing={v.multiple_testing}, parameter_sensitivity={v.parameter_sensitivity}, cross_method={v.cross_method}"
            )
            print(
                f"- **Evidence ceiling (without external validation)**: `{abi.evidence_ceiling.without_external_validation}`"
            )
            print(f"  * {abi.evidence_ceiling.note}")
            print(
                f"- **Provenance**: dataset_hash={abi.provenance.dataset_hash}, package_versions={abi.provenance.package_versions}, parameters={abi.provenance.parameters}"
            )
            print()
            return 0
        except KeyError as e:
            print(f"[ERROR] {e}", file=sys.stderr)
            return 1

    elif action == "audit-claims":
        try:
            audit = audit_claims_against_abi(args.id, args.claims)
            if args.json:
                print(json.dumps(audit.to_dict(), indent=2))
                return 0 if audit.passed else 1
            verdict = "CLAIM_SEMANTICS_CONFORMANT (no forbidden claim terms; biological claim unverified)" if audit.passed else "VIOLATIONS DETECTED"
            print(f"\n=== ABI Claim Audit: `{args.id}` -> {verdict} ===")
            for v in audit.violations:
                print(f"  - [FORBIDDEN] `{v['claim_id']}` matched: \"{v['matched_text']}\"")
                print(f"    {v['description']}")
            print()
            return 0 if audit.passed else 1
        except KeyError as e:
            print(f"[ERROR] {e}", file=sys.stderr)
            return 1

    elif action == "conformance":
        summary = abi_conformance_summary()
        if args.json:
            print(json.dumps(summary, indent=2))
        verdict = "ABI_SPEC_CONFORMANT (all declared capabilities structurally defined)" if summary["conformant"] else "NON-CONFORMANT"
        print(f"\n=== Biological Capability ABI v{summary['abi_version']} Structural Conformance: {verdict} ===")
        for cid, checks in summary["capabilities"].items():
            status = "[OK]" if checks["ok"] else "[FAIL]"
            print(f"  {status} `{cid}`")
            for k, ok in checks.items():
                if k == "ok":
                    continue
                if not ok:
                    print(f"      - missing: {k}")
        print()
        return 0 if summary["conformant"] else 1

    return 0


def handle_certification(args: argparse.Namespace) -> int:
    """Handle the 'certification' command (BNS-010): honest tier report + roadmap."""
    from bionexus.certification import certification_report

    report = certification_report()
    if args.json:
        print(json.dumps(report, indent=2))
        return 0

    tiers = report["tier_distribution"]
    print("\n=== BioNexus Capability Certification (BNS-010) ===")
    print(
        f"**CERTIFIED**: {len(tiers['CERTIFIED'])} | **SPEC_VALIDATED**: {len(tiers['VALIDATED'])} | "
        f"**EXPERIMENTAL**: {len(tiers['EXPERIMENTAL'])} | **CONNECTOR-ONLY**: {len(tiers['CONNECTOR-ONLY'])}"
    )
    print("  (Note: SPEC_VALIDATED indicates internal software contract and test suites passed; external biological truth is NOT established.)")
    print(f"M4 target: {report['m4_target_certified']} CERTIFIED -> honest gap: {report['m4_gap']}\n")

    print("| Capability | Tier | Criteria | Blocking CERTIFIED |")
    print("|---|---|---|---|")
    for cid, rec in report["records"].items():
        blocking = ", ".join(report["roadmap"][cid]["blocking_for_certified"]) or "none"
        print(
            f"| `{cid}` | `{rec['tier']}` | {rec['satisfied_count']}/{rec['total_criteria']} | {blocking} |"
        )
    print("\nTiers are computed from recorded evidence, never asserted (BNS-CF-002).")
    print("The blocking list is the certification roadmap (BNS-CF-005).\n")

    flagship = report.get("flagship") or {}
    if flagship:
        print("=== Flagship Certification Track (BNS-015) ===")
        print(f"*{flagship['principle']}*\n")
        print(f"Progress: {flagship['progress']} flagship capabilities at CERTIFIED\n")
        print("| Flagship | Tier | Blocking CERTIFIED | External criteria remaining |")
        print("|---|---|---|---|")
        for cid, info in flagship["capabilities"].items():
            ext = ", ".join(info["external_criteria_remaining"]) or "none"
            blocking = ", ".join(info["blocking_for_certified"]) or "none"
            print(f"| `{cid}` | `{info['current_tier']}` | {blocking} | {ext} |")
        print("\nThe flagship track reaches CERTIFIED through external evidence first; the 10-CERTIFIED")
        print("M4 target is unchanged and is never reached by weakening criteria (BNS-CF-006).\n")
    return 0

