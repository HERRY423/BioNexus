"""Run P0 counterexamples against the installed local wheel, outside source imports.

Invoke with python -I. Dependencies come from the host; this is not a
clean-machine install or a released rc6 artifact.
"""
import hashlib
import json
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[3]
installed = root / ".quality/rc6-p0-wheel-install"
output = root / ".quality/rc6-p0-wheel-tests"
output.mkdir(exist_ok=False)
sys.path.insert(0, str(installed))

import bionexus.claim_checker
import bionexus.claim_semantics
import bionexus.de_audit
import pytest
from bionexus.de_bundle import verify_de_bundle

for module in (bionexus.de_audit, bionexus.claim_semantics, bionexus.claim_checker):
    actual = Path(module.__file__).resolve()
    assert actual.is_relative_to(installed), actual
    assert actual.read_bytes() == (root / "src/bionexus" / actual.name).read_bytes(), actual

original = root / "tests/unit/test_rc6_p0_boundaries.py"
test_file = output / "test_wheel_p0.py"
test_file.write_bytes(original.read_bytes())
status = pytest.main([
    str(test_file), "-q", "-p", "no:cacheprovider", "--confcutdir", str(output),
    "--basetemp", str(output / "tmp"), f"--junitxml={output / 'tests.xml'}",
])
assert status == 0, status
legacy = verify_de_bundle(root / "tests/fixtures/de_bundle_legacy_v1")
assert legacy["status"] == "LEGACY_LIMITED"
assert legacy["scientific_authorization"] == "NONE"
report = {
    "status": "PASS", "source": str(bionexus.de_audit.__file__),
    "test_sha256": hashlib.sha256(test_file.read_bytes()).hexdigest(),
    "legacy_bundle": legacy["status"], "scientific_authorization": "NONE",
    "scope": "Modified local wheel, isolated package imports with host dependencies; not the published rc6 wheel or clean-machine acceptance",
}
(output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
