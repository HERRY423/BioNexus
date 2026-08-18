#!/usr/bin/env python3
"""
BioNexus Version SSOT Synchronization CLI.

Ensures that pyproject.toml, bionexus.registry.yaml, src/bionexus/versions.py,
and all generated client manifests (plugin.json, marketplace.json, etc.)
share the exact same single source of truth version without any drift.

Usage:
  python scripts/sync_version.py --check          # Check version consistency across all files
  python scripts/sync_version.py --set 0.10.0     # Set new version everywhere and regenerate
  python scripts/sync_version.py                  # Propagate versions.py SSOT to all files
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SRC = _REPO_ROOT / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import yaml  # noqa: E402
from bionexus.registry import compile_and_write_all, load_canonical_registry, sync_mirror_trees  # noqa: E402
from bionexus.versions import VERSION  # noqa: E402


def check_version_ssot(repo_root: Path, target_version: str | None = None) -> tuple[bool, list[str]]:
    """Verify that all files in the repository agree on the exact same version."""
    expected = target_version or VERSION
    diffs: list[str] = []

    # 1. Check src/bionexus/versions.py
    versions_py = repo_root / "src" / "bionexus" / "versions.py"
    if versions_py.is_file():
        content = versions_py.read_text(encoding="utf-8")
        m = re.search(r'VERSION\s*=\s*"([^"]+)"', content)
        if not m or m.group(1) != expected:
            found = m.group(1) if m else "None"
            diffs.append(f"src/bionexus/versions.py: found '{found}', expected '{expected}'")

    # 2. Check pyproject.toml
    pyproject_toml = repo_root / "pyproject.toml"
    if pyproject_toml.is_file():
        content = pyproject_toml.read_text(encoding="utf-8")
        m = re.search(r'version\s*=\s*"([^"]+)"', content)
        if not m or m.group(1) != expected:
            found = m.group(1) if m else "None"
            diffs.append(f"pyproject.toml: found '{found}', expected '{expected}'")

    # 3. Check bionexus.registry.yaml
    registry_yaml = repo_root / "bionexus.registry.yaml"
    if registry_yaml.is_file():
        try:
            with open(registry_yaml, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            reg_ver = data.get("package", {}).get("version")
            if reg_ver != expected:
                diffs.append(f"bionexus.registry.yaml: found '{reg_ver}', expected '{expected}'")
        except Exception as e:
            diffs.append(f"bionexus.registry.yaml: unparseable ({e})")

    # 4. Check plugin.json
    plugin_json = repo_root / "plugin.json"
    if plugin_json.is_file():
        import json

        try:
            with open(plugin_json, "r", encoding="utf-8") as f:
                pdata = json.load(f)
            if pdata.get("version") != expected:
                diffs.append(f"plugin.json: found '{pdata.get('version')}', expected '{expected}'")
        except Exception as e:
            diffs.append(f"plugin.json: unparseable ({e})")

    return (len(diffs) == 0, diffs)


def set_version_ssot(repo_root: Path, new_version: str) -> None:
    """Propagate a new version to all SSOT sources and compile manifests."""
    # 1. Update src/bionexus/versions.py
    versions_py = repo_root / "src" / "bionexus" / "versions.py"
    if versions_py.is_file():
        text = versions_py.read_text(encoding="utf-8")
        text = re.sub(r'VERSION\s*=\s*"[^"]+"', f'VERSION = "{new_version}"', text)
        text = re.sub(r'PLUGIN_VERSION\s*=\s*(?:"[^"]+"|VERSION)', "PLUGIN_VERSION = VERSION", text)
        versions_py.write_text(text, encoding="utf-8")
        print(f" [UPDATED] {versions_py.relative_to(repo_root)} -> {new_version}")

    # 2. Update pyproject.toml
    pyproject_toml = repo_root / "pyproject.toml"
    if pyproject_toml.is_file():
        text = pyproject_toml.read_text(encoding="utf-8")
        text = re.sub(r'version\s*=\s*"[^"]+"', f'version = "{new_version}"', text, count=1)
        pyproject_toml.write_text(text, encoding="utf-8")
        print(f" [UPDATED] {pyproject_toml.relative_to(repo_root)} -> {new_version}")

    # 3. Update bionexus.registry.yaml
    registry_yaml = repo_root / "bionexus.registry.yaml"
    if registry_yaml.is_file():
        text = registry_yaml.read_text(encoding="utf-8")
        text = re.sub(r'(\s+version:\s*)"[^"]+"', f'\\1"{new_version}"', text, count=1)
        registry_yaml.write_text(text, encoding="utf-8")
        print(f" [UPDATED] {registry_yaml.relative_to(repo_root)} -> {new_version}")

    # 4. Regenerate all client manifests from registry
    registry = load_canonical_registry(registry_yaml)
    registry["package"]["version"] = new_version
    compile_and_write_all(repo_root, registry)
    sync_mirror_trees(repo_root)
    print(f" [REGENERATED] all manifests and plugin mirrors synced to version {new_version}")


def main() -> int:
    parser = argparse.ArgumentParser(description="BioNexus Version SSOT Synchronization Tool")
    parser.add_argument("--set", dest="new_version", type=str, help="Set new version across all SSOT files")
    parser.add_argument("--check", action="store_true", help="Verify all manifests and code match the SSOT version")
    args = parser.parse_args()

    if args.new_version:
        print(f"=== Setting BioNexus SSOT Version to {args.new_version} ===")
        set_version_ssot(_REPO_ROOT, args.new_version)
        in_sync, diffs = check_version_ssot(_REPO_ROOT, args.new_version)
        if not in_sync:
            print("[ERROR] Drift detected after setting version:", file=sys.stderr)
            for d in diffs:
                print(f" - {d}", file=sys.stderr)
            return 1
        print(f"[OK] BioNexus unified version set to {args.new_version} with zero drift.")
        return 0

    if args.check or not args.new_version:
        print(f"=== Checking BioNexus SSOT Version Consistency (SSOT: {VERSION}) ===")
        in_sync, diffs = check_version_ssot(_REPO_ROOT, VERSION)
        if not in_sync:
            print("[DRIFT DETECTED] Version mismatches found:", file=sys.stderr)
            for d in diffs:
                print(f" - {d}", file=sys.stderr)
            print("\nRun `python scripts/sync_version.py --set <version>` to synchronize.", file=sys.stderr)
            return 1
        print(f"[OK] All package files and manifests are strictly unified at version {VERSION}.")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
