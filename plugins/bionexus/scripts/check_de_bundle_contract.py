"""Offline compatibility gate; can check the exact installed wheel reader."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--installed", action="store_true", help="Require actual site-packages module and schema resources")
    args = parser.parse_args()
    if args.installed:
        import bionexus.de_bundle as module

        reader = Path(module.__file__).resolve()
        expected = Path(importlib.metadata.distribution("bionexus-reliability").locate_file("bionexus/de_bundle.py")).resolve()
        if reader != expected or "site-packages" not in reader.parts:
            raise RuntimeError("Installed-wheel gate imported an editable/source reader")
    else:
        reader = ROOT / "src/bionexus/de_bundle.py"
        spec = importlib.util.spec_from_file_location("standalone_de_bundle", reader)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
    for name in ("de-shadow-bundle.schema.json", "de-bundle-verification.schema.json"):
        schema = json.loads((reader.parent / "data" / name).read_text(encoding="utf-8"))
        assert schema["type"] == "object", name
    fixture = ROOT / "tests/fixtures/de_bundle_legacy_v1"
    recorded = json.loads((fixture / "FIXTURE.json").read_text(encoding="utf-8"))["sha256"]
    for name, digest in recorded.items():
        assert hashlib.sha256((fixture / name).read_bytes()).hexdigest() == digest, name
    legacy = module.verify_de_bundle(fixture)
    assert legacy["status"] == "LEGACY_LIMITED"
    assert legacy["scientific_authorization"] == "NONE"
    assert legacy["audit_status"] == "NEEDS_REVISION"
    with tempfile.TemporaryDirectory(prefix="de-contract-") as temporary:
        target = Path(temporary) / "copy"
        shutil.copytree(fixture, target)
        manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
        manifest.update(integrity_profile=module.INTEGRITY_PROFILE,
                        immutable_artifacts={name: hashlib.sha256((target / name).read_bytes()).hexdigest()
                                             for name in module.IMMUTABLE_ARTIFACTS})
        (target / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        checked = module.verify_de_bundle(target)
        assert checked["status"] == "CONSISTENT"
        assert checked["analysis_execution_verification"] == "NOT_PERFORMED"
        with (target / "REVIEW.md").open("ab") as stream:
            stream.write(b"\nChanged report\n")
        assert module.verify_de_bundle(target)["status"] == "INVALID"
        manifest["schema"] = "bionexus.de-shadow-bundle.v999"
        (target / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        assert module.verify_de_bundle(target)["status"] == "UNSUPPORTED_SCHEMA"
    print(json.dumps({"status": "PASS", "reader": str(reader), "installed_wheel": args.installed,
                      "checks": ["packaged_schemas", "frozen_legacy_bytes", "legacy_limit", "profile_consistency",
                                 "tampered_human_report", "unknown_schema", "no_scientific_authority"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
