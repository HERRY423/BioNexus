"""Execute the explicitly approved demo unchanged, capturing local host evidence."""
from pathlib import Path
import subprocess, sys, json, hashlib, platform, shutil
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[3]
DEMO = ROOT / 'review/workbench-ifnb-demo'
def now(): return datetime.now(timezone.utc).isoformat()
def digest(p):
    with p.open('rb') as f: return hashlib.file_digest(f, 'sha256').hexdigest()
def save(p, obj): p.write_text(json.dumps(obj, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')

for i in range(1, 1000):
    out = DEMO / f'workbench-run-{i:02d}'
    records = DEMO / f'workbench-run-{i:02d}-records'
    if not out.exists() and not records.exists(): break
else: raise RuntimeError('No unused output number')
records.mkdir(exist_ok=False)
save(DEMO/'preflight-2026-09-04/approved-run-location.json', {'output':str(out), 'records':str(records)})
save(records/'authorization.json', {'recorded_at':now(), 'source':'explicit user approval in current Codex task', 'scope':'six-step exploratory analysis, literature verification, BioNexus audit, display materials and unpublished English draft', 'biological_claim_acceptance':False, 'publication_authorized':False})
commands=[]
def run(label, argv):
    item={'label':label,'argv':argv,'cwd':str(ROOT),'started_at':now()}
    print('START',label,flush=True)
    with (records/(label+'.stdout.log')).open('wb') as stdout, (records/(label+'.stderr.log')).open('wb') as stderr:
        p=subprocess.run(argv,cwd=ROOT,stdout=stdout,stderr=stderr)
    item.update(finished_at=now(),exit_code=p.returncode)
    commands.append(item); save(records/'commands.json',commands)
    print('FINISH',label,'exit',p.returncode,flush=True)
    if p.returncode: raise RuntimeError(f'{label} failed; retained logs in {records}')

save(records/'environment.json', {'captured_at':now(),'host':'Codex desktop local task','host_version':None,'session_id':None,'python_executable':sys.executable,'python_version':sys.version,'platform':platform.platform(),'working_directory':str(ROOT),'execution_kind':'local Python subprocess, not an NGS registered workflow'})
run('python-packages',[sys.executable,'-m','pip','list','--format=json'])
run('git-head',['git','rev-parse','HEAD'])
run('git-status',['git','status','--short'])
snapshot=records/'source-snapshot'; snapshot.mkdir()
source_files=[DEMO/'run_analysis.py',DEMO/'fetch_inputs.py',Path(__file__)] + list((ROOT/'src/bionexus').rglob('*.py'))
hashes={}
for p in source_files:
    rel=p.relative_to(ROOT); target=snapshot/rel; target.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(p,target); hashes[str(rel)]=digest(target)
save(records/'source-sha256.json',hashes)
run('doctor',[sys.executable,'scripts/doctor.py'])
run('fetch-inputs',[sys.executable,'review/workbench-ifnb-demo/fetch_inputs.py'])
inputs=[ROOT/'data/flagship/kang2018_pbmc_ifnb/GSE96583_RAW.tar',ROOT/'data/flagship/kang2018_pbmc_ifnb/GSE96583_batch2.total.tsne.df.tsv.gz',DEMO/'GSE96583_batch2.genes.tsv.gz']
save(records/'input-sha256.json',{str(p.relative_to(ROOT)):digest(p) for p in inputs})
if out.exists(): raise FileExistsError(out)
run('analysis',[sys.executable,'-u','review/workbench-ifnb-demo/run_analysis.py','--out',str(out.relative_to(ROOT))])
save(records/'initial-output-sha256.json',{p.name:digest(p) for p in out.iterdir() if p.is_file()})
save(records/'completion.json',{'completed_at':now(),'analysis_exit_code':0,'output':str(out),'records':str(records),'human_scientific_acceptance':'PENDING','publication_status':'NOT_PUBLISHED'})
print('OUTPUT',out,flush=True)
print('RECORDS',records,flush=True)
