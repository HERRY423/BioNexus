"""
Unit tests for BioNexus Version Single Source of Truth (SSOT).

Validates:
1. pyproject.toml, bionexus.registry.yaml, src/bionexus/versions.py, and src/bionexus/__init__.py
   strictly match the canonical version (v0.10.0).
2. All generated client manifests (plugin.json, marketplace.json, .claude-plugin, .codex-plugin)
   contain the exact canonical version.
3. Zero version drift across the entire project tree.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SRC = _REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import bionexus
from bionexus.versions import PLUGIN_VERSION, VERSION


def test_bionexus_module_version_matches_ssot():
    """bionexus.__version__ and versions.VERSION MUST match SSOT."""
    assert bionexus.__version__ == VERSION
    assert VERSION == "1.0.0-rc.2"
    assert PLUGIN_VERSION == VERSION


def test_pyproject_toml_version_matches_ssot():
    """pyproject.toml version MUST match versions.VERSION."""
    pyproject = _REPO_ROOT / "pyproject.toml"
    assert pyproject.is_file()
    content = pyproject.read_text(encoding="utf-8")
    m = re.search(r'version\s*=\s*"([^"]+)"', content)
    assert m is not None, "Version not found in pyproject.toml"
    assert m.group(1) == VERSION


def test_registry_yaml_version_matches_ssot():
    """bionexus.registry.yaml package.version MUST match versions.VERSION."""
    registry = _REPO_ROOT / "bionexus.registry.yaml"
    assert registry.is_file()
    with open(registry, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    assert data["package"]["version"] == VERSION


def test_platform_manifests_version_matches_ssot():
    """All platform plugin.json and marketplace.json manifests MUST match versions.VERSION."""
    manifest_paths = [
        "plugin.json",
        "marketplace.json",
        ".claude-plugin/plugin.json",
        ".claude-plugin/marketplace.json",
        ".codex-plugin/plugin.json",
        ".codex/config.json",
        ".agents/plugins/marketplace.json",
        ".codex/marketplace.json",
        "plugins/bionexus/plugin.json",
        "plugins/bionexus/.codex-plugin/plugin.json",
    ]
    for rel in manifest_paths:
        path = _REPO_ROOT / rel
        assert path.is_file(), f"Missing manifest: {rel}"
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if "version" in data:
            assert data["version"] == VERSION, f"Version mismatch in {rel}: {data['version']} != {VERSION}"
        elif "plugins" in data:
            for p in data["plugins"]:
                assert p["version"] == VERSION, f"Version mismatch in {rel} plugin entry: {p['version']} != {VERSION}"


def test_sync_version_cli_check():
    """scripts/sync_version.py check function MUST return zero drift."""
    from scripts.sync_version import check_version_ssot

    in_sync, diffs = check_version_ssot(_REPO_ROOT, VERSION)
    assert in_sync is True, f"Drift detected in check_version_ssot: {diffs}"
    assert len(diffs) == 0
