#!/usr/bin/env python3
"""Build a hash-bound BioNexus independent-review reproduction capsule.

The runner deliberately records failed checks and continues.  A negative or
partial result is review evidence; it must not disappear because one command
returned non-zero.  Producing this capsule is technical reproduction only and
does not create external-lab credit or an IVN VERIFIED record.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CHECKS: tuple[tuple[str, ...], ...] = (
    (
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "-p",
        "no:cacheprovider",
        "--confcutdir=tests/unit",
        "tests/unit/test_pseudobulk_inferential_warrant.py",
        "tests/unit/test_flagship_capabilities.py",
        "tests/unit/test_ivn.py",
        "tests/unit/test_validation_verifier.py",
        "-k",
        "not test_verify_validation_artifacts_passes_on_current_repo",
    ),
    (sys.executable, "-m", "bionexus.cli", "certification", "--json"),
    (sys.executable, "scripts/registry_compiler.py", "--check"),
    (sys.executable, "-m", "bionexus.cli", "ivn", "status", "--repo-root", ".", "--json"),
    (sys.executable, "-m", "bionexus.cli", "ivn", "verify", "--repo-root", ".", "--json"),
)

REVIEW_REQUIRED_DISTRIBUTIONS: tuple[str, ...] = (
    "pytest",
    "numpy",
    "PyYAML",
    "jsonschema",
    "cryptography",
)
INTENTIONALLY_OMITTED_PROJECT_DEPENDENCIES: tuple[str, ...] = (
    "pandas",
    "scipy",
    "requests",
    "tqdm",
    "scikit-learn",
)


def _run(command: Sequence[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        cwd=cwd,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        detail = "\n".join(part for part in (result.stdout.strip(), result.stderr.strip()) if part)
        raise RuntimeError(f"git {' '.join(args)} failed:\n{detail}")
    return result.stdout.strip()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _installed_version(distribution: str) -> str:
    try:
        return metadata.version(distribution)
    except metadata.PackageNotFoundError:
        return "NOT_INSTALLED"


def _safe_name(value: str) -> str:
    return "".join(ch for ch in value if ch.isalnum() or ch in "-_") or "review"


def build_capsule(*, expected_commit: str, output_dir: Path, review_id: str) -> dict[str, Any]:
    if len(expected_commit) != 40 or any(ch not in "0123456789abcdefABCDEF" for ch in expected_commit):
        raise ValueError("--expected-commit must be the full 40-character immutable Git commit SHA")

    head = _git("rev-parse", "HEAD").lower()
    if head != expected_commit.lower():
        raise RuntimeError(f"checked-out HEAD {head} does not match expected commit {expected_commit.lower()}")

    dirty = _git("status", "--short")
    if dirty:
        raise RuntimeError("review checkout is not clean; refuse to create an ambiguous capsule")

    review_versions = {name: _installed_version(name) for name in REVIEW_REQUIRED_DISTRIBUTIONS}
    missing_review_dependencies = sorted(
        name for name, version in review_versions.items() if version == "NOT_INSTALLED"
    )
    if missing_review_dependencies:
        raise RuntimeError(
            "bounded review dependencies are missing: "
            + ", ".join(missing_review_dependencies)
            + "; install with: python -m pip install --no-deps -e . && "
            "python -m pip install -r review/external-review/requirements-review.txt"
        )

    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    created_at = datetime.now(timezone.utc).isoformat()
    capsule_stem = f"BioNexus-{_safe_name(review_id)}-{head[:12]}"

    with tempfile.TemporaryDirectory(prefix="bionexus-review-") as tmp:
        staging = Path(tmp) / capsule_stem
        logs = staging / "logs"
        logs.mkdir(parents=True)

        freeze = _run((sys.executable, "-m", "pip", "freeze", "--all"), cwd=REPO_ROOT)
        if freeze.returncode != 0:
            raise RuntimeError(f"pip freeze --all failed:\n{freeze.stdout}")
        freeze_path = staging / "PIP_FREEZE.txt"
        freeze_path.write_text(freeze.stdout, encoding="utf-8")

        environment = {
            "schema_version": "bionexus.review-environment.v2",
            "created_at": created_at,
            "git_commit": head,
            "git_describe": _git("describe", "--always", "--dirty", "--tags"),
            "python": sys.version,
            "python_executable": sys.executable,
            "python_prefix": sys.prefix,
            "platform": platform.platform(),
            "machine": platform.machine(),
            "bionexus_distribution_version": _installed_version("bionexus-reliability"),
            "review_dependency_profile": "review/external-review/requirements-review.txt",
            "review_dependency_versions": review_versions,
            "intentionally_omitted_project_dependencies": list(INTENTIONALLY_OMITTED_PROJECT_DEPENDENCIES),
            "installation_scope": "BOUNDED_EXTERNAL_REVIEW_NOT_GENERAL_SCIENTIFIC_RUNTIME",
            "pip_freeze_command": [sys.executable, "-m", "pip", "freeze", "--all"],
            "pip_freeze_exit_code": freeze.returncode,
            "pip_freeze_path": "PIP_FREEZE.txt",
            "pip_freeze_sha256": _sha256(freeze_path),
        }
        (staging / "ENVIRONMENT.json").write_text(
            json.dumps(environment, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

        results: list[dict[str, Any]] = []
        for index, command in enumerate(DEFAULT_CHECKS, start=1):
            rendered = subprocess.list2cmdline(command)
            result = _run(command, cwd=REPO_ROOT)
            log_name = f"{index:02d}.log"
            (logs / log_name).write_text(
                f"COMMAND: {rendered}\nEXIT_CODE: {result.returncode}\n\n{result.stdout}",
                encoding="utf-8",
            )
            results.append(
                {
                    "sequence": index,
                    "command": list(command),
                    "exit_code": result.returncode,
                    "outcome": "PASS" if result.returncode == 0 else "NONZERO_RECORDED",
                    "log": f"logs/{log_name}",
                }
            )

        summary = {
            "schema_version": "bionexus.review-capsule.v1",
            "review_id": review_id,
            "created_at": created_at,
            "git_commit": head,
            "scope": "TECHNICAL_REPRODUCTION_FOR_INDEPENDENT_REVIEW",
            "external_lab_quota_credit": False,
            "ivn_status_effect": "NONE_UNTIL_SEPARATE_REVIEW_AND_REGISTRATION",
            "portable_scope_note": (
                "The repository-wide positive validation-artifact test requires separately retained "
                "flagship data files and is excluded from this portable pseudobulk/IVN capsule. "
                "Its fail-closed negative tests remain included."
            ),
            "environment_scope_note": (
                "PIP_FREEZE.txt records the resolved Python environment; it is evidence, not a "
                "cross-platform lockfile or proof that non-Python system dependencies are identical."
            ),
            "checks": results,
            "all_checks_passed": all(item["exit_code"] == 0 for item in results),
            "interpretation": (
                "Non-zero checks are preserved as review evidence. This capsule does not establish "
                "scientific validity, endorsement, independent-lab replication, or certification."
            ),
        }
        (staging / "SUMMARY.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

        archive = output_dir / f"{capsule_stem}.zip"
        if archive.exists():
            raise FileExistsError(f"refusing to overwrite existing capsule: {archive}")
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
            for path in sorted(staging.rglob("*")):
                if path.is_file():
                    bundle.write(path, path.relative_to(staging.parent))

    digest = _sha256(archive)
    sidecar = archive.with_suffix(archive.suffix + ".sha256")
    sidecar.write_text(f"{digest}  {archive.name}{os.linesep}", encoding="ascii")
    return {
        "capsule": str(archive),
        "sha256": digest,
        "sha256_file": str(sidecar),
        "all_checks_passed": summary["all_checks_passed"],
        "note": "Capsule creation succeeded even if recorded checks returned non-zero.",
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-commit", required=True, help="Full 40-character immutable Git commit SHA")
    parser.add_argument("--review-id", default="BN-IVN-REV-001")
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT / "review-capsules")
    args = parser.parse_args(argv)

    try:
        result = build_capsule(
            expected_commit=args.expected_commit,
            output_dir=args.output_dir,
            review_id=args.review_id,
        )
    except (FileExistsError, RuntimeError, ValueError) as exc:
        print(json.dumps({"status": "REFUSED", "error": str(exc)}, indent=2), file=sys.stderr)
        return 2
    print(json.dumps({"status": "CAPSULE_CREATED", **result}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
