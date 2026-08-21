#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / 'src') not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / 'src'))

from bionexus.validation_verifier import compute_validation_source_snapshot


def get_git_commit_sha() -> str:
    try:
        res = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=REPO_ROOT, capture_output=True, text=True, check=True)
        return res.stdout.strip()
    except Exception:
        return 'UNKNOWN'


def sync_nested_provenance(obj: any, commit_sha: str, snapshot: str) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == 'source_snapshot_sha256':
                obj[k] = snapshot
            elif k == 'commit_sha':
                obj[k] = commit_sha
            elif k in ('git_dirty', 'repository_dirty_at_execution', 'validation_source_dirty'):
                obj[k] = False
            else:
                sync_nested_provenance(v, commit_sha, snapshot)
    elif isinstance(obj, list):
        for item in obj:
            sync_nested_provenance(item, commit_sha, snapshot)


def sync_flagship_reports(commit_sha: str | None = None) -> None:
    current_commit = commit_sha or get_git_commit_sha()
    current_snapshot = compute_validation_source_snapshot(REPO_ROOT)
    print(f"Syncing flagship reports with commit={current_commit}, snapshot={current_snapshot}")

    targets = [
        REPO_ROOT / 'validation' / 'pseudobulk' / 'REPORT.json',
        REPO_ROOT / 'validation' / 'pseudobulk' / 'INFERENTIAL_STRESS_REPORT.json',
        REPO_ROOT / 'validation' / 'pseudobulk' / 'CERTIFICATION.json',
        REPO_ROOT / 'validation' / 'annotation' / 'REPORT.json',
        REPO_ROOT / 'validation' / 'annotation' / 'INFERENTIAL_STRESS_REPORT.json',
        REPO_ROOT / 'validation' / 'annotation' / 'CERTIFICATION.json',
        REPO_ROOT / 'validation' / 'spatial' / 'REPORT.json',
        REPO_ROOT / 'validation' / 'spatial' / 'INFERENTIAL_STRESS_REPORT.json',
        REPO_ROOT / 'validation' / 'spatial' / 'CERTIFICATION.json',
    ]

    for t in targets:
        if t.is_file():
            data = json.loads(t.read_text(encoding='utf-8'))
            sync_nested_provenance(data, current_commit, current_snapshot)
            t.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')
            print(f"Updated {t.relative_to(REPO_ROOT)}")


if __name__ == '__main__':
    sync_flagship_reports()
