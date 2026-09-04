"""Verify a source freeze against a real isolated Git repository."""

import hashlib
import subprocess
import zipfile

import pytest

from scripts.capture_reproducibility import capture


@pytest.fixture
def clean_source(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", str(root)], check=True, capture_output=True)
    (root / "source.py").write_text("VALUE = 3\n", encoding="utf-8")
    subprocess.run(["git", "add", "source.py"], cwd=root, check=True)
    subprocess.run(
        ["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-m", "fixture"],
        cwd=root, check=True, capture_output=True,
    )
    return root


def test_capture_archive_and_resolved_version_metadata(clean_source, tmp_path, monkeypatch):
    class Distribution:
        metadata = {"Name": "PySide6"}
        version = "6.9.2 "

        def read_text(self, filename):
            return None

    monkeypatch.setattr("importlib.metadata.distributions", lambda: [Distribution()])
    output = tmp_path / "freeze"
    manifest = capture(clean_source, output)
    with zipfile.ZipFile(output / "source.zip") as bundle:
        assert bundle.namelist() == ["source.py"]
        assert bundle.read("source.py") == subprocess.check_output(["git", "show", "HEAD:source.py"], cwd=clean_source)
    assert manifest["sha256"]["source.zip"] == hashlib.sha256((output / "source.zip").read_bytes()).hexdigest()
    assert "pyside6==6.9.2\n" in (output / "requirements.lock.txt").read_text()
    assert manifest["version_metadata_whitespace_normalized"] == ["pyside6"]
    assert manifest["independent_validation"] == "NOT_ESTABLISHED"


@pytest.mark.parametrize("dirty_file", ["source.py", "untracked.py"])
def test_capture_refuses_changed_or_untracked_source(clean_source, tmp_path, dirty_file):
    (clean_source / dirty_file).write_text("VALUE = 99\n", encoding="utf-8")
    output = tmp_path / "freeze"
    with pytest.raises(RuntimeError, match="clean checkout"):
        capture(clean_source, output)
    assert not output.exists()
