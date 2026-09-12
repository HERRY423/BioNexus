"""
BioNexus Unified Command-Line Interface — the Scientific Assertion Firewall.

Commands:
  bionexus preflight     Decide BEFORE compute whether an analysis should run (BNS-013)
  bionexus audit         Audit notebooks/scripts for scientific flaws, or data-matrix integrity
  bionexus verify        Verify final results against their Claim-Evidence Ledger (BNS-013)
  bionexus bench         BioFailureBench trap corpus: validate / summary (BNS-014)
  bionexus interop       Standards exports: RO-Crate / Workflow Run RO-Crate / BioCompute Object (BNS-016)
  bionexus standards     Standards alignment registry with honest statuses (BNS-016)
  bionexus create-plugin Scaffold a new skill following the Gold Reference pattern
  bionexus create-skill  Alias for create-plugin
  bionexus doctor        Run environment and backend preflight diagnostics
  bionexus list-skills   Display canonical skill inventory and capability tiers
  bionexus inventory     Alias for list-skills
  bionexus registry      Compile and validate multi-platform registry manifests
  bionexus ivn           Register and verify independent-validation evidence
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from bionexus.commands import (
    claims,
    de,
    diagnostics,
    execution,
    experimental,
    ivn,
    lab,
    scaffold,
    security,
    standards,
    validation,
)
from bionexus.commands.claims import handle_audit_claims as handle_audit_claims
from bionexus.commands.claims import handle_failures as handle_failures
from bionexus.commands.claims import handle_ledger as handle_ledger
from bionexus.commands.claims import handle_parse_claim as handle_parse_claim
from bionexus.commands.claims import handle_route as handle_route
from bionexus.commands.claims import handle_rule as handle_rule
from bionexus.commands.claims import handle_warrant_claim as handle_warrant_claim
from bionexus.commands.de import handle_audit as handle_audit
from bionexus.commands.de import handle_audit_de as handle_audit_de
from bionexus.commands.de import handle_audit_de_summary as handle_audit_de_summary
from bionexus.commands.de import handle_audit_de_verify as handle_audit_de_verify
from bionexus.commands.diagnostics import handle_backend_identity as handle_backend_identity
from bionexus.commands.diagnostics import handle_doctor as handle_doctor
from bionexus.commands.diagnostics import handle_list_skills as handle_list_skills
from bionexus.commands.diagnostics import handle_registry as handle_registry
from bionexus.commands.execution import handle_bigdata as handle_bigdata
from bionexus.commands.execution import handle_cluster as handle_cluster
from bionexus.commands.execution import handle_run as handle_run
from bionexus.commands.execution import handle_scfm as handle_scfm
from bionexus.commands.experimental import handle_causal as handle_causal
from bionexus.commands.experimental import handle_closed_loop as handle_closed_loop
from bionexus.commands.experimental import handle_remediate as handle_remediate
from bionexus.commands.ivn import handle_debt as handle_debt
from bionexus.commands.ivn import handle_ivn as handle_ivn
from bionexus.commands.lab import _emit_cli_payload as _emit_cli_payload
from bionexus.commands.lab import handle_airgap as handle_airgap
from bionexus.commands.lab import handle_compliance as handle_compliance
from bionexus.commands.lab import handle_ga4gh as handle_ga4gh
from bionexus.commands.lab import handle_instrument as handle_instrument
from bionexus.commands.lab import handle_lims as handle_lims
from bionexus.commands.lab import handle_nextflow as handle_nextflow
from bionexus.commands.scaffold import COMMON_PY_TEMPLATE as COMMON_PY_TEMPLATE
from bionexus.commands.scaffold import PIPELINE_SCRIPT_TEMPLATE as PIPELINE_SCRIPT_TEMPLATE

# Compatibility exports: existing handler imports remain valid.
from bionexus.commands.scaffold import SKILL_MD_TEMPLATE as SKILL_MD_TEMPLATE
from bionexus.commands.scaffold import TEST_TEMPLATE as TEST_TEMPLATE
from bionexus.commands.scaffold import _to_kebab_case as _to_kebab_case
from bionexus.commands.scaffold import _to_snake_case as _to_snake_case
from bionexus.commands.scaffold import handle_create_plugin as handle_create_plugin
from bionexus.commands.security import handle_cache as handle_cache
from bionexus.commands.security import handle_guard as handle_guard
from bionexus.commands.security import handle_security as handle_security
from bionexus.commands.standards import handle_abi as handle_abi
from bionexus.commands.standards import handle_capability as handle_capability
from bionexus.commands.standards import handle_certification as handle_certification
from bionexus.commands.standards import handle_interop as handle_interop
from bionexus.commands.standards import handle_standards as handle_standards
from bionexus.commands.validation import handle_bench as handle_bench
from bionexus.commands.validation import handle_conformance as handle_conformance
from bionexus.commands.validation import handle_eval as handle_eval
from bionexus.commands.validation import handle_eval_audit as handle_eval_audit
from bionexus.commands.validation import handle_preflight as handle_preflight
from bionexus.commands.validation import handle_prevent as handle_prevent
from bionexus.commands.validation import handle_verify as handle_verify
from bionexus.versions import PLUGIN_VERSION


def _configure_console_streams() -> None:
    """Keep CLI diagnostics printable on restricted Windows code pages.

    Scientific inventory text legitimately contains symbols such as Greek
    delta.  Windows runners and redirected consoles can still expose cp1252;
    preserve their configured encoding, but render unsupported characters as
    explicit escapes instead of crashing after otherwise successful checks.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(errors="backslashreplace")
            except (OSError, ValueError):
                # StringIO and host-provided streams may reject reconfiguration.
                pass

def main(argv: Optional[list[str]] = None) -> int:
    _configure_console_streams()
    parser = argparse.ArgumentParser(
        prog="bionexus",
        description="BioNexus: The Scientific Reliability Layer for Agentic Biology",
    )
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"%(prog)s {PLUGIN_VERSION}",
        help="Show BioNexus version and exit",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    scaffold.register_create_plugin_arguments(subparsers)
    diagnostics.register_doctor_arguments(subparsers)
    diagnostics.register_backend_identity_arguments(subparsers)
    diagnostics.register_list_skills_arguments(subparsers)
    diagnostics.register_registry_arguments(subparsers)
    de.register_audit_arguments(subparsers)
    de.register_audit_de_arguments(subparsers)
    p_preflight = validation.register_preflight_arguments(subparsers)
    validation.register_verify_arguments(subparsers)
    p_bench = validation.register_bench_arguments(subparsers)
    p_interop = standards.register_interop_arguments(subparsers)
    standards.register_standards_arguments(subparsers)
    p_cap = standards.register_capability_arguments(subparsers)
    p_abi = standards.register_abi_arguments(subparsers)
    standards.register_certification_arguments(subparsers)
    p_fail = claims.register_failures_arguments(subparsers)
    validation.register_prevent_arguments(subparsers)
    p_ledger = claims.register_ledger_arguments(subparsers)
    claims.register_route_arguments(subparsers)
    validation.register_eval_arguments(subparsers)
    validation.register_eval_audit_arguments(subparsers)
    claims.register_audit_claims_arguments(subparsers)
    claims.register_parse_claim_arguments(subparsers)
    claims.register_warrant_claim_arguments(subparsers)
    p_rule = claims.register_rule_arguments(subparsers)
    p_ivn = ivn.register_ivn_arguments(subparsers)
    p_run = execution.register_run_arguments(subparsers)
    p_cluster = execution.register_cluster_arguments(subparsers)
    p_bigdata = execution.register_bigdata_arguments(subparsers)
    p_scfm = execution.register_scfm_arguments(subparsers)
    p_closed = experimental.register_closed_loop_arguments(subparsers)
    p_security = security.register_security_arguments(subparsers)
    validation.register_verify_artifacts_arguments(subparsers)
    p_causal = experimental.register_causal_arguments(subparsers)
    experimental.register_remediate_arguments(subparsers)
    p_guard = security.register_guard_arguments(subparsers)
    p_cache = security.register_cache_arguments(subparsers)
    p_conf = validation.register_conformance_arguments(subparsers)
    ivn.register_debt_arguments(subparsers)
    p_lims = lab.register_lims_arguments(subparsers)
    p_inst = lab.register_instrument_arguments(subparsers)
    p_airgap = lab.register_airgap_arguments(subparsers)
    p_comp = lab.register_compliance_arguments(subparsers)
    p_nextflow = lab.register_nextflow_arguments(subparsers)
    p_ga4gh = lab.register_ga4gh_arguments(subparsers)

    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 0

    if args.command == "debt":
        return handle_debt(args)
    elif args.command == "conformance":
        if not getattr(args, "conformance_action", None):
            p_conf.print_help()
            return 0
        return handle_conformance(args)
    elif args.command in ("create-plugin", "create-skill"):
        return handle_create_plugin(args)
    elif args.command == "doctor":
        return handle_doctor(args)
    elif args.command == "backend-identity":
        return handle_backend_identity(args)
    elif args.command in ("list-skills", "inventory"):
        return handle_list_skills(args)
    elif args.command == "registry":
        if not (args.check or args.validate_endpoints or args.live_check or args.generate):
            args.generate = True
        return handle_registry(args)
    elif args.command == "audit":
        return handle_audit(args)
    elif args.command in ("audit-de", "de-audit"):
        return handle_audit_de(args)
    elif args.command == "audit-de-summary":
        return handle_audit_de_summary(args)
    elif args.command == "audit-de-verify":
        return handle_audit_de_verify(args)
    elif args.command == "preflight":
        if not (getattr(args, "intent", None) or getattr(args, "query", None)):
            p_preflight.print_help()
            return 2
        return handle_preflight(args)
    elif args.command == "verify":
        return handle_verify(args)
    elif args.command == "bench":
        if not getattr(args, "bench_action", None):
            p_bench.print_help()
            return 0
        return handle_bench(args)
    elif args.command == "interop":
        if not getattr(args, "interop_action", None):
            p_interop.print_help()
            return 0
        return handle_interop(args)
    elif args.command == "standards":
        return handle_standards(args)
    elif args.command == "capability":
        if not getattr(args, "capability_action", None):
            p_cap.print_help()
            return 0
        return handle_capability(args)
    elif args.command == "abi":
        if not getattr(args, "abi_action", None):
            p_abi.print_help()
            return 0
        return handle_abi(args)
    elif args.command == "certification":
        return handle_certification(args)
    elif args.command == "failures":
        if not getattr(args, "failures_action", None):
            p_fail.print_help()
            return 0
        return handle_failures(args)
    elif args.command == "prevent":
        return handle_prevent(args)
    elif args.command == "ledger":
        if not getattr(args, "ledger_action", None):
            p_ledger.print_help()
            return 0
        return handle_ledger(args)
    elif args.command == "route":
        return handle_route(args)
    elif args.command == "eval":
        return handle_eval(args)
    elif args.command == "eval-audit":
        return handle_eval_audit(args)
    elif args.command == "audit-claims":
        return handle_audit_claims(args)
    elif args.command == "parse-claim":
        return handle_parse_claim(args)
    elif args.command == "warrant-claim":
        return handle_warrant_claim(args)
    elif args.command == "rule":
        if not getattr(args, "rule_action", None):
            p_rule.print_help()
            return 0
        return handle_rule(args)
    elif args.command == "run":
        if not getattr(args, "run_action", None):
            p_run.print_help()
            return 0
        return handle_run(args)
    elif args.command == "cluster":
        if not getattr(args, "cluster_action", None):
            p_cluster.print_help()
            return 0
        return handle_cluster(args)
    elif args.command == "bigdata":
        if not getattr(args, "bigdata_action", None):
            p_bigdata.print_help()
            return 0
        return handle_bigdata(args)
    elif args.command == "scfm":
        if not getattr(args, "scfm_action", None):
            p_scfm.print_help()
            return 0
        return handle_scfm(args)
    elif args.command in ("closed-loop", "closed_loop"):
        if not getattr(args, "closed_loop_action", None):
            p_closed.print_help()
            return 0
        return handle_closed_loop(args)
    elif args.command == "security":
        if not getattr(args, "security_action", None):
            p_security.print_help()
            return 0
        return handle_security(args)
    elif args.command in ("verify-artifacts", "verify_validation_artifacts"):
        from bionexus.validation_verifier import verify_validation_artifacts

        repo_root = getattr(args, "root", None)
        enforce_ver = getattr(args, "enforce_version", None)
        res = verify_validation_artifacts(repo_root=repo_root, enforce_version=enforce_ver)
        if getattr(args, "json", False):
            print(json.dumps(res.to_dict(), indent=2, ensure_ascii=False))
        else:
            print(res.summary_str())
        return 0 if res.passed else 1
    elif args.command == "causal":
        if not getattr(args, "causal_action", None):
            p_causal.print_help()
            return 0
        return handle_causal(args)
    elif args.command == "remediate":
        return handle_remediate(args)
    elif args.command == "guard":
        if not getattr(args, "guard_action", None):
            p_guard.print_help()
            return 0
        return handle_guard(args)
    elif args.command == "cache":
        if not getattr(args, "cache_action", None):
            p_cache.print_help()
            return 0
        return handle_cache(args)


    elif args.command == "lims":
        if not getattr(args, "lims_action", None):
            p_lims.print_help()
            return 0
        return handle_lims(args)
    elif args.command == "instrument":
        if not getattr(args, "instrument_action", None):
            p_inst.print_help()
            return 0
        return handle_instrument(args)
    elif args.command == "airgap":
        if not getattr(args, "airgap_action", None):
            p_airgap.print_help()
            return 0
        return handle_airgap(args)
    elif args.command == "compliance":
        if not getattr(args, "compliance_action", None):
            p_comp.print_help()
            return 0
        return handle_compliance(args)
    elif args.command == "nextflow":
        if not getattr(args, "nextflow_action", None):
            p_nextflow.print_help()
            return 0
        return handle_nextflow(args)

    elif args.command == "ivn":
        if not getattr(args, "ivn_action", None):
            p_ivn.print_help()
            return 0
        return handle_ivn(args)
    elif args.command == "ga4gh":
        if not getattr(args, "ga4gh_action", None):
            p_ga4gh.print_help()
            return 0
        return handle_ga4gh(args)

    return 0

if __name__ == "__main__":
    sys.exit(main())
