import json,hashlib,shutil,sys,time
from pathlib import Path
from datetime import datetime,timezone
R=Path(r'C:\Plugin\BioNexus\review\spatialwarrant-run-01');W=Path(__file__).parent
A=R/'10_bionexus_audit/S7-run-01';F=R/'11_figures/S7-run-01';S=R/'12_submission/S7-run-01'
def utc():return datetime.now(timezone.utc).isoformat()
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
 return h.hexdigest()
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def dump(p,v):
 if shutil.disk_usage('C:\\').free<20*1024**3:raise RuntimeError('STOP_DISK')
 Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
for d in [A,F,S]:
 if (d/'SHA256SUMS.txt').exists() or (d/'output-manifest.json').exists():raise RuntimeError('Seal already exists; preserve it')
shutil.copy2(__file__,A/Path(__file__).name)
request={'challenge':'SpatialWarrant S7 completed-artifact audit; locked plan SHA-256 854e2d06eb25903a870606934964fd8b7f0a40a16a9658ef565cf5ab14a03c82; integration receipt only, not scientific acceptance','host_name':'codex-desktop-local','host_version':'not_exposed','human_approved':True,'model':'not_exposed','session_id':'01a0701e-b1cf-70c1-b22e-d940e66d5a98'}
if (W/'s7_host_probe_raw.json').exists():shutil.copy2(W/'s7_host_probe_raw.json',A/'bionexus-raw-responses/S7-host-probe.json')
else:dump(A/'bionexus-raw-responses/S7-host-probe.json',{'tool':'mcp__bionexus_local_mcp__bionexus_host_probe','request':request,'status':'CLIENT_WAIT_TERMINATED_WITHOUT_TOOL_RETURN','tool_response':None,'receipt_obtained':False,'recorded_at_utc':utc(),'execution_cell':'148','actual_stop_tool_return':{'result':'Script terminated','wall_time_seconds':0.0},'interpretation':'Real request issued in this S7 turn; no raw tool return or receipt observed before stopping the outstanding client wait. This is not a fabricated server failure response or proof that the server did not run. human_approved denotes user-authorized integration logging, not Human Scientific Adjudication.'})
result=read(A/'S7-result.json');result['host_probe_observation']=read(A/'bionexus-raw-responses/S7-host-probe.json')['status'];result['review_completed_at_utc']=utc();result['figure_visual_review']='PASS after correcting two presentation text overlaps; no changed source values';dump(A/'S7-result.json',result)
for cp in [A/'S7-checkpoint.md',R/'S7-checkpoint.md']:
 text=cp.read_text(encoding='utf8')
 text+='\nS7 finalization: stricter PubMed source-context audit returned INCOMPLETE (publication_status/study_design absent). An extra real MCP host-probe request produced no return before the client wait was terminated; this is recorded without inventing a server response. All four images visually reviewed; each optional thread post fits 280 characters including numbering.\n'
 cp.write_text(text,encoding='utf8')
required=['claim-ledger.json','claim-ledger.jsonld','claim-evidence-ledger.csv','evidence-card.md','debt-graph.md','adversarial-review.md','overclaim-tests.json','provenance-and-dependency-map.json','human-scientific-adjudication.template.md','S7-result.json','S7-checkpoint.md']
assert all((A/n).is_file() for n in required)
ledger=read(A/'claim-ledger.json');assert len(ledger['claims'])==8
assert all(x['human_decision']=='PENDING' for x in ledger['claims'])
assert all(sha(p['path'])==p['sha256'] for x in ledger['claims'] for p in x['artifacts'])
assert all(x['within_280'] for x in read(S/'draft-character-counts.json')['thread'])
assert sha(R/'00_plan/analysis-plan.lock.md')==ledger['locked_plan_sha256']
for d in [A,F,S]:
 for p in d.rglob('*.json'):read(p)
env=read(A/'execution-environment.json')
prebytes=sum(p.stat().st_size for d in [A,F,S] for p in d.rglob('*') if p.is_file())
dump(A/'final-package-validation.json',{'status':'PASS','at_utc':utc(),'claim_count':8,'four_selected_PNGs':len(list(F.glob('0*.png'))),'four_selected_PDFs':len(list(F.glob('0*.pdf'))),'human_decision':'PENDING','locked_plan_unchanged':True,'claim_evidence_hashes_match':True,'all_JSON_readable':True,'all_short_thread_posts_within_280':True,'visual_review':'four figures inspected; two layout overlaps corrected','S7_payload_bytes_before_final_manifests':prebytes,'S7_build_elapsed_seconds':env['elapsed_seconds'],'S7_build_peak_process_working_set_bytes':env['peak_process_working_set_bytes'],'S7_build_start_free_C_bytes':env['start_free_C_bytes'],'free_C_bytes_at_seal':shutil.disk_usage('C:\\').free,'note':'Build resource figures exclude external tool waiting, initial inspection, and later rendering/sealing; no unmeasured full-session peak or runtime asserted.'})
dump(A/'root-checkpoint-reference.json',{'path':str(R/'S7-checkpoint.md'),'sha256':sha(R/'S7-checkpoint.md')})
reports=[]
for d in [A,F,S]:
 files=sorted(p for p in d.rglob('*') if p.is_file())
 manifest={'schema':'SpatialWarrant.S7.output-manifest.v1','root':str(d),'created_at_utc':utc(),'files':[{'path':str(p.relative_to(d)).replace('\\','/'),'bytes':p.stat().st_size,'sha256':sha(p)} for p in files],'self_hash_policy':'Manifest excludes itself and SHA256SUMS.txt. SHA256SUMS includes the manifest and every other payload; it excludes itself.'}
 dump(d/'output-manifest.json',manifest)
 files.append(d/'output-manifest.json')
 (d/'SHA256SUMS.txt').write_text(''.join(f'{sha(p)}  {str(p.relative_to(d)).replace(chr(92),"/")}\n' for p in sorted(files)),encoding='utf8')
 bad=[]
 for line in (d/'SHA256SUMS.txt').read_text(encoding='utf8').splitlines():
  h,rel=line.split('  ',1)
  if sha(d/rel)!=h:bad.append(rel)
 reports.append({'directory':str(d),'files_in_SHA256SUMS':len(files),'mismatches':bad,'total_bytes':sum(p.stat().st_size for p in d.rglob('*') if p.is_file()),'SHA256SUMS_sha256':sha(d/'SHA256SUMS.txt')})
assert all(not x['mismatches'] for x in reports)
final={'status':result['status'],'sealed_at_utc':utc(),'manifests':reports,'total_S7_bytes':sum(x['total_bytes'] for x in reports),'C_free_bytes':shutil.disk_usage('C:\\').free,'human_adjudication_ledger_sha256':sha(A/'claim-ledger.json')}
(W/'s7_seal_verification.json').write_text(json.dumps(final,indent=2),encoding='utf8')
print(json.dumps(final,indent=2))
