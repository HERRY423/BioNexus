import sys,json,hashlib,shutil,time,platform
from pathlib import Path
from datetime import datetime,timezone
import pandas as pd,numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
R=Path(r'C:\Plugin\BioNexus\review\spatialwarrant-run-01');W=Path(__file__).parent
A=R/'10_bionexus_audit/S7-run-01';F=R/'11_figures/S7-run-01';S=R/'12_submission/S7-run-01';PB=R/'08_pseudobulk/S6-run-01';LR=R/'09_liana_literature/S6-run-01'
def guard():
 if shutil.disk_usage('C:\\').free<20*1024**3:raise RuntimeError('20 GiB stop')
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
 return h.hexdigest()
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def dump(p,v):guard();Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
def txt(p,v):guard();Path(p).write_text(v,encoding='utf8')
def utc():return datetime.now(timezone.utc).isoformat()
guard();shutil.copy2(__file__,A/Path(__file__).name)
# Re-render two S7 unpublished presentation panels only. No scientific recalculation.
source=(W/'build_spatialwarrant_s7.py').read_text(encoding='utf8')
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':12,'axes.spines.top':False,'axes.spines.right':False,'savefig.facecolor':'#f5f7fa','figure.facecolor':'#f5f7fa'})
navy='#17324d';teal='#087f8c';red='#ad3e3e'
def save(fig,name):
 guard();fig.savefig(F/(name+'.png'),dpi=150,bbox_inches='tight');fig.savefig(F/(name+'.pdf'),bbox_inches='tight');plt.close(fig)
def card(ax,x,y,w,h,title,body,color=navy):
 ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle='round,pad=.012',facecolor='white',edgecolor='#d1dbe4'))
 ax.text(x+.025,y+h-.045,title,color=color,weight='bold',size=17,va='top')
 ax.text(x+.025,y+h-.12,body,color=navy,size=12.5,va='top',linespacing=1.55)
effect=pd.read_csv(PB/'primary-program-B1-B2-B3-sensitivity.csv').iloc[0];six=pd.read_csv(PB/'prespecified-six-genes.csv')
block=source[source.index('fig,axs=plt.subplots(2,2,figsize=(16,11))'):source.index("print('FIGURES_AND_LEDGER_WRITTEN'")]
block=block.replace('linespacing=1.6,color=navy)',"linespacing=1.6,color=navy,va='top')")
block=block.replace("ax.text(0,.28,'Prespecified", "ax.text(0,.24,'Prespecified")
block=block.replace('linespacing=1.6,color=red)',"linespacing=1.6,color=red,va='top')")
block=block.replace('linespacing=1.7,color=navy)',"linespacing=1.7,color=navy,va='top')")
exec(compile(block,'S7_presentation_layout_correction','exec'))
txt(F/'layout-review.md','# Layout review\n\nAll four figures visually inspected. The first draft had overlapping multiline text in LIANA and Evidence Debt panels; top-aligned text resolves those presentation defects. Source numerical values, labels and all S1–S6 artifacts unchanged. A second visual check precedes final seal.\n')
# Short thread numbering must fit the usual 280-character text limit.
thread=(S/'optional-short-thread.md').read_text(encoding='utf8').replace('including a real audit-parser failure','including an audit-parser failure')
parts=thread.strip().split('\n\n');counts=[];new=[]
for j,p in enumerate(parts):
 body=p.split('\n',1)[1];n=len(f'{j+1}/{len(parts)} '+body);counts.append({'index':j+1,'characters_with_numbering':n,'within_280':n<=280});new.append(f'{j+1}/{len(parts)} ({len(body)} characters before numbering)\n{body}')
assert all(x['within_280'] for x in counts)
txt(S/'optional-short-thread.md','\n\n'.join(new)+'\n');chars=read(S/'draft-character-counts.json');chars['thread']=counts;dump(S/'draft-character-counts.json',chars)
if (W/'s7_host_probe_raw.json').exists():shutil.copy2(W/'s7_host_probe_raw.json',A/'bionexus-raw-responses/S7-host-probe.json')
local=read(A/'bionexus-raw-responses/literature-coverage-audit.json')
txt(A/'source-context-audit-notes.md',f'''# Source-context review

S7 stricter audit of existing PubMed search returns: **{local['status']}**. Missing context: publication_status and study_design. Producer: DECLARED_NOT_AUTHENTICATED. accepted_for_claim_support=false. This raw return is not edited into a successful status.

S6's prior six VALID envelopes are preserved. They checked supplied metadata strings and internal hashes; a query date is not a database release, target names are not guaranteed returned record identifiers, and an esearch ID list is not a primary-paper support/contradiction review. S7 records these debts rather than silently rewriting S6 metadata or rerunning its queries. Supporting primary evidence, contradiction and unreported findings beyond the saved source contents remain NOT_ASSESSED, not absent.

The eight new analysis envelopes bind the host's completed S7 artifact reviews. Their VALID status certifies neither the underlying biology nor independent source identity: accepted_for_claim_support=false. These are local passive audits. MCP warrant responses are a separate real transport observation with NEEDS_DATA/ABSTAIN and a semantic classification defect. A host integration receipt, if returned, still would not authenticate outside scientific producers or validate a claim.
''')
plan=R/'00_plan/analysis-plan.lock.md';cp=[plan,R/'00_plan/plan.sha256',R/'00_plan/plugin-capability-check.json',R/'S1-checkpoint.md',R/'S2-S3-checkpoint.v3.md',R/'S4-S5-checkpoint.md',R/'S4-S5-checkpoint.postaudit.v1.md',R/'S6-checkpoint.md']
dump(A/'formal-checkpoint-index.json',{'S0':'Locked plan and capability record serve as S0; no separate S0 checkpoint invented','formal_S2':'03_scrna_reference/S2-run-01','formal_S3':'04_visium_qc/S3-run-03','formal_S4':'06_deconvolution/S4-run-02','formal_S5':'07_niches/S5-run-02','checkpoints':[{'path':str(p),'sha256':sha(p)} for p in cp],'claims_original':read(A/'technical-reverification.json')['claims']})
shutil.copy2(Path(read(A/'technical-reverification.json')['claims']['source']),A/'original-claims.readonly-copy.csv')
plantext=plan.read_text(encoding='utf-8-sig');import re
block=re.search(r'(claim_id,stage,claim_class,preregistered_statement[^\n]*\n.*?)(?:\n```|\Z)',plantext,re.S).group(1)
txt(A/'locked-plan-claim-appendix.extracted.csv',block+'\n')
dump(A/'plugin-use-evidence-index.json',{'roles':read(A/'technical-reverification.json')['plugin_roles'],'current_S7':'BioNexus real MCP calls and local passive shared-kernel audit; remaining plugin activity is preserved S0–S6 evidence, not new S7 calls','evidence':[{'path':str(p),'sha256':sha(p)} for p in [R/'00_plan/plugin-capability-check.json',LR/'external-query-log.final.csv',LR/'external-evidence-summary.final.json',LR/'bionexus-external-evidence-audit.json',A/'bionexus-mcp-raw-all-attempts.json']],'execution':'local Python/scverse; not registered NGS workflow run'})
# Lists make exact numerical and display sources auditable without duplicating large files.
figsources={'01':[R/'00_plan/plugin-capability-check.json',LR/'external-evidence-summary.final.json',PB/'primary-program-B1-B2-B3-sensitivity.csv'],'02':[R/'06_deconvolution/S4-run-02/proportions_tangram.csv.gz',R/'06_deconvolution/S4-run-02/proportions_marker_nnls.csv.gz',R/'07_niches/S5-run-02/niche_labels.csv.gz'],'03':[PB/'primary-program-B1-B2-B3-sensitivity.csv',PB/'prespecified-six-genes.csv',PB/'pathway-progeny-results.full.csv',LR/'liana-prespecified-interactions.csv',LR/'liana-top10-for-external-evidence.csv'],'04':[A/'claim-ledger.json',A/'evidence-debt.json',A/'overclaim-tests.json']}
for sec in pd.read_csv(R/'04_visium_qc/S3-run-03/section-summary.csv').section:
 figs=R/f'01_inputs/zenodo4739739/spatial-extracted/spatial/{sec}_spatial';figsources['02'] += [figs/'tissue_lowres_image.png',figs/'scalefactors_json.json',R/f'04_visium_qc/S3-run-03/{sec}/spot-QC-and-metadata.csv.gz']
figsources['02'] += [R/'04_visium_qc/S3-run-03/CID4535/geometry-boundary-core-masks.csv']
dump(F/'figure-source-index.json',{k:[{'path':str(p),'sha256':sha(p)} for p in v] for k,v in figsources.items()})
result=read(A/'S7-result.json');result['literature_context_passive_audit']=local;result['formal_checkpoint_index']='formal-checkpoint-index.json';dump(A/'S7-result.json',result)
print('READY_FOR_FINAL_VISUAL_CHECK_AND_SEAL')
