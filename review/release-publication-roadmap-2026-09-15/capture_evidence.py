"""Record local evidence consulted for a release and publication analysis."""
from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
REPAIR = REPO / 'review/de-scope-repair-pilot-2026-09-15'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    paths = [
        'GA_CRITERIA.md', 'release/GA_ACTIVATION.json',
        'src/bionexus/data/core-support.v1.json', 'src/bionexus/release_contract.py',
        'src/bionexus/de_external_study.py', 'src/bionexus/de_audit.py',
        'src/bionexus/claim_semantics.py', 'scripts/sync_version.py',
        '.github/workflows/release.yml',
        'review/rc8-challenge-rerun-2026-09-14/run_replay.py',
        'review/de-scope-repair-pilot-2026-09-15/build_local_evidence.py',
        'review/de-scope-repair-pilot-2026-09-15/verify_outputs.py',
        'review/de-scope-repair-pilot-2026-09-15/attempt-02/SUMMARY.json',
        'review/de-scope-repair-pilot-2026-09-15/external-pilot/attempt-03/README.zh-CN.md',
        'review/de-scope-repair-pilot-2026-09-15/external-pilot/attempt-03/PLAN_TEMPLATE.json',
        'review/de-scope-repair-pilot-2026-09-15/external-pilot/attempt-03/PILOT_STATUS.json',
    ]
    identity = json.loads((REPAIR / 'attempt-02/IDENTITY.json').read_text(encoding='utf-8'))
    current_hashes = {
        path.relative_to(REPO / 'src').as_posix(): digest(path)
        for path in sorted((REPO / 'src/bionexus').rglob('*'))
        if path.is_file() and '__pycache__' not in path.parts and path.suffix not in {'.pyc', '.pyo'}
    }
    current_tree = hashlib.sha256('\n'.join(f'{k} {current_hashes[k]}' for k in sorted(current_hashes)).encode()).hexdigest()
    gates = {}
    for version in ['1.0.0-rc.9', '1.0.0']:
        outcome = subprocess.run(
            ['python', 'scripts/check_release_contract.py', '--version', version],
            cwd=REPO, capture_output=True, text=True, check=False,
        )
        gates[version] = {'exit_code': outcome.returncode, 'result': json.loads(outcome.stdout)}
    with (HERE / '阶段验收清单.csv').open(encoding='utf-8', newline='') as handle:
        rows = list(csv.DictReader(handle))
    data = {
        'created_utc': datetime.now(timezone.utc).isoformat(),
        'type': 'READ_ONLY_ROUTE_ANALYSIS_NOT_RELEASE_OR_EXTERNAL_VALIDATION',
        'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip(),
        'current_source_tree_sha256': current_tree,
        'matches_prior_repair_snapshot': current_tree == identity['source_tree_sha256'],
        'files': {relative: digest(REPO / relative) for relative in paths},
        'hypothetical_version_scope_checks': gates,
        'action_rows': len(rows),
        'unique_action_ids': len({row['编号'] for row in rows}) == len(rows),
        'report_sha256': digest(HERE / '路线分析.zh-CN.md'),
        'checklist_sha256': digest(HERE / '阶段验收清单.csv'),
        'remote_checks_observed_this_turn': {
            'method': 'GitHub API through gh; summarized from observed responses',
            'latest_github_prerelease': 'v1.0.0-rc.7',
            'published_at': '2026-09-12T14:30:56Z',
            'head_check_run_records': 83,
            'latest_per_name_count': 29,
            'latest_per_name_all_success': True,
            'pypi_latest': 'NOT_CHECKED',
        },
        'scope': 'Evidence identification and planning; no new product performance study executed',
    }
    with (HERE / 'EVIDENCE_AND_QA.json').open('x', encoding='utf-8') as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write('\n')
    print(json.dumps({
        'source_matches': data['matches_prior_repair_snapshot'],
        'action_rows': len(rows),
        'checks': {key: value['result']['status'] for key, value in gates.items()},
    }, ensure_ascii=False))


if __name__ == '__main__':
    main()
