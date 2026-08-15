"""
BioNexus Canonical Registry & Multi-Platform Client Compiler.

Provides a Single Source of Truth (SSOT) architecture for BioNexus package metadata
and MCP server configurations, compiling canonical definitions into platform-specific
manifests (Agent Plugins 1.0, Claude Plugin, OpenAI/Codex) and preventing configuration drift.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml


def get_default_registry_path(repo_root: Optional[Path] = None) -> Path:
    """Resolve the default bionexus.registry.yaml path."""
    if repo_root is not None:
        return repo_root / "bionexus.registry.yaml"
    # Try traversing upwards from this file
    current = Path(__file__).resolve().parent
    for _ in range(4):
        candidate = current / "bionexus.registry.yaml"
        if candidate.is_file():
            return candidate
        current = current.parent
    return Path.cwd() / "bionexus.registry.yaml"


def load_canonical_registry(path: Optional[Path | str] = None) -> Dict[str, Any]:
    """Load and parse the canonical bionexus.registry.yaml file."""
    reg_path = Path(path) if path else get_default_registry_path()
    if not reg_path.is_file():
        raise FileNotFoundError(f"Canonical registry file not found: {reg_path}")

    with open(reg_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        raise ValueError(f"Invalid registry format in {reg_path}: expected YAML mapping")

    errors = validate_registry_structure(data)
    if errors:
        raise ValueError("Registry validation failed:\n" + "\n".join(f" - {e}" for e in errors))

    return data


def validate_registry_structure(registry: Dict[str, Any]) -> List[str]:
    """Validate structure and essential fields of the canonical registry."""
    errors: List[str] = []

    pkg = registry.get("package")
    if not isinstance(pkg, dict):
        errors.append("Missing or invalid 'package' block")
    else:
        for field in ("name", "version", "description", "author", "license", "keywords"):
            if field not in pkg or not pkg[field]:
                errors.append(f"Package block missing required field: '{field}'")

    mcp = registry.get("mcp_servers")
    if not isinstance(mcp, dict):
        errors.append("Missing or invalid 'mcp_servers' block")
    else:
        hosted = mcp.get("hosted")
        if not isinstance(hosted, dict):
            errors.append("Missing or invalid 'mcp_servers.hosted' mapping")
        else:
            for s_id, s_conf in hosted.items():
                if not isinstance(s_conf, dict):
                    errors.append(f"Hosted server '{s_id}' configuration must be a mapping")
                    continue
                if s_conf.get("enabled", True):
                    url = s_conf.get("url", "")
                    if not url or not url.startswith(("http://", "https://")):
                        errors.append(f"Enabled hosted server '{s_id}' has invalid URL: '{url}'")

    return errors


def validate_endpoints(
    registry: Dict[str, Any],
    check_live: bool = False,
    timeout: float = 3.0
) -> Dict[str, Any]:
    """
    Validate all configured hosted and local endpoints.
    Optionally checks live connectivity for enabled HTTP servers.
    """
    results: Dict[str, Any] = {
        "valid": True,
        "checked_count": 0,
        "servers": {}
    }

    hosted = registry.get("mcp_servers", {}).get("hosted", {})
    url_pattern = re.compile(r"^https?://[a-zA-Z0-9\-._~:/?#\[\]@!$&'()*+,;=]+$")

    for s_id, s_conf in hosted.items():
        enabled = s_conf.get("enabled", True)
        url = s_conf.get("url", "")
        status: Dict[str, Any] = {
            "name": s_conf.get("name", s_id),
            "enabled": enabled,
            "url": url,
            "syntax_valid": True,
            "live_status": None,
            "error": None
        }

        if enabled:
            results["checked_count"] += 1
            if not url or not url_pattern.match(url):
                status["syntax_valid"] = False
                status["error"] = "Invalid URL syntax"
                results["valid"] = False
            elif check_live:
                try:
                    req = urllib.request.Request(
                        url,
                        headers={"User-Agent": "BioNexus-RegistryValidator/1.0"},
                        method="HEAD"
                    )
                    with urllib.request.urlopen(req, timeout=timeout) as resp:
                        status["live_status"] = resp.status
                except urllib.error.HTTPError as e:
                    # Many MCP endpoints require POST or Auth, so 401/403/404/405 indicates endpoint reachable
                    status["live_status"] = e.code
                except Exception as e:
                    status["live_status"] = "UNREACHABLE"
                    status["error"] = str(e)
                    results["valid"] = False

        results["servers"][s_id] = status

    return results


# --- Platform Adapters ---

def to_agent_plugins_plugin_json(registry: Dict[str, Any]) -> Dict[str, Any]:
    """Generate Agent Plugins 1.0 plugin.json manifest."""
    pkg = registry["package"]
    return {
        "$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
        "name": pkg["name"],
        "version": pkg["version"],
        "description": pkg["description"],
        "author": {
            "name": pkg["author"]["name"]
        },
        "license": pkg["license"],
        "keywords": list(pkg.get("keywords", []))
    }


def to_agent_plugins_mcp_json(registry: Dict[str, Any]) -> Dict[str, Any]:
    """Generate Agent Plugins 1.0 mcp.json configuration."""
    mcp_data = registry.get("mcp_servers", {})
    servers: Dict[str, Any] = {}

    # 1. Local stdio MCP servers
    for s_id, s_conf in mcp_data.get("local", {}).items():
        if s_conf.get("enabled", True):
            servers[s_id] = {
                "type": s_conf.get("type", "stdio"),
                "command": s_conf.get("command", "python"),
                "args": s_conf.get("args", []),
                "cwd": s_conf.get("cwd", "${PLUGIN_ROOT}")
            }

    # 2. Hosted streamable-http MCP servers
    for s_id, s_conf in mcp_data.get("hosted", {}).items():
        if s_conf.get("enabled", True) and s_conf.get("url"):
            servers[s_id] = {
                "type": s_conf.get("type", "streamable-http"),
                "url": s_conf.get("url")
            }

    return {
        "$schema": "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json",
        "mcpServers": servers
    }


def to_claude_plugin_json(registry: Dict[str, Any]) -> Dict[str, Any]:
    """Generate Claude Desktop / Claude Code .claude-plugin/plugin.json manifest."""
    pkg = registry["package"]
    return {
        "name": pkg["name"],
        "version": pkg["version"],
        "description": "Agent skill pack that routes biomedical analyses to community tools or named local heuristics, with evidence grades and refusal when a gold-standard backend is missing.",
        "author": {
            "name": pkg["author"]["name"]
        }
    }


def to_claude_mcp_json(registry: Dict[str, Any]) -> Dict[str, Any]:
    """Generate Claude Desktop / Claude Code .mcp.json manifest (only enabled servers with valid URLs)."""
    mcp_data = registry.get("mcp_servers", {})
    servers: Dict[str, Any] = {}

    # Hosted MCP servers (with Claude standard http type)
    for s_id, s_conf in mcp_data.get("hosted", {}).items():
        if s_conf.get("enabled", True) and s_conf.get("url"):
            servers[s_id] = {
                "type": s_conf.get("claude_type", "http"),
                "url": s_conf.get("url")
            }

    return {
        "mcpServers": servers
    }


def to_codex_config(registry: Dict[str, Any]) -> Dict[str, Any]:
    """Generate Codex / generic agent platform MCP configuration."""
    pkg = registry["package"]
    agent_mcp = to_agent_plugins_mcp_json(registry)
    return {
        "name": pkg["name"],
        "version": pkg["version"],
        "provider": "BioNexus",
        "mcpServers": agent_mcp.get("mcpServers", {})
    }


def to_marketplace_json(registry: Dict[str, Any]) -> Dict[str, Any]:
    """Generate Codex / Claude Marketplace registry manifest (marketplace.json)."""
    pkg = registry["package"]
    return {
        "name": "bionexus-marketplace",
        "owner": {
            "name": pkg.get("author", {}).get("name", "BioNexus Team")
        },
        "plugins": [
            {
                "name": pkg["name"],
                "description": pkg["description"],
                "version": pkg["version"],
                "source": {
                    "source": "local",
                    "path": "."
                },
                "policy": {
                    "installation": "AVAILABLE",
                    "authentication": "ON_INSTALL"
                },
                "category": "Science"
            }
        ]
    }


# --- Manifest Registry Mapping & Drift Detection ---

def get_expected_manifests(registry: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Return dictionary of relative file paths to their expected dictionary representations."""
    return {
        "plugin.json": to_agent_plugins_plugin_json(registry),
        "mcp.json": to_agent_plugins_mcp_json(registry),
        ".claude-plugin/plugin.json": to_claude_plugin_json(registry),
        ".mcp.json": to_claude_mcp_json(registry),
        ".codex/config.json": to_codex_config(registry),
        ".agents/plugins/marketplace.json": to_marketplace_json(registry),
        ".codex/marketplace.json": to_marketplace_json(registry),
        ".claude-plugin/marketplace.json": to_marketplace_json(registry),
        "marketplace.json": to_marketplace_json(registry)
    }


def check_manifest_drift(
    repo_root: Path,
    registry: Optional[Dict[str, Any]] = None
) -> Tuple[bool, List[str]]:
    """
    Check if on-disk manifests differ from canonical registry compilation.
    Returns (in_sync: bool, diff_messages: List[str]).
    """
    if registry is None:
        registry = load_canonical_registry(repo_root / "bionexus.registry.yaml")

    expected = get_expected_manifests(registry)
    diffs: List[str] = []

    for rel_path, exp_content in expected.items():
        file_path = repo_root / rel_path
        if not file_path.is_file():
            diffs.append(f"Missing file: {rel_path}")
            continue

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                disk_content = json.load(f)
        except Exception as e:
            diffs.append(f"Unparseable file {rel_path}: {e}")
            continue

        if disk_content != exp_content:
            diffs.append(
                f"Configuration drift in {rel_path}:\n"
                f"  Expected: {json.dumps(exp_content, sort_keys=True)}\n"
                f"  On disk:  {json.dumps(disk_content, sort_keys=True)}"
            )

    return (len(diffs) == 0, diffs)


def compile_and_write_all(
    repo_root: Path,
    registry: Optional[Dict[str, Any]] = None
) -> List[str]:
    """Compile canonical registry and write all platform manifests to disk."""
    if registry is None:
        registry = load_canonical_registry(repo_root / "bionexus.registry.yaml")

    expected = get_expected_manifests(registry)
    written: List[str] = []

    for rel_path, content in expected.items():
        target_path = repo_root / rel_path
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(content, f, indent=2, ensure_ascii=False)
            f.write("\n")
        written.append(rel_path)

    return written
