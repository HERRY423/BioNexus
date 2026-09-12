"""Bounded static import rules for the core and the CLI adapter package."""
import ast
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parents[2] / "src/bionexus"
# Foundation modules stay independent of higher-level policy and command adapters.
ALLOWED = {
    "contracts": set(), "integrity": set(), "de_bundle": set(),
    "pilot_costs": set(), "rule_classification": set(),
    "research_purpose": {"contracts"},
    "lab_policy": {"rule_classification"},
    "rule_provenance": {"rule_classification"},
    "researcher_override": {"contracts", "research_purpose", "rule_provenance"},
    "evidence_model": {"contracts", "research_purpose", "tool_receipt"},
    "warrant": {"contracts", "evidence_model", "lab_policy", "research_purpose",
                "researcher_override", "rule_classification"},
    "de_pilot": {"de_bundle", "pilot_costs", "versions"},
}


def internal_imports(path):
    imports = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            # Resolve relative imports at the actual package depth.
            package = ["bionexus", *path.relative_to(SOURCE).parts[:-1]]
            base = ".".join(package[:len(package) - node.level + 1]) if node.level else ""
            module = ".".join(part for part in (base, node.module) if part)
            names = [module + "." + alias.name for alias in node.names]
        else:
            continue
        imports.update(name.split(".")[1] for name in names if name.startswith("bionexus."))
    return imports


@pytest.mark.parametrize("module", sorted(ALLOWED))
def test_core_dependency_direction(module):
    assert internal_imports(SOURCE / f"{module}.py") <= ALLOWED[module]


@pytest.mark.parametrize("path", sorted((SOURCE / "commands").glob("*.py")), ids=lambda p: p.stem)
def test_command_adapters_do_not_import_compatibility_facade(path):
    assert "cli" not in internal_imports(path), "Import the domain implementation, not the CLI facade"
