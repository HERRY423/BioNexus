"""
Unit tests for the BioNexus product matrix and scope boundary (BNS-IO-012):
the documented module mapping MUST match the repository, and the non-goals
list MUST be published.
"""

import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SRC = _REPO_ROOT / "src"
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_DOC = (_REPO_ROOT / "docs" / "product-matrix.md").read_text(encoding="utf-8")

NON_GOALS = (
    "planner",
    "memory",
    "multi-agent",
    "chat UI",
    "cloud workspace",
    "notebook replacement",
    "compute service",
    "agent marketplace",
)


def test_product_matrix_document_exists_and_is_indexed():
    assert _DOC.strip(), "docs/product-matrix.md must exist"
    readme = (_REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert "docs/product-matrix.md" in readme, "README must link the product matrix"
    assert "bionexus-core" in _DOC and "bionexus-audit" in _DOC
    assert "bionexus-conformance" in _DOC and "reference capability packs" in _DOC


def test_non_goals_are_published():
    """BNS-IO-012: every non-goal from the boundary list MUST be published."""
    section = _DOC.split("## Non-goals")[1]
    for item in NON_GOALS:
        assert item.lower() in section.lower(), f"missing non-goal: {item}"


def test_documented_modules_exist():
    """Every module named in the mapping table MUST exist in the repository."""
    table = _DOC.split("## Module mapping")[1].split("## Non-goals")[0]
    module_pattern = re.compile(r"`([a-z_][a-z0-9_]*)`")
    rows = [ln for ln in table.splitlines() if ln.startswith("|")]
    assert len(rows) >= 8, "module mapping table must cover the four layers"

    src_dir = _REPO_ROOT / "src" / "bionexus"
    for row in rows:
        for name in module_pattern.findall(row):
            # skills/ and evals/ are directory trees; python modules are files
            if (src_dir / f"{name}.py").is_file():
                continue
            if (_REPO_ROOT / "skills" / name.replace("_", "-")).is_dir():
                continue
            if (_REPO_ROOT / "evals").is_dir() and name == "evals":
                continue
            if name in ("bionexus", "evals", "skills"):  # tree references
                continue
            # Anything else referenced as a module in a `src/bionexus/` context
            # must exist as a file — this is the drift guard for the mapping.
            assert (src_dir / f"{name}.py").is_file(), f"documented module missing: {name}"


def test_audit_layer_imports_flow_downward_only():
    """The audit layer consumes core; core never imports audit (layering)."""
    core = ("contracts", "capabilities", "abi", "failures", "failclosed", "intent_router", "ledger")
    for mod in core:
        text = (_REPO_ROOT / "src" / "bionexus" / f"{mod}.py").read_text(encoding="utf-8")
        for forbidden in ("from bionexus.preflight", "from bionexus.analysis_audit", "from bionexus.verification"):
            assert forbidden not in text, f"{mod}.py must not import the audit layer ({forbidden})"
