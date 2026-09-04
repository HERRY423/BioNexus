from pathlib import Path

import yaml

from bionexus.spec_registry import validate_spec_registry


def test_spec_registry_is_unique_contiguous_and_complete():
    spec_dir = Path(__file__).resolve().parents[2] / "spec"
    assert validate_spec_registry(spec_dir) == []


def test_numbering_freeze_is_locked_at_bns_025():
    spec_dir = Path(__file__).resolve().parents[2] / "spec"
    raw = yaml.safe_load((spec_dir / "registry.yaml").read_text(encoding="utf-8"))
    freeze = raw["numbering_freeze"]
    assert freeze["max_id"] == "BNS-025"
    ids = [entry["id"] for entry in raw["documents"]]
    assert max(ids) == "BNS-025"
    assert "BNS-026" not in ids
    by_id = {entry["id"]: entry["status"] for entry in raw["documents"]}
    assert by_id["BNS-024"] == "development_no_certification_effect"
    assert by_id["BNS-025"] == "development_no_certification_effect"


def test_registry_rejects_stale_or_duplicate_index_links(tmp_path):
    import shutil

    spec_dir = Path(__file__).resolve().parents[2] / "spec"
    for path in spec_dir.glob("*.md"):
        shutil.copyfile(path, tmp_path / path.name)
    shutil.copyfile(spec_dir / "registry.yaml", tmp_path / "registry.yaml")
    index = tmp_path / "README.md"
    original = index.read_text(encoding="utf-8")
    index.write_text(original.replace("(BNS-024-validation-transparency-network.md)",
                                     "(BNS-023-validation-transparency-network.md)"), encoding="utf-8")
    assert any("BNS-024 index" in error for error in validate_spec_registry(tmp_path))
    row = next(line for line in original.splitlines() if line.startswith("| [BNS-025]"))
    index.write_text(original + "\n" + row + "\n", encoding="utf-8")
    assert any("BNS-025 index" in error for error in validate_spec_registry(tmp_path))


def test_numbering_freeze_rejects_bns_026(tmp_path):
    import shutil

    spec_dir = Path(__file__).resolve().parents[2] / "spec"
    for path in spec_dir.glob("*.md"):
        shutil.copyfile(path, tmp_path / path.name)
    shutil.copyfile(spec_dir / "registry.yaml", tmp_path / "registry.yaml")
    (tmp_path / "BNS-026-should-not-exist.md").write_text(
        "# BNS-026: Should Not Exist\n", encoding="utf-8"
    )
    registry_path = tmp_path / "registry.yaml"
    raw = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    raw["documents"].append(
        {
            "id": "BNS-026",
            "file": "BNS-026-should-not-exist.md",
            "title": "Should Not Exist",
            "status": "development",
        }
    )
    registry_path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    errors = validate_spec_registry(tmp_path)
    assert any("specification freeze at BNS-025" in error for error in errors)


def test_numbering_freeze_is_required(tmp_path):
    import shutil

    spec_dir = Path(__file__).resolve().parents[2] / "spec"
    for path in spec_dir.glob("*.md"):
        shutil.copyfile(path, tmp_path / path.name)
    raw = yaml.safe_load((spec_dir / "registry.yaml").read_text(encoding="utf-8"))
    raw.pop("numbering_freeze", None)
    (tmp_path / "registry.yaml").write_text(yaml.safe_dump(raw), encoding="utf-8")
    errors = validate_spec_registry(tmp_path)
    assert any("numbering_freeze.max_id is required" in error for error in errors)
