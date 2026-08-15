#!/usr/bin/env python3
"""
BioNexus Canonical Registry Compiler CLI.

Translates bionexus.registry.yaml into platform manifests (Agent Plugins, Claude, Codex)
and checks for configuration drift in CI.

Usage:
  python scripts/registry_compiler.py --generate              # Compile all manifests
  python scripts/registry_compiler.py --check                 # Verify no drift exists
  python scripts/registry_compiler.py --validate-endpoints    # Validate endpoint syntaxes
  python scripts/registry_compiler.py --live-check            # Probe live HTTP endpoints
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add src to sys.path
_REPO_ROOT = Path(__file__).resolve().parent.parent
_SRC = _REPO_ROOT / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from bio_research.registry import (  # noqa: E402
    check_manifest_drift,
    compile_and_write_all,
    load_canonical_registry,
    validate_endpoints,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="BioNexus Canonical Registry Compiler and Multi-Platform Sync Tool"
    )
    parser.add_argument(
        "--generate",
        action="store_true",
        help="Compile bionexus.registry.yaml into target platform manifests (plugin.json, mcp.json, etc.)"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify on-disk manifests match canonical registry (fails with exit code 1 if drift detected)"
    )
    parser.add_argument(
        "--validate-endpoints",
        action="store_true",
        help="Validate syntax of all configured MCP server URLs"
    )
    parser.add_argument(
        "--live-check",
        action="store_true",
        help="Probe live connectivity for enabled HTTP endpoints"
    )
    parser.add_argument(
        "--registry-path",
        type=Path,
        default=_REPO_ROOT / "bionexus.registry.yaml",
        help="Path to bionexus.registry.yaml (default: root)"
    )

    args = parser.parse_args()

    # Default action is --generate if no specific flag passed
    if not (args.check or args.validate_endpoints or args.live_check):
        args.generate = True

    try:
        registry = load_canonical_registry(args.registry_path)
    except Exception as e:
        print(f"[ERROR] Failed to load canonical registry {args.registry_path}: {e}", file=sys.stderr)
        return 1

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
        print("\n=== Checking for Configuration Drift ===")
        in_sync, diffs = check_manifest_drift(_REPO_ROOT, registry)
        if in_sync:
            print("[OK] All platform manifests are strictly in sync with bionexus.registry.yaml.")
        else:
            print("[DRIFT DETECTED] The following files do not match bionexus.registry.yaml:", file=sys.stderr)
            for d in diffs:
                print(f" - {d}", file=sys.stderr)
            print("\nRun `python scripts/registry_compiler.py --generate` to synchronize all manifests.", file=sys.stderr)
            exit_code = 1

    if args.generate:
        print("\n=== Compiling Canonical Registry to Platform Manifests ===")
        written = compile_and_write_all(_REPO_ROOT, registry)
        for f in written:
            print(f" [GENERATED] {f}")
        print("[OK] Successfully generated all platform manifests.")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
