"""
BioNexus Unified Command-Line Interface.

Commands:
  bionexus create-plugin    Scaffold a new skill following the Gold Reference pattern
  bionexus create-skill     Alias for create-plugin
  bionexus doctor           Run environment and backend preflight diagnostics
  bionexus list-skills      Display canonical skill inventory and capability tiers
  bionexus inventory        Alias for list-skills
  bionexus registry         Compile and validate multi-platform registry manifests
  bionexus audit            Audit expression matrix or spatial coordinate integrity
  bionexus ingest           Fetch a dataset with streaming SHA-256 verification
  bionexus chain            Execute a Run Capsule chain (fail-closed orchestration)
  bionexus project          Manage the cross-session project ledger
  bionexus data-classify    Classify dataset sensitivity (governance sidecar)
  bionexus policy           Data-sensitivity x egress-zone policy decisions
  bionexus concordance      Cross-method rank concordance audit (EvidenceCard dim 6)
  bionexus external-validation  Ground-truth validation audit (EvidenceCard dim 7)
  bionexus export           Export capsules: HTML report / notebook / supplement
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Optional

from bionexus.capabilities import (
    get_capability,
    list_capabilities,
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
    compile_and_write_all,
    load_canonical_registry,
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
        if in_sync:
            print("[OK] All platform manifests are strictly in sync with bionexus.registry.yaml.")
        else:
            print("[DRIFT DETECTED] Manifest drift found:", file=sys.stderr)
            for d in diffs:
                print(f" - {d}", file=sys.stderr)
            exit_code = 1

    if args.generate:
        print("\n=== Compiling Registry Manifests ===")
        written = compile_and_write_all(repo_root, registry)
        for f in written:
            print(f" [GENERATED] {f}")
        print("[OK] Platform manifests synchronized successfully.")

    return exit_code


def handle_audit(args: argparse.Namespace) -> int:
    """Audit data semantics and matrix health via bionexus.integrity."""
    path = Path(args.path)
    if not path.is_file():
        print(f"[ERROR] Target file not found: {path}", file=sys.stderr)
        return 1

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

    elif decision.status == RoutingStatus.DEGRADED_ADVISORY:
        print("[DEGRADED ADVISORY] Execution permitted via Grade C heuristic fallback:")
        for v in decision.violations:
            print(f"  - {v}")
        return 0

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

    report = run_benchmark(
        suite=suite,
        level=level,
        provider=provider,
        model=model,
    )

    if getattr(args, "report", None):
        out_p = Path(args.report)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        with open(out_p, "w", encoding="utf-8") as f:
            f.write(format_benchmark_markdown(report))
        print(f"[OK] Benchmark report saved to: {out_p}")

    if getattr(args, "json", False):
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(format_benchmark_markdown(report))

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


def handle_ingest(args: argparse.Namespace) -> int:
    """Fetch a dataset into the workspace with streaming SHA-256 verification."""
    from bionexus.ingress import ingest

    payload = ingest(
        args.source,
        args.dest,
        filename=args.filename,
        expected_sha256=args.sha256,
        expected_size_bytes=args.size,
        timeout_seconds=args.timeout,
        overwrite=args.overwrite,
    )
    if args.json:
        print(json.dumps(payload, indent=2, default=str))
    else:
        print("\n=== BioNexus Verified Data Ingress ===")
        if payload.get("refused"):
            print(f"[REFUSED] {payload.get('abstain_reason')}")
        else:
            ing = payload["ingress"]
            print(f"[OK] Ingested {ing['size_bytes']} bytes from {ing['source']}")
            print(f"  - Destination: {ing['destination']}")
            print(f"  - SHA-256:     {ing['sha256']}")
    return 1 if payload.get("refused") else 0


def handle_chain(args: argparse.Namespace) -> int:
    """Execute a Run Capsule chain specification topologically, fail-closed."""
    from bionexus.orchestrator import ChainValidationError, run_chain

    try:
        payload = run_chain(args.spec, args.workdir, dry_run=args.dry_run)
    except ChainValidationError as e:
        print(f"[ERROR] Invalid chain specification: {e}", file=sys.stderr)
        return 1

    chain = payload["chain"]
    if args.json:
        print(json.dumps(payload, indent=2, default=str))
    else:
        print("\n=== BioNexus Capsule Chain Orchestration ===")
        print(f"**Chain**: {chain['chain_name']} | **Status**: {chain['chain_status']}")
        if chain.get("planned_order"):
            print(f"**Planned order**: {' -> '.join(chain['planned_order'])}")
        for step in chain["steps"]:
            note = f" | {step['note']}" if step.get("note") else ""
            print(
                f"  - {step['step_id']}: {step['status']}"
                + (f" (rc={step['returncode']})" if step.get("returncode") is not None else "")
                + (f" | capsule: {step['capsule_dir']}" if step.get("capsule_dir") else "")
                + note
            )
        if chain["chain_status"] == "FAILED":
            print("\n[FAIL-CLOSED] A stage failed; downstream stages were skipped. Chain output must NOT be used as a completed analysis.")
    return 0 if chain["chain_status"] in ("COMPLETED", "PLANNED") else 1


def handle_project(args: argparse.Namespace) -> int:
    """Handle 'project' subcommands for the cross-session project ledger."""
    from bionexus.project import ProjectLedger, find_project_root

    action = getattr(args, "project_action", None)
    if action == "init":
        root = Path(args.root).resolve() if args.root else Path.cwd().resolve()
        if (root / ".bionexus" / "project.json").is_file() and not args.force:
            print(f"[ERROR] Project ledger already exists at {root}. Use --force to reinitialize.", file=sys.stderr)
            return 1
        ledger = ProjectLedger(root, create=True)
        ledger.data["name"] = args.name or root.name
        ledger.save()
        print(f"[OK] BioNexus project ledger initialized: {ledger.path}")
        return 0

    root = Path(args.root).resolve() if getattr(args, "root", None) else find_project_root(Path.cwd())
    if root is None:
        print("[ERROR] No BioNexus project ledger found. Run 'bionexus project init' first.", file=sys.stderr)
        return 1
    ledger = ProjectLedger(root)

    if action == "register-dataset":
        payload = ledger.register_dataset(args.path, semantic_type=args.semantic_type)
        if payload.get("refused"):
            print(f"[REFUSED] {payload.get('abstain_reason')}", file=sys.stderr)
            return 1
        ds = payload["dataset"]
        print(f"[OK] Dataset registered (deduplicated={payload['deduplicated']}): SHA-256 {ds['sha256'][:16]}...")
        for p in ds["paths"]:
            print(f"  - {p}")
        return 0

    if action == "register-run":
        payload = ledger.register_run(args.capsule)
        if payload.get("refused"):
            print(f"[REFUSED] {payload.get('abstain_reason')}", file=sys.stderr)
            return 1
        run = payload["run"]
        print(f"[OK] Run Capsule '{run['run_id']}' registered (integrity verified).")
        print(f"  - Capability: {run.get('capability_id')} | Maturity: {run.get('conclusion_maturity')}")
        return 0

    if action == "status":
        if args.json:
            print(json.dumps(ledger.status(), indent=2, default=str))
        else:
            print(ledger.status_markdown())
        return 0

    return 0


def handle_data_classify(args: argparse.Namespace) -> int:
    """Classify a dataset's sensitivity tier and write a governance sidecar."""
    from bionexus.governance import classify_dataset

    payload = classify_dataset(args.path, declared_tier=args.tier, write_sidecar=not args.no_sidecar)
    if args.json:
        print(json.dumps(payload, indent=2, default=str))
    else:
        print("\n=== BioNexus Data Governance Classification ===")
        if payload.get("refused"):
            print(f"[REFUSED] {payload.get('abstain_reason')}")
            return 1
        rec = payload["classification"]
        print(f"[OK] Effective tier: {rec['effective_tier']}")
        print(f"  - Declared: {rec['declared_tier'] or '(none -> INTERNAL default)'}")
        print(f"  - Signals:  {rec['signals_detected'] or 'none'}")
        if rec.get("sidecar"):
            print(f"  - Sidecar:  {rec['sidecar']}")
    return 1 if payload.get("refused") else 0


def handle_policy(args: argparse.Namespace) -> int:
    """Evaluate the data-sensitivity x egress-zone policy matrix."""
    from bionexus.governance import assert_query_permitted

    payload = assert_query_permitted(
        args.tier,
        args.endpoint,
        allow_restricted_local_ack=args.ack_restricted_local,
    )
    if args.json:
        print(json.dumps(payload, indent=2, default=str))
    else:
        print("\n=== BioNexus Egress Policy Decision ===")
        if payload.get("refused"):
            print(f"[REFUSED] {payload.get('abstain_reason')}")
            return 1
        pol = payload["policy"]
        print(f"**Decision**: `{pol['decision']}` | Endpoint: {pol.get('endpoint')} ({pol.get('zone')})")
        print(f"Rationale: {pol['rationale']}")
        for r in pol.get("remedies", []):
            print(f"  * {r}")
        for note in pol.get("limitations", []):
            print(f"  - Note: {note}")
    decision = payload.get("policy", {}).get("decision")
    return 1 if decision == "ABSTAIN" else 0


def handle_concordance(args: argparse.Namespace) -> int:
    """Audit cross-method concordance (EvidenceCard dimension 6) between two rankings."""
    from bionexus.validation import rank_concordance

    try:
        payload = rank_concordance(args.primary, args.orthogonal, top_k=args.top_k)
    except (FileNotFoundError, ValueError) as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(payload, indent=2, default=str))
    else:
        print("\n=== BioNexus Cross-Method Concordance Audit (Dimension 6) ===")
        if payload.get("refused"):
            print(f"[REFUSED] {payload.get('abstain_reason')}")
            return 1
        audit = payload["audit"]
        print(f"**Grade**: `{audit['grade']}`")
        print(f"  - Spearman rho:   {audit['spearman_rho']}")
        print(f"  - Top-{audit['top_k']} Jaccard: {audit['top_k_jaccard']}")
        print(f"  - Shared items:   {audit['shared_items']}")
    return 1 if payload.get("audit", {}).get("grade") == "CONFLICTED" else 0


def handle_external_validation(args: argparse.Namespace) -> int:
    """Audit predicted calls against an independent truth set (EvidenceCard dimension 7)."""
    from bionexus.validation import external_validation

    try:
        payload = external_validation(args.predicted, args.truth, truth_key=args.truth_key)
    except (FileNotFoundError, ValueError, json.JSONDecodeError, KeyError) as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(payload, indent=2, default=str))
    else:
        print("\n=== BioNexus External Validation Audit (Dimension 7) ===")
        if payload.get("refused"):
            print(f"[REFUSED] {payload.get('abstain_reason')}")
            return 1
        audit = payload["audit"]
        print(f"**Grade**: `{audit['grade']}`")
        print(
            f"  - Precision: {audit['precision']} | Recall: {audit['recall']} | F1: {audit['f1']} "
            f"| Jaccard: {audit['jaccard']}"
        )
        print(f"  - TP {audit['true_positives']} / predicted {audit['predicted_size']} / truth {audit['truth_size']}")
    return 1 if payload.get("audit", {}).get("grade") == "CONFLICTED" else 0


def handle_export(args: argparse.Namespace) -> int:
    """Export a Run Capsule into human- and journal-facing deliverables."""
    from bionexus.delivery import (
        build_methods_text,
        export_supplement,
        load_capsule_bundle,
        render_html_report,
        render_notebook,
    )

    try:
        bundle = load_capsule_bundle(args.capsule)
    except FileNotFoundError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return 1

    run_id = bundle.run_id
    action = args.export_action

    if action == "methods":
        print(build_methods_text(bundle))
        return 0

    out_root = Path(args.output) if args.output else Path("dist") / run_id

    if action == "report":
        target = out_root if out_root.suffix == ".html" else out_root / "report.html"
        payload = render_html_report(args.capsule, target)
    elif action == "notebook":
        target = out_root if out_root.suffix == ".ipynb" else out_root / "reproduce.ipynb"
        payload = render_notebook(args.capsule, target)
    elif action == "supplement":
        payload = export_supplement(args.capsule, out_root)
    elif action == "all":
        report = render_html_report(args.capsule, out_root / "report.html")
        notebook = render_notebook(args.capsule, out_root / "reproduce.ipynb")
        supplement = export_supplement(args.capsule, out_root / "supplement")
        payload = {
            "refused": any(p.get("refused") for p in (report, notebook, supplement)),
            "export": {
                "format": "all",
                "path": str(out_root),
                "run_id": run_id,
                "report": report.get("export"),
                "notebook": notebook.get("export"),
                "supplement": supplement.get("export"),
                "abstain_reason": "; ".join(
                    p.get("abstain_reason") for p in (report, notebook, supplement) if p.get("refused")
                )
                or None,
            },
        }
    else:
        print(f"[ERROR] Unknown export action '{action}'", file=sys.stderr)
        return 1

    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2, default=str))
    else:
        export = payload.get("export", {})
        if payload.get("refused"):
            print(f"[REFUSED] {payload.get('abstain_reason')}", file=sys.stderr)
            return 1
        print(f"[OK] {export.get('format')} exported -> {export.get('path')}")
        if export.get("integrity_verified") is False:
            print("  [WARN] Capsule integrity verification failed; the report carries a warning banner.")
    return 1 if payload.get("refused") else 0


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

    # 5. audit
    p_audit = subparsers.add_parser("audit", help="Audit data semantics and matrix health")
    p_audit.add_argument("path", help="Path to .h5ad or matrix file to inspect")
    p_audit.add_argument("--expected-type", choices=["counts", "normalized"], default="counts")

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
        ],
        default="all",
        help="Benchmark evaluation suite",
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
    p_eval.add_argument("--json", action="store_true", help="Output benchmark results as JSON")

    # 9. audit-claims (Prohibited Claims & Hallucination Auditor)
    p_claim = subparsers.add_parser(
        "audit-claims", help="Audit text response or report artifact for prohibited scientific claims"
    )
    p_claim.add_argument("target", help="Response text or file path to evaluate")
    p_claim.add_argument("--capability", default=None, help="Optional capability context ID")
    p_claim.add_argument("--json", action="store_true", help="Output claim audit result as JSON")

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

    # 11. ingest (Verified Data Ingress)
    p_ingest = subparsers.add_parser(
        "ingest", help="Fetch a dataset (local/file/http[s]) into the workspace with SHA-256 verification"
    )
    p_ingest.add_argument("source", help="Source URI or path (file://, http(s)://, or local path)")
    p_ingest.add_argument("dest", help="Destination directory for the ingested artifact")
    p_ingest.add_argument("--filename", default=None, help="Override destination filename")
    p_ingest.add_argument("--sha256", default=None, help="Expected SHA-256 (fail-closed on mismatch)")
    p_ingest.add_argument("--size", type=int, default=None, help="Expected size in bytes (fail-closed on mismatch)")
    p_ingest.add_argument("--timeout", type=int, default=60, help="Network timeout in seconds (default: 60)")
    p_ingest.add_argument("--overwrite", action="store_true", help="Replace an existing destination file")
    p_ingest.add_argument("--json", action="store_true", help="Output result payload as JSON")

    # 12. chain (Run Capsule chain orchestration)
    p_chain = subparsers.add_parser(
        "chain", help="Execute a multi-stage research workflow as verified Run Capsules (fail-closed)"
    )
    p_chain.add_argument("spec", help="Chain specification file (.yaml/.yml or .json)")
    p_chain.add_argument("--workdir", default="chain_runs", help="Working directory for stage capsules")
    p_chain.add_argument("--dry-run", action="store_true", help="Validate and plan the chain without executing")
    p_chain.add_argument("--json", action="store_true", help="Output chain report as JSON")

    # 13. project (cross-session project ledger)
    p_project = subparsers.add_parser(
        "project", help="Manage the project ledger: datasets, Run Capsules, and cross-session memory"
    )
    project_subs = p_project.add_subparsers(dest="project_action", help="Project actions")

    p_project_init = project_subs.add_parser("init", help="Initialize a project ledger (.bionexus/project.json)")
    p_project_init.add_argument("--root", default=None, help="Project root (default: current directory)")
    p_project_init.add_argument("--name", default=None, help="Project display name")
    p_project_init.add_argument("--force", action="store_true", help="Reinitialize an existing ledger")

    p_project_ds = project_subs.add_parser("register-dataset", help="Register a dataset by content hash")
    p_project_ds.add_argument("path", help="Path to the dataset file")
    p_project_ds.add_argument("--semantic-type", default="unspecified", help="Semantic input type label")
    p_project_ds.add_argument("--root", default=None, help="Project root (default: discovered from cwd)")

    p_project_run = project_subs.add_parser("register-run", help="Register a verified Run Capsule")
    p_project_run.add_argument("capsule", help="Path to the run capsule directory (or run.json)")
    p_project_run.add_argument("--root", default=None, help="Project root (default: discovered from cwd)")

    p_project_status = project_subs.add_parser("status", help="Show project summary")
    p_project_status.add_argument("--root", default=None, help="Project root (default: discovered from cwd)")
    p_project_status.add_argument("--json", action="store_true", help="Output status as JSON")

    # 14. data-classify (Data governance classification)
    p_classify = subparsers.add_parser(
        "data-classify", help="Classify dataset sensitivity tier with a hash-bound governance sidecar"
    )
    p_classify.add_argument("path", help="Path to the dataset file")
    p_classify.add_argument(
        "--tier",
        choices=["PUBLIC", "INTERNAL", "SENSITIVE", "RESTRICTED"],
        default=None,
        help="Declared sensitivity tier (default: INTERNAL unless heuristic signals cap it)",
    )
    p_classify.add_argument("--no-sidecar", action="store_true", help="Do not write the governance sidecar")
    p_classify.add_argument("--json", action="store_true", help="Output result payload as JSON")

    # 15. policy (Egress policy matrix)
    p_policy = subparsers.add_parser(
        "policy", help="Evaluate data-sensitivity x egress-zone policy for an endpoint"
    )
    policy_subs = p_policy.add_subparsers(dest="policy_action", help="Policy actions")
    p_policy_check = policy_subs.add_parser("check", help="Check one tier x endpoint combination")
    p_policy_check.add_argument("--tier", required=True, choices=["PUBLIC", "INTERNAL", "SENSITIVE", "RESTRICTED"])
    p_policy_check.add_argument("--endpoint", required=True, help="Endpoint id (hosted id, or 'local')")
    p_policy_check.add_argument(
        "--ack-restricted-local",
        action="store_true",
        help="Explicit acknowledgement for local-only RESTRICTED (PHI) analysis (RUO limitations apply)",
    )
    p_policy_check.add_argument("--json", action="store_true", help="Output decision payload as JSON")

    # 16. concordance (Cross-method concordance audit, EvidenceCard dimension 6)
    p_concordance = subparsers.add_parser(
        "concordance", help="Rank-concordance audit between two method outputs (dimension 6)"
    )
    p_concordance.add_argument("primary", help="Primary ranked table (CSV/TSV with gene,score columns)")
    p_concordance.add_argument("orthogonal", help="Orthogonal ranked table (CSV/TSV)")
    p_concordance.add_argument("--top-k", type=int, default=20, help="Top-k overlap size (default: 20)")
    p_concordance.add_argument("--json", action="store_true", help="Output audit payload as JSON")

    # 17. external-validation (Ground-truth audit, EvidenceCard dimension 7)
    p_extval = subparsers.add_parser(
        "external-validation", help="Validate predicted calls against an independent truth set (dimension 7)"
    )
    p_extval.add_argument("predicted", help="Predicted calls: CSV/TSV/JSON path")
    p_extval.add_argument("truth", help="Ground truth: CSV/TSV/JSON path")
    p_extval.add_argument("--truth-key", default=None, help="JSON key selecting the truth array")
    p_extval.add_argument("--json", action="store_true", help="Output audit payload as JSON")

    # 18. export (Delivery layer: report / notebook / supplement)
    p_export = subparsers.add_parser(
        "export", help="Export a Run Capsule as an HTML report, reproducibility notebook, or supplement bundle"
    )
    export_subs = p_export.add_subparsers(dest="export_action", help="Export actions")

    def _capsule_arg(parser: argparse.ArgumentParser) -> None:
        parser.add_argument("capsule", help="Path to a Run Capsule directory (or run.json)")
        parser.add_argument("-o", "--output", default=None, help="Output path (default: dist/<run_id>/)")
        parser.add_argument("--json", action="store_true", help="Output result payload as JSON")

    p_exp_report = export_subs.add_parser("report", help="Self-contained interactive HTML report")
    _capsule_arg(p_exp_report)
    p_exp_notebook = export_subs.add_parser("notebook", help="Reproducibility Jupyter notebook (.ipynb)")
    _capsule_arg(p_exp_notebook)
    p_exp_supp = export_subs.add_parser("supplement", help="Journal-style supplementary bundle (fail-closed on tampered capsules)")
    _capsule_arg(p_exp_supp)
    p_exp_all = export_subs.add_parser("all", help="Report + notebook + supplement in one directory")
    _capsule_arg(p_exp_all)
    p_exp_methods = export_subs.add_parser("methods", help="Print capsule-level Methods text (markdown)")
    p_exp_methods.add_argument("capsule", help="Path to a Run Capsule directory (or run.json)")

    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 0

    if args.command in ("create-plugin", "create-skill"):
        return handle_create_plugin(args)
    elif args.command == "doctor":
        return handle_doctor(args)
    elif args.command in ("list-skills", "inventory"):
        return handle_list_skills(args)
    elif args.command == "registry":
        # Default to --generate if no flag specified
        if not (args.check or args.validate_endpoints or args.live_check or args.generate):
            args.generate = True
        return handle_registry(args)
    elif args.command == "audit":
        return handle_audit(args)
    elif args.command == "capability":
        if not getattr(args, "capability_action", None):
            p_cap.print_help()
            return 0
        return handle_capability(args)
    elif args.command == "route":
        return handle_route(args)
    elif args.command == "eval":
        return handle_eval(args)
    elif args.command == "audit-claims":
        return handle_audit_claims(args)
    elif args.command == "run":
        if not getattr(args, "run_action", None):
            p_run.print_help()
            return 0
        return handle_run(args)
    elif args.command == "ingest":
        return handle_ingest(args)
    elif args.command == "chain":
        return handle_chain(args)
    elif args.command == "project":
        if not getattr(args, "project_action", None):
            p_project.print_help()
            return 0
        return handle_project(args)
    elif args.command == "data-classify":
        return handle_data_classify(args)
    elif args.command == "policy":
        if not getattr(args, "policy_action", None):
            p_policy.print_help()
            return 0
        return handle_policy(args)
    elif args.command == "concordance":
        return handle_concordance(args)
    elif args.command == "external-validation":
        return handle_external_validation(args)
    elif args.command == "export":
        if not getattr(args, "export_action", None):
            p_export.print_help()
            return 0
        return handle_export(args)

    return 0


if __name__ == "__main__":
    sys.exit(main())
