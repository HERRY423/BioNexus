"""Frozen PVL cases through the actual public helper import, not its AST."""
import json
from pathlib import Path

import pytest

from bionexus.nextflow_bridge import parse_samplesheet

CASES = json.loads((Path(__file__).resolve().parents[1]/'pvl_samplesheet_retest/protocol.json').read_text(encoding='utf-8'))['cases']


@pytest.mark.parametrize('case', CASES, ids=[c['id'] for c in CASES])
def test_independent_donor_counts_and_unresolved_identity(case, tmp_path):
    path = tmp_path/'samples.csv'
    path.write_text(case['table'], encoding='utf-8')
    _, facts = parse_samplesheet(path)
    for key, expected in case['expected'].items():
        assert facts[key] == expected
    assert facts['replicate_identity_status'] == ('UNRESOLVED' if 'missing' in case['id'] or 'partial' in case['id'] else 'DECLARED_COMPLETE')
