#!/usr/bin/env python3
"""Capture a clean Git source archive and resolved environment without claiming validation."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
import re
import subprocess
import sys
from pathlib import Path


def capture(root: Path, output: Path) -> dict:
    def git(*args: str) -> str:
        return subprocess.check_output(["git", *args], cwd=root, text=True).strip()

    # Ignored runtime data are outside this source archive and need their own hashes.
    if git("status", "--porcelain", "--untracked-files=normal"):
        raise RuntimeError("Source freeze requires a clean checkout, including nonignored untracked files")
    commit = git("rev-parse", "HEAD")
    output.mkdir(parents=True, exist_ok=False)
    archive = output / "source.zip"
    subprocess.run(
        ["git", "-c", "core.autocrlf=false", "-c", "core.eol=lf", "archive", "--format=zip", "-o", str(archive.resolve()), commit],
        cwd=root, check=True,
    )
    packages, non_index, normalized_versions = {}, [], []
    for dist in importlib.metadata.distributions():
        name = re.sub(r"[-_.]+", "-", dist.metadata["Name"]).lower()
        version = dist.version.strip()
        if version != dist.version:
            normalized_versions.append(name)
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", name) or not re.fullmatch(r"[a-zA-Z0-9.+!_-]+", version):
            raise ValueError("Unsafe package metadata in environment")
        if name in packages and packages[name] != version:
            raise ValueError(f"Multiple installed versions for {name}")
        packages[name] = version
        if dist.read_text("direct_url.json"):
            non_index.append(name)
    pins = output / "requirements.lock.txt"
    pins.write_text(
        "# Exact installed versions for the recorded Python and OS; not a cross-platform lock.\n"
        "# Install BioNexus from source.zip; direct-source packages require separate source recovery.\n"
        + "".join(f"{name}=={version}\n" for name, version in sorted(packages.items()) if name != "bionexus-reliability"),
        encoding="utf-8",
    )
    manifest = {
        "evidence_class": "SOURCE_AND_RESOLVED_ENVIRONMENT_SNAPSHOT",
        "commit": commit,
        "git_tree": git("rev-parse", "HEAD^{tree}"),
        "python": sys.version,
        "platform": platform.platform(),
        "packages": dict(sorted(packages.items())),
        "direct_source_packages": sorted(set(non_index)),
        "version_metadata_whitespace_normalized": sorted(set(normalized_versions)),
        "sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (archive, pins)},
        "independent_validation": "NOT_ESTABLISHED",
        "limitations": [
            "This capture does not assert that tests passed; retain the corresponding test/job result.",
            "Ignored datasets and model weights are not included in the source archive.",
            "Version pins are scoped to this interpreter and OS; wheels and their hashes are not bundled.",
            "Other direct-source packages require their original sources; version pins alone cannot recover them.",
        ],
    }
    # Fail if tracked/untracked source changed during capture; ignored output is allowed.
    if git("rev-parse", "HEAD") != commit or git("status", "--porcelain", "--untracked-files=normal"):
        raise RuntimeError("Source changed during freeze (output must be ignored or outside the checkout)")
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    manifest = capture(Path(__file__).resolve().parents[1], args.output)
    print(f"Frozen {manifest['commit']}: {manifest['sha256']['source.zip']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
