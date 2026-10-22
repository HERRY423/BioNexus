"""The passive reader must load by filename without a package or sys.path edits."""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


def test_filename_import_in_process():
    reader = Path(__file__).resolve().parents[2] / "src/bionexus/de_bundle.py"
    spec = importlib.util.spec_from_file_location("passive_reader_coverage", reader)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    contract = module.evidence_contract("CONDITIONAL")
    assert contract["scientific_facts_verified"] is False


def test_filename_import_rejects_unloadable_sibling(monkeypatch):
    reader = Path(__file__).resolve().parents[2] / "src/bionexus/de_bundle.py"
    spec = importlib.util.spec_from_file_location("passive_reader_unloadable", reader)
    module = importlib.util.module_from_spec(spec)
    original = importlib.util.spec_from_file_location

    def unavailable(name, location, *args, **kwargs):
        if name == "_bionexus_passive_evidence_contract":
            return None
        return original(name, location, *args, **kwargs)

    monkeypatch.setattr(importlib.util, "spec_from_file_location", unavailable)
    with pytest.raises(ImportError, match="Cannot load sibling"):
        spec.loader.exec_module(module)


def test_filename_import_uses_sibling_contract_without_site_packages(tmp_path):
    root = Path(__file__).resolve().parents[2]
    (tmp_path / "evidence_contract.py").write_text("raise RuntimeError('decoy must not load')")
    code = """
import importlib.util, json, sys
spec = importlib.util.spec_from_file_location('standalone_de_bundle', sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
print(json.dumps(module.verify_de_bundle(sys.argv[2])))
"""
    result = subprocess.run(
        [sys.executable, "-I", "-S", "-c", code,
         str(root / "src/bionexus/de_bundle.py"), str(root / "tests/fixtures/de_bundle_legacy_v1")],
        cwd=tmp_path, capture_output=True, text=True, timeout=30, check=True,
    )
    payload = json.loads(result.stdout)
    assert payload["status"] == "LEGACY_LIMITED"
    assert payload["scientific_authorization"] == "NONE"
