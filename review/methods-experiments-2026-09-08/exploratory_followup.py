"""Post-outcome mechanism ablation; preserves original frozen product and results."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd

import run_experiments as experiment

HERE = Path(__file__).resolve().parent


def run():
    experiment.verify_freeze()
    from bionexus.de_audit import DEAuditEngine, FindingSeverity

    class HeuristicAdvisoryEngine(DEAuditEngine):
        def _audit_de_table(self, de_df, findings, pi_decisions, checks, claim_text=None):
            super()._audit_de_table(de_df, findings, pi_decisions, checks, claim_text=claim_text)
            for finding in findings:
                if finding.rule_id == 'BFA-001c':
                    finding.severity = FindingSeverity.ADVISORY

    out = HERE / 'exploratory-01'
    out.mkdir(exist_ok=False)
    experiment.write_json(out / 'FREEZE.json', {'started_utc': datetime.now(timezone.utc).isoformat(),
                                              'parent_freeze_sha256': experiment.digest(HERE / 'FREEZE.json'),
                                              'amendment_sha256': experiment.digest(HERE / 'EXPLORATORY_AMENDMENT.md'),
                                              'runner_sha256': experiment.digest(__file__),
                                              'status': 'EXPLORATORY_AFTER_PRIMARY_OUTCOMES'})
    try:
        rows, localization = [], []
        for folder in sorted((HERE / 'run-01/challenge/cases').iterdir()):
            definition = json.loads((folder / 'case.json').read_text(encoding='utf-8'))
            receipt = json.loads((folder / 'receipt.json').read_text(encoding='utf-8'))
            original = json.loads((folder / 'bionexus_full.json').read_text(encoding='utf-8'))
            checks = {x['check_id']: x for x in original['checks']}
            localization.append({'case_id': folder.name, 'family': definition['family'], 'invalid': definition['invalid'],
                                 'original_binding_status': checks['analysis_execution_binding']['status'],
                                 'original_claim_status': checks['claim_targeted_warrant']['status'],
                                 'original_rules': '|'.join(x['rule_id'] for x in original['findings'])})
            for arm in ['heuristic_advisory', 'heuristic_advisory_without_claim']:
                start = time.perf_counter()
                result = HeuristicAdvisoryEngine().audit(
                    de_table=folder / 'de.csv', sample_metadata=folder / 'metadata.csv',
                    execution_record=receipt, donor_col='donor', condition_col='condition',
                    claim_text=definition['claim'] if arm == 'heuristic_advisory' else None)
                experiment.write_json(out / f'{folder.name}-{arm}.json', result.to_dict())
                rows.append({'case_id': folder.name, 'family': definition['family'], 'invalid': definition['invalid'],
                             'arm': arm, 'status': result.overall_status, 'accepted': result.passed,
                             'seconds': time.perf_counter() - start,
                             'remaining_high_rules': '|'.join(f.rule_id for f in result.findings if f.severity.value in {'BLOCKER', 'HIGH_IMPACT'})})
        frame = pd.DataFrame(rows)
        frame.to_csv(out / 'case-outcomes.csv', index=False)
        pd.DataFrame(localization).to_csv(out / 'original-check-localization.csv', index=False)
        summaries = []
        for arm, group in frame.groupby('arm'):
            bad, good = group[group.invalid], group[~group.invalid]
            summaries.append({'arm': arm, 'invalid_accepted': int(bad.accepted.sum()), 'invalid_total': len(bad),
                              'valid_retained': int(good.accepted.sum()), 'valid_total': len(good),
                              'unsupported_acceptance_rate': float(bad.accepted.mean()), 'valid_retention': float(good.accepted.mean())})
        experiment.write_json(out / 'summary.json', {'status': 'COMPLETE_EXPLORATORY', 'product_code_changed': False, 'arms': summaries})
        make_packet()
    except Exception as exc:
        experiment.write_json(out / 'FAILURE.json', {'status': 'FAILED', 'error': str(exc)})
        raise


def make_packet():
    packet = HERE / 'reviewer-packet'
    packet.mkdir(exist_ok=False)
    original = HERE / 'run-01/challenge/cases'
    folders = sorted(original.iterdir())
    rng = np.random.default_rng(418209)
    order = rng.permutation(len(folders))
    key, forms, assisted_forms = [], [], []
    (packet / 'cases').mkdir()
    (packet / 'common').mkdir()
    shutil.copyfile(HERE / 'run-01/paired/kang-counts.csv', packet / 'common/counts.csv')
    for number, i in enumerate(order, 1):
        folder = folders[int(i)]
        case_id = f'C{number:03}'
        definition = json.loads((folder / 'case.json').read_text(encoding='utf-8'))
        target = packet / 'cases' / case_id
        target.mkdir()
        for filename in ['de.csv', 'metadata.csv', 'design.csv', 'receipt.json']:
            shutil.copyfile(folder / filename, target / filename)
        experiment.write_json(target / 'claim.json', {'case_id': case_id, 'claim': definition['claim'],
                                                    'scope': 'Completed supplied analysis only; evaluate whether evidence supports the exact statement.'})
        key.append({'case_id': case_id, 'source_case': folder.name, 'family': definition['family'], 'provisional_invalid': definition['invalid']})
        forms.append({'case_id': case_id, 'reviewer_id': '', 'independent_of_project': '', 'rating': '',
                      'issue_type': '', 'evidence_location': '', 'rationale': '', 'review_minutes': '',
                      'status': 'PENDING'})
        assisted_forms.append({'case_id': case_id, 'analyst_id': '', 'arm': '', 'sequence_period': '',
                               'setup_minutes_allocated': '', 'review_minutes': '', 'repair_minutes': '',
                               'final_claim': '', 'would_use_again': '', 'status': 'PENDING'})
    pd.DataFrame(key).to_csv(HERE / 'reviewer-key-PRIVATE.csv', index=False)
    pd.DataFrame(forms).to_csv(packet / 'expert-ratings-BLANK.csv', index=False)
    pd.DataFrame(assisted_forms).to_csv(HERE / 'lab-time-records-BLANK.csv', index=False)
    manifest = {p.relative_to(packet).as_posix(): experiment.digest(p) for p in sorted(packet.rglob('*')) if p.is_file()}
    experiment.write_json(packet / 'MANIFEST.json', {'files': manifest, 'external_reviews_received': 0,
                                                  'notice': 'Do not distribute developer key, product outputs, or experimental results to blinded adjudicators.'})
    shutil.make_archive(str(HERE / 'reviewer-packet'), 'zip', packet)


if __name__ == '__main__':
    run()
