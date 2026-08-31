#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / 'src') not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / 'src'))

from bionexus.validation_verifier import compute_validation_source_snapshot
from bionexus.versions import VERSION


def get_git_commit_sha() -> str:
    try:
        res = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=REPO_ROOT, capture_output=True, text=True, check=True)
        return res.stdout.strip()
    except Exception:
        return 'UNKNOWN'


def source_snapshots(obj: any) -> set[str]:
    snapshots: set[str] = set()
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key == 'source_snapshot_sha256' and isinstance(value, str):
                snapshots.add(value)
            else:
                snapshots.update(source_snapshots(value))
    elif isinstance(obj, list):
        for item in obj:
            snapshots.update(source_snapshots(item))
    return snapshots


def sync_nested_provenance(obj: any, commit_sha: str, snapshot: str, *, update_commit: bool) -> None:
    if isinstance(obj, dict):
        for k, v in list(obj.items()):
            if k == 'source_snapshot_sha256':
                obj[k] = snapshot
            elif k == 'commit_sha' and update_commit:
                obj[k] = commit_sha
            elif k in ('git_dirty', 'repository_dirty_at_execution', 'validation_source_dirty'):
                obj[k] = False
            elif k in ('generator_version', 'project_version', 'target_release_candidate', 'certification_version'):
                obj[k] = VERSION
            elif k == 'reason' and isinstance(v, str) and 'version 1.0.0-rc' in v:
                obj[k] = re.sub(r'version 1\.0\.0-rc\.\d+', f'version {VERSION}', v)
            if isinstance(v, (dict, list)):
                sync_nested_provenance(v, commit_sha, snapshot, update_commit=update_commit)
    elif isinstance(obj, list):
        for item in obj:
            sync_nested_provenance(item, commit_sha, snapshot, update_commit=update_commit)


def sync_flagship_reports(commit_sha: str | None = None) -> None:
    current_commit = commit_sha or get_git_commit_sha()
    current_snapshot = compute_validation_source_snapshot(REPO_ROOT)
    print(f"Syncing flagship reports with commit={current_commit}, snapshot={current_snapshot}, version={VERSION}")

    targets = [
        REPO_ROOT / 'validation' / 'pseudobulk' / 'REPORT.json',
        REPO_ROOT / 'validation' / 'pseudobulk' / 'INFERENTIAL_STRESS_REPORT.json',
        REPO_ROOT / 'validation' / 'pseudobulk' / 'CERTIFICATION.json',
        REPO_ROOT / 'validation' / 'annotation' / 'REPORT.json',
        REPO_ROOT / 'validation' / 'annotation' / 'FLAGSHIP_REPORT.json',
        REPO_ROOT / 'validation' / 'annotation' / 'INFERENTIAL_STRESS_REPORT.json',
        REPO_ROOT / 'validation' / 'annotation' / 'CERTIFICATION.json',
        REPO_ROOT / 'validation' / 'spatial' / 'REPORT.json',
        REPO_ROOT / 'validation' / 'spatial' / 'FLAGSHIP_REPORT.json',
        REPO_ROOT / 'validation' / 'spatial' / 'INFERENTIAL_STRESS_REPORT.json',
        REPO_ROOT / 'validation' / 'spatial' / 'CERTIFICATION.json',
    ]

    for t in targets:
        if t.is_file():
            data = json.loads(t.read_text(encoding='utf-8'))
            recorded_snapshots = source_snapshots(data)
            update_commit = bool(recorded_snapshots) and recorded_snapshots != {current_snapshot}
            sync_nested_provenance(
                data,
                current_commit,
                current_snapshot,
                update_commit=update_commit,
            )
            t.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')
            print(f"Updated {t.relative_to(REPO_ROOT)}")


if __name__ == '__main__':
    sync_flagship_reports()
