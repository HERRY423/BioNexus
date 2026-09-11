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
from pathlib import Path
from typing import Optional

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

    # 1. create-plugin / create-skill
    for cmd_name in ("create-plugin", "create-skill"):
        p_scaffold = subparsers.add_parser(
            cmd_name,
            help="Scaffold a new skill following the Gold Reference pattern",
        )
        p_scaffold.add_argument("name", help="Name of the skill (e.g., spatial-cell-type-mapper)")
        p_scaffold.add_argument("--display-name", default=None, help="Human-readable title")
        p_scaffold.add_argument(
            "--tier",
            choices=["core", "wrapper", "heuristic", "outline"],
            default="core",
            help="Capability tier (default: core)",
        )
        p_scaffold.add_argument(
            "--grade",
            choices=["A", "B", "C", "abstain"],
            default="A",
            help="Evidence grade (default: A)",
        )
        p_scaffold.add_argument(
            "--status",
            choices=["canonical", "active", "heuristic", "outline", "deprecated"],
            default="canonical",
            help="Lifecycle status (default: canonical)",
        )
        p_scaffold.add_argument("--backend", default="scanpy", help="Required backend (default: scanpy)")
        p_scaffold.add_argument("--description", default=None, help="Brief skill summary")
        p_scaffold.add_argument("--author", default="BioNexus Team", help="Skill author")
        p_scaffold.add_argument("--output-dir", default=None, help="Target skill directory")
        p_scaffold.add_argument("--test-dir", default=None, help="Target unit test directory")
        p_scaffold.add_argument("--no-test", action="store_true", help="Skip creating unit test file")

    # 2. doctor
    p_doctor = subparsers.add_parser("doctor", help="Run environment preflight diagnostics")
    p_doctor.add_argument("--json", action="store_true", help="Output diagnostic report in JSON")
    p_doctor.add_argument("--require-scverse", action="store_true", help="Enforce scverse stack presence")
    p_doctor.add_argument("--require-spatial", action="store_true", help="Enforce spatial stack presence")

    # 2.5 backend-identity
    p_backend_identity = subparsers.add_parser(
        "backend-identity",
        help="Audit Backend Identity Conformance: declared_backend == observed_backend (BNS-EF-012..016, BN-F010)",
    )
    p_backend_identity.add_argument("--json", action="store_true", help="Output identity reports as JSON")
    p_backend_identity.add_argument("--capability", default=None, help="Audit a single capability id")
    p_backend_identity.add_argument("--canonical-only", action="store_true", help="Skip the frontier track")

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

    # 4. registry
    p_registry = subparsers.add_parser("registry", help="Compile and validate multi-platform registry manifests")
    p_registry.add_argument("--generate", action="store_true", help="Compile manifests from registry")
    p_registry.add_argument("--check", action="store_true", help="Verify zero configuration drift")
    p_registry.add_argument("--validate-endpoints", action="store_true", help="Validate MCP endpoint syntax")
    p_registry.add_argument("--live-check", action="store_true", help="Probe live HTTP endpoints")
    p_registry.add_argument("--registry-path", default=None, help="Path to bionexus.registry.yaml")

    # 5. audit (data files AND notebooks/scripts -> static scientific audit)
    p_audit = subparsers.add_parser(
        "audit",
        help="Audit a notebook/script for scientific flaws, or audit data matrix semantics",
    )
    p_audit.add_argument(
        "path",
        help="Path to notebook (.ipynb), script (.py/.R/.Rmd/.qmd), or data file (.h5ad/csv)",
    )
    p_audit.add_argument("--expected-type", choices=["counts", "normalized"], default="counts")
    p_audit.add_argument("--de", action="store_true", help="Perform comprehensive multi-donor single-cell differential expression audit")
    p_audit.add_argument("--json", action="store_true", help="Output audit result as JSON")

    # 5.1 audit-de (Multi-donor single-cell DE evidence audit for lab meeting / submission / sharing)
    p_audit_de = subparsers.add_parser(
        "audit-de",
        aliases=["de-audit"],
        help="Evidence audit for multi-donor single-cell differential expression before lab meetings, submission, or sharing",
    )
    p_audit_de.add_argument("path", nargs="?", default=None, help="Path to .h5ad, DE table (.csv), or analysis script")
    p_audit_de.add_argument("--h5ad", "--data", dest="h5ad", default=None, help="Path to AnnData (.h5ad) file")
    p_audit_de.add_argument("--de-table", "--results", dest="de_table", default=None, help="Path to DEG results table (CSV/TSV)")
    p_audit_de.add_argument("--sample-sheet", "--design", dest="sample_sheet", default=None, help="Path to sample/donor metadata CSV/TSV")
    p_audit_de.add_argument("--script", "--notebook", dest="script", default=None, help="Path to analysis script (.py/.R) or notebook (.ipynb)")
    p_audit_de.add_argument("--execution", "--execution-record", dest="execution", default=None, help="Path to execution record JSON or verification bundle")
    p_audit_de.add_argument("--claim", "--statement", dest="claim", default=None, help="Free-text scientific claim statement to verify")
    p_audit_de.add_argument("--donor-col", dest="donor_col", default=None, help="Column name for biological donors (auto-detected if omitted)")
    p_audit_de.add_argument("--condition-col", dest="condition_col", default=None, help="Column name for experimental conditions (auto-detected if omitted)")
    p_audit_de.add_argument("--cell-type-col", dest="cell_type_col", default=None, help="Column name for cell types/clusters (auto-detected if omitted)")
    p_audit_de.add_argument("--batch-col", dest="batch_col", default=None, help="Column name for technical batches (auto-detected if omitted)")
    p_audit_de.add_argument("-o", "--out", "--output", dest="out", default=None, help="Export audit report to Markdown (.md) or JSON (.json)")
    p_audit_de.add_argument("--json", action="store_true", help="Output audit result as JSON")
    p_audit_de.add_argument("--bundle", default=None, help="New directory for concise review, evidence and human pilot observation template")
    p_audit_de.add_argument("--demo", action="store_true", help="Use synthetic teaching inputs with --bundle; excluded from pilot outcomes")

    p_de_summary = subparsers.add_parser("audit-de-summary", help="Summarize human-reported DE pilot observations without certifying benefit")
    p_de_summary.add_argument("reviews", nargs="+", help="Paths to completed or pending bundle review.json files")
    p_de_summary.add_argument("--json", action="store_true", help="Output descriptive observations as JSON")
    p_de_summary.add_argument("-o", "--out", default=None, help="Write a new summary file; existing files are never replaced")

    p_de_verify = subparsers.add_parser("audit-de-verify", help="Read-only DE bundle file verification; never scientific approval")
    p_de_verify.add_argument("bundle", help="Existing DE shadow-review directory")
    p_de_verify.add_argument("--expected-manifest-sha256", default=None, help="Manifest digest retained independently by the caller")

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

    # 5.6 verify (Scientific Assertion Firewall entry 3, BNS-013)
    p_verify = subparsers.add_parser(
        "verify",
        help="Verify final results against their Claim-Evidence Ledger (BNS-013)",
    )
    p_verify.add_argument("path", help="Path to results ledger JSON or a results directory containing one")
    p_verify.add_argument("--json", action="store_true", help="Output verification report as JSON")

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

    # 5.8 interop (standards-based exports, BNS-016)
    p_interop = subparsers.add_parser(
        "interop",
        help="Standards-based exports: RO-Crate / Workflow Run RO-Crate / BioCompute Object (BNS-016)",
    )
    interop_subs = p_interop.add_subparsers(dest="interop_action", help="Interoperability actions")
    p_io_crate = interop_subs.add_parser(
        "ro-crate", help="Export a run capsule or ledger as an RO-Crate 1.1 document"
    )
    p_io_crate.add_argument("path", help="Run capsule (dir/run.json) or ledger JSON")
    p_io_crate.add_argument("--out", default=None, help="Output file (default: print to stdout)")
    p_io_bco = interop_subs.add_parser(
        "bco", help="Export a run capsule as an IEEE 2791-2020 BioCompute Object"
    )
    p_io_bco.add_argument("path", help="Run capsule directory or run.json file")
    p_io_bco.add_argument("--out", default=None, help="Output file (default: print to stdout)")
    p_io_wfrun = interop_subs.add_parser(
        "wfrun-crate",
        help=(
            "Export a run capsule as a Workflow Run RO-Crate Research Object "
            "(inputs, software, execution, steps, outputs, EvidenceCard, Claim Ledger)"
        ),
    )
    p_io_wfrun.add_argument("path", help="Run capsule directory or run.json file")
    p_io_wfrun.add_argument("--out", default=None, help="Output crate directory (default: print to stdout)")
    p_io_wfrun.add_argument(
        "--ledger", default=None, help="Claim–Evidence Ledger JSON to embed (default: adjacent bionexus.ledger.json)"
    )
    p_io_wfrun.add_argument("--zip", action="store_true", help="Also write a deterministic .zip of the crate")
    p_io_de_crate = interop_subs.add_parser(
        "de-crate", help="Export a Differential Expression audit report as an RO-Crate 1.1 Research Object"
    )
    p_io_de_crate.add_argument("report", help="Path to differential expression audit report JSON")
    p_io_de_crate.add_argument("--out", required=True, help="Output crate directory")
    p_io_de_crate.add_argument("--zip", action="store_true", help="Also write a deterministic .zip of the crate")
    p_io_check = interop_subs.add_parser(
        "check", help="Structurally validate the projections for a run capsule or ledger"
    )
    p_io_check.add_argument("path", help="Run capsule (dir/run.json) or ledger JSON")

    # 5.9 standards (alignment registry, BNS-016)
    p_standards = subparsers.add_parser(
        "standards",
        help="Standards alignment registry: RO-Crate, BCO, PROV-O, GA4GH, ... (honest statuses)",
    )
    p_standards.add_argument("--json", action="store_true", help="Output alignment report as JSON")

    # 6. capability
    p_cap = subparsers.add_parser(
        "capability", help="Query and validate machine-readable scientific capability contracts"
    )
    cap_subs = p_cap.add_subparsers(dest="capability_action", help="Capability actions")

    # capability list
    p_cap_list = cap_subs.add_parser("list", help="List available capability contracts")
    p_cap_list.add_argument("--intent", default=None, help="Filter by scientific intent")
    p_cap_list.add_argument("--skill", default=None, help="Filter by skill name")
    p_cap_list.add_argument("--json", action="store_true", help="Output as JSON")

    # capability show <id>
    p_cap_show = cap_subs.add_parser("show", help="Show full capability contract specification")
    p_cap_show.add_argument("id", help="Capability contract ID (e.g. scrna.pseudobulk_de)")
    p_cap_show.add_argument("--json", action="store_true", help="Output contract as JSON")

    # capability check <id>
    p_cap_check = cap_subs.add_parser("check", help="Evaluate capability preconditions and refusal triggers")
    p_cap_check.add_argument("id", help="Capability contract ID (e.g. scrna.pseudobulk_de)")
    p_cap_check.add_argument("--meta-json", default=None, help="Path to input metadata JSON")
    p_cap_check.add_argument("--min-replicates", type=int, default=None, help="Number of replicates per condition")
    p_cap_check.add_argument("--is-normalized", action="store_true", help="Flag if input is normalized floats")
    p_cap_check.add_argument("--json", action="store_true", help="Output evaluation as JSON")

    # 6.5 abi (Biological Capability ABI)
    p_abi = subparsers.add_parser(
        "abi", help="Inspect the Biological Capability ABI (Scientific ABI boundary for host agents)"
    )
    abi_subs = p_abi.add_subparsers(dest="abi_action", help="ABI actions")

    # abi list
    p_abi_list = abi_subs.add_parser("list", help="List all capability ABI records")
    p_abi_list.add_argument("--json", action="store_true", help="Output as JSON")

    # abi show <id>
    p_abi_show = abi_subs.add_parser("show", help="Show the full ABI record for a capability")
    p_abi_show.add_argument("id", help="Capability contract ID (e.g. spatial.morans_svg)")
    p_abi_show.add_argument("--json", action="store_true", help="Output ABI record as JSON")

    # abi audit-claims <id> --claims ...
    p_abi_audit = abi_subs.add_parser(
        "audit-claims", help="Audit candidate output claims against the capability's forbidden claims"
    )
    p_abi_audit.add_argument("id", help="Capability contract ID")
    p_abi_audit.add_argument(
        "--claims", nargs="+", required=True, help="Candidate claim strings to audit"
    )
    p_abi_audit.add_argument("--json", action="store_true", help="Output audit as JSON")

    # abi conformance
    p_abi_conf = abi_subs.add_parser(
        "conformance", help="Structural conformance scan of all ABI records (BNS-CC-010..014)"
    )
    p_abi_conf.add_argument("--json", action="store_true", help="Output as JSON")

    # 6.6 certification (BNS-010)
    p_cert = subparsers.add_parser(
        "certification", help="Capability certification tiers, evidence, and honest gap roadmap (BNS-010)"
    )
    p_cert.add_argument("--json", action="store_true", help="Output full certification report as JSON")

    # 6.7 failures (BNS-011)
    p_fail = subparsers.add_parser(
        "failures", help="BioNexus Scientific Failure Taxonomy (BN-Fxxx) (BNS-011)"
    )
    fail_subs = p_fail.add_subparsers(dest="failures_action", help="Failure taxonomy actions")

    p_fail_list = fail_subs.add_parser("list", help="List all failure modes")
    p_fail_list.add_argument("--json", action="store_true", help="Output as JSON")

    p_fail_matrix = fail_subs.add_parser("matrix", help="Show Capability x Failure Mode mapping matrix")
    p_fail_matrix.add_argument("--json", action="store_true", help="Output as JSON")

    p_fail_tax = fail_subs.add_parser("taxonomy", help="Dump complete Failure Taxonomy v1 specification")
    p_fail_tax.add_argument("--json", action="store_true", help="Output as JSON")

    p_fail_show = fail_subs.add_parser("show", help="Show one failure mode record")
    p_fail_show.add_argument("id", help="Failure mode ID (e.g. BN-F002)")
    p_fail_show.add_argument("--json", action="store_true", help="Output as JSON")

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

    # 6.9 ledger (BNS-012)
    p_ledger = subparsers.add_parser(
        "ledger", help="Inspect a Claim–Evidence Ledger JSON artifact (BNS-012)"
    )
    ledger_subs = p_ledger.add_subparsers(dest="ledger_action", help="Ledger actions")

    p_ledger_show = ledger_subs.add_parser("show", help="Render ledger claims and evidence status")
    p_ledger_show.add_argument("path", help="Path to ledger JSON file")
    p_ledger_show.add_argument("--json", action="store_true", help="Output raw ledger as JSON")

    p_ledger_ld = ledger_subs.add_parser("jsonld", help="Project the ledger as PROV-O JSON-LD")
    p_ledger_ld.add_argument("path", help="Path to ledger JSON file")

    # 7. route (Validated Scientific Intent Router)
    p_route = subparsers.add_parser(
        "route", help="Route scientific queries to validated capabilities with invariant checks"
    )
    p_route.add_argument("query", help="User scientific query / intent string")
    p_route.add_argument("--data", default=None, help="Optional path to dataset file (.h5ad, .csv)")
    p_route.add_argument(
        "--min-replicates", type=int, default=None, help="Number of biological replicates per condition"
    )
    p_route.add_argument(
        "--is-normalized", action="store_true", help="Flag if input matrix is normalized continuous floats"
    )
    p_route.add_argument("--allow-degraded", action="store_true", help="Allow fallback to Grade C heuristics")
    p_route.add_argument(
        "--allow-frontier", action="store_true", help="Explicit opt-in to execute experimental frontier capabilities"
    )
    p_route.add_argument("--purpose", "--research-purpose", dest="purpose", default=None, help="Explicit research purpose (exploratory / screening / confirmatory / causal / clinical)")
    p_route.add_argument("--factors", "--evidence-factors", dest="factors", default=None, help="Comma-separated declared evidence factors")
    p_route.add_argument("--claim-class", dest="claim_class", default=None, help="Claim class under evaluation")
    p_route.add_argument("--documented-extras", dest="documented_extras", default=None, help="Comma-separated documentable extra conditions")
    p_route.add_argument("--override-justification", default="", help="Justification string for researcher override")
    p_route.add_argument("--lab-policy", default=None, help="Lab policy profile name")
    p_route.add_argument("--json", action="store_true", help="Output routing decision as JSON")

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

    # 9. audit-claims (Prohibited Claims & Hallucination Auditor)
    p_claim = subparsers.add_parser(
        "audit-claims", help="Audit text response or report artifact for prohibited scientific claims"
    )
    p_claim.add_argument("target", help="Response text or file path to evaluate")
    p_claim.add_argument("--capability", default=None, help="Optional capability context ID")
    p_claim.add_argument("--json", action="store_true", help="Output claim audit result as JSON")

    # 9.1 parse-claim (Scientific Claim IR Parser, BNS-017)
    p_parse = subparsers.add_parser(
        "parse-claim", help="Parse natural-language claim into structured ScientificClaimIR (BNS-017)"
    )
    p_parse.add_argument("claim", help="Natural-language claim statement or file path")
    p_parse.add_argument("--json", action="store_true", help="Output structured claim IR as JSON")

    # 9.2 warrant-claim (Deterministic Warrant Engine, BNS-017)
    p_warrant = subparsers.add_parser(
        "warrant-claim", help="Evaluate claim against EvidenceProfile using Deterministic Warrant Engine (BNS-017)"
    )
    p_warrant.add_argument("claim", help="Natural-language claim statement or file path")
    p_warrant.add_argument("--evidence-json", default=None, help="Path to JSON file containing EvidenceProfile")
    p_warrant.add_argument("--spatial", action="store_true", help="Flag: spatial colocalization evidence present")
    p_warrant.add_argument("--ligand-receptor", action="store_true", help="Flag: ligand-receptor inference present")
    p_warrant.add_argument("--perturbation", action="store_true", help="Flag: experimental perturbation present")
    p_warrant.add_argument("--replicates", type=int, default=0, help="Number of biological replicates")
    p_warrant.add_argument("--json", action="store_true", help="Output warrant evaluation result as JSON")

    # 9.3 rule (Rule Calibration & Challenge Network, BNS-018)
    p_rule = subparsers.add_parser(
        "rule", help="Inspect and challenge rules in the Scientific Reliability Knowledge Base (BNS-018)"
    )
    rule_subs = p_rule.add_subparsers(dest="rule_action", help="Rule actions")

    # rule list
    p_r_list = rule_subs.add_parser("list", help="List all calibrated rules in the reliability knowledge base")
    p_r_list.add_argument("--json", action="store_true", help="Output rules as JSON")

    # rule show <rule_id>
    p_r_show = rule_subs.add_parser("show", help="Show detailed calibration, sensitivity, and peer reviews for a rule")
    p_r_show.add_argument("rule_id", help="Canonical rule ID or alias")
    p_r_show.add_argument("--json", action="store_true", help="Output calibrated rule as JSON")

    # rule challenge <rule_id>
    p_r_chal = rule_subs.add_parser("challenge", help="Submit a formal challenge to a rule in the network")
    p_r_chal.add_argument("rule_id", help="Canonical rule ID to challenge")
    p_r_chal.add_argument("--challenger", required=True, help="Challenger identity (ORCID, name, or institution)")
    p_r_chal.add_argument(
        "--type",
        default="EMPIRICAL_COUNTEREXAMPLE",
        choices=[
            "EMPIRICAL_COUNTEREXAMPLE",
            "BENCHMARK_DISSENT",
            "REGIME_BOUNDARY_VIOLATION",
            "PARAMETER_DRIFT",
            "MATHEMATICAL_FLAW",
            "PLATFORM_INCOMPATIBILITY",
        ],
        help="Category of scientific challenge",
    )
    p_r_chal.add_argument("--title", required=True, help="Short title of the challenge")
    p_r_chal.add_argument("--description", required=True, help="Detailed scientific rationale and empirical proof")
    p_r_chal.add_argument("--dataset", default=None, help="Supporting dataset DOI, URL, or accession")

    # rule list-challenges
    p_r_lchal = rule_subs.add_parser("list-challenges", help="List all recorded scientific challenges and statuses")
    p_r_lchal.add_argument("--json", action="store_true", help="Output challenges as JSON")

    # 9.5 ivn (Independent Validation Network, BNS-023)
    p_ivn = subparsers.add_parser(
        "ivn",
        help="Independent Validation Network: >= 3 independent datasets x >= 2 external labs x >= 1 non-author reviewer per flagship (BNS-023)",
    )
    ivn_subs = p_ivn.add_subparsers(dest="ivn_action", help="IVN actions")

    p_ivn_status = ivn_subs.add_parser(
        "status", help="Assess every flagship capability against the IVN quotas and OPEN_QUESTIONS blockers"
    )
    p_ivn_status.add_argument("--registry", default=None, help="Path to the IVN registry (default: validation/ivn/REGISTRY.json)")
    p_ivn_status.add_argument("--repo-root", default=".", help="Repository root used to resolve artifact paths")
    p_ivn_status.add_argument("--json", action="store_true", help="Output the full assessment as JSON")

    p_ivn_verify = ivn_subs.add_parser(
        "verify", help="Recompute every recorded artifact hash in the IVN registry (drift check)"
    )
    p_ivn_verify.add_argument("--registry", default=None, help="Path to the IVN registry")
    p_ivn_verify.add_argument("--repo-root", default=".", help="Repository root used to resolve artifact paths")
    p_ivn_verify.add_argument("--json", action="store_true", help="Output the integrity report as JSON")

    for register_kind, register_help in (
        ("register-dataset", "Register an independent dataset (requires on-disk preregistration/report artifacts)"),
        ("register-lab-study", "Register an external-lab study executed against a registered dataset"),
        ("register-review", "Register a blinded non-author review (refuses author-roster overlap)"),
    ):
        p_reg = ivn_subs.add_parser(register_kind, help=register_help)
        p_reg.add_argument("--payload", required=True, help="Entity JSON payload (see validation/ivn/templates/)")
        p_reg.add_argument("--registry", default=None, help="Path to the IVN registry")
        p_reg.add_argument("--repo-root", default=".", help="Repository root used to resolve artifact paths")
        p_reg.add_argument("--json", action="store_true", help="Output the registration receipt as JSON")

    p_ivn_verify_review = ivn_subs.add_parser(
        "verify-review",
        help="Promote one REGISTERED review after fail-closed artifact and blinding verification",
    )
    p_ivn_verify_review.add_argument("--review-id", required=True, help="Registered review id")
    p_ivn_verify_review.add_argument(
        "--expected-commit", required=True, help="Full immutable commit reviewed by the external reviewer"
    )
    p_ivn_verify_review.add_argument(
        "--verified-by", required=True, help="Named maintainer or governance body performing the check"
    )
    p_ivn_verify_review.add_argument(
        "--receipt-output",
        default=None,
        help="Repository-relative verification receipt path (default: alongside the review)",
    )
    p_ivn_verify_review.add_argument("--notes", default="", help="Verification notes")
    p_ivn_verify_review.add_argument("--registry", default=None, help="Path to the IVN registry")
    p_ivn_verify_review.add_argument("--repo-root", default=".", help="Repository root for artifact paths")
    p_ivn_verify_review.add_argument("--json", action="store_true", help="Output the verification receipt summary")

    p_ivn_freeze = ivn_subs.add_parser(
        "freeze-profile", help="Freeze an APPROVED calibration profile to its held-out contexts (fail-closed)"
    )
    p_ivn_freeze.add_argument("--profile-json", required=True, help="Calibration profile JSON payload")
    p_ivn_freeze.add_argument("--held-out-json", required=True, help="JSON list of held-out context payloads")
    p_ivn_freeze.add_argument("--freeze-id", required=True, help="Unique freeze id")
    p_ivn_freeze.add_argument("--frozen-by", required=True, help="Accountable person or body performing the freeze")
    p_ivn_freeze.add_argument("--notes", default="", help="Freeze notes")
    p_ivn_freeze.add_argument("--registry", default=None, help="Path to the IVN registry (freezes are recorded there)")
    p_ivn_freeze.add_argument("--repo-root", default=".", help="Repository root used to resolve default registry path")
    p_ivn_freeze.add_argument("--json", action="store_true", help="Output the freeze record as JSON")

    p_ivn_authorize = ivn_subs.add_parser(
        "authorize", help="Fail-closed gate: may a calibration profile authorize this context? (requires an intact freeze)"
    )
    p_ivn_authorize.add_argument("--profile-json", required=True, help="Calibration profile JSON payload")
    p_ivn_authorize.add_argument("--context-json", required=True, help="Held-out context JSON payload")
    p_ivn_authorize.add_argument("--registry", default=None, help="Path to the IVN registry")
    p_ivn_authorize.add_argument("--repo-root", default=".", help="Repository root used to resolve default registry path")
    p_ivn_authorize.add_argument("--json", action="store_true", help="Output the decision as JSON")

    p_ivn_build = ivn_subs.add_parser(
        "build-ledger",
        aliases=["render-page", "render-ledger"],
        help="Compile and render the standalone public IVN evidence ledger HTML portal (GitHub Pages ready)",
    )
    p_ivn_build.add_argument("-o", "--output", default="docs/ivn/index.html", help="Output path for HTML file (default: docs/ivn/index.html)")
    p_ivn_build.add_argument("--registry", default=None, help="Path to the IVN registry")
    p_ivn_build.add_argument("--repo-root", default=".", help="Repository root used to resolve artifact paths")
    p_ivn_build.add_argument("--json", action="store_true", help="Output build summary as JSON")

    # 10. run (Run Capsule Artifact Contract)
    p_run = subparsers.add_parser("run", help="Manage and inspect standardized BioNexus Run Capsule Artifacts")
    run_subs = p_run.add_subparsers(dest="run_action", help="Run capsule actions")

    # run inspect <path>
    p_run_inspect = run_subs.add_parser("inspect", help="Inspect a run.json capsule descriptor for agent handoff")
    p_run_inspect.add_argument("path", help="Path to run/ directory or run.json file")
    p_run_inspect.add_argument("--json", action="store_true", help="Output descriptor as JSON")

    # run verify <path>
    p_run_verify = run_subs.add_parser(
        "verify", help="Verify cryptographic completeness and tamper integrity of run capsule"
    )
    p_run_verify.add_argument("path", help="Path to run/ directory or run.json file")
    p_run_verify.add_argument("--json", action="store_true", help="Output verification as JSON")

    # run list [path]
    p_run_list = run_subs.add_parser("list", help="List all BioNexus run capsules in a directory")
    p_run_list.add_argument("path", nargs="?", default=".", help="Parent directory to search (default: .)")

    # 11. cluster (HPC & Cloud Cluster Orchestrator)
    p_cluster = subparsers.add_parser("cluster", help="HPC and Cloud-Native batch cluster job orchestrator")
    cluster_subs = p_cluster.add_subparsers(dest="cluster_action", help="Cluster actions")

    # cluster probe
    p_cl_probe = cluster_subs.add_parser("probe", help="Probe host environment for available schedulers and GPUs")
    p_cl_probe.add_argument("--json", action="store_true", help="Output probe report as JSON")

    # cluster generate
    p_cl_gen = cluster_subs.add_parser("generate", help="Generate submission script for HPC / cloud batch")
    p_cl_gen.add_argument("--scheduler", default="slurm", choices=["slurm", "pbs", "lsf", "kubernetes", "aws_batch", "gcp_batch", "local"])
    p_cl_gen.add_argument("--command", "--cmd", dest="job_command", required=True, help="Bioinformatics command string to execute")
    p_cl_gen.add_argument("--job-name", default="bionexus_job", help="Job name identifier")
    p_cl_gen.add_argument("--cpus", type=int, default=8, help="Number of CPU cores requested")
    p_cl_gen.add_argument("--memory", default="32GB", help="Memory limit (e.g. 64GB, 128GB)")
    p_cl_gen.add_argument("--time-limit", default="24:00:00", help="Walltime limit (HH:MM:SS)")
    p_cl_gen.add_argument("--partition", default=None, help="Queue or partition name")
    p_cl_gen.add_argument("--account", default=None, help="Allocation or billing account")
    p_cl_gen.add_argument("--qos", default=None, help="Quality of service level")
    p_cl_gen.add_argument("--gpus", type=int, default=0, help="Number of GPUs requested")
    p_cl_gen.add_argument("--gpu-type", default=None, help="GPU type (e.g. a100, v100, h100)")
    p_cl_gen.add_argument("--image", default=None, help="Container image for K8s / Cloud Batch")
    p_cl_gen.add_argument("--workdir", default=None, help="Working directory on worker node")
    p_cl_gen.add_argument("--output-log", default=None, help="Custom path for stdout log")
    p_cl_gen.add_argument("--error-log", default=None, help="Custom path for stderr log")
    p_cl_gen.add_argument("-o", "--output", default=None, help="File path to save the generated script")

    # cluster submit
    p_cl_sub = cluster_subs.add_parser("submit", help="Submit script file to cluster scheduler")
    p_cl_sub.add_argument("script", help="Path to batch submission script")
    p_cl_sub.add_argument("--scheduler", default="slurm", choices=["slurm", "pbs", "lsf", "kubernetes", "local"])
    p_cl_sub.add_argument("--dry-run", action="store_true", help="Validate submission without executing")
    p_cl_sub.add_argument("--json", action="store_true", help="Output submission result as JSON")

    # cluster status
    p_cl_stat = cluster_subs.add_parser("status", help="Check execution state of an HPC job")
    p_cl_stat.add_argument("job_id", help="Cluster job ID to query")
    p_cl_stat.add_argument("--scheduler", default="slurm", choices=["slurm", "pbs", "lsf"])
    p_cl_stat.add_argument("--json", action="store_true", help="Output status as JSON")

    # cluster diagnose
    p_cl_diag = cluster_subs.add_parser("diagnose", help="Diagnose post-mortem failure cause from exit code and logs")
    p_cl_diag.add_argument("exit_code", type=int, help="Process exit code (e.g. 137, 143, 127)")
    p_cl_diag.add_argument("--log", default=None, help="Path to worker log file")
    p_cl_diag.add_argument("--memory-gb", type=float, default=32.0, help="Memory allocated in failed run")
    p_cl_diag.add_argument("--cpus", type=int, default=8, help="CPUs allocated in failed run")
    p_cl_diag.add_argument("--json", action="store_true", help="Output diagnosis as JSON")

    # cluster tes-task
    p_cl_tes = cluster_subs.add_parser("tes-task", help="Generate GA4GH Task Execution Service (TES) v1.0.0 task JSON")
    p_cl_tes.add_argument("--command", "--cmd", dest="job_command", required=True, help="Command string or arguments to execute")
    p_cl_tes.add_argument("--job-name", default="bionexus_tes_job", help="Job name identifier")
    p_cl_tes.add_argument("--image", default="quay.io/biocontainers/scanpy:1.10.0", help="Container image")
    p_cl_tes.add_argument("--cpus", type=int, default=8, help="Number of CPU cores")
    p_cl_tes.add_argument("--memory", default="32GB", help="Memory limit (e.g. 32GB, 64GB)")
    p_cl_tes.add_argument("--workdir", default=None, help="Working directory path")
    p_cl_tes.add_argument("-o", "--output", default=None, help="Save task JSON to file")

    # cluster elastic-profile
    p_cl_ep = cluster_subs.add_parser("elastic-profile", help="Generate cloud-native elastic scaling and retry profile")
    p_cl_ep.add_argument("--provider", default="kubernetes", choices=["kubernetes", "aws_batch", "gcp_batch", "slurm"], help="Cloud/cluster execution provider")
    p_cl_ep.add_argument("--container-engine", default="docker", choices=["docker", "singularity", "apptainer"], help="Container engine")
    p_cl_ep.add_argument("--image", default=None, help="Container image URI")
    p_cl_ep.add_argument("--min-nodes", type=int, default=1, help="Minimum worker nodes")
    p_cl_ep.add_argument("--max-nodes", type=int, default=64, help="Maximum worker nodes")
    p_cl_ep.add_argument("--max-retries", type=int, default=3, help="Max OOM retries")
    p_cl_ep.add_argument("--oom-multiplier", type=float, default=2.0, help="Memory escalation multiplier on exit 137")
    p_cl_ep.add_argument("-o", "--output", default=None, help="Save profile JSON to file")

    # 12. bigdata (Out-of-Core & Large-Scale Biological Matrix Safeguard)
    p_bigdata = subparsers.add_parser("bigdata", help="Large-scale biological matrix memory safety and out-of-core tools")
    bigdata_subs = p_bigdata.add_subparsers(dest="bigdata_action", help="Bigdata actions")

    # bigdata estimate
    p_bd_est = bigdata_subs.add_parser("estimate", help="Estimate working RAM requirements for large matrix")
    p_bd_est.add_argument("--n-cells", type=int, required=True, help="Number of cells / observations")
    p_bd_est.add_argument("--n-genes", type=int, default=30000, help="Number of genes / variables")
    p_bd_est.add_argument("--dense", action="store_true", help="Treat matrix as dense instead of sparse CSR")
    p_bd_est.add_argument("--sparsity", type=float, default=0.90, help="Expected fraction of zero values (default: 0.90)")
    p_bd_est.add_argument("--layers", type=int, default=1, help="Number of expression layers stored")
    p_bd_est.add_argument("--pcs", type=int, default=50, help="Number of PCA components computed")
    p_bd_est.add_argument("--precision", default="float32", choices=["float32", "float64"])
    p_bd_est.add_argument("--ram-gb", type=float, default=None, help="Host RAM to test against")
    p_bd_est.add_argument("--json", action="store_true", help="Output memory estimation as JSON")

    # bigdata audit
    p_bd_aud = bigdata_subs.add_parser("audit", help="Audit dataset storage format and out-of-core streaming readiness")
    p_bd_aud.add_argument("path", help="Path to dataset file or Zarr directory")
    p_bd_aud.add_argument("--json", action="store_true", help="Output storage audit as JSON")

    # bigdata plan
    p_bd_plan = bigdata_subs.add_parser("plan", help="Generate out-of-core chunked streaming execution plan")
    p_bd_plan.add_argument("--n-cells", type=int, required=True, help="Total number of cells")
    p_bd_plan.add_argument("--n-genes", type=int, default=30000, help="Total number of genes")
    p_bd_plan.add_argument("--target-ram-mb", type=float, default=2048.0, help="RAM budget per chunk in MB")
    p_bd_plan.add_argument("--json", action="store_true", help="Output streaming plan as JSON")

    # bigdata stream-aggregate
    p_bd_sa = bigdata_subs.add_parser("stream-aggregate", help="Stream-aggregate large count matrix into pseudobulk counts")
    p_bd_sa.add_argument("--counts", required=True, help="Counts CSV file (cells x genes)")
    p_bd_sa.add_argument("--obs", required=True, help="Observations CSV file with grouping columns")
    p_bd_sa.add_argument("--groupby", default="donor,condition", help="Comma-separated grouping columns")
    p_bd_sa.add_argument("--chunk-size", type=int, default=5000, help="Chunk size in number of cells")
    p_bd_sa.add_argument("-o", "--output-dir", required=True, help="Output directory for pseudobulk_counts.csv and pseudobulk_design.csv")


    # 13. scfm (Single-Cell Foundation Models: Geneformer & scGPT)
    p_scfm = subparsers.add_parser("scfm", help="Single-Cell Foundation Models (Geneformer & scGPT) inference tools")
    scfm_subs = p_scfm.add_subparsers(dest="scfm_action", help="scFM actions")

    # scfm embed
    p_scfm_emb = scfm_subs.add_parser("embed", help="Extract zero-shot or pretrained foundation model cell representations")
    p_scfm_emb.add_argument("input", help="Path to single-cell .h5ad dataset")
    p_scfm_emb.add_argument("--model", default="geneformer", choices=["geneformer", "scgpt"], help="Foundation model family")
    p_scfm_emb.add_argument("--checkpoint", default=None, help="Path to official pretrained checkpoint directory or HuggingFace ID")
    p_scfm_emb.add_argument("--proxy", action="store_true", help="Explicitly use Grade C Rank-Weighted SVD exploratory proxy")
    p_scfm_emb.add_argument("--allow-proxy", action="store_true", help="Allow fallback to Grade C proxy if checkpoint is absent")
    p_scfm_emb.add_argument("--dim", type=int, default=512, help="Embedding dimension (default: 512)")
    p_scfm_emb.add_argument("--device", default="auto", choices=["auto", "cuda", "cpu"], help="Inference device")
    p_scfm_emb.add_argument("--output", "-o", default=None, help="Optional output path to save updated .h5ad file")
    p_scfm_emb.add_argument("--json", action="store_true", help="Output embedding result as JSON")

    # scfm perturb
    p_scfm_pert = scfm_subs.add_parser("perturb", help="Simulate in silico genetic perturbation (knockout/overexpression)")
    p_scfm_pert.add_argument("input", help="Path to single-cell .h5ad dataset")
    p_scfm_pert.add_argument("--gene", required=True, help="Target gene identifier to perturb (e.g. TP53, MYC)")
    p_scfm_pert.add_argument("--mode", default="knockout", choices=["knockout", "overexpression"], help="Perturbation mode")
    p_scfm_pert.add_argument("--model", default="geneformer", choices=["geneformer", "scgpt"], help="Foundation model family")
    p_scfm_pert.add_argument("--checkpoint", default=None, help="Path to official pretrained checkpoint directory or HuggingFace ID")
    p_scfm_pert.add_argument(
        "--allow-proxy",
        action="store_true",
        help="Explicitly allow fallback to the Grade C proxy if the canonical checkpoint is absent",
    )
    p_scfm_pert.add_argument("--device", default="auto", choices=["auto", "cuda", "cpu"], help="Inference device")
    p_scfm_pert.add_argument("--json", action="store_true", help="Output perturbation report as JSON")

    # 14. closed-loop (Dry-Wet Closed Loop: GEARS Perturbation to NicheFormer Spatial Niche)
    p_closed = subparsers.add_parser("closed-loop", aliases=["closed_loop"], help="Dry-Wet closed loop perturbation to spatial niche tools")
    closed_subs = p_closed.add_subparsers(dest="closed_loop_action", help="Closed-loop actions")

    # closed-loop gears
    p_cl_gears = closed_subs.add_parser("gears", help="Simulate combinatorial in silico genetic perturbation with GEARS")
    p_cl_gears.add_argument("input", help="Path to single-cell .h5ad baseline dataset")
    p_cl_gears.add_argument("--genes", required=True, help="Comma-separated target gene symbols (e.g. TP53 or MYC,CDKN1A)")
    p_cl_gears.add_argument("--mode", default="knockout", choices=["knockout", "overexpression"], help="Perturbation mode")
    p_cl_gears.add_argument("--output", "-o", default=None, help="Optional output path to save perturbed .h5ad dataset")
    p_cl_gears.add_argument("--json", action="store_true", help="Output result as JSON")

    # closed-loop nicheformer
    p_cl_niche = closed_subs.add_parser("nicheformer", help="Forecast spatial microenvironment / niche distributions with NicheFormer")
    p_cl_niche.add_argument("--cells", required=True, help="Path to single-cell .h5ad dataset")
    p_cl_niche.add_argument("--spatial", required=True, help="Path to spatial .h5ad dataset with obsm['spatial']")
    p_cl_niche.add_argument("--niches", type=int, default=5, help="Number of spatial niche classes")
    p_cl_niche.add_argument("--output", "-o", default=None, help="Optional output path to save updated spatial dataset")
    p_cl_niche.add_argument("--json", action="store_true", help="Output forecast result as JSON")

    # closed-loop run
    p_cl_run = closed_subs.add_parser("run", help="Run full closed-loop pipeline from perturbation to spatial niche remodeling")
    p_cl_run.add_argument("--cells", required=True, help="Path to single-cell .h5ad baseline dataset")
    p_cl_run.add_argument("--spatial", required=True, help="Path to spatial reference .h5ad dataset")
    p_cl_run.add_argument("--genes", required=True, help="Comma-separated target gene symbols (e.g. TP53,CDKN1A)")
    p_cl_run.add_argument("--mode", default="knockout", choices=["knockout", "overexpression"], help="Perturbation mode")
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

    # 16. verify-artifacts (Validation Artifacts & Certification Verifier)
    p_verify_art = subparsers.add_parser(
        "verify-artifacts",
        aliases=["verify_validation_artifacts"],
        help="Verify validation artifacts, checksums, provenance, and certification consistency",
    )
    p_verify_art.add_argument("--root", type=Path, default=None, help="Repository root path")
    p_verify_art.add_argument("--enforce-version", type=str, default=None, help="Enforce specific version string")
    p_verify_art.add_argument("--json", action="store_true", help="Output result as JSON")

    # 17. causal (Structural Causal DAG & Identifiability)
    p_causal = subparsers.add_parser("causal", help="Structural Causal DAG, d-separation, and backdoor identification")
    causal_subs = p_causal.add_subparsers(dest="causal_action", help="Causal actions")
    p_causal_check = causal_subs.add_parser("check", help="Evaluate if a causal claim is warranted given DAG structure")
    p_causal_check.add_argument("--treatment", "-t", required=True, help="Treatment variable name")
    p_causal_check.add_argument("--outcome", "-y", required=True, help="Outcome variable name")
    p_causal_check.add_argument("--confounders", "-c", default="", help="Comma-separated observed confounders")
    p_causal_check.add_argument("--conditioned", "-z", default="", help="Comma-separated conditioned variables")
    p_causal_check.add_argument(
        "--claim-class",
        default="causal",
        choices=["causal", "mechanistic", "association", "population_effect", "descriptive"],
        help="Requested claim class",
    )
    p_causal_check.add_argument("--json", action="store_true", help="Output result as JSON")

    # 18. remediate (Prescriptive Power & Study Design Remediation)
    p_remediate = subparsers.add_parser("remediate", help="Prescriptive study design and power remediation calculations")
    p_remediate.add_argument("--violation", "-v", default="BN-F006", help="Violation ID (e.g. BN-F006, BN-F001, BN-F005)")
    p_remediate.add_argument("--n-samples", "-n", type=int, default=2, help="Current replicates per group")
    p_remediate.add_argument("--log2fc", type=float, default=1.0, help="Target effect size log2FC")
    p_remediate.add_argument("--dispersion", type=float, default=0.25, help="Biological dispersion")
    p_remediate.add_argument("--power", action="store_true", help="Perform quantitative power calculation")
    p_remediate.add_argument("--json", action="store_true", help="Output prescription as JSON")

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

    # 22. debt (Scientific Evidence Debt Engine - BNS-021)
    p_debt = subparsers.add_parser("debt", help="BioNexus Scientific Evidence Debt Engine (BNS-021) — Track & Amortize Scientific Debt")
    debt_subs = p_debt.add_subparsers(dest="debt_action", help="Evidence debt actions")

    p_d_audit = debt_subs.add_parser("audit", help="Audit project evidence debt and epistemic keystones")
    p_d_audit.add_argument("target", nargs="?", default=".", help="Path to ledger.json or project directory (default: .)")
    p_d_audit.add_argument("--json", action="store_true", help="Output machine-readable JSON debt report")
    p_d_audit.add_argument("--markdown", "--md", action="store_true", help="Output Markdown debt certificate")
    p_d_audit.add_argument("-o", "--output", default=None, help="Save report to file path")
    p_d_audit.add_argument("-v", "--verbose", action="store_true", help="Display detailed debt breakdown")

    p_d_payoff = debt_subs.add_parser("payoff", aliases=["schedule"], help="Compute optimal scientific debt repayment schedule")
    p_d_payoff.add_argument("target", nargs="?", default=".", help="Path to ledger.json or project directory (default: .)")
    p_d_payoff.add_argument("--json", action="store_true", help="Output schedule as JSON")
    p_d_payoff.add_argument("--markdown", "--md", action="store_true", help="Output schedule as Markdown")

    p_d_graph = debt_subs.add_parser("graph", help="Generate Mermaid DAG visualization of evidence debt propagation")
    p_d_graph.add_argument("target", nargs="?", default=".", help="Path to ledger.json or project directory (default: .)")

    p_d_sample = debt_subs.add_parser("sample", help="Generate and audit an exemplary 20-claim research debt ledger")
    p_d_sample.add_argument("-o", "--output", default="sample_evidence_debt_ledger.json", help="Save sample ledger JSON to file")
    p_d_sample.add_argument("--json", action="store_true", help="Output audit report as JSON")
    p_d_sample.add_argument("--markdown", "--md", action="store_true", help="Output audit report as Markdown")


    # 23. lims
    p_lims = subparsers.add_parser("lims", help="BioNexus LIMS Hub (BNS-LIMS-001) — Benchling, LabWare, C04 Pairing Connectors")
    lims_subs = p_lims.add_subparsers(dest="lims_action", help="LIMS actions")

    p_l_audit = lims_subs.add_parser("audit-pairing", help="Audit C04 custodian pairing manifest")
    p_l_audit.add_argument("manifest", help="Path to pairing manifest CSV")
    p_l_audit.add_argument("--json", action="store_true", help="Output JSON report")

    p_l_sync = lims_subs.add_parser("sync-samples", help="Sync samples with generic REST LIMS")
    p_l_sync.add_argument("--url", default="https://lims.internal/api/v1", help="LIMS base URL")
    p_l_sync.add_argument("--samples", nargs="+", default=["SMP-001", "SMP-002"], help="Sample IDs")
    p_l_sync.add_argument("--json", action="store_true", help="Output JSON report")

    p_l_export = lims_subs.add_parser("export-assay", help="Export plate assay results to Benchling")
    p_l_export.add_argument("--plate-id", default="PLT-001", help="Plate identifier")
    p_l_export.add_argument("--schema-id", default="sch_plate_reader", help="Benchling assay schema ID")
    p_l_export.add_argument("--wells", type=int, default=96, help="Well count")
    p_l_export.add_argument("--json", action="store_true", help="Output JSON report")

    p_l_export_asm = lims_subs.add_parser("export-asm", help="Bridge Allotrope ASM instrument file to LIMS assay")
    p_l_export_asm.add_argument("--asm", required=True, help="Path to Allotrope ASM JSON file")
    p_l_export_asm.add_argument("--endpoint", default="https://api.benchling.com/v2/assay-results", help="Target LIMS endpoint URL")
    p_l_export_asm.add_argument("--target", default="BENCHLING", choices=["BENCHLING", "LABWARE", "SAPIO", "GENERIC_REST"], help="Target LIMS system")
    p_l_export_asm.add_argument("--schema-id", default="sch_plate_reader", help="Assay schema ID")
    p_l_export_asm.add_argument("--plate-id", default="PLT-001", help="Plate identifier")
    p_l_export_asm.add_argument("--project-id", default=None, help="LIMS project ID")
    p_l_export_asm.add_argument("--token", default=None, help="Bearer authorization token")
    p_l_export_asm.add_argument("--mock", action="store_true", help="Perform mock dispatch")
    p_l_export_asm.add_argument("--json", action="store_true", help="Output JSON report")

    # 24. instrument
    p_inst = subparsers.add_parser("instrument", help="BioNexus Instrument Gateway (BNS-INST-001) — Plate Reader, NGS, Single-Cell Ingestion")
    inst_subs = p_inst.add_subparsers(dest="instrument_action", help="Instrument actions")

    p_i_detect = inst_subs.add_parser("detect", help="Auto-detect laboratory instrument file type")
    p_i_detect.add_argument("file", help="Path to instrument output file")
    p_i_detect.add_argument("--json", action="store_true", help="Output JSON result")

    p_i_ingest = inst_subs.add_parser("ingest", help="Ingest and standardize instrument file to Allotrope ASM")
    p_i_ingest.add_argument("file", help="Path to instrument output file")
    p_i_ingest.add_argument("-o", "--output", default=None, help="Output JSON/ASM path")
    p_i_ingest.add_argument("--json", action="store_true", help="Output JSON result")

    # 25. airgap
    p_airgap = subparsers.add_parser("airgap", help="BioNexus Airgap & Zero-Egress DLP Guard (BNS-SEC-011)")
    airgap_subs = p_airgap.add_subparsers(dest="airgap_action", help="Airgap actions")

    p_a_audit = airgap_subs.add_parser("audit", help="Audit airgap policy and DLP metrics")
    p_a_audit.add_argument("--mode", default="AIRGAP_STRICT", choices=["AIRGAP_STRICT", "VPC_INTERNAL_ONLY", "ALLOWLIST_AUDITED", "OPEN_CONNECTED"])
    p_a_audit.add_argument("--json", action="store_true", help="Output JSON report")

    p_a_eval = airgap_subs.add_parser("evaluate", help="Evaluate destination egress permissions and DLP")
    p_a_eval.add_argument("url", help="Destination URL or hostname")
    p_a_eval.add_argument("--mode", default="AIRGAP_STRICT", choices=["AIRGAP_STRICT", "VPC_INTERNAL_ONLY", "ALLOWLIST_AUDITED", "OPEN_CONNECTED"])
    p_a_eval.add_argument("--payload", default=None, help="Payload string to inspect")
    p_a_eval.add_argument("--json", action="store_true", help="Output JSON report")

    # 26. compliance
    p_comp = subparsers.add_parser("compliance", help="BioNexus 21 CFR Part 11 & GxP Compliance Engine (BNS-COMP-001)")
    comp_subs = p_comp.add_subparsers(dest="compliance_action", help="Compliance actions")

    p_cmp_sign = comp_subs.add_parser("sign", help="Apply 21 CFR Part 11 electronic signature to artifact")
    p_cmp_sign.add_argument("target", help="Path to target artifact")
    p_cmp_sign.add_argument("--name", default="Dr. Alice Smith", help="Signer name")
    p_cmp_sign.add_argument("--email", default="alice.smith@lab.org", help="Signer email")
    p_cmp_sign.add_argument("--role", default="PI_SIGNER", choices=["PI_SIGNER", "QA_AUDITOR", "SYSTEM_ADMIN", "BIOINFORMATICIAN", "RESEARCHER"])
    p_cmp_sign.add_argument("--reason", default="APPROVAL_OF_SCIENTIFIC_EVIDENCE", help="Signing reason")
    p_cmp_sign.add_argument("--json", action="store_true", help="Output JSON signature")

    p_cmp_ver = comp_subs.add_parser("verify-sig", help="Verify 21 CFR Part 11 electronic signature")
    p_cmp_ver.add_argument("target", help="Path to target artifact")
    p_cmp_ver.add_argument("signature_file", help="Path to JSON signature file")
    p_cmp_ver.add_argument("--json", action="store_true", help="Output JSON verification")

    p_cmp_ledger = comp_subs.add_parser("audit-ledger", help="Audit GxP hash chain integrity")
    p_cmp_ledger.add_argument("--json", action="store_true", help="Output JSON report")

    # 27. nextflow (execution provenance and explicit launch preparation)
    p_nextflow = subparsers.add_parser(
        "nextflow", help="Passive Nextflow execution-provenance harvester and launch preparation (BNS-021)"
    )
    nf_subs = p_nextflow.add_subparsers(dest="nextflow_action", help="Nextflow actions")

    p_nf_ingest = nf_subs.add_parser(
        "ingest", help="Harvest a run directory and emit a hash-bound provenance-only receipt"
    )
    p_nf_ingest.add_argument("--run-dir", "-r", required=True, help="Path to Nextflow execution directory")
    p_nf_ingest.add_argument("--pipeline-name", "-p", default=None, help="Pipeline name (e.g. nf-core/rnaseq)")
    p_nf_ingest.add_argument(
        "--samplesheet",
        "-s",
        default=None,
        help="Optional explicit descriptive input; never creates scientific evidence factors",
    )
    p_nf_ingest.add_argument("-o", "--output", default=None, help="Output path for receipt JSON")
    p_nf_ingest.add_argument("--json", action="store_true", help="Output JSON receipt to stdout")

    p_nf_inspect = nf_subs.add_parser(
        "inspect", help="Inspect Nextflow run directory and display execution summary"
    )
    p_nf_inspect.add_argument("run_dir", help="Path to Nextflow execution directory")
    p_nf_inspect.add_argument("--json", action="store_true", help="Output execution summary as JSON")

    p_nf_launch = nf_subs.add_parser("launch", help="Prepare nf-core launch script and configurations")
    p_nf_launch.add_argument(
        "--pipeline",
        required=True,
        choices=[
            "rnaseq",
            "scrnaseq",
            "differentialabundance",
            "sarek",
            "spatialtranscriptomics",
            "ampliseq",
        ],
        help="nf-core pipeline name",
    )
    p_nf_launch.add_argument("--samplesheet", required=True, help="Path to input samplesheet.csv")
    p_nf_launch.add_argument("--outdir", default="results", help="Pipeline output directory")
    p_nf_launch.add_argument("-o", "--output", default="run.sh", help="Output path for run script")
    p_nf_launch.add_argument("--profile", default="docker", help="Execution profile (e.g. docker, singularity, slurm)")

    # 28. ga4gh
    p_ga4gh = subparsers.add_parser("ga4gh", help="GA4GH Global Standards (DRS v1.2.0, Phenopackets v2)")
    ga4gh_subs = p_ga4gh.add_subparsers(dest="ga4gh_action", help="GA4GH actions")

    p_g_drs = ga4gh_subs.add_parser("drs-descriptor", help="Generate GA4GH DRS v1.2.0 object descriptor for data file")
    p_g_drs.add_argument("file", help="Path to data file")
    p_g_drs.add_argument("--id", default=None, help="DRS identifier (default: filename)")
    p_g_drs.add_argument("--authority", default="bionexus.local", help="DRS authority URI prefix")
    p_g_drs.add_argument("--mime-type", default=None, help="MIME type")
    p_g_drs.add_argument("--json", action="store_true", help="Output JSON object")

    p_g_pheno = ga4gh_subs.add_parser("phenopacket", help="Export donor/patient clinical phenotype as GA4GH Phenopacket v2")
    p_g_pheno.add_argument("donor_id", help="Donor / Subject identifier")
    p_g_pheno.add_argument("--sex", default="UNKNOWN_SEX", choices=["UNKNOWN_SEX", "FEMALE", "MALE", "OTHER_SEX"], help="Biological sex")
    p_g_pheno.add_argument("--disease", default=None, help="Disease CURIE:Label (e.g. MONDO:0005015:Diabetes)")
    p_g_pheno.add_argument("--phenotype", default=None, help="Phenotype CURIE:Label (e.g. HP:0001250:Seizure)")
    p_g_pheno.add_argument("-o", "--output", default=None, help="Output JSON file path")
    p_g_pheno.add_argument("--json", action="store_true", help="Output JSON phenopacket")

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
