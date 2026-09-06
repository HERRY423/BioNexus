"""
BioNexus Conformance Test Kit (BCTK) Command-Line Interface.

Usage:
  bctk test <target> [--json] [--output <path>] [--badge] [--markdown] [--strict] [--verbose]
  bctk inspect <target>
  bctk badge  # suspended during Scientific Trust Reset
  bctk rules [--json]
  bctk init
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

from bionexus.bctk.engine import run_conformance_test
from bionexus.bctk.reporters import render_markdown_report, render_terminal_report
from bionexus.bctk.spec import BCTK_RULE_CATALOG
from bionexus.bctk.targets import detect_target


def handle_test(args: argparse.Namespace) -> int:
    """Run BCTK conformance test against a target."""
    target_path = args.target or "."
    strict = getattr(args, "strict", False)
    verbose = getattr(args, "verbose", False)

    report = run_conformance_test(target_path, strict=strict)

    if getattr(args, "json", False):
        print(json.dumps(report.to_dict(), indent=2))
    elif getattr(args, "markdown", False):
        print(render_markdown_report(report))
    else:
        print(render_terminal_report(report, verbose=verbose))

    # Optional file outputs
    if getattr(args, "output", None):
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        if out_path.suffix.lower() == ".json":
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(report.to_dict(), f, indent=2)
        elif out_path.suffix.lower() in (".md", ".markdown"):
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(render_markdown_report(report))
        else:
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(render_terminal_report(report, verbose=True))
        print(f"\n[BCTK] Report saved to {out_path}")

    if getattr(args, "badge", False):
        print(
            "[BCTK] Badge issuance is suspended pending independent, target-bound evidence.",
            file=sys.stderr,
        )

    # Development diagnostics can never satisfy a certification gate.
    return 2


def handle_inspect(args: argparse.Namespace) -> int:
    """Inspect target metadata and entrypoints."""
    target = detect_target(args.target)
    info = {
        "name": target.name,
        "type": target.target_type.value,
        "root_path": str(target.root_path),
        "declared_backend": target.declared_backend,
        "entrypoints": target.entrypoints,
        "scripts": [str(s) for s in target.script_paths],
        "artifacts": [str(a) for a in target.artifact_paths],
        "manifest": target.manifest_data,
    }
    if getattr(args, "json", False):
        print(json.dumps(info, indent=2))
    else:
        print("=== BCTK Target Inspection ===")
        print(f"Name:             {info['name']}")
        print(f"Type:             {info['type']}")
        print(f"Root:             {info['root_path']}")
        print(f"Declared Backend: {info['declared_backend'] or 'None'}")
        print(f"Scripts:          {len(info['scripts'])}")
        print(f"Artifacts:        {len(info['artifacts'])}")
        print("==============================")
    return 0


def handle_badge(args: argparse.Namespace) -> int:
    """Fail closed while self-certified badge issuance is suspended."""
    print(
        "[BCTK] Badge issuance is suspended. A score or caller-selected tier is not independent certification.",
        file=sys.stderr,
    )
    return 2


def handle_rules(args: argparse.Namespace) -> int:
    """List all normative BCTK rules."""
    if getattr(args, "json", False):
        print(json.dumps({
            k: {
                "rule_id": v.rule_id,
                "dimension": v.dimension.value,
                "title": v.title,
                "description": v.description,
                "severity": v.severity.value,
                "bns_reference": v.bns_reference,
            }
            for k, v in BCTK_RULE_CATALOG.items()
        }, indent=2))
    else:
        print("=" * 80)
        print("              BioNexus Conformance Test Kit (BCTK) Rule Catalog")
        print("=" * 80)
        for rule_id, r in sorted(BCTK_RULE_CATALOG.items()):
            print(f"[{r.rule_id}] {r.title} ({r.severity.value})")
            print(f"  Dimension: {r.dimension.value} | Ref: {r.bns_reference}")
            print(f"  {r.description}\n")
        print(f"Total Rules in Catalog: {len(BCTK_RULE_CATALOG)}")
    return 0


def handle_init(args: argparse.Namespace) -> int:
    """Scaffold a .bctk.yaml configuration in the current repository."""
    config_content = """# BioNexus Conformance Test Kit (BCTK) Configuration
version: "1.0"
target:
  name: "my-scientific-plugin"
  type: "plugin"
  abi_version: "1.0"

conformance:
  certification: "SUSPENDED"
  strict: true
  dimensions:
    biological_semantics: true
    input_state_honesty: true
    backend_identity: true
    provenance: true
    claim_warrant: true
    abstention: true
    failure_handling: true
    cross_host_consistency: true

reporting:
  output_json: "bctk-report.json"
  output_markdown: "CONFORMANCE.md"
  generate_badge: false
"""
    cfg_path = Path(".bctk.yaml")
    if cfg_path.exists() and not getattr(args, "force", False):
        print("[ERROR] .bctk.yaml already exists. Use --force to overwrite.", file=sys.stderr)
        return 1
    with open(cfg_path, "w", encoding="utf-8") as f:
        f.write(config_content)
    print(f"[SUCCESS] Created {cfg_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build command line argument parser for BCTK."""
    parser = argparse.ArgumentParser(
        prog="bctk",
        description="BioNexus BCTK development diagnostics — certification and badging suspended",
    )
    subparsers = parser.add_subparsers(dest="command", help="BCTK subcommands")

    # test
    p_test = subparsers.add_parser("test", help="Run a non-certifying diagnostic against a target")
    p_test.add_argument("target", nargs="?", default=".", help="Target path, module, or package (default: .)")
    p_test.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    p_test.add_argument("--markdown", "--md", action="store_true", help="Output Markdown diagnostic")
    p_test.add_argument("-o", "--output", default=None, help="Save report to file path")
    p_test.add_argument("--badge", action="store_true", help="Request a badge (always refused while suspended)")
    p_test.add_argument("--strict", action="store_true", help="Enforce strict failure on warnings")
    p_test.add_argument("-v", "--verbose", action="store_true", help="Display verbose per-rule evaluation")

    # inspect
    p_inspect = subparsers.add_parser("inspect", help="Inspect target structure and entrypoints")
    p_inspect.add_argument("target", nargs="?", default=".", help="Target path or spec")
    p_inspect.add_argument("--json", action="store_true", help="Output inspection as JSON")

    # badge
    p_badge = subparsers.add_parser("badge", help="Badge issuance is suspended")
    p_badge.add_argument("--tier", default="GOLD", choices=["GOLD", "SILVER", "BRONZE", "NON_CONFORMANT"])
    p_badge.add_argument("-o", "--output", default="bionexus-conformance-badge.svg", help="Output SVG path")

    # rules
    p_rules = subparsers.add_parser("rules", help="List all normative rules in BCTK")
    p_rules.add_argument("--json", action="store_true", help="Output rules as JSON")

    # init
    p_init = subparsers.add_parser("init", help="Initialize .bctk.yaml configuration")
    p_init.add_argument("-f", "--force", action="store_true", help="Overwrite existing configuration")

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """Main CLI entrypoint for BCTK."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 0

    if args.command == "test":
        return handle_test(args)
    elif args.command == "inspect":
        return handle_inspect(args)
    elif args.command == "badge":
        return handle_badge(args)
    elif args.command == "rules":
        return handle_rules(args)
    elif args.command == "init":
        return handle_init(args)

    return 0


if __name__ == "__main__":
    sys.exit(main())
