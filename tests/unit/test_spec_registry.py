from pathlib import Path

from bionexus.spec_registry import validate_spec_registry


def test_spec_registry_is_unique_contiguous_and_complete():
    spec_dir = Path(__file__).resolve().parents[2] / "spec"
    assert validate_spec_registry(spec_dir) == []
