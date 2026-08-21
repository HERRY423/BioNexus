#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / 'src'
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from bionexus.cryptographic_verifier import verify_study_provenance


def main() -> int:
    parser = argparse.ArgumentParser(description='Verify study provenance')
    parser.add_argument('study_dir', type=Path, help='Path to study directory')
    parser.add_argument('--report-out', type=Path, help='Optional output path')
    args = parser.parse_args()

    report = verify_study_provenance(args.study_dir)
    report_dict = report.to_dict()

    if args.report_out:
        args.report_out.write_text(json.dumps(report_dict, indent=2) + chr(10), encoding='utf-8')

    print(json.dumps(report_dict, indent=2))
    return 0 if report.status == 'PASS_VERIFIED' else 2


if __name__ == '__main__':
    raise SystemExit(main())
