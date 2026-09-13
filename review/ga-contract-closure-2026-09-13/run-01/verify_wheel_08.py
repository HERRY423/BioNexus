"""Test the built wheel with installed host dependencies, without source imports."""
import json
import os
import runpy
import shutil
import sys
from pathlib import Path

OUTPUT = Path(__file__).resolve().parent
ROOT = OUTPUT.parents[2]
TARGET = OUTPUT / "wheel-install-08/site-packages"
sys.path.insert(0, str(TARGET))
temporary = OUTPUT / "tmp/wheel-08"
temporary.mkdir(parents=True, exist_ok=True)
os.environ["TMP"] = str(temporary)
os.environ["TEMP"] = str(temporary)

import bionexus.de_audit as module
import bionexus.release_contract as release

assert Path(module.__file__).is_relative_to(TARGET)
assert Path(release.__file__).is_relative_to(TARGET)
assert json.loads((TARGET / "bionexus/data/core-support.v1.json").read_bytes()) == json.loads((ROOT / "src/bionexus/data/core-support.v1.json").read_bytes())
sys.argv = [str(ROOT / "scripts/check_de_bundle_contract.py"), "--installed"]
gate = runpy.run_path(sys.argv[0], run_name="wheel_bundle_check")
assert gate["main"]() == 0

test_root = OUTPUT / "wheel-test-08"
test_root.mkdir(exist_ok=False)
for name in ("test_ga_semantic_boundaries.py", "test_rc6_p0_boundaries.py"):
    shutil.copyfile(ROOT / "tests/unit" / name, test_root / name)

import pytest

code = pytest.main([str(test_root), "-q", "-p", "no:cacheprovider",
                    "--basetemp", str(OUTPUT / "tmp/wheel-pytest-08"),
                    "--junitxml=" + str(OUTPUT / "wheel-tests-08.xml")])
assert Path(module.__file__).is_relative_to(TARGET)
with (OUTPUT / "wheel-result-08.json").open("x", encoding="utf-8") as handle:
    json.dump({"status": "PASS" if code == 0 else "FAIL", "reader": module.__file__,
               "scope": "Built local wheel using existing host dependencies; not a clean-machine or published release test",
               "scientific_authorization": "NONE"}, handle, indent=2)
raise SystemExit(code)
