"""
Target discovery, introspection, and execution abstraction for BCTK.

Provides a unified interface to test:
1. BioNexus / Third-Party Plugins & Skills (SKILL.md, plugin.json, scripts/)
2. Python Modules, Functions, and Packages
3. CLI Executables & Scripts
4. MCP Servers
5. Analysis Artifacts & Run Bundles
"""

from __future__ import annotations

import hashlib
import importlib
import json
import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union


class TargetType(str, Enum):
    """Supported target architecture types."""

    PLUGIN = "plugin"
    SKILL = "skill"
    PYTHON_MODULE = "python_module"
    CLI_SCRIPT = "cli_script"
    MCP_SERVER = "mcp_server"
    ARTIFACT_BUNDLE = "artifact_bundle"
    REPO_ROOT = "repo_root"
    UNKNOWN = "unknown"


@dataclass
class TargetDescriptor:
    """Introspected metadata and entrypoints for a testing target."""

    name: str
    target_type: TargetType
    root_path: Path
    entrypoints: List[str] = field(default_factory=list)
    declared_backend: Optional[str] = None
    manifest_data: Dict[str, Any] = field(default_factory=dict)
    skill_md_path: Optional[Path] = None
    plugin_json_path: Optional[Path] = None
    script_paths: List[Path] = field(default_factory=list)
    artifact_paths: List[Path] = field(default_factory=list)
    callable_func: Optional[Callable[..., Any]] = None
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TargetSnapshot:
    """Deterministic digest of the bytes actually placed in BCTK scope."""

    sha256: str
    file_count: int
    error: str = ""


_SNAPSHOT_EXTENSIONS = {
    ".json", ".md", ".nf", ".py", ".sh", ".smk", ".toml", ".yaml", ".yml",
}
_SNAPSHOT_EXCLUDED_DIRS = {
    ".git", ".mypy_cache", ".pytest_cache", ".ruff_cache", "__pycache__",
    ".venv", ".vendor", "build", "dist", "logs", "node_modules", "validation", "venv",
}


def snapshot_target(target: TargetDescriptor, *, max_files: int = 5000) -> TargetSnapshot:
    """Bind a diagnostic report to target content instead of target metadata alone."""
    explicit = [*target.script_paths, *target.artifact_paths]
    if target.skill_md_path:
        explicit.append(target.skill_md_path)
    if target.plugin_json_path:
        explicit.append(target.plugin_json_path)

    if target.target_type in {TargetType.CLI_SCRIPT, TargetType.ARTIFACT_BUNDLE} and explicit:
        candidates = sorted({path.resolve() for path in explicit if path.is_file()}, key=str)
    elif target.root_path.is_dir():
        candidates = []
        for path in target.root_path.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in _SNAPSHOT_EXTENSIONS:
                continue
            try:
                relative = path.relative_to(target.root_path)
            except ValueError:
                continue
            if any(part in _SNAPSHOT_EXCLUDED_DIRS or part.startswith(".pytest-tmp") for part in relative.parts):
                continue
            candidates.append(path.resolve())
        candidates.sort(key=lambda path: path.relative_to(target.root_path.resolve()).as_posix())
    else:
        return TargetSnapshot("", 0, "target path does not exist or is not readable")

    if not candidates:
        return TargetSnapshot("", 0, "no supported target files were found")
    if len(candidates) > max_files:
        return TargetSnapshot("", len(candidates), f"target exceeds snapshot limit of {max_files} files")

    digest = hashlib.sha256()
    root = target.root_path.resolve()
    for path in candidates:
        try:
            relative = path.relative_to(root).as_posix()
        except ValueError:
            relative = path.name
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        try:
            with path.open("rb") as handle:
                for block in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(block)
        except OSError as exc:
            return TargetSnapshot("", len(candidates), f"cannot read target file {relative}: {exc}")
        digest.update(b"\0")
    return TargetSnapshot(digest.hexdigest(), len(candidates))


def detect_target(target_path_or_spec: Union[str, Path]) -> TargetDescriptor:
    """
    Introspect and categorize any input target into a structured TargetDescriptor.
    """
    spec_str = str(target_path_or_spec).strip()
    path = Path(spec_str).resolve() if os.path.exists(spec_str) else Path(spec_str)

    # 1. Check if it's a Python callable notation (e.g. "package.module:function")
    if ":" in spec_str and not path.exists():
        mod_name, func_name = spec_str.split(":", 1)
        try:
            mod = importlib.import_module(mod_name)
            fn = getattr(mod, func_name)
            return TargetDescriptor(
                name=f"{mod_name}:{func_name}",
                target_type=TargetType.PYTHON_MODULE,
                root_path=Path(getattr(mod, "__file__", ".")).parent,
                entrypoints=[func_name],
                callable_func=fn,
                extra={"module_name": mod_name, "function_name": func_name},
            )
        except Exception:
            pass

    # 2. Check if path is a file
    if path.is_file():
        suffix = path.suffix.lower()
        if suffix in (".py", ".sh", ".nf", ".smk", ".exe"):
            return TargetDescriptor(
                name=path.stem,
                target_type=TargetType.CLI_SCRIPT,
                root_path=path.parent,
                entrypoints=[str(path)],
                script_paths=[path],
            )
        elif suffix in (".json", ".yaml", ".yml", ".ipynb", ".h5ad", ".tsv", ".csv"):
            return TargetDescriptor(
                name=path.stem,
                target_type=TargetType.ARTIFACT_BUNDLE,
                root_path=path.parent,
                artifact_paths=[path],
            )

    # 3. Check if path is a directory
    if path.is_dir():
        # Check for plugin / skill indicators
        skill_md = path / "SKILL.md"
        plugin_json = path / "plugin.json"
        mcp_json = path / "mcp.json" or path / ".mcp.json"
        scripts_dir = path / "scripts"

        scripts = list(scripts_dir.glob("*.py")) if scripts_dir.is_dir() else list(path.glob("*.py"))
        artifacts = list(path.glob("*.json")) + list(path.glob("*.ipynb"))

        manifest: Dict[str, Any] = {}
        declared_backend = None

        if plugin_json.is_file():
            try:
                with open(plugin_json, "r", encoding="utf-8") as f:
                    manifest = json.load(f)
            except Exception:
                pass

        if skill_md.is_file():
            # Parse frontmatter if present
            try:
                with open(skill_md, "r", encoding="utf-8") as f:
                    content = f.read()
                    if content.startswith("---"):
                        parts = content.split("---", 2)
                        if len(parts) >= 3:
                            for line in parts[1].splitlines():
                                if ":" in line:
                                    k, v = line.split(":", 1)
                                    manifest[k.strip()] = v.strip().strip('"').strip("'")
                                    if k.strip().lower() == "backend":
                                        declared_backend = v.strip().strip('"').strip("'")
            except Exception:
                pass

        if (path / "pyproject.toml").is_file() and (path / "src").is_dir():
            return TargetDescriptor(
                name=path.name,
                target_type=TargetType.REPO_ROOT,
                root_path=path,
                declared_backend=declared_backend,
                manifest_data=manifest,
                skill_md_path=skill_md if skill_md.is_file() else None,
                plugin_json_path=plugin_json if plugin_json.is_file() else None,
                script_paths=scripts,
                artifact_paths=artifacts,
            )

        if skill_md.is_file() or (scripts_dir.is_dir() and len(scripts) > 0):
            return TargetDescriptor(
                name=path.name,
                target_type=TargetType.SKILL,
                root_path=path,
                declared_backend=declared_backend,
                manifest_data=manifest,
                skill_md_path=skill_md if skill_md.is_file() else None,
                plugin_json_path=plugin_json if plugin_json.is_file() else None,
                script_paths=scripts,
                artifact_paths=artifacts,
            )

        if plugin_json.is_file() or (path / "skills").is_dir():
            return TargetDescriptor(
                name=path.name,
                target_type=TargetType.PLUGIN,
                root_path=path,
                declared_backend=declared_backend,
                manifest_data=manifest,
                plugin_json_path=plugin_json if plugin_json.is_file() else None,
                script_paths=scripts,
                artifact_paths=artifacts,
            )

        if mcp_json.is_file():
            return TargetDescriptor(
                name=path.name,
                target_type=TargetType.MCP_SERVER,
                root_path=path,
                manifest_data=manifest,
            )

        return TargetDescriptor(
            name=path.name,
            target_type=TargetType.ARTIFACT_BUNDLE,
            root_path=path,
            script_paths=scripts,
            artifact_paths=artifacts,
        )

    # 4. Fallback: try python import directly
    try:
        mod = importlib.import_module(spec_str)
        return TargetDescriptor(
            name=spec_str,
            target_type=TargetType.PYTHON_MODULE,
            root_path=Path(getattr(mod, "__file__", ".")).parent,
            extra={"module_name": spec_str},
        )
    except Exception:
        pass

    return TargetDescriptor(
        name=spec_str,
        target_type=TargetType.UNKNOWN,
        root_path=path,
    )
