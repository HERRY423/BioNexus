"""
Unit tests for BioNexus Plugin Scaffolding Engine.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC = _REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from bionexus.cli import main


def test_scaffold_create_plugin_end_to_end():
    """Verify create-plugin generates valid scaffold and runnable tests."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        skill_dir = tmp_path / "skills" / "demo-pathway-scorer"
        test_dir = tmp_path / "tests"

        # Run scaffolding
        ret = main([
            "create-plugin",
            "demo-pathway-scorer",
            "--display-name", "Demo Pathway Scorer",
            "--tier", "core",
            "--grade", "A",
            "--backend", "scanpy",
            "--description", "Automated pathway activity scoring test plugin.",
            "--output-dir", str(skill_dir),
            "--test-dir", str(test_dir),
        ])
        assert ret == 0

        # Verify created artifacts
        assert (skill_dir / "SKILL.md").is_file()
        assert (skill_dir / "scripts" / "demo_pathway_scorer_pipeline.py").is_file()
        assert (skill_dir / "scripts" / "_common.py").is_file()
        assert (skill_dir / "references" / "README.md").is_file()
        assert (skill_dir / "configs" / "default.yaml").is_file()
        test_file = test_dir / "test_demo_pathway_scorer.py"
        assert test_file.is_file()

        # Verify SKILL.md contents
        skill_md = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
        assert "name: demo-pathway-scorer" in skill_md
        assert "tier: core" in skill_md
        assert "grade: A" in skill_md
        assert "status: canonical" in skill_md
        assert "backend: \"scanpy\"" in skill_md

        # Run pytest on the generated test file
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", str(test_file), "-v"],
            capture_output=True,
            text=True,
            cwd=str(_REPO_ROOT),
        )
        assert proc.returncode == 0
        assert "test_demo_pathway_scorer_pipeline_execution PASSED" in proc.stdout
        assert "test_demo_pathway_scorer_backend_refusal PASSED" in proc.stdout


def test_scaffold_create_skill_alias():
    """Verify create-skill alias works identically."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        skill_dir = tmp_path / "skills" / "alias-skill"
        ret = main([
            "create-skill",
            "alias-skill",
            "--no-test",
            "--output-dir", str(skill_dir),
        ])
        assert ret == 0
        assert (skill_dir / "SKILL.md").is_file()
        assert (skill_dir / "scripts" / "alias_skill_pipeline.py").is_file()
