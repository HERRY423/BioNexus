"""Collect final local verification evidence without asserting external approval."""
import hashlib
import json
import shutil
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

here = Path(__file__).resolve().parent
root = here.parents[2]
quality = root / ".quality"
frozen = json.loads((here / "source-before-final-tests.json").read_text(encoding="utf-8"))
for name, digest in frozen.items():
    assert hashlib.sha256((root / name).read_bytes()).hexdigest() == digest, name


def junit(path):
    tree = ET.parse(path)
    suites = list(tree.getroot().iter("testsuite"))
    counts = {key: sum(int(s.attrib.get(key, 0)) for s in suites)
              for key in ("tests", "failures", "errors", "skipped")}
    counts["passed"] = counts["tests"] - counts["failures"] - counts["errors"] - counts["skipped"]
    counts["skip_reasons"] = sorted({n.attrib.get("message", "") for n in tree.getroot().iter("skipped")})
    assert counts["failures"] == counts["errors"] == 0, counts
    return counts


checks = {
    "full_unit": junit(quality / "rc6-p0-full-final-03.xml"),
    "fixed_core": junit(quality / "rc6-p0-core-final/tests.xml"),
    "de_requirements": junit(quality / "rc6-p0-de-final/tests.xml"),
    "installed_wheel_p0": junit(quality / "rc6-p0-wheel-tests/tests.xml"),
}
assert "Core line and branch coverage floors passed" in (quality / "rc6-p0-core-final.log").read_text(encoding="utf-8")
report = {
    "status": "LOCAL_FIXES_VERIFIED_EXTERNAL_ACCEPTANCE_PENDING",
    "base_commit": "4bf9a754cb9a58a02bddaad3acb7d8f62d518f5d",
    "python": sys.version, "checks": checks, "source_sha256": frozen,
    "coverage_floors": "UNCHANGED_AND_PASSED",
    "artifact_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in (quality / "rc6-p0-dist-final").iterdir() if p.is_file()},
    "wheel_scope": "Modified local build, exact installed package imports with existing host dependencies; not published rc6 or clean-machine validation",
    "preexisting_dirty_worktree": True,
    "scientific_authorization": "NONE",
    "hosted_ci_for_this_change": "NOT_RUN",
    "pages_deployment_for_this_change": "NOT_RUN",
    "ga_support_policy": "PROPOSED_NOT_ACTIVATED_PENDING_NAMED_ACCEPTANCE_AND_ACTUAL_DATES",
    "release": "NOT_PUBLISHED",
}
(here / "summary.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
copies = {
    "rc6-p0-full-final-03.log": "full-unit.log", "rc6-p0-full-final-03.xml": "full-unit.xml",
    "rc6-p0-core-final.log": "core-quality.log", "rc6-p0-core-final/tests.xml": "core-quality.xml",
    "rc6-p0-de-final/report.json": "de-traceability.json", "rc6-p0-de-final/receipts.json": "de-receipts.json",
    "rc6-p0-de-final/tests.xml": "de-tests.xml", "rc6-p0-wheel-tests/report.json": "wheel-report.json",
    "rc6-p0-wheel-tests/tests.xml": "wheel-tests.xml", "rc6-p0-build-final.log": "build.log",
    "rc6-p0-lint-final.log": "lint.log", "rc6-p0-types-final.log": "types.log",
    "rc6-p0-registry-final.log": "registry.log", "rc6-p0-ivn-final.log": "ivn.log",
}
for source, target in copies.items():
    shutil.copyfile(quality / source, here / target)
print(json.dumps({"status": report["status"], "checks": checks}, indent=2, ensure_ascii=False))
