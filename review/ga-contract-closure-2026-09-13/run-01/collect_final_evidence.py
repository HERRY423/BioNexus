"""Retain exact local verification outputs; no release or scientific authority."""
import hashlib
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
sys.path.insert(0, str(ROOT / "src"))
from bionexus.validation_verifier import compute_validation_source_snapshot

EXPECTED = "7cd0af17f44e0ad1ca7f75914d6fd98eb553e10ff9458999ef0554d13c3bd85c"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(name, value):
    with (OUT / name).open("x", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, ensure_ascii=False)


assert compute_validation_source_snapshot(ROOT) == EXPECTED
static = []
for name, command in [
    ("ruff-08", [sys.executable, "-m", "ruff", "check", "src", "scripts", "evals", "tests"]),
    ("mypy-08", [sys.executable, "-m", "mypy", "--config-file", "mypy.ini"]),
    ("registry-08", [sys.executable, "scripts/registry_compiler.py", "--check"]),
    ("endpoints-08", [sys.executable, "scripts/registry_compiler.py", "--validate-endpoints"]),
    ("diff-check-08", ["git", "diff", "--check"]),
    ("coverage-gate-08", [sys.executable, "scripts/check_coverage.py", str(OUT / "core-08/coverage.json"), "--baseline", "quality/coverage-baseline.json"]),
]:
    result = subprocess.run(command, cwd=ROOT, capture_output=True)
    (OUT / (name + ".log")).write_bytes(result.stdout + result.stderr)
    static.append({"name": name, "command": command, "return_code": result.returncode})
write("static-checks-08.json", static)
assert all(item["return_code"] == 0 for item in static)

suites = {}
for name, relative in [("full_unit", "full-08.xml"), ("core", "core-08/tests.xml"),
                       ("de_requirements", "de-08/tests.xml"), ("installed_wheel", "wheel-tests-08.xml")]:
    document = ET.parse(OUT / relative)
    cases = list(document.iter("testcase"))
    skipped = [case for case in cases if case.find("skipped") is not None]
    failures = [case for case in cases if case.find("failure") is not None or case.find("error") is not None]
    suites[name] = {"junit": relative, "passed": len(cases) - len(skipped) - len(failures),
                    "skipped": len(skipped), "failed_or_error": len(failures),
                    "skip_reasons": [{"case": case.attrib.get("name"), "reason": case.find("skipped").attrib.get("message")} for case in skipped]}
assert all(suite["failed_or_error"] == 0 for suite in suites.values())
history = json.loads((OUT / "history-08.json").read_bytes())
strict = json.loads((OUT / "historical-strict-rejection-08.json").read_bytes())
rc = json.loads((OUT / "rc-scope-08.json").read_bytes())
ga = json.loads((OUT / "ga-blocked-08.json").read_bytes())
assert history["archive_integrity"] == "VERIFIED" and len(history["records"]) == 11
assert all(row["relationship"] == "PRESERVED_LEGACY" for row in history["records"])
assert strict["passed"] is False and rc["status"] == "RC_SCOPE_VALID" and ga["status"] == "BLOCKED"
paths = set()
for command in (["git", "diff", "--name-only"], ["git", "ls-files", "--others", "--exclude-standard"]):
    paths.update(subprocess.check_output(command, cwd=ROOT, text=True).splitlines())
changed = {name: digest(ROOT / name) for name in sorted(paths) if not name.startswith("review/") and (ROOT / name).is_file()}
write("changed-files-08.json", changed)
base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
summary = {"schema": "bionexus.local-engineering-closure.v1", "status": "LOCAL_ENGINEERING_VERIFIED",
           "created_at": datetime.now(timezone.utc).isoformat(), "base_commit": base,
           "working_tree": "UNCOMMITTED", "package_version": "1.0.0-rc.7 (locally modified; not the published rc7 wheel)",
           "validation_source_snapshot_sha256": EXPECTED, "suites": suites,
           "history": {"preserved_reports": 11, "archive_integrity": "VERIFIED", "original_execution_authenticity": "NOT_ESTABLISHED"},
           "strict_flagship_verification": {"passed": False, "expected_rejection": True, "errors": strict["errors"]},
           "support_scope": rc["status"], "ga_activation": ga["status"],
           "known_severe_cases": "Recorded counterexamples closed by executable regressions; not proof of absence of unknown defects",
           "full_suite_selection": "tests/unit -m 'not flagship_data' --ignore=tests/unit/test_scvi_smoke.py (existing CI selection; one deselected case)",
           "wheel_environment": "Isolated import path and local wheel, using pre-existing host dependencies; not clean-machine installation",
           "scientific_authorization": "NONE", "independent_validation": "NOT_ESTABLISHED", "current_hosted_ci": "NOT_RUN",
           "published_release": "NOT_PERFORMED", "limitations": [
               "Historical flagship reports and source-bound evidence index remain stale; actual scientific reruns and reviewed index updates are still required.",
               "Named maintainer support acceptance and external review are not created by this repair.",
               "Local capsules are not authenticated producers, independently anchored logs or scientific certification.",
               "Early collection attempts stalled in Windows Numba cache creation; full-05 passed after writable cache configuration. full-07 was stopped after a final contract correction. Only final -08 outputs attest this final candidate.",
           ]}
assert compute_validation_source_snapshot(ROOT) == EXPECTED
write("summary.json", summary)
artifacts = [OUT / name for name in (
    "summary.json", "changed-files-08.json", "static-checks-08.json", "history-08.json",
    "historical-strict-rejection-08.json", "rc-scope-08.json", "ga-blocked-08.json",
    "full-08.log", "full-08.xml", "core-08.log", "core-08/tests.xml", "core-08/coverage.json",
    "de-08.log", "de-08/tests.xml", "de-08/report.json", "de-08/receipts.json", "build-08.log", "wheel-08.log",
    "wheel-result-08.json", "wheel-tests-08.xml")]
artifacts.extend((OUT / "dist-08").iterdir())
artifacts.extend(OUT / (item["name"] + ".log") for item in static)
write("evidence-sha256.json", {path.relative_to(OUT).as_posix(): digest(path) for path in artifacts if path.is_file()})
print(json.dumps({"status": summary["status"], "suites": suites}, ensure_ascii=False))
