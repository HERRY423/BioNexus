"""Run the fixed, core-dependency quality profile and enforce coverage floors."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New directory for this run")
    parser.add_argument("--measure-only", action="store_true", help="Measure without claiming the coverage gate passed")
    args = parser.parse_args(argv)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    tests = json.loads((ROOT / "quality/core-tests.json").read_text(encoding="utf-8"))
    env = os.environ.copy()
    env["COVERAGE_FILE"] = str(output / ".coverage")
    env["NUMBA_CACHE_DIR"] = str(ROOT / ".numba-cache")
    command = [sys.executable, "-m", "pytest", *tests, "-q", "-p", "no:cacheprovider",
               "--hypothesis-seed=20260911",
               "--basetemp", str(output / "tmp"), "--cov=src/bionexus", "--cov-branch",
               f"--cov-report=json:{output / 'coverage.json'}", "--cov-report=term:skip-covered",
               f"--junitxml={output / 'tests.xml'}"]
    (output / "command.json").write_text(json.dumps(command, indent=2), encoding="utf-8")
    result = subprocess.run(command, cwd=ROOT, env=env, check=False)
    if result.returncode:
        return result.returncode
    if args.measure_only:
        print("Measurement only; coverage gate NOT ASSESSED")
        return 0
    return subprocess.run([sys.executable, str(ROOT / "scripts/check_coverage.py"),
                           str(output / "coverage.json"), "--baseline",
                           str(ROOT / "quality/coverage-baseline.json")], cwd=ROOT, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
