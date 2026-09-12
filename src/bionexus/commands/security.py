"""Security command handlers, extracted without changing command semantics."""


from __future__ import annotations

import argparse
import json
from pathlib import Path


def handle_security(args: argparse.Namespace) -> int:
    """Handle BioNexus Data Governance & Security commands."""
    import json
    from pathlib import Path

    from bionexus.egress_guard import get_egress_guard

    action = getattr(args, "security_action", None)
    guard = get_egress_guard()

    if action in ("egress-policy", "policy"):
        if getattr(args, "mode", None):
            guard.set_mode(args.mode)
            print(f"[OK] Data Egress Mode updated to: {guard.mode.value}")

        if getattr(args, "json", False):
            print(json.dumps({
                "mode": guard.mode.value,
                "audit_log_path": str(guard.audit_log_path),
                "approved_domains_count": len(guard.allowed_domains),
                "approved_domains": sorted(list(guard.allowed_domains)),
            }, indent=2))
        else:
            print("\n=== BioNexus Data Governance & Egress Policy (BNS-SEC-001) ===")
            print(f"Active Egress Mode:      {guard.mode.value}")
            print(f"Audit Log Destination:   {guard.audit_log_path}")
            print(f"Approved Knowledge APIs: {len(guard.allowed_domains)} domains")
            print("\nMode Guidelines:")
            print("  * OFFLINE_STRICT : Zero network access. Air-gapped local compute only.")
            print("  * ALLOWLIST      : Approved scientific services only. Raw biological matrices & PHI blocked.")
            print("  * CONNECTED      : External calls permitted with mandatory cryptographic audit logging.")
            print()
        return 0

    elif action == "audit":
        audit_file = guard.audit_log_path
        records = []
        if audit_file.is_file():
            with open(audit_file, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        try:
                            records.append(json.loads(line.strip()))
                        except Exception:
                            pass
        records.extend([r.to_dict() for r in guard.get_audit_trail()])
        seen = set()
        deduped = []
        for r in records:
            rid = r.get("record_id")
            if rid not in seen:
                seen.add(rid)
                deduped.append(r)

        limit = getattr(args, "limit", 20)
        sliced = deduped[-limit:] if limit else deduped

        if getattr(args, "json", False):
            print(json.dumps({"total_records": len(deduped), "audit_records": sliced}, indent=2))
        else:
            print(f"\n=== BioNexus Cryptographic Egress Audit Trail ({len(deduped)} total events) ===")
            if not sliced:
                print("  No external egress calls recorded in this session.")
            for r in sliced:
                outcome_color = "[PERMITTED]" if r.get("outcome") == "PERMITTED" else "[BLOCKED]  "
                print(f"{outcome_color} {r.get('timestamp')} | {r.get('egress_mode'):<14} | {r.get('endpoint')}")
                print(f"    Purpose: {r.get('purpose')} | SHA256: {r.get('payload_sha256', '')[:12]}...")
                if r.get("block_reason"):
                    print(f"    Block Reason: {r.get('block_reason')}")
            print()
        return 0

    elif action == "sbom":
        from scripts.generate_sbom import generate_cyclonedx_sbom
        sbom = generate_cyclonedx_sbom()
        out_path = Path(args.output) if args.output else Path("sbom.json")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(sbom, indent=2), encoding="utf-8")
        print(f"[OK] Generated CycloneDX SBOM ({len(sbom['components'])} components) -> {out_path}")
        return 0

    return 0


def handle_guard(args: argparse.Namespace) -> int:
    import subprocess

    from bionexus.guard import BioNexusGuard, GuardStatus

    guard = BioNexusGuard()
    action = getattr(args, "guard_action", "check")

    if action == "check":
        code_to_check = getattr(args, "code", None)
        file_path = getattr(args, "file", None)
        if file_path:
            p = Path(file_path)
            if not p.exists():
                print(f"Error: File {file_path} not found")
                return 2
            code_to_check = p.read_text(encoding="utf-8")
        elif not code_to_check:
            print("Error: Must provide either code string or --file")
            return 2

        verdict = guard.inspect_code(code_to_check, file_path=file_path or "inline_code")
        if getattr(args, "json", False):
            print(json.dumps(verdict.to_dict(), indent=2, ensure_ascii=False))
        else:
            print("=" * 60)
            print("BioNexus Runtime Pre-Tool Guard Check")
            print("=" * 60)
            print(f"Status: {verdict.status.value}")
            print(f"Execution Permitted: {verdict.execution_permitted}")
            if verdict.violation_ids:
                print(f"Violations: {', '.join(verdict.violation_ids)}")
            if verdict.warrant_guidance:
                print("\nWarrant Guidance:")
                for g in verdict.warrant_guidance:
                    print(f"  * {g}")
            if verdict.forbidden_claims:
                print("\nForbidden Claims:")
                for fc in verdict.forbidden_claims:
                    print(f"  [X] {fc}")
            if verdict.suggested_remedy:
                print(f"\nSuggested Remedy:\n{verdict.suggested_remedy}")
            print("=" * 60)
        return 0 if verdict.execution_permitted else 1

    elif action == "run":
        cmd_args = getattr(args, "cmd", [])
        if not cmd_args:
            print("Error: No command specified to run")
            return 2
        verdict = guard.inspect_command(cmd_args)
        if not verdict.execution_permitted:
            print(verdict.format_agent_injection_prompt())
            print("\n[BLOCKED] Execution halted by BioNexus Runtime Guard.")
            return 1
        elif verdict.status == GuardStatus.INJECT_CONSTRAINTS:
            print(verdict.format_agent_injection_prompt())
            print("\n[PROCEEDING WITH CONSTRAINTS]...")

        # Execute command
        return subprocess.call(cmd_args)

    elif action == "hook":
        agent = getattr(args, "agent", "codex")
        print(f"=== BioNexus Pre-Tool Hook for {agent.upper()} ===")
        print("Configure your AI Agent to invoke 'bionexus guard check' before tool execution.")
        print("Hook payload schema: bionexus.guard.GuardVerdict")
        return 0

    return 0


def handle_cache(args: argparse.Namespace) -> int:
    from bionexus.local_cache import BioLocalCache, default_local_cache

    cache = default_local_cache or BioLocalCache()
    action = getattr(args, "cache_action", "gene")

    if action == "gene":
        query = getattr(args, "query", "")
        if not query:
            print("Error: Must provide gene symbol or ID")
            return 2
        gene = cache.get_gene(query)
        if getattr(args, "json", False):
            print(json.dumps(gene or {}, indent=2, ensure_ascii=False))
        elif gene:
            print(f"Gene: {gene['symbol']} ({gene['name']})")
            print(f"Ensembl ID: {gene['ensembl_id']} | UniProt: {gene['uniprot_id']} | Chr: {gene['chromosome']}")
            print(f"Synonyms: {', '.join(gene['synonyms']) or 'None'}")
            print(f"Summary: {gene['summary']}")
        else:
            print(f"Gene '{query}' not found in local offline cache.")
            return 1
        return 0

    elif action == "markers":
        cell_type = getattr(args, "cell_type", "")
        if not cell_type:
            print("Error: Must provide cell type query")
            return 2
        markers = cache.get_markers(cell_type)
        if getattr(args, "json", False):
            print(json.dumps({"cell_type": cell_type, "markers": markers}, indent=2, ensure_ascii=False))
        else:
            print(f"Canonical Markers for '{cell_type}':")
            if markers:
                for m in markers:
                    print(f"  * {m}")
            else:
                print("  No canonical markers found in local cache.")
        return 0

    elif action == "pathway":
        gene = getattr(args, "gene", "")
        if not gene:
            print("Error: Must provide gene symbol")
            return 2
        pathways = cache.get_pathways_for_gene(gene)
        if getattr(args, "json", False):
            print(json.dumps({"gene": gene, "pathways": pathways}, indent=2, ensure_ascii=False))
        else:
            print(f"Reactome Pathways for '{gene}':")
            if pathways:
                for p in pathways:
                    print(f"  * [{p['stId']}] {p['name']} ({p['species']})")
            else:
                print("  No pathways found in local cache.")
        return 0

    return 0


def register_security_arguments(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    # 15. security (Data Governance, Egress Policy, Cryptographic Audit, SBOM)
    p_security = subparsers.add_parser("security", help="Data governance, egress control policy, and cryptographic audit")
    sec_subs = p_security.add_subparsers(dest="security_action", help="Security actions")

    # security egress-policy
    p_sec_policy = sec_subs.add_parser("egress-policy", aliases=["policy"], help="Display or update active Data Egress policy")
    p_sec_policy.add_argument(
        "--mode",
        choices=["OFFLINE_STRICT", "ALLOWLIST", "CONNECTED"],
        default=None,
        help="Update active egress mode (OFFLINE_STRICT / ALLOWLIST / CONNECTED)",
    )
    p_sec_policy.add_argument("--json", action="store_true", help="Output policy as JSON")

    # security audit
    p_sec_audit = sec_subs.add_parser("audit", help="Display cryptographic egress audit trail")
    p_sec_audit.add_argument("--limit", type=int, default=20, help="Number of recent records to display (default: 20)")
    p_sec_audit.add_argument("--json", action="store_true", help="Output audit log as JSON")

    # security sbom
    p_sec_sbom = sec_subs.add_parser("sbom", help="Generate CycloneDX Software Bill of Materials (SBOM)")
    p_sec_sbom.add_argument("-o", "--output", default="sbom.json", help="Output JSON path (default: sbom.json)")
    return p_security


def register_guard_arguments(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    # 19. guard (Pre-Tool Runtime Guard & Constraint Injection)
    p_guard = subparsers.add_parser("guard", help="Runtime pre-execution guard and warrant constraint injection")
    guard_subs = p_guard.add_subparsers(dest="guard_action", help="Guard actions")
    p_guard_check = guard_subs.add_parser("check", help="Preflight check a code snippet or script file")
    p_guard_check.add_argument("code", nargs="?", default=None, help="Code string to inspect")
    p_guard_check.add_argument("-f", "--file", default=None, help="Script path to inspect")
    p_guard_check.add_argument("--json", action="store_true", help="Output result as JSON")

    p_guard_run = guard_subs.add_parser("run", help="Run command with active pre-tool guard protection")
    p_guard_run.add_argument("cmd", nargs=argparse.REMAINDER, help="Command and arguments to execute")

    p_guard_hook = guard_subs.add_parser("hook", help="Show Agent pre-tool hook setup instructions")
    p_guard_hook.add_argument("--agent", default="codex", choices=["codex", "claude", "cursor"], help="Target AI agent")
    return p_guard


def register_cache_arguments(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    # 20. cache (Air-Gapped Embedded Knowledge Base & Local Cache)
    p_cache = subparsers.add_parser("cache", help="Query local offline biomedical knowledge base")
    cache_subs = p_cache.add_subparsers(dest="cache_action", help="Cache actions")
    p_cache_gene = cache_subs.add_parser("gene", help="Query gene symbol / Ensembl / UniProt from local cache")
    p_cache_gene.add_argument("query", help="Gene symbol, synonym, or ID")
    p_cache_gene.add_argument("--json", action="store_true", help="Output result as JSON")

    p_cache_markers = cache_subs.add_parser("markers", help="Query canonical markers for a cell type")
    p_cache_markers.add_argument("cell_type", help="Cell type name (e.g. 'T cell', 'B cell')")
    p_cache_markers.add_argument("--json", action="store_true", help="Output result as JSON")

    p_cache_pathway = cache_subs.add_parser("pathway", help="Query Reactome pathways for a gene")
    p_cache_pathway.add_argument("gene", help="Gene symbol (e.g. TP53, EGFR)")
    p_cache_pathway.add_argument("--json", action="store_true", help="Output result as JSON")
    return p_cache
