"""Read-only verification of project evidence quoted in the publication plan."""
from pathlib import Path
import collections
import hashlib
import json
import subprocess
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
REPLAY = ROOT / 'review/rc8-challenge-rerun-2026-09-14'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))

paths = [
    'README.md', 'pyproject.toml', 'GA_CRITERIA.md',
    'src/bionexus/data/core-support.v1.json', 'src/bionexus/de_audit.py',
    'src/bionexus/claim_semantics.py', 'src/bionexus/de_external_study.py',
    'src/bionexus/pilot_costs.py', 'validation/ivn/REGISTRY.json',
    'docs/validation-history.md', 'docs/external-gain-and-correctable-governance.zh-CN.md',
    'review/methods-experiments-2026-09-08/REPORT.zh-CN.md',
    'review/methods-experiments-2026-09-08/run-01/real-null/summary.json',
    'review/methods-experiments-2026-09-08/run-01/paired/summary.json',
    'review/rc8-challenge-rerun-2026-09-14/PROTOCOL.md',
    'review/rc8-challenge-rerun-2026-09-14/IDENTITY.json',
    'review/rc8-challenge-rerun-2026-09-14/run-01/summary.json',
    'review/rc8-challenge-rerun-2026-09-14/run-01/execution-end.json',
    'review/external-gain-governance-2026-09-10/run-01/synthetic-summary.json',
    'manuscript/biorxiv_submission_2026-08-22/BioNexus_bioRxiv_manuscript.md',
]
identity = read(REPLAY / 'IDENTITY.json')
registry = read(ROOT / 'validation/ivn/REGISTRY.json')
counts = collections.Counter()
case_records = []
for case_dir in sorted((REPLAY / 'run-01/cases').iterdir()):
    if not case_dir.is_dir():
        continue
    case = read(case_dir / 'case.json')
    result = read(case_dir / 'bionexus_full.json')
    category = 'invalid' if case['invalid'] else 'developer_labeled_valid'
    counts[category + '_total'] += 1
    counts[category + '_accepted'] += result['overall_status'] == 'ROBUST_PASS'
    original = ROOT / 'review/methods-experiments-2026-09-08/run-01/challenge/cases' / case_dir.name / 'case.json'
    case_records.append({'case_id': case['case_id'], 'label': category,
                         'status': result['overall_status'], 'output_sha256': sha(case_dir / 'bionexus_full.json'),
                         'case_metadata_matches_original': sha(original) == sha(case_dir / 'case.json')})
checks = {
    '54_case_outputs_present': len(case_records) == 54,
    '42_invalid_and_12_developer_labeled_valid': counts['invalid_total'] == 42 and counts['developer_labeled_valid_total'] == 12,
    'no_invalid_or_valid_acceptances': counts['invalid_accepted'] == 0 and counts['developer_labeled_valid_accepted'] == 0,
    'case_metadata_bytes_preserved': all(c['case_metadata_matches_original'] for c in case_records),
    'replay_protocol_hash_matches': sha(REPLAY / 'PROTOCOL.md') == identity['protocol_sha256'],
    'replay_runner_hash_matches': sha(REPLAY / 'run_replay.py') == identity['runner_sha256'],
    'replay_snapshot_hashes_match': all(sha(REPLAY / 'rc8-source' / Path(p).relative_to('src')) == h for p, h in identity['source_hashes'].items()),
}
snapshot = {
    'checked_at_utc': datetime.now(timezone.utc).isoformat(),
    'workspace_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
    'replay_engine_commit': identity['engine_commit'],
    'scope': 'Artifact consistency and source reading; no new biological execution, external review, or full software test run.',
    'checks': checks, 'case_counts': dict(counts),
    'ivn_counts': {k: len(registry[k]) for k in ('datasets', 'lab_studies', 'reviews', 'calibration_freezes')},
    'quoted_files': [{'path': p, 'sha256': sha(ROOT / p)} for p in paths],
    'case_records': case_records,
}
(HERE / 'PROJECT_EVIDENCE.json').write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'checks': checks, 'case_counts': dict(counts), 'ivn_counts': snapshot['ivn_counts']}, ensure_ascii=False, indent=2))
if not all(checks.values()):
    raise SystemExit(1)
