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

from bio_research.registry import (
    check_manifest_drift,
    compile_and_write_all,
    load_canonical_registry,
    to_agent_plugins_mcp_json,
    to_agent_plugins_plugin_json,
    to_claude_mcp_json,
    to_claude_plugin_json,
    to_codex_config,
    validate_endpoints,
    validate_registry_structure,
)


def test_canonical_registry_loading_and_structure():
    """Verify bionexus.registry.yaml loads properly and satisfies schema."""
    registry = load_canonical_registry(_REPO_ROOT / "bionexus.registry.yaml")
    assert registry is not None
    assert registry["package"]["name"] == "bio-research"
    assert registry["package"]["version"] == "2.7.0"
    assert "mcp_servers" in registry
    assert "local" in registry["mcp_servers"]
    assert "hosted" in registry["mcp_servers"]

    errors = validate_registry_structure(registry)
    assert errors == []


def test_generate_agent_plugins_manifests():
    """Verify Agent Plugins 1.0 plugin.json and mcp.json format."""
    registry = load_canonical_registry(_REPO_ROOT / "bionexus.registry.yaml")
    plugin_json = to_agent_plugins_plugin_json(registry)
    mcp_json = to_agent_plugins_mcp_json(registry)

    assert plugin_json["$schema"] == "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
    assert plugin_json["name"] == "bio-research"
    assert plugin_json["author"]["name"] == "BioNexus Team"

    assert mcp_json["$schema"] == "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json"
    servers = mcp_json["mcpServers"]
    assert "local-bio-mcp" in servers
    assert servers["local-bio-mcp"]["type"] == "stdio"
    assert "pubmed" in servers
    assert servers["pubmed"]["type"] == "streamable-http"
    assert "benchling" not in servers  # Disabled server excluded


def test_generate_claude_manifests():
    """Verify Claude Desktop/Code manifests format."""
    registry = load_canonical_registry(_REPO_ROOT / "bionexus.registry.yaml")
    c_plugin = to_claude_plugin_json(registry)
    c_mcp = to_claude_mcp_json(registry)

    assert c_plugin["name"] == "bio-research"
    assert "mcpServers" in c_mcp
    servers = c_mcp["mcpServers"]
    assert "pubmed" in servers
    assert servers["pubmed"]["type"] == "http"
    # Verify no local-bio-mcp in hosted-only Claude manifest and disabled benchling is absent
    assert "local-bio-mcp" not in servers
    assert "benchling" not in servers


def test_generate_codex_config():
    """Verify Codex / generic agent configuration format."""
    registry = load_canonical_registry(_REPO_ROOT / "bionexus.registry.yaml")
    codex_conf = to_codex_config(registry)

    assert codex_conf["name"] == "bio-research"
    assert codex_conf["provider"] == "BioNexus"
    assert "local-bio-mcp" in codex_conf["mcpServers"]
    assert "pubmed" in codex_conf["mcpServers"]


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


def test_registry_compiler_cli():
    """Verify CLI tool execution and arguments."""
    cli_path = _REPO_ROOT / "scripts" / "registry_compiler.py"

    # Test --check
    proc_check = subprocess.run(
        [sys.executable, str(cli_path), "--check"],
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT)
    )
    assert proc_check.returncode == 0
    assert "strictly in sync" in proc_check.stdout

    # Test --validate-endpoints
    proc_val = subprocess.run(
        [sys.executable, str(cli_path), "--validate-endpoints"],
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT)
    )
    assert proc_val.returncode == 0
    assert "Endpoint syntax validated successfully" in proc_val.stdout
