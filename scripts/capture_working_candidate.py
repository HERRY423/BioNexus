#!/usr/bin/env python3
"""Freeze selected current-worktree bytes as an unreleased local candidate, never a Git release."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import re
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

SOURCE_DIRECTORIES = (
    "src", "evals", "scripts", "tests", "skills", "plugins", "spec", "quality", "docs", ".github",
    ".codex-plugin", ".claude-plugin", ".agents/plugins", "standards", "governance", "container",
    "cluster", "tools", "assets", "calibration/spatial-empirical-gold-standard",
)
ROOT_FILES = frozenset({
    "pyproject.toml", "MANIFEST.in", "setup.cfg", "setup.py", "setup.sh", "setup.ps1", "setup.bat",
    "README.md", "LICENSE", "CHANGELOG.md", "CHANGES.md", "CONTRIBUTING.md", "SECURITY.md",
    "SUPPORT.md", "MAINTENANCE.md", "GA_CRITERIA.md", "CONNECTORS.md", "AGENTS.md",
    ".codex/config.json", ".codex/marketplace.json",
    "bionexus.registry.yaml", "plugin.json", "marketplace.json", "mcp.json", ".mcp.json",
    ".gitignore", ".gitattributes", "mypy.ini", "pytest.ini", "ruff.toml", ".ruff.toml",
    "environment.yml", "environment.yaml", "uv.lock", "poetry.lock", "Pipfile", "Pipfile.lock",
    "requirements.txt", "requirements-dev.txt", "package.json", "package-lock.json",
    "pnpm-lock.yaml", "yarn.lock", "Dockerfile", "Makefile", "tox.ini",
})
EXCLUDED_DIRECTORIES = frozenset({
    ".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".hypothesis",
    ".venv", "venv", "node_modules", "build", "dist", ".artifacts", ".quality",
    "review", "validation", "cross-host", "runtime", "runtime_lance", "runtime_wheels",
    "data", "datasets", "cache", "caches", "logs", "results", "output", "outputs",
    "checkpoints", "model", "models", "work", ".nextflow", "lance_runtime",
})
EXCLUDED_SUFFIXES = frozenset({".pyc", ".pyo", ".log", ".tmp", ".swp", ".whl"})
EVIDENCE_CLASS = "UNRELEASED_WORKTREE_SNAPSHOT"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _credential_path(path: Path) -> bool:
    name = path.name.lower()
    return (
        name == ".env" or name.startswith(".env.") or name.endswith(".env")
        or name in {"credentials.json", "credentials.toml", "secrets.json", "secrets.toml", "id_rsa", "id_ed25519", ".git-credentials", ".netrc", ".npmrc"}
        or name.endswith((".key", ".p12", ".pfx"))
    )


def _is_link(path: Path) -> bool:
    return path.is_symlink() or bool(getattr(path, "is_junction", lambda: False)())


def _excluded_directory(path: Path, relative: Path) -> bool:
    # Package resource directories and model code are source; top-level runtime data are excluded.
    if relative.parts[0] in {"src", "evals", "tests"} and path.name in {"data", "datasets", "model", "models"}:
        return False
    return (
        path.name in EXCLUDED_DIRECTORIES or path.name.endswith(".egg-info")
        or path.name.startswith((".pytest", ".numba", "_tmp_", ".codex_tmp", ".env"))
    )


def _source_inventory(root: Path) -> dict[str, dict[str, Any]]:
    paths: list[Path] = []
    for relative in SOURCE_DIRECTORIES:
        base = root / relative
        if not base.exists():
            continue
        if _is_link(base) or not base.is_dir():
            raise RuntimeError(f"Selected source root must be a real directory: {relative}")
        for directory, folders, files in os.walk(base, followlinks=False):
            parent = Path(directory)
            retained = []
            for folder in sorted(folders):
                candidate = parent / folder
                if _excluded_directory(candidate, candidate.relative_to(root)):
                    continue
                if _is_link(candidate):
                    raise RuntimeError(f"Refusing linked source directory: {candidate.relative_to(root)}")
                retained.append(folder)
            folders[:] = retained
            for name in sorted(files):
                path = parent / name
                if _credential_path(path) or path.suffix.lower() in EXCLUDED_SUFFIXES:
                    continue
                paths.append(path)
    paths.extend(root / name for name in sorted(ROOT_FILES) if (root / name).is_file())
    inventory = {}
    for path in sorted(set(paths)):
        rel = path.relative_to(root).as_posix()
        if _is_link(path) or not path.resolve().is_relative_to(root):
            raise RuntimeError(f"Refusing linked or escaping source file: {rel}")
        inventory[rel] = {"sha256": _sha256_file(path), "size_bytes": path.stat().st_size}
    if not inventory:
        raise RuntimeError("No source files matched the explicit snapshot scope")
    return inventory


def _git_state(root: Path) -> dict[str, Any]:
    def git(*args: str) -> str:
        return subprocess.check_output(["git", *args], cwd=root, text=True, encoding="utf-8", errors="strict").rstrip("\r\n")

    head = git("rev-parse", "HEAD")
    status = git("status", "--porcelain=v1", "--untracked-files=all")
    return {"base_head": head, "dirty": bool(status), "status_porcelain": status}


def _installed_packages() -> dict[str, str]:
    packages = {}
    for dist in importlib.metadata.distributions():
        name = re.sub(r"[-_.]+", "-", str(dist.metadata["Name"])).lower()
        version = dist.version.strip()
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", name) or not re.fullmatch(r"[a-zA-Z0-9.+!_-]+", version):
            raise ValueError("Unsafe package metadata in environment")
        if name in packages and packages[name] != version:
            raise ValueError(f"Multiple installed versions for {name}")
        packages[name] = version
    return dict(sorted(packages.items()))


def _input_inventory(inputs: Mapping[str, Path]) -> dict[str, dict[str, Any]]:
    observed = {}
    for label, path in sorted(inputs.items()):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", label):
            raise ValueError(f"Unsafe input label: {label!r}")
        if _credential_path(path) or _credential_path(path.resolve()):
            raise ValueError(f"Refusing credential/environment input: {label}")
        if _is_link(path) or not path.is_file():
            raise ValueError(f"Input must be a regular, nonlinked file: {label}")
        observed[label] = {"path": str(path.resolve()), "sha256": _sha256_file(path), "size_bytes": path.stat().st_size}
    return observed


def _write_archive(root: Path, path: Path, inventory: Mapping[str, Mapping[str, Any]]) -> None:
    with zipfile.ZipFile(path, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for relative, expected in sorted(inventory.items()):
            source = root / relative
            if _is_link(source) or not source.resolve().is_relative_to(root):
                raise RuntimeError(f"Source became a link during capture: {relative}")
            info = zipfile.ZipInfo(relative, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (source.stat().st_mode & 0xFFFF) << 16
            digest = hashlib.sha256()
            size = 0
            with source.open("rb") as reader, archive.open(info, "w") as writer:
                for chunk in iter(lambda: reader.read(1024 * 1024), b""):
                    digest.update(chunk)
                    size += len(chunk)
                    writer.write(chunk)
            if digest.hexdigest() != expected["sha256"] or size != expected["size_bytes"]:
                raise RuntimeError(f"Source bytes changed during archive creation: {relative}")


def capture(root: Path, output: Path, *, inputs: Mapping[str, Path] | None = None) -> dict[str, Any]:
    """Capture byte-identical selected source at both ends, retaining failed attempts separately."""
    root = root.resolve()
    output = output.resolve()
    for selected in SOURCE_DIRECTORIES:
        if output.is_relative_to(root / selected):
            raise ValueError("Snapshot output must be outside the selected source directories")
    if output == root:
        raise ValueError("Snapshot output cannot be the source root")
    if output.is_relative_to(root / ".git"):
        raise ValueError("Snapshot output cannot alter Git metadata")
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite a snapshot destination: {output}")
    git_before = _git_state(root)
    output.mkdir(parents=True, exist_ok=False)
    attempt = {"status": "FAILED_SNAPSHOT", "evidence_class": EVIDENCE_CLASS, "git_before": git_before}
    try:
        source_before = _source_inventory(root)
        inputs_before = _input_inventory(inputs or {})
        source_digest = _canonical_hash(source_before)
        attempt["source_sha256_start"] = source_digest
        partial = output / "source.zip.partial"
        _write_archive(root, partial, source_before)
        packages = _installed_packages()
        pins = output / "requirements.lock.txt"
        with pins.open("x", encoding="utf-8") as handle:
            handle.write(
                "# Installed version pins for this Python/OS only; not a dependency artifact lock.\n"
                "# Build BioNexus from source.zip. These pins do not recover editable/direct-source dependencies.\n"
                + "".join(f"{name}=={version}\n" for name, version in packages.items() if name not in {"bionexus", "bionexus-reliability"})
            )
        source_after = _source_inventory(root)
        inputs_after = _input_inventory(inputs or {})
        git_after = _git_state(root)
        attempt["source_sha256_end"] = _canonical_hash(source_after)
        attempt["git_after"] = git_after
        if source_before != source_after:
            raise RuntimeError("Selected source changed during capture; candidate is not stable")
        if inputs_before != inputs_after:
            raise RuntimeError("Input bytes changed during capture; candidate is not stable")
        if git_before["base_head"] != git_after["base_head"]:
            raise RuntimeError("Git HEAD changed during capture; candidate base is not stable")
        archive = output / "source.zip"
        partial.rename(archive)
        manifest = {
            "schema_version": "bionexus.working-candidate-snapshot.v1",
            "status": "CAPTURED_STABLE_SOURCE",
            "evidence_class": EVIDENCE_CLASS,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "base_git_head": git_before["base_head"],
            "source_is_git_commit": False,
            "git_before": git_before,
            "git_after": git_after,
            "source_sha256_start": source_digest,
            "source_sha256_end": _canonical_hash(source_after),
            "files": source_before,
            "input_digests": inputs_before,
            "inputs_copied": False,
            "python": sys.version,
            "platform": platform.platform(),
            "packages": packages,
            "sha256": {path.name: _sha256_file(path) for path in (archive, pins)},
            "selection": {
                "source_directories": list(SOURCE_DIRECTORIES),
                "root_files": sorted(ROOT_FILES),
                "excluded_directory_names": sorted(EXCLUDED_DIRECTORIES),
                "packaged_source_exceptions": "{src,evals,tests}/**/{data,datasets,model,models}",
                "credential_and_dotenv_files": "EXCLUDED_WITHOUT_READING",
            },
            "release_state": "UNRELEASED",
            "independent_validation": "NOT_ESTABLISHED",
            "limitations": [
                "This is an explicit subset of current worktree bytes, including selected uncommitted files; not git archive HEAD.",
                "Capture asserts no test, wheel, host, laboratory, scientific, or publication acceptance.",
                "Review, validation runs, cross-host receipts, runtime caches, datasets and credentials are not source inputs here.",
                "Explicit input files are hashed, not bundled; archive completeness does not establish input availability.",
                "Pins describe this interpreter and OS, omit wheel hashes, and do not recover direct-source/editable dependencies.",
                "Root manifests/configs are selected explicitly; environment files including .env.example are never read.",
                "Checks establish identical selected bytes before/archive/after; changes outside the selected scope are recorded only by Git state.",
            ],
        }
        with (output / "manifest.json").open("x", encoding="utf-8") as handle:
            handle.write(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
        return manifest
    except Exception as exc:
        attempt["error"] = str(exc)
        with (output / "FAILED.json").open("x", encoding="utf-8") as handle:
            json.dump(attempt, handle, indent=2)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", "--output-dir", required=True, type=Path)
    parser.add_argument("--input", action="append", default=[], metavar="LABEL=PATH", help="Hash an explicit input file without bundling it")
    args = parser.parse_args(argv)
    inputs = {}
    for item in args.input:
        label, separator, value = item.partition("=")
        if not separator or not label or not value or label in inputs:
            parser.error("--input requires unique nonempty LABEL=PATH entries")
        inputs[label] = Path(value)
    try:
        manifest = capture(args.root, args.output, inputs=inputs)
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"Snapshot failed: {exc}", file=sys.stderr)
        return 1
    print(f"{EVIDENCE_CLASS}: {manifest['source_sha256_start']} ({len(manifest['files'])} source files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
