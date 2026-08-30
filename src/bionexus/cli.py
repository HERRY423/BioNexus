"""
BioNexus Unified Command-Line Interface — the Scientific Assertion Firewall.

Commands:
  bionexus preflight     Decide BEFORE compute whether an analysis should run (BNS-013)
  bionexus audit         Audit notebooks/scripts for scientific flaws, or data-matrix integrity
  bionexus verify        Verify final results against their Claim-Evidence Ledger (BNS-013)
  bionexus bench         BioFailureBench trap corpus: validate / summary (BNS-014)
  bionexus interop       Standards exports: RO-Crate / Workflow Run Crate / BioCompute Object (BNS-016)
  bionexus standards     Standards alignment registry with honest statuses (BNS-016)
  bionexus create-plugin Scaffold a new skill following the Gold Reference pattern
  bionexus create-skill  Alias for create-plugin
  bionexus doctor        Run environment and backend preflight diagnostics
  bionexus list-skills   Display canonical skill inventory and capability tiers
  bionexus inventory     Alias for list-skills
  bionexus registry      Compile and validate multi-platform registry manifests
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Optional

from bionexus.bigdata import (
    audit_dataset_storage,
    estimate_memory_requirements,
    generate_streaming_plan,
)
from bionexus.capabilities import (
    get_capability,
    list_capabilities,
)
from bionexus.cluster import (
    JobResourceConfig,
    diagnose_job_failure,
    generate_job_script,
    get_job_status,
    probe_cluster_environment,
    submit_job,
)
from bionexus.doctor import run_doctor
from bionexus.integrity import audit_expression_matrix
from bionexus.intent_router import RoutingStatus, route_scientific_intent
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
from bionexus.versions import PLUGIN_VERSION


def _to_snake_case(name: str) -> str:
    """Convert hyphenated or mixed name to snake_case."""
    s = re.sub(r"[\s\-_]+", "_", name)
    return s.lower().strip("_")


def _to_kebab_case(name: str) -> str:
    """Convert snake_case or mixed name to kebab-case."""
    s = re.sub(r"[\s\-_]+", "-", name)
    return s.lower().strip("-")


# ==============================================================================
# Scaffold Templates
# ==============================================================================

SKILL_MD_TEMPLATE = """---
name: {kebab_name}
display_name: "{display_name}"
description: {description}
tier: {tier}
grade: {grade}
status: {status}
backend: "{backend}"
---

# {display_name} (`{kebab_name}`)

{description}

## Quick Start (Canonical Pipeline)

```bash
# 1. Verify backend environment
bionexus doctor

# 2. Run the canonical pipeline
python skills/{kebab_name}/scripts/{snake_name}_pipeline.py input.h5ad -o output.h5ad
```

## Analytical Specifications & Evidence Contracts

| Property | Value | Notes |
| :--- | :--- | :--- |
| **Lifecycle Status** | `{status}` | Single canonical implementation |
| **Capability Tier** | `{tier}` | Default routing grade |
| **Evidence Grade** | `{grade}` | Evaluated across 7 dimensions |
| **Primary Backend** | `{backend}` | Required execution backend |

## Core Pipeline Steps

| Step | Script | Description |
| :--- | :--- | :--- |
| 1. Execute | `{snake_name}_pipeline.py` | Main analysis and EvidenceCard generation |

## Scientific Honesty Invariants & Forbidden Actions

- **Forbidden:** Faking or hallucinating benchmark results or classifications without empirical evidence.
- **Forbidden:** Masquerading a local heuristic under a gold-standard community tool name.
- **Refusal Requirement:** If `{backend}` is missing or incompatible, the pipeline must cleanly refuse with an `EvidenceGrade.ABSTAIN` payload.
"""

PIPELINE_SCRIPT_TEMPLATE = '''#!/usr/bin/env python3
"""
{display_name} Canonical Pipeline.

Single Source of Truth (SSOT) implementation for {kebab_name}.
Enforces deterministic backend verification, data integrity audits,
W3C PROV-O provenance sidecars, and 7-dimensional EvidenceCard generation.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

# Add src and common scripts to sys.path
_CURRENT_DIR = Path(__file__).resolve().parent
for _p in [_CURRENT_DIR.parent.parent.parent, _CURRENT_DIR.parent.parent, Path.cwd()]:
    _src = _p / "src"
    if _src.is_dir() and str(_src) not in sys.path:
        sys.path.insert(0, str(_src))
        break

from bionexus.backends import BackendUnavailable, require
from bionexus.contracts import (
    GRADE_A,
    GRADE_B,
    GRADE_C,
    EvidenceCard,
    attach_meta,
    refuse,
)
from bionexus.gate import require_doctor
from bionexus.integrity import audit_expression_matrix
from bionexus.pipeline_config import load_pipeline_config, merge_config
from bionexus.provenance import sidecar


def run_{snake_name}_pipeline(
    data: Any,
    *,
    backend_name: str = "{backend_simple}",
    parameters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Execute canonical {display_name} analysis.

    Parameters:
        data: Input data matrix or AnnData object.
        backend_name: Name of backend to probe and execute.
        parameters: Optional pipeline hyperparameters.

    Returns:
        Structured result payload conforming to BioNexus Evidence Operating Layer.
    """
    params = parameters or {{}}

    # 1. Enforce backend requirement
    if backend_name and backend_name != "none":
        try:
            require(backend_name, for_method="run_{snake_name}_pipeline")
        except BackendUnavailable as e:
            return refuse(
                method="{snake_name}_gold_chain",
                reason=str(e),
                extra={{"input_data_summary": "Precondition failed: missing required backend"}},
            )

    # 2. Audit input data semantics
    matrix_data = getattr(data, "X", data)
    input_grade, input_notes, input_stats = audit_expression_matrix(
        matrix_data,
        expected_type=params.get("expected_matrix_type", "counts")
    )

    # 3. Perform analytical calculations
    analysis_results = {{
        "n_samples": input_stats.get("shape", [0, 0])[0] if input_stats.get("shape") else 100,
        "parameters_applied": params,
        "execution_notes": "Canonical {snake_name} pipeline executed successfully.",
    }}

    # 4. Construct 7-dimensional EvidenceCard
    card = EvidenceCard(
        execution_fidelity="{grade}",
        input_integrity=input_grade,
        assumption_validity=GRADE_A if input_grade == GRADE_A else GRADE_B,
        statistical_support=GRADE_B,
        parameter_robustness="UNTESTED",
        cross_method_concordance="UNTESTED",
        external_validation="UNTESTED",
        details={{
            "backend": backend_name,
            "input_notes": input_notes,
            "input_stats": input_stats,
        }}
    )

    # 5. Synthesize and attach standardized metadata
    return attach_meta(
        analysis_results,
        method="{snake_name}_gold_chain",
        backend=backend_name,
        evidence_grade="{grade}",
        limitations=[
            "Research-use only.",
            "Results must be corroborated with orthogonal biological validation."
        ],
        evidence_card=card,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="{display_name} Canonical Pipeline"
    )
    parser.add_argument("input", help="Path to input data file (.h5ad, .csv, or .tsv)")
    parser.add_argument("-o", "--output", default=None, help="Path to output results file")
    parser.add_argument("--config", default=None, help="Path to optional JSON/YAML configuration file")
    parser.add_argument("--skip-doctor", action="store_true", help="Bypass environment doctor preflight check")
    parser.add_argument("--expected-type", choices=["counts", "normalized"], default="counts", help="Expected matrix scale")

    args = parser.parse_args()

    # Preflight doctor gate check
    require_doctor(skip=args.skip_doctor)

    # Load configuration
    cfg = merge_config(
        load_pipeline_config(args.config) if args.config else {{}},
        {{
            "output": args.output,
            "expected_matrix_type": args.expected_type,
        }}
    )

    input_path = Path(args.input)
    if not input_path.is_file():
        print(f"[ERROR] Input file not found: {{input_path}}", file=sys.stderr)
        return 1

    # Mock or load input data
    import numpy as np
    dummy_matrix = np.ones((50, 20), dtype=float)

    # Execute canonical pipeline
    result = run_{snake_name}_pipeline(
        dummy_matrix,
        parameters=cfg,
    )

    # Write output and provenance sidecar if output path specified
    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)

        sidecar_path = out_path.with_suffix(".provenance.json")
        with open(sidecar_path, "w", encoding="utf-8") as f:
            json.dump(
                sidecar(
                    activity_name="{snake_name}_pipeline",
                    input_files=[str(input_path)],
                    output_files=[str(out_path)],
                    method="{snake_name}_gold_chain",
                    backend="{backend_simple}",
                    parameters=cfg,
                ),
                f,
                indent=2,
            )
        print(f"[SUCCESS] Results written to {{out_path}}")

    print(json.dumps(result, indent=2))
    return 0 if not result.get("abstain") else 2


if __name__ == "__main__":
    sys.exit(main())
'''

COMMON_PY_TEMPLATE = '''"""Shared imports and environment bootstrapping for {kebab_name}."""

from __future__ import annotations

import sys
from pathlib import Path

# Add project root and src to sys.path
_CURRENT_DIR = Path(__file__).resolve().parent
for _p in [_CURRENT_DIR.parent.parent.parent, _CURRENT_DIR.parent.parent, Path.cwd()]:
    _src = _p / "src"
    if _src.is_dir() and str(_src) not in sys.path:
        sys.path.insert(0, str(_src))
        break
'''

TEST_TEMPLATE = '''"""
Unit and regression tests for {kebab_name} canonical skill.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

# Resolve src directory
_TEST_DIR = Path(__file__).resolve().parent
for _p in [_TEST_DIR.parent.parent, _TEST_DIR.parent, Path.cwd()]:
    _src = _p / "src"
    if _src.is_dir() and str(_src) not in sys.path:
        sys.path.insert(0, str(_src))
        break

# Resolve skill scripts directory
for _candidate in [
    _TEST_DIR.parent / "skills" / "{kebab_name}" / "scripts",
    _TEST_DIR.parent.parent / "skills" / "{kebab_name}" / "scripts",
    Path.cwd() / "skills" / "{kebab_name}" / "scripts",
]:
    if _candidate.is_dir() and str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))
        break

try:
    from {snake_name}_pipeline import run_{snake_name}_pipeline
except ImportError:
    run_{snake_name}_pipeline = None


def test_{snake_name}_pipeline_execution():
    """Verify {kebab_name} executes cleanly and returns compliant EvidenceCard."""
    if run_{snake_name}_pipeline is None:
        pytest.skip("{kebab_name} pipeline module not importable")

    # Generate synthetic input matrix
    rng = np.random.default_rng(42)
    matrix = rng.poisson(lam=2.0, size=(20, 10)).astype(float)

    result = run_{snake_name}_pipeline(matrix, backend_name="none")

    assert result is not None
    assert "method" in result
    assert "backend" in result
    assert "evidence_grade" in result
    assert "evidence_card" in result
    assert "conclusion_status" in result
    assert result["abstain"] is False

    # Verify EvidenceCard structure
    card = result["evidence_card"]
    assert "execution_fidelity" in card
    assert "input_integrity" in card
    assert "assumption_validity" in card
    assert "statistical_support" in card


def test_{snake_name}_backend_refusal():
    """Verify {kebab_name} cleanly refuses when a non-existent backend is required."""
    if run_{snake_name}_pipeline is None:
        pytest.skip("{kebab_name} pipeline module not importable")

    matrix = np.ones((5, 5))
    result = run_{snake_name}_pipeline(matrix, backend_name="nonexistent_backend_pkg_xyz")

    assert result["abstain"] is True
    assert result["evidence_grade"] == "abstain"
    assert result["conclusion_status"] == "ABSTAIN"
    assert "reason" in result or "abstain_reason" in result
'''


# ==============================================================================
# CLI Implementation Handlers
# ==============================================================================


def handle_create_plugin(args: argparse.Namespace) -> int:
    """Scaffold a new BioNexus skill / plugin."""
    kebab_name = _to_kebab_case(args.name)
    snake_name = _to_snake_case(args.name)
    display_name = args.display_name or kebab_name.replace("-", " ").title()
    tier = args.tier
    grade = args.grade
    status = args.status
    backend = args.backend
    backend_simple = backend.split()[0].split("+")[0].strip()
    description = args.description or f"Canonical implementation for {display_name} analysis."

    repo_root = Path.cwd()
    if not (repo_root / "pyproject.toml").is_file():
        # Check if we are inside a subdirectory of the repo
        for parent in repo_root.parents:
            if (parent / "pyproject.toml").is_file():
                repo_root = parent
                break

    output_dir = Path(args.output_dir) if args.output_dir else repo_root / "skills" / kebab_name
    scripts_dir = output_dir / "scripts"
    references_dir = output_dir / "references"
    configs_dir = output_dir / "configs"

    test_dir = Path(args.test_dir) if args.test_dir else repo_root / "tests" / "unit"

    print(f"=== Scaffolding BioNexus Skill: {kebab_name} ===")
    print(f" - Output Directory: {output_dir}")
    print(f" - Tier: {tier} | Grade: {grade} | Status: {status} | Backend: {backend}")

    # Create directories
    scripts_dir.mkdir(parents=True, exist_ok=True)
    references_dir.mkdir(parents=True, exist_ok=True)
    configs_dir.mkdir(parents=True, exist_ok=True)

    # 1. Write SKILL.md
    skill_md_path = output_dir / "SKILL.md"
    skill_md_content = SKILL_MD_TEMPLATE.format(
        kebab_name=kebab_name,
        snake_name=snake_name,
        display_name=display_name,
        description=description,
        tier=tier,
        grade=grade,
        status=status,
        backend=backend,
    )
    with open(skill_md_path, "w", encoding="utf-8") as f:
        f.write(skill_md_content)
    print(f" [CREATED] {skill_md_path}")

    # 2. Write scripts/<snake_name>_pipeline.py
    pipeline_path = scripts_dir / f"{snake_name}_pipeline.py"
    pipeline_content = PIPELINE_SCRIPT_TEMPLATE.format(
        kebab_name=kebab_name,
        snake_name=snake_name,
        display_name=display_name,
        tier=tier,
        grade=grade,
        status=status,
        backend=backend,
        backend_simple=backend_simple,
    )
    with open(pipeline_path, "w", encoding="utf-8") as f:
        f.write(pipeline_content)
    print(f" [CREATED] {pipeline_path}")

    # 3. Write scripts/_common.py
    common_path = scripts_dir / "_common.py"
    with open(common_path, "w", encoding="utf-8") as f:
        f.write(COMMON_PY_TEMPLATE.format(kebab_name=kebab_name))
    print(f" [CREATED] {common_path}")

    # 4. Write references/README.md
    ref_path = references_dir / "README.md"
    with open(ref_path, "w", encoding="utf-8") as f:
        f.write(f"# {display_name} References\n\nAdd biological background and citations here.\n")
    print(f" [CREATED] {ref_path}")

    # 5. Write configs/default.yaml
    cfg_path = configs_dir / "default.yaml"
    with open(cfg_path, "w", encoding="utf-8") as f:
        f.write(f"# Default configuration for {kebab_name}\nexpected_matrix_type: counts\n")
    print(f" [CREATED] {cfg_path}")

    # 6. Write unit test if requested
    if not args.no_test:
        test_dir.mkdir(parents=True, exist_ok=True)
        test_file_path = test_dir / f"test_{snake_name}.py"
        test_content = TEST_TEMPLATE.format(
            kebab_name=kebab_name,
            snake_name=snake_name,
            display_name=display_name,
        )
        with open(test_file_path, "w", encoding="utf-8") as f:
            f.write(test_content)
        print(f" [CREATED] {test_file_path}")

    print("\n[SUCCESS] Skill scaffolding complete! Next steps:")
    print(f" 1. Implement analytical logic in: {pipeline_path}")
    print(f" 2. Run unit tests: pytest tests/unit/test_{snake_name}.py -v")
    print(" 3. Sync platform manifests: bionexus registry --generate\n")
    return 0


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


def handle_debt(args: argparse.Namespace) -> int:
    """Handle the 'debt' command: Scientific Evidence Debt Engine (BNS-021)."""
    from bionexus.debt import (
        EvidenceDebtEngine,
        create_sample_debt_ledger,
        render_markdown_debt_report,
        render_mermaid_debt_dag,
        render_terminal_debt_report,
    )
    from bionexus.ledger import ClaimLedger

    action = getattr(args, "debt_action", "audit")
    target = getattr(args, "target", ".")

    # Load or generate ledger
    if action == "sample":
        ledger = create_sample_debt_ledger()
        out_p = Path(getattr(args, "output", None) or "sample_evidence_debt_ledger.json")
        ledger.save(out_p)
        if not getattr(args, "json", False):
            print(f"[INFO] Sample research ledger saved to: {out_p}")
    else:
        target_p = Path(target)
        if target_p.is_file() and target_p.suffix.lower() == ".json":
            ledger = ClaimLedger.load(target_p)
        elif target_p.is_dir():
            candidates = [
                target_p / "ledger.json",
                target_p / "claim-evidence-ledger.json",
                target_p / "sample_evidence_debt_ledger.json",
            ]
            found = next((c for c in candidates if c.is_file()), None)
            if found:
                ledger = ClaimLedger.load(found)
            else:
                ledger = create_sample_debt_ledger()
        else:
            ledger = create_sample_debt_ledger()

    report = EvidenceDebtEngine.audit_ledger(ledger)

    if action == "graph":
        print(render_mermaid_debt_dag(report, ledger))
        return 0

    if getattr(args, "json", False):
        print(json.dumps(report.to_dict(), indent=2))
        return 0
    elif getattr(args, "markdown", False):
        md = render_markdown_debt_report(report)
        if getattr(args, "output", None):
            Path(args.output).write_text(md, encoding="utf-8")
            print(f"[INFO] Markdown debt report written to: {args.output}")
        else:
            print(md)
        return 0
    else:
        term = render_terminal_debt_report(report, verbose=getattr(args, "verbose", False))
        print(term)
        return 0


def handle_doctor(args: argparse.Namespace) -> int:
    """Run BioNexus environment doctor diagnostics."""
    report = run_doctor()
    ready = report.get("ready", {})
    offline_requested = bool(
        getattr(args, "offline", False) or getattr(args, "require_offline", False)
    )
    offline_profile = None
    if offline_requested:
        from bionexus.offline_mode import offline_readiness

        offline_profile = offline_readiness()
        report["offline_profile"] = offline_profile
    if getattr(args, "require_scverse", False) and not ready.get("scverse_ready"):
        print("[ERROR] scverse stack required but missing (scanpy + anndata)", file=sys.stderr)
        return 1
    if getattr(args, "require_spatial", False) and not ready.get("spatial_ready"):
        print("[ERROR] spatial stack required but missing (squidpy)", file=sys.stderr)
        return 1
    if offline_requested and not offline_profile["offline_ready"]:
        failed = [c["name"] for c in offline_profile["checks"] if not c["ok"]]
        print("[ERROR] offline deployment gate failed: " + ", ".join(failed), file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print("=" * 78)
        print("                          BioNexus Environment Doctor")
        print("=" * 78)
        print(f"Plugin Version:  {report['plugin_version']}")
        print(f"Tier:            {report['tier']}")
        if offline_requested:
            state = "READY" if offline_profile["offline_ready"] else "NOT READY"
            print(f"Offline profile: {state} (egress mode {offline_profile['egress_mode']})")
        print("\nActive Analytical Capabilities:")
        for cap, status in ready.items():
            pass_str = "[PASS]" if status else "[MISSING]"
            print(f"  {pass_str:9s} {cap:18s} : {'ready' if status else 'not installed'}")
        print("=" * 78)

    return 0 if report.get("tier") != "refuse" else 1


def handle_offline_check(args: argparse.Namespace) -> int:
    """Offline deployment gate (air-gapped labs / HPC nodes)."""
    import os

    from bionexus import offline_mode as offline_mod

    if getattr(args, "enforce", False):
        os.environ[offline_mod.OFFLINE_ENV_VAR] = "1"
    report = offline_mod.offline_readiness()
    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print("=" * 78)
        print("                    BioNexus Offline Deployment Check")
        print("=" * 78)
        print(f"Offline enforced: {report['offline_enforced']} | egress mode: {report['egress_mode']}")
        for check in report["checks"]:
            mark = "[PASS]" if check["ok"] else "[FAIL]"
            print(f"  {mark} {check['name']}: {check['detail']}")
        print(f"Offline ready: {report['offline_ready']}")
    return 0 if report["offline_ready"] else 1


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


def handle_audit(args: argparse.Namespace) -> int:
    """Audit data semantics OR static scientific analysis flaws (BNS-013)."""
    from bionexus.analysis_audit import audit_analysis, render_analysis_audit

    path = Path(args.path)
    if not path.is_file():
        print(f"[ERROR] Target file not found: {path}", file=sys.stderr)
        return 1

    # Code artifacts (notebooks / scripts) -> static scientific analysis audit
    if path.suffix.lower() in {".ipynb", ".py", ".r", ".rmd", ".qmd", ".jl"}:
        result = audit_analysis(path)
        if getattr(args, "json", False):
            print(json.dumps(result.to_dict(), indent=2))
        else:
            print(render_analysis_audit(result))
        return 0 if result.passed else 1

    print(f"=== Auditing Biological Data File: {path} ===")
    if path.suffix == ".h5ad":
        try:
            import anndata as ad

            adata = ad.read_h5ad(path)
            grade, notes, stats = audit_expression_matrix(adata.X, expected_type=args.expected_type)
            print(f" [MATRIX AUDIT] Grade: {grade}")
            for note in notes:
                print(f"  - {note}")
            print(f" [STATS] Shape: {stats.get('shape')} | Min: {stats.get('min')} | Max: {stats.get('max')}")
            return 0 if grade in ("A", "B") else 1
        except ImportError:
            print("[ERROR] anndata package required for .h5ad audit. Install: pip install anndata", file=sys.stderr)
            return 1
    else:
        print(f"[NOTE] Reading text/csv matrix: {path}")
        import numpy as np

        data = np.genfromtxt(path, delimiter=",")
        grade, notes, stats = audit_expression_matrix(data, expected_type=args.expected_type)
        print(f" [MATRIX AUDIT] Grade: {grade}")
        for note in notes:
            print(f"  - {note}")
        return 0 if grade in ("A", "B") else 1


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
    elif action == "run":
        # Delegate to the standard eval runner over the identical suite:
        # any host (Claude, Codex, Cursor, Biomni) executes the same traps.
        args.suite = "biofailurebench"
        return handle_eval(args)
    return 0


def handle_interop(args: argparse.Namespace) -> int:
    """Handle the 'interop' command (BNS-016): standards-based exports."""
    from bionexus.interop import (
        export_bco,
        export_ro_crate,
        ledger_to_ro_crate,
        load_interop_source,
        run_bundle_to_bco,
        run_bundle_to_ro_crate,
        validate_bco,
        validate_ro_crate,
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

        elif action == "check":
            kind, manifest, siblings = load_interop_source(args.path)
            crate = (
                ledger_to_ro_crate(ClaimLedger.from_dict(manifest))
                if kind == "ledger"
                else run_bundle_to_ro_crate(manifest, siblings)
            )
            crate_errors = validate_ro_crate(crate)
            bco_errors: list = ["n/a: ledgers do not project to BCO"]
            if kind == "run":
                bco_errors = validate_bco(run_bundle_to_bco(manifest, siblings))
            print(f"=== Interop check: {args.path} (source kind: {kind}) ===")
            print(f"RO-Crate 1.1 structural validation: {'PASS' if not crate_errors else 'FAIL'}")
            for e in crate_errors:
                print(f"  - {e}")
            print(f"IEEE 2791-2020 BCO structural validation: {'PASS' if not bco_errors else 'FAIL'}")
            for e in bco_errors:
                print(f"  - {e}")
            return 0 if not crate_errors and not (kind == "run" and bco_errors) else 1
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
            verdict = "CONFORMANT" if audit.passed else "VIOLATIONS DETECTED"
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
        verdict = "CONFORMANT" if summary["conformant"] else "NON-CONFORMANT"
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
        f"**CERTIFIED**: {len(tiers['CERTIFIED'])} | **VALIDATED**: {len(tiers['VALIDATED'])} | "
        f"**EXPERIMENTAL**: {len(tiers['EXPERIMENTAL'])} | **CONNECTOR-ONLY**: {len(tiers['CONNECTOR-ONLY'])}"
    )
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


def handle_failures(args: argparse.Namespace) -> int:
    """Handle the 'failures' command (BNS-011): scientific failure taxonomy."""
    from bionexus.failures import (
        failure_to_dict,
        get_failure_mode,
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
        print("| ID | Failure Mode | Required Behavior | Benchmark Cases | Open Gap |")
        print("|---|---|---|---|---|")
        for m in list_failure_modes():
            gap = "**OPEN**" if m.open_gap else ""
            print(f"| `{m.failure_id}` | {m.name} | {m.required_behavior.split(';')[0]} | {len(m.benchmark_cases)} | {gap} |")
        print(f"\nOpen gaps (no benchmark coverage yet): {', '.join(summary['open_gaps'])}\n")
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
        print(f"**Definition**: {mode.definition}\n")
        print(f"**Example**: {mode.example}\n")
        print(f"**Affected capabilities**: {', '.join(f'`{c}`' for c in mode.affected_capabilities)}\n")
        print(f"**Detection rule**: {mode.detection_rule}\n")
        print(f"**Required behavior**: {mode.required_behavior}\n")
        print(f"**Acceptable degradation**: {mode.acceptable_degradation}\n")
        print(f"**Benchmark cases**: {', '.join(f'`{c}`' for c in mode.benchmark_cases) or '*none (open gap)*'}\n")
        return 0
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

    decision = route_scientific_intent(
        query=args.query,
        data_path=args.data,
        data_metadata=meta,
        allow_degraded=args.allow_degraded,
        allow_frontier=getattr(args, "allow_frontier", False),
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


def handle_run(args: argparse.Namespace) -> int:
    """Handle 'run' subcommands (inspect, verify, list) for Run Capsule Artifact Contracts."""
    from bionexus.artifacts import load_run_bundle, verify_run_bundle

    action = getattr(args, "run_action", None)
    if action == "inspect":
        target = Path(args.path)
        try:
            data = load_run_bundle(target)
        except Exception as e:
            print(f"[ERROR] Failed to load run capsule: {e}")
            return 1

        if getattr(args, "json", False):
            print(json.dumps(data, indent=2))
            return 0

        print("\n============================================================")
        print(f"📦 BioNexus Run Capsule: {data.get('run_id')}")
        print("============================================================")
        print(f"• Capability ID:       {data.get('capability_id')}")
        print(f"• Skill Name:          {data.get('skill_name')}")
        print(f"• Status:              {data.get('status')} ({data.get('execution_state')})")
        print(f"• Conclusion Maturity: {data.get('conclusion_maturity')}")
        print(f"• Duration:            {data.get('duration_seconds')}s")
        print(f"• Start Time:          {data.get('timestamp_start')}")

        artifacts = data.get("artifacts", {})
        print("\n📂 Core Descriptors:")
        for k in (
            "inputs_manifest",
            "parameters_manifest",
            "evidence_card",
            "provenance_sidecar",
            "environment_snapshot",
            "execution_log",
        ):
            val = artifacts.get(k)
            if val:
                print(f"  - {k}: {val}")

        results = artifacts.get("results", [])
        print(f"\n📊 Result Artifacts ({len(results)}):")
        for r in results:
            prim = " [PRIMARY]" if r.get("path") == artifacts.get("primary_result") else ""
            print(f"  - {r.get('name')}: {r.get('path')} ({r.get('semantic_type')}){prim}")

        figures = artifacts.get("figures", [])
        if figures:
            print(f"\n📈 Visualizations ({len(figures)}):")
            for fig in figures:
                print(f"  - {fig.get('title')}: {fig.get('path')} ({fig.get('format')})")

        suggestions = data.get("downstream_suggestions", [])
        if suggestions:
            print(f"\n🤖 Next Agent Actionable Suggestions ({len(suggestions)}):")
            for i, sug in enumerate(suggestions, 1):
                print(f"  {i}. Intent: {sug.get('intent')} -> {sug.get('capability_id')}")
                print(f"     Input:   {sug.get('input_artifact')}")
                print(f"     Command: {sug.get('recommended_command')}")
                if sug.get("rationale"):
                    print(f"     Why:     {sug.get('rationale')}")

        print("============================================================\n")
        return 0

    elif action == "verify":
        target = Path(args.path)
        res = verify_run_bundle(target)
        if getattr(args, "json", False):
            print(json.dumps(res.to_dict(), indent=2))
            return 0 if res.valid else 1

        print(f"\n=== Verifying Run Capsule: {res.run_id} ===")
        if res.valid:
            print("[PASS] Run capsule is complete, structurally intact, and cryptographically verified.")
            return 0
        else:
            print("[FAIL] Integrity verification failed:")
            for m in res.missing_files:
                print(f"  - MISSING: {m}")
            for t in res.tampered_files:
                print(f"  - TAMPERED: {t}")
            for n in res.notes:
                print(f"  - Note: {n}")
            return 1

    elif action == "list":
        parent = Path(args.path or ".")
        runs = sorted(parent.glob("**/run.json"))
        if not runs:
            print(f"No BioNexus run capsules found in '{parent}'.")
            return 0

        print(f"\nFound {len(runs)} BioNexus Run Capsule(s) in '{parent}':")
        for r_file in runs:
            r_dir = r_file.parent
            try:
                d = json.loads(r_file.read_text(encoding="utf-8"))
                print(
                    f"  • {d.get('run_id')} | Cap: {d.get('capability_id')} | Status: {d.get('status')} | Dir: {r_dir}"
                )
            except Exception:
                print(f"  • [Invalid] Dir: {r_dir}")
        return 0

    return 0


def handle_cluster(args: argparse.Namespace) -> int:
    """Handle bionexus cluster subcommands."""
    action = getattr(args, "cluster_action", None)
    if action == "probe":
        report = probe_cluster_environment()
        if getattr(args, "json", False):
            print(json.dumps(report.to_dict(), indent=2))
            return 0
        print("\n=== BioNexus HPC & Cloud Cluster Environment Probe ===")
        print(f"Default Scheduler:   {report.default_scheduler.upper()}")
        print(f"Available Schedulers: {', '.join(report.available_schedulers) or 'None (local only)'}")
        print(f"Slurm (sbatch):      {'[READY]' if report.has_slurm else '[NOT DETECTED]'}")
        print(f"PBS/Torque (qsub):   {'[READY]' if report.has_pbs else '[NOT DETECTED]'}")
        print(f"LSF (bsub):          {'[READY]' if report.has_lsf else '[NOT DETECTED]'}")
        print(f"Kubernetes (kubectl):{'[READY]' if report.has_kubernetes else '[NOT DETECTED]'}")
        print(f"AWS Batch CLI:       {'[READY]' if report.has_aws_cli else '[NOT DETECTED]'}")
        print(f"GCP Batch CLI:       {'[READY]' if report.has_gcp_cli else '[NOT DETECTED]'}")
        print(f"Singularity/Apptainer: {'[READY]' if report.has_singularity else '[NOT DETECTED]'}")
        print(f"Docker:              {'[READY]' if report.has_docker else '[NOT DETECTED]'}")
        print(f"Host System Cores:   {report.system_cores}")
        print(f"Host System RAM:     {report.system_ram_gb} GB")
        print(f"GPU Accelerators:    {report.gpu_count} ({', '.join(report.gpu_devices) if report.gpu_devices else 'None'})")
        return 0

    elif action == "generate":
        res = JobResourceConfig(
            job_name=args.job_name,
            cpus=args.cpus,
            memory=args.memory,
            time_limit=args.time_limit,
            partition=args.partition,
            account=args.account,
            qos=args.qos,
            gpus=args.gpus,
            gpu_type=args.gpu_type,
            container_image=args.image,
            workdir=args.workdir,
            output_log=args.output_log,
            error_log=args.error_log,
        )
        script_text = generate_job_script(
            scheduler=args.scheduler,
            command=args.job_command,
            resources=res,
        )
        if args.output:
            dest = Path(args.output)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(script_text, encoding="utf-8")
            print(f"Generated {args.scheduler.upper()} job script saved to: {dest.resolve()}")
        else:
            print(script_text)
        return 0

    elif action == "submit":
        res = submit_job(
            script_path=args.script,
            scheduler=args.scheduler,
            dry_run=args.dry_run,
        )
        if getattr(args, "json", False):
            print(json.dumps(res.to_dict(), indent=2))
            return 0 if res.success else 1
        print(f"\n=== Submitting Job to {res.scheduler.upper()} ===")
        if res.success:
            print(f"[PASS] Job ID: {res.job_id}")
            print(f"Command: {res.submission_command}")
            print(f"Message: {res.message}")
            return 0
        else:
            print(f"[FAIL] {res.message}")
            return 1

    elif action == "status":
        state, msg = get_job_status(args.job_id, scheduler=args.scheduler)
        if getattr(args, "json", False):
            print(json.dumps({"job_id": args.job_id, "state": state.value, "message": msg}, indent=2))
            return 0
        print(f"Job {args.job_id} on {args.scheduler.upper()}: [{state.value}] - {msg}")
        return 0

    elif action == "diagnose":
        log_txt = ""
        if args.log:
            p = Path(args.log)
            if p.is_file():
                log_txt = p.read_text(encoding="utf-8", errors="ignore")
        diag = diagnose_job_failure(
            exit_code=args.exit_code,
            log_content=log_txt,
            current_memory_gb=args.memory_gb,
            current_cpus=args.cpus,
        )
        if getattr(args, "json", False):
            print(json.dumps(diag.to_dict(), indent=2))
            return 0
        print("\n=== BioNexus Job Post-Mortem Failure Diagnosis ===")
        print(f"Exit Code:     {diag.exit_code}")
        print(f"Primary Cause: {diag.primary_cause}")
        print(f"Action Remedy: {diag.remedy}")
        if diag.suggested_resource_adjustment:
            print(f"Suggested Adjustments: {diag.suggested_resource_adjustment}")
        return 0

    return 0


def handle_bigdata(args: argparse.Namespace) -> int:
    """Handle bionexus bigdata subcommands."""
    action = getattr(args, "bigdata_action", None)
    if action == "estimate":
        est = estimate_memory_requirements(
            n_cells=args.n_cells,
            n_genes=args.n_genes,
            is_sparse=not args.dense,
            sparsity=args.sparsity,
            n_layers=args.layers,
            n_pcs=args.pcs,
            precision=args.precision,
            available_ram_gb=args.ram_gb,
        )
        if getattr(args, "json", False):
            print(json.dumps(est.to_dict(), indent=2))
            return 0
        print("\n=== BioNexus Matrix Memory Estimation & Safeguard ===")
        print(f"Dataset Shape:       {est.n_cells:,} cells x {est.n_genes:,} genes")
        print(f"Matrix Format:       {'Dense' if args.dense else f'Sparse CSR (~{int(est.sparsity*100)}% zeros)'}")
        print(f"Base Matrix Size:    {est.sparse_csr_gb if not args.dense else est.dense_matrix_gb} GB")
        print(f"PCA/Graph Overhead:  {est.graph_and_pca_overhead_gb} GB")
        print(f"Recommended RAM:     {est.recommended_ram_gb} GB (with safety multiplier)")
        print(f"Host System RAM:     {est.available_system_ram_gb} GB")
        print(f"Safety Verdict:      [{est.safety_verdict}]")
        print(f"Strategy:            {est.recommended_strategy}")
        print(f"Actionable Remedy:   {est.actionable_remedy}")
        return 0

    elif action == "audit":
        rep = audit_dataset_storage(args.path)
        if getattr(args, "json", False):
            print(json.dumps(rep.to_dict(), indent=2))
            return 0
        print("\n=== BioNexus Dataset Storage & Streaming Feasibility Audit ===")
        print(f"Path:                {rep.path}")
        print(f"Detected Format:     {rep.format.upper()}")
        print(f"File/Store Size:     {rep.file_size_mb} MB")
        print(f"Chunked Layout:      {'Yes' if rep.is_chunked else 'No'}")
        print(f"Out-of-Core Ready:   {'Yes' if rep.supports_out_of_core else 'No'}")
        print(f"Streaming Rating:    {rep.streaming_compatibility}")
        for note in rep.notes:
            print(f"Note: {note}")
        return 0

    elif action == "plan":
        plan = generate_streaming_plan(
            total_cells=args.n_cells,
            total_genes=args.n_genes,
            target_ram_mb=args.target_ram_mb,
        )
        if getattr(args, "json", False):
            print(json.dumps(plan.to_dict(), indent=2))
            return 0
        print("\n=== BioNexus Out-of-Core Streaming Execution Plan ===")
        print(f"Total Cells:         {plan.total_cells:,} | Genes: {args.n_genes:,}")
        print(f"Optimal Chunk Size:  {plan.chunk_size:,} cells/chunk")
        print(f"Total Chunks:        {plan.num_chunks}")
        print(f"RAM Peak per Chunk:  ~{plan.estimated_memory_per_chunk_mb} MB")
        print("\nStreaming Execution Workflow:")
        for step in plan.streaming_pipeline_steps:
            print(f"  {step}")
        return 0

    return 0


def handle_scfm(args: argparse.Namespace) -> int:
    import json

    import anndata as ad

    from bionexus.scfm import (
        FoundationModelFamily,
        SCFMConfig,
        extract_rank_proxy_embeddings,
        extract_scfm_embeddings,
        simulate_gene_perturbation,
    )

    action = getattr(args, "scfm_action", None)
    if action == "embed":
        adata = ad.read_h5ad(args.input)
        if getattr(args, "proxy", False):
            res = extract_rank_proxy_embeddings(adata, embedding_dim=args.dim)
        else:
            family = FoundationModelFamily.GENEFORMER if args.model == "geneformer" else FoundationModelFamily.SCGPT
            cfg = SCFMConfig(
                model_family=family,
                model_name_or_path=args.checkpoint,
                device=args.device,
                embedding_dim=args.dim,
            )
            res = extract_scfm_embeddings(adata, config=cfg, allow_proxy_fallback=getattr(args, "allow_proxy", False))

        if getattr(args, "json", False):
            print(json.dumps(res.to_dict(), indent=2))
            return 0 if res.success else 1
        print("\n=== BioNexus Single-Cell Foundation Model Embedding ===")
        print(f"Status:              {res.status}")
        print(f"Model Family:        {res.model_family.upper()}")
        print(f"Cells / Genes:       {res.n_cells:,} cells / {res.n_genes:,} genes")
        print(f"Embedding Dimension: {res.embedding_dim}")
        print(f"Backend Used:        {res.backend_used}")
        print(f"Obsm Key:            adata.obsm['{res.obsm_key}']")
        for note in res.execution_notes:
            print(f"  Note: {note}")
        if not res.success and res.remedy_if_failed:
            print(f"  Remedy: {res.remedy_if_failed}")
        if args.output and res.success:
            adata.write_h5ad(args.output)
            print(f"Saved dataset with embeddings to: {args.output}")
        return 0 if res.success else 1

    elif action == "perturb":
        adata = ad.read_h5ad(args.input)
        family = FoundationModelFamily.GENEFORMER if args.model == "geneformer" else FoundationModelFamily.SCGPT
        cfg = SCFMConfig(model_family=family, model_name_or_path=args.checkpoint, device=args.device)
        res = simulate_gene_perturbation(
            adata=adata,
            target_gene=args.gene,
            mode=args.mode,
            config=cfg,
            allow_proxy_fallback=getattr(args, "allow_proxy", False),
        )
        if getattr(args, "json", False):
            print(json.dumps(res.to_dict(), indent=2))
            return 0 if res.success else 1
        print("\n=== BioNexus In Silico Gene Perturbation Analysis ===")
        print(f"Status:              {res.status}")
        print(f"Model Family:        {res.model_family.upper()}")
        print(f"Target Gene:         {res.target_gene}")
        print(f"Perturbation Mode:   {res.perturbation_mode.upper()}")
        print(f"Cells Evaluated:     {res.n_cells_evaluated:,}")
        print(f"Mean Shift Delta:    {res.mean_displacement_magnitude:.4f}")
        print(f"Backend Used:        {res.backend_used}")
        for note in res.execution_notes:
            print(f"  Note: {note}")
        if not res.success and res.remedy_if_failed:
            print(f"  Remedy: {res.remedy_if_failed}")
        return 0 if res.success else 1

    return 0


def handle_closed_loop(args: argparse.Namespace) -> int:
    import json

    import anndata as ad

    from bionexus.closed_loop import (
        GEARSPerturbationConfig,
        NicheFormerConfig,
        forecast_spatial_niche,
        predict_gears_perturbation,
        run_perturbation_to_niche_closed_loop,
    )

    action = getattr(args, "closed_loop_action", None)
    if action == "gears":
        adata = ad.read_h5ad(args.input)
        target_genes = [g.strip() for g in args.genes.split(",") if g.strip()]
        cfg = GEARSPerturbationConfig(target_genes=target_genes, mode=args.mode)
        adata_pert, res = predict_gears_perturbation(adata, target_genes=target_genes, mode=args.mode, config=cfg)
        if getattr(args, "json", False):
            print(json.dumps(res.to_dict(), indent=2))
            return 0 if res.success else 1
        print("\n=== BioNexus GEARS Perturbation Prediction ===")
        print(f"Status:               {res.status}")
        print(f"Target Gene(s):       {', '.join(res.target_genes)} ({res.perturbation_mode.upper()})")
        print(f"Cells Predicted:      {res.n_cells_predicted:,}")
        print(f"Top Upregulated:      {', '.join(res.top_upregulated_genes)}")
        print(f"Top Downregulated:    {', '.join(res.top_downregulated_genes)}")
        print(f"Backend Used:         {res.backend_used}")
        for note in res.execution_notes:
            print(f"  Note: {note}")
        if args.output:
            adata_pert.write_h5ad(args.output)
            print(f"Saved perturbed dataset to: {args.output}")
        return 0 if res.success else 1

    elif action == "nicheformer":
        adata_cells = ad.read_h5ad(args.cells)
        adata_spatial = ad.read_h5ad(args.spatial)
        cfg = NicheFormerConfig(n_niche_classes=args.niches)
        ad_sp, res = forecast_spatial_niche(adata_cells, adata_spatial, config=cfg)
        if getattr(args, "json", False):
            print(json.dumps(res.to_dict(), indent=2))
            return 0 if res.success else 1
        print("\n=== BioNexus NicheFormer Spatial Niche Forecast ===")
        print(f"Status:               {res.status}")
        print(f"Spots Evaluated:      {res.n_spots:,}")
        print(f"Niche Types:          {res.n_niche_types}")
        print(f"Dominant Breakdown:   {res.dominant_niche_distribution}")
        print(f"Backend Used:         {res.backend_used}")
        for note in res.execution_notes:
            print(f"  Note: {note}")
        if args.output:
            ad_sp.write_h5ad(args.output)
            print(f"Saved spatial dataset with niches to: {args.output}")
        return 0 if res.success else 1

    elif action == "run":
        adata_cells = ad.read_h5ad(args.cells)
        adata_spatial = ad.read_h5ad(args.spatial)
        target_genes = [g.strip() for g in args.genes.split(",") if g.strip()]
        res = run_perturbation_to_niche_closed_loop(
            adata_cells=adata_cells,
            adata_spatial=adata_spatial,
            target_genes=target_genes,
            mode=args.mode,
        )
        if getattr(args, "json", False):
            print(json.dumps(res.to_dict(), indent=2))
            return 0 if res.success else 1
        print("\n=== BioNexus Dry-Wet Closed-Loop Evaluation Pipeline ===")
        print(f"Status:               {res.status}")
        print(f"Target Perturbation:  {', '.join(res.target_perturbation)} ({res.perturbation_mode.upper()})")
        print("\nSpatial Niche Remodeling Shifts:")
        for niche, score in res.top_remodeled_niches:
            print(f"  * {niche:<32}: {score:+.2%}")
        print("\nWet-Lab Hypothesis & Validation Protocol:")
        for hyp in res.wet_lab_hypothesis_card.get("primary_hypotheses", []):
            print(f"  [Hypothesis] {hyp}")
        for assay in res.wet_lab_hypothesis_card.get("recommended_wet_lab_assays", []):
            print(f"  [Assay]      {assay}")
        for note in res.execution_notes:
            print(f"  Note: {note}")
        return 0 if res.success else 1

    return 0


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


def handle_causal(args: argparse.Namespace) -> int:
    from bionexus.causal_dag import CausalDAG, NodeType

    action = getattr(args, "causal_action", "check")
    if action != "check":
        print(f"Unknown causal action: {action}")
        return 2

    dag = CausalDAG()
    treatment = args.treatment.strip()
    outcome = args.outcome.strip()
    dag.add_node(treatment, NodeType.TREATMENT)
    dag.add_node(outcome, NodeType.OUTCOME)
    dag.add_edge(treatment, outcome, directed=True)

    if getattr(args, "confounders", ""):
        for c in args.confounders.split(","):
            c = c.strip()
            if c:
                dag.add_node(c, NodeType.OBSERVED_CONFOUNDER)
                dag.add_edge(c, treatment, directed=True)
                dag.add_edge(c, outcome, directed=True)

    conditioned_set = set()
    if getattr(args, "conditioned", ""):
        for z in args.conditioned.split(","):
            z = z.strip()
            if z:
                conditioned_set.add(z)
                if z not in dag.nodes:
                    dag.add_node(z, NodeType.COVARIATE)

    claim_class = getattr(args, "claim_class", "causal")
    res = dag.evaluate_causal_claim(
        treatment=treatment,
        outcome=outcome,
        conditioned_set=conditioned_set,
        requested_claim_class=claim_class,
    )

    if getattr(args, "json", False):
        print(json.dumps(res.to_dict(), indent=2, ensure_ascii=False))
    else:
        print("=" * 60)
        print("BioNexus Structural Causal Identifiability Evaluation")
        print("=" * 60)
        print(f"Treatment: {treatment} -> Outcome: {outcome}")
        print(f"Requested Claim: {res.requested_claim_class.upper()}")
        print(f"Warranted Status: {'WARRANTED' if res.is_warranted else 'NOT_WARRANTED_AS_REQUESTED'}")
        print(f"Warranted Claim: {res.warranted_claim_class.upper()} (Ceiling: {res.maturity_ceiling})")
        if res.violations:
            print("\nViolations / Open Biases:")
            for v in res.violations:
                print(f"  [!] {v}")
        if res.recommended_adjustment_set:
            print(f"\nRecommended Adjustment Set: {res.recommended_adjustment_set}")
        print(f"\nRationale: {res.rationale}")
        print("=" * 60)
    return 0 if res.is_warranted else 1


def handle_remediate(args: argparse.Namespace) -> int:
    from bionexus.remediation import generate_prescription_for_violation

    violation_id = getattr(args, "violation", "BN-F006")
    n_samples = getattr(args, "n_samples", 2)
    log2fc = getattr(args, "log2fc", 1.0)
    disp = getattr(args, "dispersion", 0.25)

    meta = {
        "n_donors_min": n_samples,
        "target_log2fc": log2fc,
        "dispersion": disp,
    }
    prescription = generate_prescription_for_violation(violation_id, meta)

    if getattr(args, "json", False):
        print(json.dumps(prescription.to_dict(), indent=2, ensure_ascii=False))
    else:
        print("=" * 60)
        print("BioNexus Prescriptive Study Design Remediation")
        print("=" * 60)
        print(f"Violation: {prescription.violation_id}")
        print(f"Primary Strategy: {prescription.primary_strategy}")
        print(f"Current State: {prescription.current_state_summary}")
        print(f"Target Maturity: {prescription.target_maturity}")
        if prescription.minimum_required_samples > 0:
            print(f"Required Samples: N={prescription.minimum_required_samples} (Need +{prescription.additional_samples_needed} more)")
        if prescription.power_assessment:
            p = prescription.power_assessment
            print(f"Statistical Power: {p.power:.1%} (alpha={p.alpha}, log2FC={p.target_log2fc}, dispersion={p.dispersion})")
        print("\nPrescription Recipe:")
        print(f"  {prescription.remediation_text}")
        if prescription.analytical_remedies:
            print("\nAnalytical Remedies:")
            for r in prescription.analytical_remedies:
                print(f"  - {r}")
        if prescription.academic_citations:
            print("\nAcademic Citations:")
            for c in prescription.academic_citations:
                print(f"  * {c}")
        print("=" * 60)
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


# ==============================================================================
# Main Parser & Router
# ==============================================================================


def main(argv: Optional[list[str]] = None) -> int:
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
    p_doctor.add_argument(
        "--offline",
        action="store_true",
        help="Add the offline deployment profile report and fail if the air-gapped gate is not ready",
    )
    p_doctor.add_argument(
        "--require-offline",
        dest="require_offline",
        action="store_true",
        help="Alias of --offline for deployment gate scripts",
    )

    # 2.6 offline-check (lab-grade deployment: air-gapped / HPC profile)
    p_offline = subparsers.add_parser(
        "offline-check",
        help="Offline deployment gate: verify zero-egress readiness (BIONEXUS_OFFLINE=1 profile)",
    )
    p_offline.add_argument(
        "--enforce",
        action="store_true",
        help="Set BIONEXUS_OFFLINE=1 for this process before evaluating",
    )
    p_offline.add_argument("--json", action="store_true", help="Output the readiness report as JSON")

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
    p_audit.add_argument("--json", action="store_true", help="Output audit result as JSON")

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
        "bench", help="BioFailureBench: the scientific trap corpus (BNS-014)"
    )
    bench_subs = p_bench.add_subparsers(dest="bench_action", help="BioFailureBench actions")
    p_bench_validate = bench_subs.add_parser("validate", help="Validate corpus schema and taxonomy linkage")
    p_bench_validate.add_argument("--json", action="store_true", help="Output corpus report as JSON")
    p_bench_run = bench_subs.add_parser("run", help="Run the trap suite (same as eval --suite biofailurebench)")
    p_bench_run.add_argument("--json", action="store_true", help="Output benchmark as JSON")
    p_bench_run.add_argument("--strict", action="store_true", help="Strict mode: skips are failures")
    p_bench_run.add_argument("--report", default=None, help="Path to save Markdown report")

    # 5.8 interop (standards-based exports, BNS-016)
    p_interop = subparsers.add_parser(
        "interop",
        help="Standards-based exports: RO-Crate / Workflow Run Crate / BioCompute Object (BNS-016)",
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

    elif args.command == "offline-check":
        return handle_offline_check(args)

    return 0



if __name__ == "__main__":
    sys.exit(main())
