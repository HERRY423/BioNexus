"""Read-only support-contract gate used before a stable release is published."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from bionexus.release_contract import check_release
from bionexus.versions import VERSION


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", default=VERSION)
    args = parser.parse_args()
    result = check_release(ROOT, args.version)
    print(json.dumps(result, indent=2))
    return int(result["status"] == "BLOCKED")


if __name__ == "__main__":
    raise SystemExit(main())
