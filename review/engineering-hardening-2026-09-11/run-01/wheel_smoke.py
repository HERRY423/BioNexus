"""Verify the wheel outside the checkout import path, using host dependencies."""
import importlib
import importlib.util
import json
import pkgutil
import sys
from pathlib import Path

here = Path(__file__).resolve().parent
installed = here / "wheel-install"
sys.path.insert(0, str(installed))
from bionexus import cli, commands
from bionexus.de_bundle import verify_de_bundle

assert Path(cli.__file__).resolve().is_relative_to(installed)
loaded = []
for module in pkgutil.iter_modules(commands.__path__):
    imported = importlib.import_module(f"bionexus.commands.{module.name}")
    assert Path(imported.__file__).resolve().is_relative_to(installed)
    loaded.append(module.name)
root = here.parents[2]
spec = importlib.util.spec_from_file_location("compatibility_probe", root / "tests/unit/test_cli_compatibility.py")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
expected = json.loads((root / "tests/fixtures/cli_contract_v1.json").read_text(encoding="utf-8"))
assert probe.parser_contract(cli.main) == expected
result = verify_de_bundle(root / "tests/fixtures/de_bundle_legacy_v1")
assert result["status"] == "LEGACY_LIMITED"
assert result["scientific_authorization"] == "NONE"
report = {"status": "PASS", "cli": cli.__file__, "command_modules": loaded,
          "parser_contract": "MATCHES_PRE_REFACTOR", "legacy_bundle": result["status"],
          "scope": "Isolated wheel target with existing host dependencies, not clean-machine acceptance"}
(here / "wheel-smoke.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
