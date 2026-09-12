"""Diagnostics command handlers, extracted without changing command semantics."""


from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from bionexus.doctor import run_doctor
from bionexus.inventory import (
    SKILLS,
    as_markdown_table,
    skills_by_tier,
)
from bionexus.registry import (
    check_manifest_drift,
    check_mirror_drift,
    compile_and_write_all,
    load_canonical_registry,
    sync_mirror_trees,
    validate_endpoints,
)


def handle_backend_identity(args: argparse.Namespace) -> int:
    """Audit Backend Identity Conformance: declared_backend == observed_backend (BNS-EF-012..016)."""
    import json as _json

    from bionexus.backend_conformance import (
        BackendIdentityState,
        backend_identity_summary,
        verify_all_backend_identity,
        verify_backend_identity,
    )
    from bionexus.capabilities import ALL_CAPABILITIES

    capability = getattr(args, "capability", None)
    if capability:
        if capability not in ALL_CAPABILITIES:
            print(f"[ERROR] Unknown capability '{capability}'.", file=sys.stderr)
            return 2
        reports = [verify_backend_identity(ALL_CAPABILITIES[capability])]
    else:
        reports = verify_all_backend_identity(include_frontier=not getattr(args, "canonical_only", False))

    if getattr(args, "json", False):
        print(_json.dumps({"reports": [r.to_dict() for r in reports], "summary": backend_identity_summary(reports)}, indent=2))
    else:
        print("=== BioNexus Backend Identity Conformance (BNS-EF-012..016 / BN-F010) ===")
        print(f"{'Capability':<38} {'Track':<10} {'Claimed':<28} {'Observed':<16} {'Version':<10} {'State':<22} Action")
        for r in reports:
            print(
                f"{r.capability_id:<38} {r.track:<10} {r.claimed_backend:<28} "
                f"{(r.observed_backend or '-'):<16} {(r.version or '-'):<10} "
                f"{r.state.value:<22} {r.action}"
            )
            if r.execution_fingerprint:
                print(f"    fingerprint: {r.execution_fingerprint}  entry_points: {len(r.entry_points_resolved)}/{len(r.entry_points_declared)}  fallback: {r.fallback}")
            if r.state in (BackendIdentityState.MASQUERADE, BackendIdentityState.INCOMPATIBLE_VERSION):
                print(f"    BN-F010 BLOCK: {r.reason}")
        summary = backend_identity_summary(reports)
        print(
            f"\nVerdict: {summary['verdict']} "
            f"(conformant {summary['conformant']}/{summary['total']}, not installed {summary['not_installed']}, blocked {len(summary['blocked'])})"
        )

    return 1 if any(r.action == "BLOCK" for r in reports) else 0


def handle_doctor(args: argparse.Namespace) -> int:
    """Run BioNexus environment doctor diagnostics."""
    report = run_doctor()
    ready = report.get("ready", {})
    if getattr(args, "require_scverse", False) and not ready.get("scverse_ready"):
        print("[ERROR] scverse stack required but missing (scanpy + anndata)", file=sys.stderr)
        return 1
    if getattr(args, "require_spatial", False) and not ready.get("spatial_ready"):
        print("[ERROR] spatial stack required but missing (squidpy)", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print("=" * 78)
        print("                          BioNexus Environment Doctor")
        print("=" * 78)
        print(f"Plugin Version:  {report['plugin_version']}")
        print(f"Tier:            {report['tier']}")
        print("\nActive Analytical Capabilities:")
        for cap, status in ready.items():
            pass_str = "[PASS]" if status else "[MISSING]"
            print(f"  {pass_str:9s} {cap:18s} : {'ready' if status else 'not installed'}")
        print("=" * 78)

    return 0 if report.get("tier") != "refuse" else 1


def handle_list_skills(args: argparse.Namespace) -> int:
    """Display skill inventory table or JSON."""
    records = SKILLS
    if args.tier:
        records = skills_by_tier(args.tier)
    if args.status:
        records = [r for r in records if r.get("status") == args.status]
    if args.grade:
        records = [r for r in records if r.get("grade") == args.grade]

    if args.json:
        print(json.dumps(records, indent=2))
    else:
        print(f"\n=== BioNexus Skill Inventory ({len(records)} Skills) ===\n")
        print(as_markdown_table(records))
        print()
    return 0


def handle_registry(args: argparse.Namespace) -> int:
    """Compile, check, and validate canonical registry manifests."""
    reg_path = Path(args.registry_path) if args.registry_path else Path.cwd() / "bionexus.registry.yaml"
    if not reg_path.is_file():
        # Traverse upwards
        for parent in Path.cwd().parents:
            if (parent / "bionexus.registry.yaml").is_file():
                reg_path = parent / "bionexus.registry.yaml"
                break

    try:
        registry = load_canonical_registry(reg_path)
    except Exception as e:
        print(f"[ERROR] Failed to load registry {reg_path}: {e}", file=sys.stderr)
        return 1

    repo_root = reg_path.parent
    exit_code = 0

    if args.validate_endpoints or args.live_check:
        print("=== Validating BioNexus MCP Endpoints ===")
        val_res = validate_endpoints(registry, check_live=args.live_check)
        for s_id, s_info in val_res["servers"].items():
            status_str = "ENABLED" if s_info["enabled"] else "DISABLED"
            live_str = f" [Live: {s_info['live_status']}]" if s_info.get("live_status") is not None else ""
            err_str = f" (Error: {s_info['error']})" if s_info.get("error") else ""
            print(f" - {s_id:12s} [{status_str:8s}] -> {s_info['url'] or 'N/A'}{live_str}{err_str}")
        if not val_res["valid"]:
            print("[ERROR] Endpoint validation detected invalid configurations!", file=sys.stderr)
            exit_code = 1
        else:
            print("[OK] Endpoint syntax validated successfully.")

    if args.check:
        print("\n=== Checking Manifest Drift ===")
        in_sync, diffs = check_manifest_drift(repo_root, registry)
        mirror_sync, mirror_diffs = check_mirror_drift(repo_root)
        if in_sync and mirror_sync:
            print("[OK] All platform manifests are strictly in sync with bionexus.registry.yaml.")
            print("[OK] Plugin mirror trees (plugins/bionexus/skills, scripts) are byte-identical to the canonical root.")
        else:
            if not in_sync:
                print("[DRIFT DETECTED] Manifest drift found:", file=sys.stderr)
                for d in diffs:
                    print(f" - {d}", file=sys.stderr)
            if not mirror_sync:
                print(
                    "[MIRROR DRIFT DETECTED] plugins/bionexus code mirror differs from the canonical root trees:",
                    file=sys.stderr,
                )
                for d in mirror_diffs:
                    print(f" - {d}", file=sys.stderr)
            print(
                "Run 'bionexus registry --generate' to resynchronize. Edit only the canonical root "
                "skills/ and scripts/ trees; the plugins/bionexus copies are regenerated.",
                file=sys.stderr,
            )
            exit_code = 1

    if args.generate:
        print("\n=== Compiling Registry Manifests ===")
        written = compile_and_write_all(repo_root, registry)
        for f in written:
            print(f" [GENERATED] {f}")
        print("[OK] Platform manifests synchronized successfully.")

        print("\n=== Synchronizing Plugin Mirror Trees (skills/, scripts/) ===")
        synced = sync_mirror_trees(repo_root)
        print(f" [MIRROR] {len(synced)} files verified/synchronized into plugins/bionexus/")
        mirror_sync, _mirror_diffs = check_mirror_drift(repo_root)
        if mirror_sync:
            print("[OK] Plugin mirror trees are byte-identical to the canonical root.")
        else:
            print("[ERROR] Mirror sync failed verification.", file=sys.stderr)
            exit_code = 1

    return exit_code


def register_doctor_arguments(subparsers: argparse._SubParsersAction) -> None:
    # 2. doctor
    p_doctor = subparsers.add_parser("doctor", help="Run environment preflight diagnostics")
    p_doctor.add_argument("--json", action="store_true", help="Output diagnostic report in JSON")
    p_doctor.add_argument("--require-scverse", action="store_true", help="Enforce scverse stack presence")
    p_doctor.add_argument("--require-spatial", action="store_true", help="Enforce spatial stack presence")


def register_backend_identity_arguments(subparsers: argparse._SubParsersAction) -> None:
    # 2.5 backend-identity
    p_backend_identity = subparsers.add_parser(
        "backend-identity",
        help="Audit Backend Identity Conformance: declared_backend == observed_backend (BNS-EF-012..016, BN-F010)",
    )
    p_backend_identity.add_argument("--json", action="store_true", help="Output identity reports as JSON")
    p_backend_identity.add_argument("--capability", default=None, help="Audit a single capability id")
    p_backend_identity.add_argument("--canonical-only", action="store_true", help="Skip the frontier track")


def register_list_skills_arguments(subparsers: argparse._SubParsersAction) -> None:
    # 3. list-skills / inventory
    for cmd_name in ("list-skills", "inventory"):
        p_skills = subparsers.add_parser(cmd_name, help="Display canonical skill inventory and capability tiers")
        p_skills.add_argument("--json", action="store_true", help="Output inventory as JSON")
        p_skills.add_argument("--tier", choices=["core", "wrapper", "heuristic", "outline"], default=None)
        p_skills.add_argument(
            "--status", choices=["canonical", "active", "heuristic", "outline", "deprecated"], default=None
        )
        p_skills.add_argument(
            "--grade", choices=["A", "B", "C", "gold-wrapper", "heuristic", "refuse", "outline"], default=None
        )


def register_registry_arguments(subparsers: argparse._SubParsersAction) -> None:
    # 4. registry
    p_registry = subparsers.add_parser("registry", help="Compile and validate multi-platform registry manifests")
    p_registry.add_argument("--generate", action="store_true", help="Compile manifests from registry")
    p_registry.add_argument("--check", action="store_true", help="Verify zero configuration drift")
    p_registry.add_argument("--validate-endpoints", action="store_true", help="Validate MCP endpoint syntax")
    p_registry.add_argument("--live-check", action="store_true", help="Probe live HTTP endpoints")
    p_registry.add_argument("--registry-path", default=None, help="Path to bionexus.registry.yaml")
