"""Frozen PVL component retest; standard library only; no model/network calls."""
import argparse
import ast
import csv
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple, Union


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, help='Exact before/after source file')
    parser.add_argument('--output', required=True, help='New output directory')
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    protocol = json.loads((root/'protocol.json').read_text(encoding='utf-8'))
    manifest = json.loads((root/'manifest.json').read_text(encoding='utf-8'))
    assert digest((root/'protocol.json').read_bytes()) == manifest['protocol_sha256'], 'Protocol changed'
    source = Path(args.source).resolve()
    code = source.read_bytes()
    assert digest(code.replace(b'\r\n', b'\n')) in manifest['normalized_source_sha256'].values(), 'Unfrozen source revision'
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    rows = []
    for case in protocol['cases']:
        directory = output/case['id']
        directory.mkdir()
        started = time.perf_counter()
        if protocol['component'] == 'ngs':
            quant = directory/'quant.sf'
            quant.write_text(case['table'], encoding='utf-8')
            config = {'rnaseq_salmon_samples': {'S1': {'layout':'SE', 'strandedness':'unstranded',
                'row_indices':[0], 'r1':['synthetic.fastq'], 'r2':[]}}, 'references':{}}
            (directory/'config.json').write_text(json.dumps(config), encoding='utf-8')
            p = subprocess.run([sys.executable, '-I', str(source), '--config', str(directory/'config.json'),
                '--outdir', str(directory/'matrices'), '--quant', 'S1='+str(quant)],
                stdin=subprocess.DEVNULL, capture_output=True, timeout=30)
            (directory/'stdout.txt').write_bytes(p.stdout)
            (directory/'stderr.txt').write_bytes(p.stderr)
            matrix = directory/'matrices/num_reads.tsv'
            actual = None
            if matrix.is_file():
                with matrix.open(encoding='utf-8', newline='') as stream:
                    actual = {r['transcript_id']:float(r['S1']) for r in csv.DictReader(stream, delimiter='\t')}
            observed = {'rejected_before_matrix':p.returncode != 0 and not matrix.exists(),
                        'valid_matrix':p.returncode == 0 and actual == case.get('expected_matrix')}
        else:
            sheet = directory/'samples.csv'
            sheet.write_text(case['table'], encoding='utf-8')
            tree = ast.parse(code.decode('utf-8-sig'))
            node = next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='parse_samplesheet')
            scope = {'csv':csv, 'Path':Path, 'Any':Any, 'Dict':Dict, 'List':List, 'Set':Set, 'Tuple':Tuple, 'Union':Union}
            exec(compile(ast.Module(body=[node],type_ignores=[]),str(source),'exec'),scope)
            _, observed = scope['parse_samplesheet'](sheet)
        passed = all(observed.get(k)==v for k,v in case['expected'].items())
        rows.append({'id':case['id'], 'passed':passed, 'observed':observed, 'expected':case['expected'],
                     'seconds':time.perf_counter()-started, 'input_sha256':digest(case['table'].encode())})
    report = {'format':'pvl-upstream-retest-1', 'component':protocol['component'],
              'source_sha256':digest(code), 'protocol_sha256':manifest['protocol_sha256'],
              'passed':sum(r['passed'] for r in rows), 'total':len(rows), 'cases':rows,
              'scope':protocol['scope'], 'model_calls':0, 'maintainer_adoption':None, 'human_minutes':None}
    (output/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2))
    return 0 if report['passed']==report['total'] else 1

if __name__=='__main__':
    raise SystemExit(main())
