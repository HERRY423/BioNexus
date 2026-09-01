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
