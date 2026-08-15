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
            print(f"| `{c.id}` | **{c.display_name}** | `{c.skill_name}` | `{c.backend.canonical_name}` | {intents_str} |")
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
            print(f"- **Canonical Backend**: `{contract.backend.canonical_name}` (min version: {contract.backend.minimum_version or 'any'})")
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
    print(f"**Query**: \"{args.query}\"")
    print(f"**Routing Status**: `{decision.status.value}`")
    if decision.matched_capability:
        print(f"**Matched Capability**: `{decision.matched_capability.id}` ({decision.matched_capability.display_name})")
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

    report = run_benchmark(suite=suite, level=level)

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
            print(f"  {i}. [{v.violation_type.value}] Matched: \"{v.matched_text}\"")
            print(f"     Rule: {v.rule_description}")
            print(f"     Remedy: {v.remedy}")
        return 1


# ==============================================================================
# Main Parser & Router
# ==============================================================================

def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="bionexus",
        description="BioNexus: The Scientific Reliability Layer for Agentic Biology",
    )
    parser.add_argument(
        "-v", "--version",
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
        p_skills.add_argument("--status", choices=["canonical", "active", "heuristic", "outline", "deprecated"], default=None)
        p_skills.add_argument("--grade", choices=["A", "B", "C", "gold-wrapper", "heuristic", "refuse", "outline"], default=None)

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
    p_cap = subparsers.add_parser("capability", help="Query and validate machine-readable scientific capability contracts")
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
    p_route = subparsers.add_parser("route", help="Route scientific queries to validated capabilities with invariant checks")
    p_route.add_argument("query", help="User scientific query / intent string")
    p_route.add_argument("--data", default=None, help="Optional path to dataset file (.h5ad, .csv)")
    p_route.add_argument("--min-replicates", type=int, default=None, help="Number of biological replicates per condition")
    p_route.add_argument("--is-normalized", action="store_true", help="Flag if input matrix is normalized continuous floats")
    p_route.add_argument("--allow-degraded", action="store_true", help="Allow fallback to Grade C heuristics")
    p_route.add_argument("--json", action="store_true", help="Output routing decision as JSON")

    # 8. eval (BioNexus Agent Behavior & Epistemic Benchmark)
    p_eval = subparsers.add_parser("eval", help="Run BioNexus Agent Behavior & Scientific Reliability Benchmark (BioNexus Eval 2.0)")
    p_eval.add_argument("--level", choices=["all", "L1", "L2", "L3"], default="all", help="Benchmark tier level (L1=Router, L2=Agent Claims, L3=Outcome)")
    p_eval.add_argument("--suite", choices=["all", "routing", "refusal", "capability_claim", "scientific_semantics", "backend_failure", "adversarial", "l2_agent_claims", "l3_scientific_outcomes"], default="all", help="Benchmark evaluation suite")
    p_eval.add_argument("--report", default=None, help="Path to save Markdown evaluation report")
    p_eval.add_argument("--json", action="store_true", help="Output benchmark results as JSON")

    # 9. audit-claims (Prohibited Claims & Hallucination Auditor)
    p_claim = subparsers.add_parser("audit-claims", help="Audit text response or report artifact for prohibited scientific claims")
    p_claim.add_argument("target", help="Response text or file path to evaluate")
    p_claim.add_argument("--capability", default=None, help="Optional capability context ID")
    p_claim.add_argument("--json", action="store_true", help="Output claim audit result as JSON")

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

    return 0


if __name__ == "__main__":
    sys.exit(main())

