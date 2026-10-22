"""Worktree snapshots preserve exact bytes without presenting dirty source as a Git release."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import zipfile
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/capture_working_candidate.py"
SPEC = importlib.util.spec_from_file_location("working_candidate_capture", SCRIPT)
assert SPEC and SPEC.loader
capture_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(capture_module)


@pytest.fixture
def source_tree(tmp_path, monkeypatch):
    root = tmp_path / "source"
    root.mkdir()
    for rel, content in {
        "src/bionexus/core.py": "candidate = 2\n",
        "src/bionexus/data/contract.json": '{"schema": "fixture"}\n',
        "scripts/tool.py": "print('source')\n",
        "tests/fixtures/case.tsv": "gene\tvalue\nA\t1\n",
        "plugins/example/plugin.json": '{"name":"fixture"}\n',
        "pyproject.toml": '[project]\nname="fixture"\nversion="0.0.1"\n',
        "README.md": "candidate documentation\n",
        "review/old/result.json": "excluded evidence\n",
        "validation/runs/a/result.json": "excluded validation\n",
        "src/bionexus/__pycache__/x.pyc": "excluded cache\n",
        "scripts/run.log": "excluded log\n",
        "src/bionexus/.env": "DO_NOT_READ=credential\n",
        ".env.example": "DO_NOT_READ=even_examples_are_excluded\n",
    }.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    monkeypatch.setattr(capture_module, "_git_state", lambda _: {
        "base_head": "a" * 40, "dirty": True, "status_porcelain": " M src/bionexus/core.py",
    })
    monkeypatch.setattr(capture_module, "_installed_packages", lambda: {"fixture-dep": "1.2.3", "bionexus-reliability": "1.0.0rc8"})
    return root


def test_dirty_candidate_archive_has_exact_selected_bytes_and_input_digests(source_tree, tmp_path):
    input_file = tmp_path / "input.tsv"
    input_file.write_bytes(b"explicit input")
    output = source_tree / "review/new-candidate"
    manifest = capture_module.capture(source_tree, output, inputs={"matrix": input_file})
    assert manifest["evidence_class"] == "UNRELEASED_WORKTREE_SNAPSHOT"
    assert manifest["release_state"] == "UNRELEASED"
    assert manifest["source_is_git_commit"] is False
    assert manifest["base_git_head"] == "a" * 40
    assert manifest["git_before"]["dirty"] is True
    assert manifest["source_sha256_start"] == manifest["source_sha256_end"]
    assert manifest["input_digests"]["matrix"]["sha256"] == hashlib.sha256(b"explicit input").hexdigest()
    assert manifest["inputs_copied"] is False
    assert "commit" not in manifest
    with zipfile.ZipFile(output / "source.zip") as archive:
        assert set(archive.namelist()) == set(manifest["files"])
        assert "src/bionexus/data/contract.json" in archive.namelist()
        assert not any("review/" in path or ".env" in path or "__pycache__" in path for path in archive.namelist())
        for name in archive.namelist():
            assert archive.read(name) == (source_tree / name).read_bytes()
            assert hashlib.sha256(archive.read(name)).hexdigest() == manifest["files"][name]["sha256"]
    pins = (output / "requirements.lock.txt").read_text(encoding="utf-8")
    assert "fixture-dep==1.2.3" in pins
    assert "bionexus-reliability==" not in pins
    assert not (output / "FAILED.json").exists()


def test_dotenv_files_are_excluded_before_any_content_read(source_tree, tmp_path, monkeypatch):
    original = Path.open

    def forbid_env_read(path, *args, **kwargs):
        assert not path.name.startswith(".env"), "Snapshot must never open an environment file"
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", forbid_env_read)
    capture_module.capture(source_tree, tmp_path / "snapshot")


def test_output_cannot_overwrite_even_empty_existing_directory(source_tree, tmp_path):
    output = tmp_path / "existing"
    output.mkdir()
    with pytest.raises(FileExistsError, match="overwrite"):
        capture_module.capture(source_tree, output)
    assert list(output.iterdir()) == []


def test_output_inside_selected_source_is_refused(source_tree):
    with pytest.raises(ValueError, match="outside the selected source"):
        capture_module.capture(source_tree, source_tree / "scripts/snapshot")


@pytest.mark.parametrize("change", ["modify", "add", "remove"])
def test_source_changes_during_archive_retain_failed_attempt(source_tree, tmp_path, monkeypatch, change):
    original = capture_module._write_archive

    def changed_archive(root, path, inventory):
        original(root, path, inventory)
        target = root / "src/bionexus/core.py"
        if change == "modify":
            target.write_text("changed while freezing", encoding="utf-8")
        elif change == "add":
            (root / "src/bionexus/new.py").write_text("new source", encoding="utf-8")
        else:
            target.unlink()

    monkeypatch.setattr(capture_module, "_write_archive", changed_archive)
    output = tmp_path / "unstable"
    with pytest.raises(RuntimeError, match="Selected source changed"):
        capture_module.capture(source_tree, output)
    assert (output / "source.zip.partial").is_file()
    assert not (output / "source.zip").exists()
    assert not (output / "manifest.json").exists()
    assert json.loads((output / "FAILED.json").read_text(encoding="utf-8"))["status"] == "FAILED_SNAPSHOT"


def test_changed_input_during_freeze_is_refused(source_tree, tmp_path, monkeypatch):
    input_file = tmp_path / "matrix.tsv"
    input_file.write_text("before", encoding="utf-8")

    def changing_packages():
        input_file.write_text("after", encoding="utf-8")
        return {}

    monkeypatch.setattr(capture_module, "_installed_packages", changing_packages)
    with pytest.raises(RuntimeError, match="Input bytes changed"):
        capture_module.capture(source_tree, tmp_path / "snapshot", inputs={"matrix": input_file})


def test_git_head_change_is_refused_even_when_selected_bytes_are_stable(source_tree, tmp_path, monkeypatch):
    calls = iter([{"base_head": "a" * 40, "dirty": True}, {"base_head": "b" * 40, "dirty": True}])
    monkeypatch.setattr(capture_module, "_git_state", lambda _: next(calls))
    with pytest.raises(RuntimeError, match="Git HEAD changed"):
        capture_module.capture(source_tree, tmp_path / "snapshot")


def test_explicit_dotenv_input_is_refused(source_tree, tmp_path):
    with pytest.raises(ValueError, match="credential/environment input"):
        capture_module.capture(source_tree, tmp_path / "snapshot", inputs={"secret": source_tree / "src/bionexus/.env"})


def test_cli_alias_and_duplicate_input_labels(source_tree, tmp_path):
    assert capture_module.main(["--root", str(source_tree), "--output-dir", str(tmp_path / "snapshot")]) == 0
    with pytest.raises(SystemExit) as error:
        capture_module.main(["--output", str(tmp_path / "unused"), "--input", "x=a", "--input", "x=b"])
    assert error.value.code == 2
