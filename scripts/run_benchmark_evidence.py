#!/usr/bin/env python3
"""Run a bounded replay/backend benchmark and retain reports with source hashes."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source_hashes() -> dict[str, str]:
    paths = {Path(__file__).resolve(), ROOT / "pyproject.toml"}
    for directory in ("src/bionexus", "evals", "skills", "tests/fixtures"):
        for path in (ROOT / directory).rglob("*"):
            if path.is_file() and path.suffix in {".py", ".yaml", ".json"} and "reports" not in path.parts:
                paths.add(path)
    return {p.relative_to(ROOT).as_posix(): _digest(p) for p in sorted(paths)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, required=True, help="New output directory; existing reports are never overwritten"
    )
    parser.add_argument("--suite", default="all")
    parser.add_argument("--level", choices=["all", "L1", "L2", "L3"], default="all")
    parser.add_argument("--exclude", action="append", default=[])
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)
    # Establish the writable Numba cache before importing any scientific backend.
    cache = ROOT / ".numba-cache"
    cache.mkdir(exist_ok=True)
    os.environ.setdefault("NUMBA_CACHE_DIR", str(cache))

    from evals.runner import format_benchmark_markdown, run_benchmark

    args.output.mkdir(parents=True, exist_ok=False)
    source_before = _source_hashes()
    report = run_benchmark(
        suite=args.suite,
        level=args.level,
        provider="replay",
        strict=True if args.strict else None,
        exclude=args.exclude,
    )
    source_after = _source_hashes()
    source_stable = source_before == source_after
    payload = report.to_dict()
    (args.output / "report.json").write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    (args.output / "report.md").write_text(format_benchmark_markdown(report), encoding="utf-8")
    packages = {}
    for package in (
        "numpy",
        "pandas",
        "scipy",
        "scanpy",
        "anndata",
        "squidpy",
        "pydeseq2",
        "scikit-learn",
        "leidenalg",
        "igraph",
    ):
        try:
            packages[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            packages[package] = None
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False)
    manifest = {
        "evidence_class": "LOCAL_REPLAY_AND_BACKEND_CHECKS",
        "independent_validation": "NOT_ESTABLISHED",
        "empirical_calibration_approval": "NOT_ESTABLISHED",
        "timestamp": report.timestamp,
        "python": sys.version,
        "platform": platform.platform(),
        "packages": packages,
        "base_commit": head.stdout.strip() if head.returncode == 0 else None,
        "checkout_note": "Source hashes describe working files, including uncommitted changes; base_commit alone does not identify them.",
        "selection": report.selection,
        "strict": report.strict_mode,
        "source_stable_during_run": source_stable,
        "source_sha256": source_before,
        "report_sha256": {name: _digest(args.output / name) for name in ("report.json", "report.md")},
        "fixture_sha256": {
            p.relative_to(ROOT).as_posix(): _digest(p) for p in sorted((ROOT / "tests/fixtures").glob("*.h5ad"))
        },
    }
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(
        f"Evidence written to {args.output}: passed={report.passed_cases}, failed={report.failed_cases}, skipped={report.skipped_cases}, source_stable={source_stable}"
    )
    return 0 if report.failed_cases == 0 and source_stable else 1


if __name__ == "__main__":
    raise SystemExit(main())
