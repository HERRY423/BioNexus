"""Scaffold command handlers, extracted without changing command semantics."""


from __future__ import annotations

import argparse
import re
from pathlib import Path

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

def _to_snake_case(name: str) -> str:
    """Convert hyphenated or mixed name to snake_case."""
    s = re.sub(r"[\s\-_]+", "_", name)
    return s.lower().strip("_")


def _to_kebab_case(name: str) -> str:
    """Convert snake_case or mixed name to kebab-case."""
    s = re.sub(r"[\s\-_]+", "-", name)
    return s.lower().strip("-")


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


def register_create_plugin_arguments(subparsers: argparse._SubParsersAction) -> None:
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
