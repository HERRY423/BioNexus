"""Tests for the independent-review reproduction capsule builder."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import zipfile
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "review" / "external-review" / "build_review_capsule.py"
_SPEC = importlib.util.spec_from_file_location("bionexus_review_capsule", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
capsule_module = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(capsule_module)


def test_default_checks_are_portable_and_do_not_invoke_a_noop_module():
    rendered = [" ".join(command) for command in capsule_module.DEFAULT_CHECKS]

    assert any("scripts/registry_compiler.py --check" in command for command in rendered)
    assert any("not test_verify_validation_artifacts_passes_on_current_repo" in command for command in rendered)
    assert all("-m bionexus.validation_verifier" not in command for command in rendered)


def test_git_ignores_nonfatal_stderr_warnings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(capsule_module, "REPO_ROOT", tmp_path)

    class Result:
        returncode = 0
        stdout = "\n"
        stderr = "warning: inaccessible global excludes file\n"

    monkeypatch.setattr(capsule_module.subprocess, "run", lambda *args, **kwargs: Result())
    assert capsule_module._git("status", "--short") == ""


def test_capsule_preserves_nonzero_checks_and_hashes_archive(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    commit = "a" * 40

    def fake_git(*args: str) -> str:
        if args == ("rev-parse", "HEAD"):
            return commit
        if args == ("status", "--short"):
            return ""
        if args == ("describe", "--always", "--dirty", "--tags"):
            return "review-test"
        raise AssertionError(f"unexpected git call: {args}")

    monkeypatch.setattr(capsule_module, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(capsule_module, "_git", fake_git)
    monkeypatch.setattr(capsule_module, "_installed_version", lambda name: "9.0.0" if name == "pytest" else "1.0.0")
    monkeypatch.setattr(
        capsule_module,
        "DEFAULT_CHECKS",
        (
            (sys.executable, "-c", "print('pass')"),
            (sys.executable, "-c", "import sys; print('negative retained'); sys.exit(7)"),
        ),
    )

    result = capsule_module.build_capsule(
        expected_commit=commit,
        output_dir=tmp_path / "capsules",
        review_id="BN-IVN-REV-TEST",
    )

    archive = Path(result["capsule"])
    assert archive.is_file()
    assert result["all_checks_passed"] is False
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == result["sha256"]
    assert Path(result["sha256_file"]).read_text(encoding="ascii").startswith(result["sha256"])

    with zipfile.ZipFile(archive) as bundle:
        summary_name = next(name for name in bundle.namelist() if name.endswith("/SUMMARY.json"))
        summary = json.loads(bundle.read(summary_name))
        assert summary["external_lab_quota_credit"] is False
        assert summary["ivn_status_effect"] == "NONE_UNTIL_SEPARATE_REVIEW_AND_REGISTRATION"
        assert [item["exit_code"] for item in summary["checks"]] == [0, 7]
        assert summary["checks"][1]["outcome"] == "NONZERO_RECORDED"
        environment_name = next(name for name in bundle.namelist() if name.endswith("/ENVIRONMENT.json"))
        environment = json.loads(bundle.read(environment_name))
        freeze_name = next(name for name in bundle.namelist() if name.endswith("/PIP_FREEZE.txt"))
        assert environment["pip_freeze_sha256"] == hashlib.sha256(bundle.read(freeze_name)).hexdigest()


def test_capsule_refuses_when_review_dependency_is_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    commit = "a" * 40
    monkeypatch.setattr(capsule_module, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        capsule_module,
        "_git",
        lambda *args: commit if args == ("rev-parse", "HEAD") else "",
    )
    monkeypatch.setattr(capsule_module, "_installed_version", lambda name: "NOT_INSTALLED")

    with pytest.raises(RuntimeError, match=r"\.\[review\]"):
        capsule_module.build_capsule(
            expected_commit=commit,
            output_dir=tmp_path / "capsules",
            review_id="BN-IVN-REV-TEST",
        )


def test_capsule_refuses_mutable_or_mismatched_identity(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    with pytest.raises(ValueError, match="40-character"):
        capsule_module.build_capsule(
            expected_commit="main",
            output_dir=tmp_path,
            review_id="BN-IVN-REV-TEST",
        )

    monkeypatch.setattr(capsule_module, "_git", lambda *args: "b" * 40)
    with pytest.raises(RuntimeError, match="does not match expected commit"):
        capsule_module.build_capsule(
            expected_commit="a" * 40,
            output_dir=tmp_path,
            review_id="BN-IVN-REV-TEST",
        )
