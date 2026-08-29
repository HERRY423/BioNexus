"""
Unit tests for BioNexus Canonical Registry & Multi-Platform Compiler.

Validates:
1. Canonical bionexus.registry.yaml integrity and structure.
2. Accurate compilation to Agent Plugins (plugin.json, mcp.json).
3. Accurate compilation to Claude (.claude-plugin/plugin.json, .mcp.json).
4. Accurate compilation to Codex (.codex/config.json).
5. Endpoint syntax and validation.
6. Zero-drift guarantee and tampering detection.
"""

import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path

# Ensure repo root and src are on sys.path
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SRC = _REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from bionexus.registry import (
    check_manifest_drift,
    check_mirror_drift,
    compile_and_write_all,
    load_canonical_registry,
    sync_mirror_trees,
    to_agent_plugins_mcp_json,
    to_agent_plugins_plugin_json,
    to_claude_mcp_json,
    to_claude_plugin_json,
    to_codex_config,
    validate_endpoints,
    validate_registry_structure,
)
from bionexus.versions import PLUGIN_VERSION


def test_canonical_registry_loading_and_structure():
    """Verify bionexus.registry.yaml loads properly and satisfies schema."""
    registry = load_canonical_registry(_REPO_ROOT / "bionexus.registry.yaml")
    assert registry is not None
    assert registry["package"]["name"] == "bionexus-reliability"
    assert registry["package"]["version"] == PLUGIN_VERSION
    assert "mcp_servers" in registry
    assert "local" in registry["mcp_servers"]
    assert "hosted" in registry["mcp_servers"]
    assert registry["mcp_servers"]["hosted"]["pubmed"]["bundle_with_plugin"] is False

    errors = validate_registry_structure(registry)
    assert errors == []


def test_generate_agent_plugins_manifests():
    """Verify Agent Plugins 1.0 plugin.json and mcp.json format."""
    registry = load_canonical_registry(_REPO_ROOT / "bionexus.registry.yaml")
    plugin_json = to_agent_plugins_plugin_json(registry)
    mcp_json = to_agent_plugins_mcp_json(registry)

    assert plugin_json["$schema"] == "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
    assert plugin_json["name"] == "bionexus-reliability"
    assert plugin_json["author"]["name"] == "BioNexus Team"

    assert mcp_json["$schema"] == "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json"
    servers = mcp_json["mcpServers"]
    assert "bionexus-local-mcp" in servers
    assert servers["bionexus-local-mcp"]["type"] == "stdio"
    assert "pubmed" not in servers
    assert "benchling" not in servers  # Disabled server excluded


def test_generate_claude_manifests():
    """Verify Claude Desktop/Code manifests format."""
    registry = load_canonical_registry(_REPO_ROOT / "bionexus.registry.yaml")
    c_plugin = to_claude_plugin_json(registry)
    c_mcp = to_claude_mcp_json(registry)

    assert c_plugin["name"] == "bionexus-reliability"
    assert "mcpServers" in c_mcp
    servers = c_mcp["mcpServers"]
    assert "pubmed" not in servers
    # Verify no bionexus-local-mcp in hosted-only Claude manifest and disabled benchling is absent
    assert "bionexus-local-mcp" not in servers
    assert "benchling" not in servers


def test_generate_codex_config():
    """Verify Codex / generic agent configuration format."""
    registry = load_canonical_registry(_REPO_ROOT / "bionexus.registry.yaml")
    codex_conf = to_codex_config(registry)

    assert codex_conf["name"] == "bionexus-reliability"
    assert codex_conf["provider"] == "BioNexus"
    assert "bionexus-local-mcp" in codex_conf["mcpServers"]
    assert "pubmed" not in codex_conf["mcpServers"]


def test_endpoint_validation():
    """Verify URL syntax validation and handling of disabled endpoints."""
    registry = load_canonical_registry(_REPO_ROOT / "bionexus.registry.yaml")
    res = validate_endpoints(registry, check_live=False)

    assert res["valid"] is True
    assert res["checked_count"] >= 10
    assert res["servers"]["pubmed"]["syntax_valid"] is True
    assert res["servers"]["benchling"]["enabled"] is False

    # Test corrupted URL detection
    corrupted = copy.deepcopy(registry)
    corrupted["mcp_servers"]["hosted"]["pubmed"]["url"] = "not_a_url"
    corrupt_res = validate_endpoints(corrupted, check_live=False)
    assert corrupt_res["valid"] is False
    assert corrupt_res["servers"]["pubmed"]["syntax_valid"] is False


def test_drift_detection_clean():
    """Verify on-disk repository has zero drift against bionexus.registry.yaml."""
    in_sync, diffs = check_manifest_drift(_REPO_ROOT)
    assert in_sync is True, f"Drift detected in clean repository: {diffs}"
    assert diffs == []


def test_drift_detection_catches_tampering():
    """Verify drift detector catches modified or missing files."""
    registry = load_canonical_registry(_REPO_ROOT / "bionexus.registry.yaml")
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        compile_and_write_all(tmp_path, registry)

        # Clean check
        in_sync, diffs = check_manifest_drift(tmp_path, registry)
        assert in_sync is True
        assert len(diffs) == 0

        # Tamper with .mcp.json (simulate manual edit drift)
        mcp_file = tmp_path / ".mcp.json"
        with open(mcp_file, "w", encoding="utf-8") as f:
            json.dump({"mcpServers": {"tampered": {"type": "http", "url": "https://evil.com"}}}, f)

        tampered_in_sync, tampered_diffs = check_manifest_drift(tmp_path, registry)
        assert tampered_in_sync is False
        assert len(tampered_diffs) == 1
        assert "Configuration drift in .mcp.json" in tampered_diffs[0]


def test_plugin_mirror_zero_drift():
    """Verify the repository ships byte-identical canonical and mirror code trees.

    Regression guard for the dual-tree drift defect: root `skills/` and
    `scripts/` are the single source of truth; the `plugins/bionexus/` copies
    must never diverge (historically `scrna_pipeline.py` drifted by 49 lines
    and no check noticed).
    """
    in_sync, diffs = check_mirror_drift(_REPO_ROOT)
    assert in_sync is True, f"Plugin mirror drift detected: {diffs}"

    canonical = (_REPO_ROOT / "skills" / "single-cell-rna-qc" / "scripts" / "scrna_pipeline.py").read_bytes()
    mirror = (
        _REPO_ROOT / "plugins" / "bionexus" / "skills" / "single-cell-rna-qc" / "scripts" / "scrna_pipeline.py"
    ).read_bytes()
    assert canonical == mirror


def test_mirror_drift_detection_catches_all_divergence_classes():
    """Mirror checker must catch content edits, missing files, and stale extras."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        canonical_skill = tmp_path / "skills" / "demo-skill" / "scripts"
        canonical_script = tmp_path / "scripts"
        canonical_skill.mkdir(parents=True)
        canonical_script.mkdir(parents=True)
        (canonical_skill / "pipeline.py").write_text("print('canonical')\n", encoding="utf-8")
        (canonical_script / "helper.py").write_text("VERSION = 1\n", encoding="utf-8")

        synced = sync_mirror_trees(tmp_path)
        assert set(synced) == {"demo-skill/scripts/pipeline.py", "helper.py"}
        in_sync, diffs = check_mirror_drift(tmp_path)
        assert in_sync is True, diffs

        # 1. Content divergence in the mirror
        mirror_pipeline = tmp_path / "plugins" / "bionexus" / "skills" / "demo-skill" / "scripts" / "pipeline.py"
        mirror_pipeline.write_text("print('hand-edited mirror')\n", encoding="utf-8")
        in_sync, diffs = check_mirror_drift(tmp_path)
        assert in_sync is False
        assert any("content differs" in d and "skills/demo-skill/scripts/pipeline.py" in d for d in diffs)

        # 2. Missing file in the mirror
        (tmp_path / "skills" / "demo-skill" / "scripts" / "extra.py").write_text("x = 1\n", encoding="utf-8")
        in_sync, diffs = check_mirror_drift(tmp_path)
        assert in_sync is False
        assert any("missing in plugins/bionexus/skills" in d and "extra.py" in d for d in diffs)

        # 3. Stale extra file in the mirror
        stale = tmp_path / "plugins" / "bionexus" / "skills" / "demo-skill" / "scripts" / "stale.py"
        stale.write_text("orphaned\n", encoding="utf-8")
        in_sync, diffs = check_mirror_drift(tmp_path)
        assert in_sync is False
        assert any("stale file only in plugins/bionexus/skills" in d and "stale.py" in d for d in diffs)

        # 4. Sync repairs everything back to byte-identity
        sync_mirror_trees(tmp_path)
        in_sync, diffs = check_mirror_drift(tmp_path)
        assert in_sync is True, diffs
        assert not stale.exists(), "stale mirror-only file must be removed by sync"


def test_plugin_root_manifests_are_self_contained():
    """plugins/bionexus must be a complete, self-contained plugin root.

    Every relative reference its manifests declare (`./skills/`, `./mcp.json`,
    `./.mcp.json`) must resolve inside the mirror — this failed historically
    for `.mcp.json` and for the deleted `plugins/codex/` tree.
    """
    plugin_root = _REPO_ROOT / "plugins" / "bionexus"
    assert (plugin_root / "skills").is_dir(), "mirror skills/ tree missing"
    assert (plugin_root / "scripts").is_dir(), "mirror scripts/ tree missing"
    for manifest in ("plugin.json", "mcp.json", ".mcp.json", ".codex-plugin/plugin.json"):
        assert (plugin_root / manifest).is_file(), f"plugins/bionexus/{manifest} missing"

    assert not (_REPO_ROOT / "plugins" / "codex").exists(), (
        "plugins/codex should not exist: its only manifest pointed at a ./skills/ directory "
        "that never existed there."
    )


def test_registry_compiler_cli():
    """Verify CLI tool execution and arguments."""
    cli_path = _REPO_ROOT / "scripts" / "registry_compiler.py"

    # Test --check
    proc_check = subprocess.run(
        [sys.executable, str(cli_path), "--check"], capture_output=True, text=True, cwd=str(_REPO_ROOT)
    )
    assert proc_check.returncode == 0
    assert "strictly in sync" in proc_check.stdout
    assert "byte-identical to the canonical root" in proc_check.stdout

    # Test --validate-endpoints
    proc_val = subprocess.run(
        [sys.executable, str(cli_path), "--validate-endpoints"], capture_output=True, text=True, cwd=str(_REPO_ROOT)
    )
    assert proc_val.returncode == 0
    assert "Endpoint syntax validated successfully" in proc_val.stdout
