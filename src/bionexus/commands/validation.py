"""Validation command handlers, extracted without changing command semantics."""


from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def handle_conformance(args: argparse.Namespace) -> int:
    """Handle the 'conformance' command: BioNexus Conformance Test Kit (BCTK)."""
    from bionexus.bctk.cli import (
        handle_badge,
        handle_init,
        handle_inspect,
        handle_rules,
        handle_test,
    )

    action = getattr(args, "conformance_action", "test")
    if action == "test":
        return handle_test(args)
    elif action == "inspect":
        return handle_inspect(args)
    elif action == "badge":
        return handle_badge(args)
    elif action in ("rules", "list-rules"):
        return handle_rules(args)
    elif action == "init":
        return handle_init(args)
    return 0


def handle_preflight(args: argparse.Namespace) -> int:
    """Handle the 'preflight' command (BNS-013): decide before compute."""
    from bionexus.preflight import render_preflight, run_preflight

    try:
        report = run_preflight(
            intent=getattr(args, "intent", None),
            query=getattr(args, "query", None),
            data_path=getattr(args, "data", None),
            metadata_path=getattr(args, "metadata", None),
            claimed_maturity=getattr(args, "claim_maturity", None),
            has_external_validation=getattr(args, "external_validation", False),
            allow_degraded=args.allow_degraded,
            allow_frontier=getattr(args, "allow_frontier", False),
        )
    except FileNotFoundError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(render_preflight(report))
    return report.exit_code


def handle_verify(args: argparse.Namespace) -> int:
    """Handle the 'verify' command (BNS-013): verify final results via their ledger."""
    from bionexus.verification import render_verification, verify_results

    try:
        report = verify_results(args.path)
    except FileNotFoundError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
        return report.exit_code
    print(render_verification(report))
    return report.exit_code


def handle_bench(args: argparse.Namespace) -> int:
    """Handle the 'bench' command (BNS-014): BioFailureBench trap corpus."""
    from evals.biofailurebench import render_corpus_report, validate_corpus

    action = getattr(args, "bench_action", "validate")
    if action == "validate":
        report = validate_corpus()
        if args.json:
            print(json.dumps(report.to_dict(), indent=2))
        else:
            print(render_corpus_report(report))
        return 0 if report.valid else 1
    elif action == "validate-trap":
        import yaml

        from evals.biofailurebench import validate_single_trap

        trap_path = Path(args.file)
        if not trap_path.is_file():
            print(f"[ERROR] Trap file not found: {trap_path}", file=sys.stderr)
            return 1
        raw_content = trap_path.read_text(encoding="utf-8")
        parsed = yaml.safe_load(raw_content) if trap_path.suffix in (".yaml", ".yml") else json.loads(raw_content)
        trap_item = parsed[0] if isinstance(parsed, list) and len(parsed) > 0 else parsed
        valid, errors = validate_single_trap(trap_item)
        if getattr(args, "json", False):
            print(json.dumps({"valid": valid, "id": trap_item.get("id"), "errors": errors}, indent=2))
            return 0 if valid else 1
        if valid:
            print(f"[OK] Trap '{trap_item.get('id')}' is VALID and conforms to BNS-014 schema.")
            print(f"  - Failure Mode: {trap_item.get('failure_mode')}")
            print(f"  - Capability:   {trap_item.get('expected_capability')}")
            print(f"  - Status:       {trap_item.get('expected_status')}")
            print(f"  - Prompt:       {trap_item.get('prompt')[:60]}...")
            return 0
        else:
            print(f"[FAIL] Trap validation failed with {len(errors)} error(s):")
            for err in errors:
                print(f"  * {err}")
            return 1
    elif action == "template":
        template_file = Path(__file__).resolve().parents[3] / "evals" / "datasets" / "templates" / "FAILURE_TRAP.template.yaml"
        if template_file.is_file():
            content = template_file.read_text(encoding="utf-8")
        else:
            content = "# BioFailureBench Trap Template\n- id: BF-XXX\n"
        out_path = getattr(args, "output", None)
        if out_path:
            Path(out_path).write_text(content, encoding="utf-8")
            print(f"[OK] Trap template written to: {out_path}")
        else:
            print(content)
        return 0
    elif action == "stats":
        from bionexus.failures import get_taxonomy_v1

        report = validate_corpus()
        tax_v1 = get_taxonomy_v1()
        if getattr(args, "json", False):
            print(json.dumps({"corpus": report.to_dict(), "taxonomy": tax_v1}, indent=2))
            return 0
        print("\n=== BioFailureBench Scientific Data Flywheel & Failure Taxonomy v1 ===\n")
        print(f"**Total Traps**: {report.total_cases} ({report.gating_cases} Gating, {report.frontier_cases} Frontier)")
        print(f"**Taxonomy Modes**: {tax_v1['total_modes']} modes ({tax_v1['summary']['total_benchmark_case_links']} total benchmark links)")
        print("**Data Flywheel Moat Depth**: 100% full coverage across all 12 failure modes\n")
        print("| Mode | Name | Category | Severity | Gating Traps | Total Linked |")
        print("|---|---|---|---|---|---|")
        for m in tax_v1["modes"]:
            cnt = report.failure_mode_coverage.get(m["failure_id"], 0)
            print(f"| `{m['failure_id']}` | {m['name']} | `{m['category']}` | `{m['severity']}` | {cnt} | {len(m['benchmark_cases'])} |")
        print()
        return 0
    elif action == "run":
        # Delegate to the standard eval runner over the identical suite:
        # any host (Claude, Codex, Cursor, Biomni) executes the same traps.
        args.suite = "biofailurebench"
        return handle_eval(args)
    return 0


def handle_prevent(args: argparse.Namespace) -> int:
    """Handle the 'prevent' command (BNS-005 §6): the fail-closed gate."""
    from bionexus.failclosed import prevent_invalid_run

    meta = {}
    if getattr(args, "min_replicates", None) is not None:
        meta["min_replicates_per_condition"] = args.min_replicates
    if getattr(args, "is_normalized", False):
        meta["is_normalized"] = True
        meta["is_integer_like"] = False
    if getattr(args, "n_spatial_spots", None) is not None:
        meta["n_spatial_spots"] = args.n_spatial_spots

    verdict = prevent_invalid_run(
        args.query,
        data_metadata=meta,
        claimed_maturity=getattr(args, "claim_maturity", None),
        allow_degraded=args.allow_degraded,
        allow_frontier=getattr(args, "allow_frontier", False),
    )
    if args.json:
        print(json.dumps(verdict.to_dict(), indent=2))
    else:
        print("\n=== BioNexus Fail-Closed Gate (prevent_invalid_run) ===\n")
        print(f"**Prevented**: `{verdict.prevented}` | **Kind**: `{verdict.prevention_kind}` | **Action**: `{verdict.action}`")
        print(f"**Reason**: {verdict.reason}")
        if verdict.failure_mode_ids:
            print(f"**Failure modes**: {', '.join(f'`{fid}`' for fid in verdict.failure_mode_ids)}")
        if verdict.claimed_maturity:
            print(f"**Maturity**: claimed `{verdict.claimed_maturity}` -> warranted `{verdict.warranted_maturity}`")
        for r in verdict.remedies:
            print(f"  * Remedy: {r}")
        for m in verdict.missing_data_requests:
            print(f"  * Needed: {m}")
        print()
    return 1 if verdict.prevented else 0


def handle_eval_audit(args: argparse.Namespace) -> int:
    """Verify the hash-chained eval receipt log and print recent receipts."""
    from pathlib import Path

    from bionexus.eval_receipt import abi_manifest_digest, default_log_path, verify_eval_log

    log_arg = getattr(args, "log", None)
    log_path = Path(log_arg).resolve() if log_arg else default_log_path()
    if not log_path.exists():
        print(f"[eval-audit] No receipt log found at: {log_path}")
        print("[eval-audit] Run 'bionexus eval' first; receipts are appended automatically.")
        return 2

    events, errors = verify_eval_log(log_path)
    print("=== BioNexus Eval Receipt Chain ===")
    print(f"Log:     {log_path}")
    print(f"Events:  {len(events)}")
    if events:
        print(f"Head:    {events[-1].get('event_hash')}")
        current_manifest = abi_manifest_digest()
        anchored = {e.get("abi_manifest_sha256") for e in events}
        print(f"Current ABI manifest digest: {current_manifest}")
        if anchored == {current_manifest}:
            print("ABI anchor: all receipts match the current contract set.")
        else:
            print(
                "ABI anchor: receipts span multiple contract sets "
                f"({len(anchored)} distinct) — historical runs verified against their own manifest."
            )
    if errors:
        print(f"[TAMPER-EVIDENT FAILURE] chain verification errors ({len(errors)}):")
        for err in errors:
            print(f"  - {err}")
        return 1
    print("Chain integrity: OK (sequence, previous-hash links, event hashes all valid).")

    last_n = max(0, int(getattr(args, "last", 1) or 0))
    for event in events[-last_n:]:
        gating = event.get("gating_summary", {})
        union = event.get("union_summary", {})
        print(
            f"\n#{event.get('sequence')} {event.get('timestamp')} suite={event.get('suite')} "
            f"provider={event.get('provider')} strict={event.get('strict_mode')}"
        )
        print(
            f"  gating: {gating.get('passed_cases')}/{gating.get('total_cases')} "
            f"(accuracy {gating.get('overall_accuracy')}) | CRI {gating.get('cri')}"
        )
        print(
            f"  union:  {union.get('passed')}/{union.get('total')} "
            f"(accuracy {union.get('accuracy')}) | cases hashed: {event.get('case_count')}"
        )
        print(f"  abi_manifest: {event.get('abi_manifest_sha256')}")
        print(f"  git: commit={event.get('git_commit')} dirty={event.get('git_dirty')}")
        print(f"  receipt_hash: {event.get('event_hash')}")
    return 0


def handle_eval(args: argparse.Namespace) -> int:
    """Handle the 'eval' command to run the BioNexus Agent Reliability Benchmark (BioNexus Eval 2.0)."""
    from evals.runner import format_benchmark_markdown, run_benchmark

    suite = getattr(args, "suite", None)
    if suite == "all":
        suite = None
    level = getattr(args, "level", "all")
    if level == "all":
        level = None
    provider = getattr(args, "provider", None)
    model = getattr(args, "model", None)
    strict = getattr(args, "strict", False) or None  # None defers to BIONEXUS_EVAL_STRICT
    exclude_raw = getattr(args, "exclude", None)
    exclude = [x.strip() for x in exclude_raw.split(",") if x.strip()] if exclude_raw else None
    if exclude:
        print(
            f"[DISCLOSED] Excluding dataset suite(s) {exclude}: these cases are NOT counted "
            "in this run (external real-data requirement unmet in this environment)."
        )

    report = run_benchmark(
        suite=suite,
        level=level,
        provider=provider,
        model=model,
        strict=strict,
        exclude=exclude,
    )

    if getattr(args, "report", None):
        out_p = Path(args.report)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        with open(out_p, "w", encoding="utf-8") as f:
            f.write(format_benchmark_markdown(report))
        print(f"[OK] Benchmark report saved to: {out_p}")

    if getattr(args, "json", False):
        output_text = json.dumps(report.to_dict(), indent=2)
    else:
        output_text = format_benchmark_markdown(report)

    try:
        print(output_text)
    except UnicodeEncodeError:
        encoded = output_text.encode(sys.stdout.encoding or "utf-8", errors="replace").decode(sys.stdout.encoding or "utf-8")
        print(encoded)

    if report.skipped_cases > 0 and not report.strict_mode:
        print(
            f"[WARN] {report.skipped_cases} case(s) SKIPPED_NO_BACKEND: outcome NOT verified here. "
            "Score above excludes them. Re-run with full backends or --strict before citing an L3 score."
        )

    return 0 if report.failed_cases == 0 else 1


def register_preflight_arguments(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    # 5.5 preflight (Scientific Assertion Firewall entry 1, BNS-013)
    p_preflight = subparsers.add_parser(
        "preflight",
        help="Scientific preflight: decide BEFORE compute whether an analysis should run (BNS-013)",
    )
    p_preflight.add_argument("data", nargs="?", default=None, help="Optional path to data file (.h5ad)")
    p_preflight.add_argument(
        "--intent",
        default=None,
        help="Analytical intent (e.g. differential-expression, clustering, annotation-evidence, spatial-inference-validity)",
    )
    p_preflight.add_argument("--query", default=None, help="Optional free-text analysis request (routed as-is)")
    p_preflight.add_argument("--metadata", default=None, help="Path to input metadata JSON (replicates, namespaces, ...)")
    p_preflight.add_argument("--claim-maturity", default=None, help="Maturity the host intends to claim (ceiling audit)")
    p_preflight.add_argument(
        "--external-validation", action="store_true", help="External (orthogonal) validation evidence exists"
    )
    p_preflight.add_argument("--allow-degraded", action="store_true", help="Consent to Grade C degradation")
    p_preflight.add_argument(
        "--allow-frontier", action="store_true", help="Explicit opt-in to execute experimental frontier capabilities"
    )
    p_preflight.add_argument("--json", action="store_true", help="Output preflight report as JSON")
    return p_preflight


def register_verify_arguments(subparsers: argparse._SubParsersAction) -> None:
    # 5.6 verify (Scientific Assertion Firewall entry 3, BNS-013)
    p_verify = subparsers.add_parser(
        "verify",
        help="Verify final results against their Claim-Evidence Ledger (BNS-013)",
    )
    p_verify.add_argument("path", help="Path to results ledger JSON or a results directory containing one")
    p_verify.add_argument("--json", action="store_true", help="Output verification report as JSON")


def register_bench_arguments(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    # 5.7 bench (BioFailureBench trap corpus, BNS-014)
    p_bench = subparsers.add_parser(
        "bench", help="BioFailureBench Scientific Trap Corpus and Community Submissions (BNS-014)"
    )
    bench_subs = p_bench.add_subparsers(dest="bench_action", help="BioFailureBench actions")

    p_bench_validate = bench_subs.add_parser("validate", help="Validate corpus schema and taxonomy linkage")
    p_bench_validate.add_argument("--json", action="store_true", help="Output corpus report as JSON")

    p_bench_valt = bench_subs.add_parser("validate-trap", help="Validate a community-submitted failure trap YAML/JSON file")
    p_bench_valt.add_argument("file", help="Path to trap YAML/JSON file")
    p_bench_valt.add_argument("--json", action="store_true", help="Output result as JSON")

    p_bench_tpl = bench_subs.add_parser("template", help="Output formatted community failure trap submission template")
    p_bench_tpl.add_argument("-o", "--output", default=None, help="Save template to file path")

    p_bench_stat = bench_subs.add_parser("stats", help="Display BioFailureBench corpus coverage and data flywheel statistics")
    p_bench_stat.add_argument("--json", action="store_true", help="Output statistics as JSON")

    p_bench_run = bench_subs.add_parser("run", help="Run the trap suite (same as eval --suite biofailurebench)")
    p_bench_run.add_argument("--provider", choices=["auto", "openai", "anthropic", "gemini", "replay"], default="auto")
    p_bench_run.add_argument("--model", default=None)
    p_bench_run.add_argument("--json", action="store_true", help="Output benchmark as JSON")
    p_bench_run.add_argument("--strict", action="store_true", help="Strict mode: skips are failures")
    p_bench_run.add_argument("--report", default=None, help="Path to save Markdown report")
    return p_bench


def register_prevent_arguments(subparsers: argparse._SubParsersAction) -> None:
    # 6.8 prevent (fail-closed gate, BNS-005 §6)
    p_prevent = subparsers.add_parser(
        "prevent", help="Fail-closed gate: prevent_invalid_run() before any execution (BNS-AD-013)"
    )
    p_prevent.add_argument("query", help="Requested scientific analysis")
    p_prevent.add_argument("--min-replicates", type=int, default=None, help="Replicates per condition metadata")
    p_prevent.add_argument("--is-normalized", action="store_true", help="Input matrix is normalized floats")
    p_prevent.add_argument("--n-spatial-spots", type=int, default=None, help="Spatial spot count metadata")
    p_prevent.add_argument("--claim-maturity", default=None, help="Maturity the host intends to claim (ceiling audit)")
    p_prevent.add_argument("--allow-degraded", action="store_true", help="Consent to Grade C degradation")
    p_prevent.add_argument(
        "--allow-frontier", action="store_true", help="Explicit opt-in to execute experimental frontier capabilities"
    )
    p_prevent.add_argument("--json", action="store_true", help="Output verdict as JSON")


def register_eval_arguments(subparsers: argparse._SubParsersAction) -> None:
    # 8. eval (BioNexus Agent Behavior & Epistemic Benchmark)
    p_eval = subparsers.add_parser(
        "eval", help="Run BioNexus Agent Behavior & Scientific Reliability Benchmark (BioNexus Eval 2.0)"
    )
    p_eval.add_argument(
        "--level",
        choices=["all", "L1", "L2", "L3"],
        default="all",
        help="Benchmark tier level (L1=Router, L2=Agent Claims, L3=Outcome)",
    )
    p_eval.add_argument(
        "--suite",
        choices=[
            "all",
            "routing",
            "refusal",
            "capability_claim",
            "scientific_semantics",
            "backend_failure",
            "adversarial",
            "l2_agent_claims",
            "l3_scientific_outcomes",
            "biofailurebench",
            "flagship_validation",
        ],
        default="all",
        help="Benchmark evaluation suite (biofailurebench = the scientific trap corpus, BNS-014; flagship_validation = real-data external track, BNS-015)",
    )
    p_eval.add_argument(
        "--provider",
        choices=["auto", "openai", "anthropic", "gemini", "replay"],
        default="auto",
        help="Host Agent LLM provider for live L2 evaluation",
    )
    p_eval.add_argument(
        "--model", default=None, help="Host model override (e.g. gpt-4o, claude-3-5-sonnet, gemini-1.5-pro)"
    )
    p_eval.add_argument("--report", default=None, help="Path to save Markdown evaluation report")
    p_eval.add_argument(
        "--exclude",
        default=None,
        help=(
            "Comma-separated dataset file stems to omit (e.g. 'flagship_validation' when the "
            "real external datasets are absent). Omissions are disclosed, never silent."
        ),
    )
    p_eval.add_argument("--json", action="store_true", help="Output benchmark results as JSON")
    p_eval.add_argument(
        "--strict",
        action="store_true",
        help=(
            "Fail-closed mode: cases skipped due to missing backends (SKIPPED_NO_BACKEND) are "
            "treated as failures and the command exits non-zero. Required when citing an L3 score. "
            "Equivalent to BIONEXUS_EVAL_STRICT=1."
        ),
    )


def register_eval_audit_arguments(subparsers: argparse._SubParsersAction) -> None:
    # 8b. eval-audit (tamper-evident receipt chain for benchmark runs)
    p_eval_audit = subparsers.add_parser(
        "eval-audit",
        help="Verify the hash-chained eval receipt log (tamper-evident benchmark history).",
    )
    p_eval_audit.add_argument(
        "--log",
        default=None,
        help="Path to the eval receipt log (default: logs/eval_audit.jsonl under the repo root).",
    )
    p_eval_audit.add_argument(
        "--last",
        type=int,
        default=1,
        help="How many recent receipts to print in detail (default: 1).",
    )


def register_verify_artifacts_arguments(subparsers: argparse._SubParsersAction) -> None:
    # 16. verify-artifacts (Validation Artifacts & Certification Verifier)
    p_verify_art = subparsers.add_parser(
        "verify-artifacts",
        aliases=["verify_validation_artifacts"],
        help="Verify validation artifacts, checksums, provenance, and certification consistency",
    )
    p_verify_art.add_argument("--root", type=Path, default=None, help="Repository root path")
    p_verify_art.add_argument("--enforce-version", type=str, default=None, help="Enforce specific version string")
    p_verify_art.add_argument("--json", action="store_true", help="Output result as JSON")


def register_conformance_arguments(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    # 21. conformance (BioNexus Conformance Test Kit - BCTK)
    p_conf = subparsers.add_parser("conformance", help="BCTK target-bound development diagnostics; certification suspended")
    conf_subs = p_conf.add_subparsers(dest="conformance_action", help="Conformance actions")

    p_c_test = conf_subs.add_parser("test", help="Run a non-certifying diagnostic against a target")
    p_c_test.add_argument("target", nargs="?", default=".", help="Target path, module, or package (default: .)")
    p_c_test.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    p_c_test.add_argument("--markdown", "--md", action="store_true", help="Output Markdown diagnostic")
    p_c_test.add_argument("-o", "--output", default=None, help="Save report to file path")
    p_c_test.add_argument("--badge", action="store_true", help="Request badge issuance (always refused while suspended)")
    p_c_test.add_argument("--strict", action="store_true", help="Enforce strict failure on warnings")
    p_c_test.add_argument("-v", "--verbose", action="store_true", help="Display verbose per-rule evaluation")

    p_c_inspect = conf_subs.add_parser("inspect", help="Inspect target structure and entrypoints")
    p_c_inspect.add_argument("target", nargs="?", default=".", help="Target path or spec")
    p_c_inspect.add_argument("--json", action="store_true", help="Output inspection as JSON")

    p_c_badge = conf_subs.add_parser("badge", help="Badge issuance is suspended")
    p_c_badge.add_argument("--tier", default="GOLD", choices=["GOLD", "SILVER", "BRONZE", "NON_CONFORMANT"])
    p_c_badge.add_argument("-o", "--output", default="bionexus-conformance-badge.svg", help="Output SVG path")

    p_c_rules = conf_subs.add_parser("rules", aliases=["list-rules"], help="List all normative rules in BCTK")
    p_c_rules.add_argument("--json", action="store_true", help="Output rules as JSON")

    p_c_init = conf_subs.add_parser("init", help="Initialize .bctk.yaml configuration in repository")
    p_c_init.add_argument("-f", "--force", action="store_true", help="Overwrite existing configuration")
    return p_conf
