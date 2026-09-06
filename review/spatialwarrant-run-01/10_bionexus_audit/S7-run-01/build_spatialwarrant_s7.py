from __future__ import annotations
import os,sys,json,csv,hashlib,shutil,time,platform,subprocess,re,textwrap
from pathlib import Path
from datetime import datetime,timezone
import numpy as np,pandas as pd,psutil
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
R=Path(r'C:\Plugin\BioNexus\review\spatialwarrant-run-01'); W=Path(__file__).parent
A=R/'10_bionexus_audit/S7-run-01'; F=R/'11_figures/S7-run-01'; S=R/'12_submission/S7-run-01'
S2=R/'03_scrna_reference/S2-run-01'; S3=R/'04_visium_qc/S3-run-03'; S4=R/'06_deconvolution/S4-run-02'; S5=R/'07_niches/S5-run-02'; PB=R/'08_pseudobulk/S6-run-01'; LR=R/'09_liana_literature/S6-run-01'
start=time.perf_counter(); startfree=shutil.disk_usage('C:\\').free
def guard():
 if shutil.disk_usage('C:\\').free<20*1024**3: raise RuntimeError('STOP: C free space below 20 GiB')
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(8*1024*1024),b''): h.update(b)
 return h.hexdigest()
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def dump(p,v):
 guard(); Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def txt(p,v):guard();Path(p).write_text(v,encoding='utf-8')
def utc():return datetime.now(timezone.utc).isoformat()
def canon(v):return hashlib.sha256(json.dumps(v,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()
guard()
assert sha(R/'00_plan/analysis-plan.lock.md')=='854e2d06eb25903a870606934964fd8b7f0a40a16a9658ef565cf5ab14a03c82','plan hash mismatch'
inspection=read(W/'s7_inspection.json')
assert all(not v['mismatches'] for v in inspection['manifests'].values())
assert all(x['matches'] for x in inspection['input_verifications'])
assert inspection['claims']['semantic_equal']
if '--resume-render' not in sys.argv:
 for d in [A,F,S]:
  if d.exists():raise RuntimeError('S7 output conflict: '+str(d))
 for d in [A,F,S]:d.mkdir(parents=True)
else:
 assert (A/'build-session.json').exists(),'No matching S7 build session'
dump(A/'build-session.json',{'status':'BUILDING','scope':'S7 only; read existing results and render; no S1-S6 computation','started_at_utc':utc(),'start_free_C_bytes':startfree,'plan_sha256':sha(R/'00_plan/analysis-plan.lock.md')})
shutil.copy2(__file__,A/'build_spatialwarrant_s7.py')
shutil.copy2(W/'s7_inspect.py',A/'s7_inspect.py')
shutil.copy2(W/'s7_inspection.json',A/'technical-reverification.json')
shutil.copy2(W/'s7_bionexus_mcp_raw.json',A/'bionexus-mcp-raw-all-attempts.json')
rawdir=A/'bionexus-raw-responses';rawdir.mkdir(exist_ok=True)
raw=read(W/'s7_bionexus_mcp_raw.json')
tests=[]
for attempt_group,rows in raw.items():
 for row in rows:
  dump(rawdir/f'{row["test_id"]}-{attempt_group}.json',row)
  if attempt_group=='corrected_purpose_attempts':
   returned=json.loads(row['raw_response']['structuredContent']['result'])
   ce=returned.get('claim_warrant_evaluation',{})
   tests.append({'test_id':row['test_id'],'exact_claim':row['request']['query'],'request':row['request'],'actual_top_status':returned['status'],'actual_claim_layer':ce,'matched_capability_id':returned.get('matched_capability_id'),'raw_file':str(rawdir/f'{row["test_id"]}-{attempt_group}.json'),'started_at_utc':row['started_at_utc'],'ended_at_utc':row['ended_at_utc'],'scientific_interpretation':'NOT A SUCCESSFUL SEMANTIC REJECTION: intended population/causal/clinical/technical class resolved as descriptive; no granted warrant.'})
dump(A/'overclaim-tests.json',{'tests':tests,'initial_failures_preserved':4,'corrected_calls':4,'status':'AUDIT_DEFECT_OBSERVED','governing_status':'NEEDS_DATA; claim layer ABSTAIN','authentication':'MCP response transport observed; no authenticated producer receipt obtained','not_a_biological_validation':True})
sys.path.insert(0,r'C:\Plugin\BioNexus\src')
from bionexus.ecosystem_intake import ExternalCapabilityFamily, ExternalEvidenceEnvelope, ExternalProducerIdentity,audit_external_evidence
from bionexus.provenance import sidecar
doctorcmd=[sys.executable,'-X','utf8',r'C:\Plugin\BioNexus\scripts\doctor.py']
try:
 dr=subprocess.run(doctorcmd,cwd=A,capture_output=True,text=True,encoding='utf8',errors='replace',timeout=60)
 dump(rawdir/'doctor.json',{'command':doctorcmd,'returncode':dr.returncode,'stdout':dr.stdout,'stderr':dr.stderr,'at_utc':utc()})
except Exception as e:dump(rawdir/'doctor.json',{'command':doctorcmd,'error':repr(e),'at_utc':utc()})
claims=inspection['claims']['rows']
ev={
 'C1':[S3/'section-summary.csv',S3/'CID4535/domain-pathology-metrics.json',S3/'CID4535/geometry-boundary-rule.json',S3/'CID4535/geometry-boundary-core-masks.csv'],
 'C2':[S4/'postcompletion-audit.v1.json',S4/'tangram-nnls-concordance.csv',S4/'ingest-label-agreement.csv',S4/'tangram-parameter-sensitivity.csv'],
 'C3':[S5/'four-component-coenrichment-assessment.v1.json',S5/'selected-k.json',S5/'boundary-niche-enrichment.csv',S5/'niche-distribution-by-section.csv',S5/'10x-transfer-result.json'],
 'C4':[PB/'primary-program-B1-B2-B3-sensitivity.csv',PB/'primary-program-gene-coverage.json',PB/'prespecified-six-genes.csv',PB/'pseudobulk-design-status.csv',PB/'raw-count-source-correction.v2.json'],
 'C5':[LR/'liana-method-and-resource.json',LR/'liana-prespecified-interactions.csv',LR/'boundary-celltype-specific-liana-status.json',LR/'liana-spatial-niche-context.csv',LR/'external-query-log.final.csv'],
 'C6':[R/'00_plan/analysis-plan.lock.md',R/'S6-checkpoint.md'],
 'T1':[R/'00_plan/analysis-plan.lock.md',PB/'primary-program-B1-B2-B3-sensitivity.csv',R/'02_identity/scRNA-identity-resolution.v1.json'],
 'T2':[A/'technical-reverification.json',R/'00_plan/analysis-plan.lock.md',PB/'SHA256SUMS.txt',LR/'SHA256SUMS.txt']}
# Exact existing filenames are resolved from the explicit formal stage only.
ev['C3']=[p for p in ev['C3'] if p.exists()]+[S5/'S5-result.json']
details={
 'C1':('STUDY_BOUND_DESCRIPTIVE','Six sections: ARI 0.00173–0.49012, NMI 0.01967–0.53850; fixed numeric resolution 0.5. CID4535 boundary Dice 0.29712, Jaccard 0.17448.','Agreement varies widely; same-study producer pathology is not independent ground truth; only one separable boundary qualifies.','Per-section descriptive spatial/domain comparison; no universal accuracy claim.',['Wu study','S3 producer labels and coordinates'],'Independent pathology adjudication and external sections'),
 'C2':('METHOD_SENSITIVE','54 Tangram parameter runs completed; Tangram–NNLS dominant agreement 4.788%; ingest–Tangram dominant-label agreement 5.166%; NNLS unknown 0.','Cross-method agreement is very low. Requested 1000/2000 gene runs both use capped 644–655 genes; 500-gene sensitivity has lower agreement.','Shared-reference method sensitivity, with ingest as transferred similarity labels only; no calibrated proportions.',['Wu scRNA','S2 reference','S3 spots','S4'],'Independent reference and orthogonal composition validation; full 2000-gene perturbation absent'),
 'C3':('TARGET_NICHE_NOT_OBSERVED','k=10 selected before boundary comparison from 15 KMeans combinations; six-section spatial niches and technical transfer to 3798 10x spots completed.','No niche meets all four component relative-enrichment conditions. Five boundary comparisons unavailable. This does not establish absence of a biological niche.','Observed technical niches and CID4535 niche distributions only; no asserted four-component boundary niche.',['S4 main Tangram','S3 frozen geometry','S5 scaler and centers'],'Independent spatial validation; composition uncertainty; one eligible boundary'),
 'C4':('SINGLE_SECTION_DESCRIPTIVE','Frozen IFN program matches 196/200; B2−core +0.051510938742152845, B1 +0.03490665160847417, B3 +0.02216377668145686.','Small effect, one eligible section; CXCL11 −0.15958494 and STAT1 −0.00413840 do not follow uniform enhancement. No replication for inference.','Preregistered CID4535 descriptive endpoint; no population CI, p value, sign test or leave-one-section-out inference.',['Wu CID4535 raw counts','S3 frozen geometry','frozen Hallmark 2024.1'],'Additional verified independent boundary-eligible sections; inferential DE not run'),
 'C5':('CAUSAL_CLAIM_NOT_ESTABLISHED','LIANA reference-wide rank_aggregate and prespecified CXCL9/10–CXCR3 records available; spatial composition/niche context is descriptive.','Reference expression cannot identify boundary cell-type-specific communication; no perturbation, temporal ordering or directional recruitment evidence. Resource/output presence is not significant interaction evidence.','Communication feasibility and follow-up hypotheses only.',['Wu scRNA','S2 reference','S4/S5 shared-reference derivatives','result-selected external queries'],'Perturbation, spatial cell-resolved ligand/receptor measurements, temporal ordering, independent confirmation'),
 'C6':('CLINICAL_CLAIM_REJECTED_FOR_THIS_DATA','Workflow provides technical and descriptive features only; no outcome evidence supports prediction.','No immunotherapy response labels, independent held-out cohort, calibration or clinical validation.','No treatment-response prediction claim.',['Same observational study; no treatment outcome dataset'],'Outcome-linked independent validation and clinically appropriate study'),
 'T1':('POPULATION_MECHANISM_CLAIM_NOT_ESTABLISHED','One preregistered eligible section within six-section technical/spatial workflow.','One section is not independent population replication; source_sample_id is not patient_id; no mechanistic intervention.','Single-section descriptive result; neither population mechanism nor patient-level inference.',['C4','Wu dataset','identity evidence'],'Verified independent subjects, replicated effects and mechanistic evidence'),
 'T2':('LOCAL_TECHNICAL_REVERIFICATION_PASS','Declared input/output SHA-256 lists match; unique barcode sets match across S3/S4/S5; all 15601 coordinate rows finite.','Same-host verification is not independent external execution or authenticated receipt; hash consistency does not validate biology.','Observed same-host technical hash/connection/coordinate recomputation only.',['Immutable files','S7 read-only inspection implementation'],'Independent implementation/rerun and authenticated external receipt')}
ledger=[];audits=[]
for c in claims:
 k=c['claim_id'];state,support,against,ceiling,dep,debt=details[k]
 files=[{'path':str(p),'sha256':sha(p)} for p in ev[k]]
 payload={'claim_id':k,'original_statement':c['preregistered_statement'],'artifacts':files,'host_review_state':state,'support':support,'counterevidence':against,'maximum_claim':ceiling,'dependencies':dep}
 env=ExternalEvidenceEnvelope.create(evidence_id='SPATIALWARRANT-S7-'+k,family=ExternalCapabilityFamily.ANALYSIS,producer=ExternalProducerIdentity(plugin_id='local-python-s7-review',capability='completed-artifact-scientific-review',tool_name='build_spatialwarrant_s7.py',plugin_version='sha256:'+sha(__file__)),source_context={'backend_name':'local Python/scverse artifact review','backend_version':platform.python_version(),'input_artifact_sha256':canon(files),'parameters_sha256':canon({'scope':'S7','original_claim':c}),'execution_receipt_sha256':sha(A/'technical-reverification.json')},payload=payload,request={'action':'passive audit of completed artifact review; not authenticated scientific support'})
 audit=audit_external_evidence(env).to_dict();audits.append(audit)
 dump(rawdir/f'{k}-passive-envelope.json',env.to_dict());dump(rawdir/f'{k}-passive-audit.json',audit)
 ledger.append({**payload,'preregistered_record':c,'BioNexus_actual_passive_audit':audit,'BioNexus_MCP_overclaim_test':next((x for x in tests if x['test_id']==k),None),'evidence_debt':debt,'human_scientific_adjudication_required':True,'human_decision':'PENDING','scientific_acceptance':'PENDING','independent_evidence_groups':['Wu study'] if k!='T2' else ['same-host local verification'],'literature_role':'Context only, search-selected and not a replication; supporting/contradictory primary-paper assessment incomplete'})
# A stricter literature envelope leaves genuinely unknown source context absent.
lit=ExternalEvidenceEnvelope.create(evidence_id='SPATIALWARRANT-S7-LITERATURE-COVERAGE',family='literature',producer=ExternalProducerIdentity(plugin_id='life-sciences-literature',capability='ncbi-entrez',tool_name='S6 saved PubMed esearch',plugin_version='0.1.5'),source_context={'source_name':'PubMed','identifiers':sorted({pmid for q in inspection['literature_retrieval'] for pmid in q.get('ids',[])})},payload=inspection['literature_retrieval'],request={'action':'audit saved retrieval metadata; individual study design and publication status not established'})
dump(rawdir/'literature-coverage-envelope.json',lit.to_dict());dump(rawdir/'literature-coverage-audit.json',audit_external_evidence(lit).to_dict())
document={'schema':'SpatialWarrant.S7.claim-ledger.v1','created_at_utc':utc(),'locked_plan_sha256':inspection['plan_sha256'],'claim_source':inspection['claims'],'scope':'Six-section spatial workflow; one preregistered boundary-eligible section','execution_route':'Local Python/scverse execution; no registered NGS workflow run','governing_machine_review':'COMPLETED_WITH_AUDIT_DEFECTS_AND_EVIDENCE_DEBT','human_scientific_adjudication':'PENDING','claims':ledger,'no_independent_evidence_double_counting':True}
dump(A/'claim-ledger.json',document)
dump(A/'claim-ledger.jsonld',{'@context':{'@vocab':'https://schema.org/','prov':'http://www.w3.org/ns/prov#','sw':'urn:spatialwarrant:','claims':{'@id':'sw:claims','@container':'@set'}},'@id':'urn:spatialwarrant:run01:S7','@type':'Dataset','name':'SpatialWarrant Claim–Evidence Ledger','claims':[{'@id':'urn:spatialwarrant:'+x['claim_id'],'@type':'CreativeWork','name':x['original_statement'],'sw:review':x} for x in ledger]})
pd.DataFrame([{'claim_id':x['claim_id'],'original_claim':x['original_statement'],'host_review':x['host_review_state'],'support':x['support'],'counterevidence':x['counterevidence'],'maximum_claim':x['maximum_claim'],'files_and_sha256':json.dumps(x['artifacts']),'dependencies':'; '.join(x['dependencies']),'BioNexus_raw_audit_file':str(rawdir/(x['claim_id']+'-passive-audit.json')),'evidence_debt':x['evidence_debt'],'Human_Scientific_Adjudication':'PENDING'} for x in ledger]).to_csv(A/'claim-evidence-ledger.csv',index=False)
pd.DataFrame([{'path':k,'sha256':v} for k,v in inspection['hashes'].items()]).to_csv(A/'input-SHA256-index.csv',index=False)
summary=pd.read_csv(S3/'section-summary.csv'); s4audit=read(S4/'postcompletion-audit.v1.json'); sens=s4audit['method_sensitivity_summary']; niche=pd.read_csv(S5/'niche-distribution-by-section.csv'); boundary=pd.read_csv(S5/'boundary-niche-enrichment.csv');six=pd.read_csv(PB/'prespecified-six-genes.csv');effect=pd.read_csv(PB/'primary-program-B1-B2-B3-sensitivity.csv').iloc[0]
for src in [S3/'section-summary.csv',S5/'niche-distribution-by-section.csv',S5/'boundary-niche-enrichment.csv',LR/'external-evidence-summary.final.json',R/'S4-S5-checkpoint.postaudit.v1.md']:
 shutil.copy2(src,A/src.name)
txt(A/'evidence-card.md',f'''# SpatialWarrant — evidence card

Six public breast-cancer Visium sections and a same-study scRNA reference support a six-section technical and spatial workflow. Only CID4535 has verified, separable producer Invasive cancer/Stroma labels for the preregistered geometry-only boundary endpoint. Other sections were not repurposed as primary endpoints.

## What the completed outputs show

- C1: spatial QC, six numeric-domain comparisons and descriptive spatial statistics completed. Pathology agreement varies; same-study pathology is not independent truth.
- C2: 54/54 Tangram parameter runs; Tangram–NNLS dominant agreement {sens['tangram_nnls']['spot_dominant_agreement_overall']:.3%}; ingest–Tangram label agreement {sens['ingest']['transferred_label_vs_tangram_dominant_agreement_overall']:.3%}. Ingest is label transfer. All three share the same reference. Requested 1000/2000 training features both cap at 644–655; stability must not be overstated as a full 2000-feature perturbation.
- C3: k=10 selected before boundary comparison; no niche simultaneously met the four-component relative-enrichment criterion. This is a negative descriptive finding, not proof of biological absence. Technical transfer assigned 3798 10x spots using frozen scaler/centers; no independent biological replication.
- C4: 196/200 frozen IFN genes; B1/B2/B3 minus core = +0.034906652/+0.051510939/+0.022163777 mean log2(CPM+1). One eligible section, small descriptive effect. B2 spots=94, core=273. No population interval or p value; inferential DE NOT_RUN_INSUFFICIENT_REPLICATION.
- CXCL9, CXCL10, IDO1 and IRF1 are positive; CXCL11 and STAT1 do not exhibit uniform positive enhancement. See exact six-gene table in S6.
- C5: LIANA reference-wide results provide communication feasibility/hypotheses. Visium boundary cell-type-specific communication NOT_IDENTIFIABLE. Full return_all_lrs output and required-pair FOUND states are not independent, significant or causal proof.
- C6/T1: clinical prediction and population-wide mechanism are unsupported by this design. Patient-level inference remains BLOCKED.
- T2: saved declared input/output hashes, barcode joins and coordinates passed same-host read-only re-verification; this is technical integrity only.

## External context and audit

163/180 final external queries succeeded; 17 failures and prior failures remain saved. The ten top LIANA records all describe MIF–CD74_CXCR4 in different source/target combinations: not ten independent interaction mechanisms. Saved PubMed target queries are primarily esearch IDs, not a completed primary-paper support/contradiction review. Database release provenance is incomplete where a query date or target name was used as release/record identity in the S6 envelope. Existing S6 VALID statuses are preserved; they establish neither full metadata provenance nor scientific support.

The four real S7 BioNexus MCP calls returned NEEDS_DATA with claim-layer ABSTAIN. The parser classified all as descriptive, with intended higher claim tiers NOT_APPLICABLE. This is an audit defect, not demonstrated semantic refusal of the population, causal or clinical overclaim. Local passive-envelope audits are internal consistency checks; no authenticated external receipt has been obtained. Human scientific acceptance is PENDING.

## Evidence hierarchy

1. Six-section technical/spatial and method-sensitivity outputs.
2. CID4535 single-section preregistered descriptive endpoint.
3. Same-study scRNA communication feasibility.
4. Result-selected database/literature background; not independent verification.
5. Independent replication, mechanistic perturbation and clinical outcome validation: not performed.

The actual research endpoint is reportable with these limits; neither result magnitude nor technical integrity establishes population, causal or treatment-predictive conclusions. All claim-level artifact paths and SHA-256 values are in claim-ledger.json. Human adjudication is left blank in one centralized template.
''')
debts=[('D1','C1/C3/C4/T1','Independent boundary-eligible sections and verified subject identity absent','Limits population inference; cannot fix by counting spots or shared derivations'),('D2','C2/C3/C5','Reference shared across Tangram, NNLS, ingest, LIANA and niches','Limits independence and composition truth'),('D3','C3','Four-component target niche not observed','Retain negative result; do not change k or component map'),('D4','C5','No perturbation/temporal evidence or cell-resolved boundary expression','Blocks causal recruitment claim'),('D5','C6','No immunotherapy outcome/test cohort/calibration','Blocks clinical prediction'),('D6','All','PubMed searches lack target-wise primary-paper support/contradiction adjudication; 17/180 failed queries','Limits external-context synthesis; no consensus/replication claim'),('D7','All','BioNexus Chinese claim-class parsing defect and no authenticated receipt','Blocks claims of successful automatic semantic refusal or certified external audit'),('D8','T2','Same-host hash/join check, no independent rerun','Technical only'),('D9','C2','1000 and 2000 feature requests share capped actual sets','Limits claimed parameter coverage'),('D10','All','Some S6 external envelopes use query dates/targets as release/record provenance','VALID remains internal schema consistency; exact database release/returned-record mapping unresolved')]
dump(A/'evidence-debt.json',{'debts':[dict(zip(['id','claims','gap','impact'],d)) for d in debts]})
txt(A/'debt-graph.md','# Evidence Debt\n\n'+'\n'.join(f'- **{a} ({b})**: {c}. {d}.' for a,b,c,d in debts)+'\n\nAll debts remain open. Human acceptance with limits does not discharge missing empirical evidence.\n')
dependency={'nodes':['Wu study','scRNA source','six Visium sections','S2 reference','S3 frozen labels/geometry','S4 Tangram/NNLS/ingest','S5 niches','S6 pseudobulk','S6 LIANA','result-selected external searches','10x technical transfer','S7 review'],'edges':[['Wu study','scRNA source'],['Wu study','six Visium sections'],['scRNA source','S2 reference'],['six Visium sections','S3 frozen labels/geometry'],['S2 reference','S4 Tangram/NNLS/ingest'],['S3 frozen labels/geometry','S4 Tangram/NNLS/ingest'],['S4 Tangram/NNLS/ingest','S5 niches'],['S3 frozen labels/geometry','S6 pseudobulk'],['S2 reference','S6 LIANA'],['S6 LIANA','result-selected external searches'],['S6 pseudobulk','result-selected external searches'],['S5 niches','10x technical transfer']], 'independence_rule':'Shared study/reference, derivative analyses and result-selected literature are not separate independent confirmations.'}
dump(A/'provenance-and-dependency-map.json',dependency)
txt(A/'provenance-and-dependency-map.md','# Provenance and dependence\n\n```mermaid\ngraph TD\n W[Wu study] --> R[scRNA reference]\n W --> V[Six Visium sections]\n R --> D[Tangram / NNLS / ingest]\n V --> G[Producer pathology + frozen geometry]\n G --> D\n D --> N[Niches]\n G --> P[CID4535 pseudobulk]\n R --> L[LIANA]\n P --> E[Result-selected external searches]\n L --> E\n N --> T[10x technical transfer]\n```\n\nLocal Python/scverse execution. Workbench contributes data understanding/design/catalog routing, Literature and Databases supply external query returns, and BioNexus passively audits supplied records. None supplies independent biological replication.\n')
txt(A/'adversarial-review.md','''# Adversarial scientific review

Completed S7 review of existing evidence; no S1–S6 computations or frozen inputs changed.

| Challenge | Observation | Consequence |
|---|---|---|
| Is this merely a single-section study? | Six sections have technical/spatial results, but only CID4535 qualifies for main boundary endpoint. | State both scopes; neither discard five sections nor manufacture five endpoints. |
| Does the boundary follow desired expression? | S3 exact producer pathology + geometry frozen before downstream interpretation. | No expression-, cluster-, niche- or deconvolution-derived boundary edits. |
| Do three methods independently validate composition? | Shared Wu scRNA reference; dominant agreement only about 5%. | Method sensitivity, not calibrated cell fraction or independent validation. |
| Was a target niche selected after looking at enrichment? | k fixed using silhouette; no all-four enriched niche observed. | Keep negative observation and original mapping. |
| Do B1/B2/B3 establish a robust population effect? | Small same-section effects; nested masks on one specimen, not replications. | n=1 descriptive only; no pseudo-replicated inference. |
| Do six individual genes uniformly support the IFN narrative? | CXCL11 and STAT1 lack matching positive direction. | Explicitly preserve contrary observations. |
| Is LIANA boundary-specific or causal? | Reference-wide communication inference; mixed spots do not identify cell-specific expression. | Hypothesis/feasibility only; required-pair presence is not statistical or mechanistic proof. |
| Do successful queries prove literature support? | 163/180 transport successes; PubMed esearch primarily IDs; no complete primary-paper contradiction assessment. | Evidence debt stays open; no literature consensus claim. |
| Did BioNexus identify and refuse the three overclaims? | NEEDS_DATA/ABSTAIN, but all parsed descriptive; intended tiers NOT_APPLICABLE. | Real semantic audit defect. Do not advertise automatic overclaim detection success. |
| Is VALID a certified scientific verdict? | Passive local context/hash checks; declared producers, no authenticated external receipt. | Internal consistency only. |
| Are runtime/RAM fields all comparable? | S4 original peak field was max individual process; post-audit reports no continuous tree peak. | Use corrected stage records; do not sum or present unmeasured peaks. |

Submission repair list: disclose parser failure and literature-depth gap in any demo; remove claims of successful automatic semantic rejection, external certification, primary-paper triangulation, independent biological validation, population mechanism, causality and treatment prediction. An honest descriptive workflow/demo draft can still be prepared. Repairing the parser or completing literature adjudication would require later work, not covertly changing S7 evidence. No additional analysis was launched.
''')
concepts=['Workbench question/units/plan/approval','Real catalog response and local Python routing','Actual Literature Wu-study return, success and failure','Six-section H&E, producer pathology and geometry-only masks','Tangram/NNLS sensitivity; ingest separately as labels','Eligible-unit effects, valid uncertainty/LOO and full DE context','Receipt-backed EvidenceCard, ledger and Evidence Debt','Actual overclaim response and named human adjudication, even if test fails']
dump(F/'eight-original-screenshot-concepts.json',{'original_concepts':concepts,'selection':{'01-workflow-and-roles.png':[1,2,3],'02-six-section-spatial-atlas.png':[4,5],'03-S6-descriptive-evidence.png':[6],'04-claims-debt-actual-audit.png':[7,8]},'corrections':'Artifact-based figures, not fabricated UI screenshots. No authenticated receipt or human name is invented. No volcano/CI/LOO generated because inference unavailable.'})
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':12,'axes.spines.top':False,'axes.spines.right':False,'savefig.facecolor':'#f5f7fa','figure.facecolor':'#f5f7fa'})
navy='#17324d';teal='#087f8c';red='#ad3e3e'
def save(fig,name):
 guard();fig.savefig(F/(name+'.png'),dpi=150,bbox_inches='tight');fig.savefig(F/(name+'.pdf'),bbox_inches='tight');plt.close(fig)
def card(ax,x,y,w,h,title,body,color=navy):
 ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle='round,pad=.012',facecolor='white',edgecolor='#d1dbe4'))
 ax.text(x+.025,y+h-.045,title,color=color,weight='bold',size=17,va='top')
 ax.text(x+.025,y+h-.12,body,color=navy,size=12.5,va='top',linespacing=1.55)
fig,ax=plt.subplots(figsize=(16,10));ax.set(xlim=(0,1),ylim=(0,1));ax.axis('off')
ax.text(.02,.96,'SpatialWarrant',size=34,weight='bold',color=navy)
ax.text(.02,.9,'Six-section spatial workflow',size=23,color=teal)
ax.text(.02,.85,'One preregistered boundary-eligible section',size=18,color=navy)
card(ax,.02,.47,.455,.32,'Completed scientific workflow','6 public breast-cancer Visium sections\nSame-study scRNA reference: 40,000 cells\nSpatial QC → method sensitivity → niches\nFrozen IFN endpoint → LIANA → pathways\nCID4535 endpoint: B2 − core = +0.05151')
card(ax,.52,.47,.455,.32,'Actual Rosalind plugins used','NGS Analysis Workbench — design / catalog\nLife Sciences Literature — source lookups\nLife Sciences Databases — context queries\nBioNexus Reliability — passive record audit\nExternal queries: 163 / 180 successful')
card(ax,.02,.14,.455,.27,'Local Python/scverse execution','No compatible registered matrix workflow found\nExisting stage outputs reviewed; no stage reruns\nLocked plan, input/output hashes, saved returns\nShared reference ≠ independent validation')
card(ax,.52,.14,.455,.27,'A result with explicit limits','Descriptive effect, not population inference\nNo causal or immunotherapy prediction claim\nActual audit defect preserved, not retouched\nHuman Scientific Adjudication: PENDING',red)
ax.text(.02,.045,'Artifact-based evidence summary • draft only • no fabricated app screenshots',size=11,color='#5d6e7c')
save(fig,'01-workflow-and-roles')
sections=summary.section.astype(str).tolist(); tang=pd.read_csv(S4/'proportions_tangram.csv.gz');nnls=pd.read_csv(S4/'proportions_marker_nnls.csv.gz');nl=pd.read_csv(S5/'niche_labels.csv.gz');vocab=[c for c in tang if c not in ['section','barcode']]
metadata={sec:pd.read_csv(S3/sec/'spot-QC-and-metadata.csv.gz',index_col=0) for sec in sections}
labels=sorted({str(x) for m in metadata.values() for x in m.Classification.dropna().unique()}); cmap=plt.get_cmap('tab20');cellcolors={x:plt.get_cmap('gist_rainbow')(j/max(1,len(vocab)-1)) for j,x in enumerate(vocab)};pathcolors={x:cmap(j%20) for j,x in enumerate(labels)}
pd.DataFrame({'producer_label':vocab,'plot_color':[matplotlib.colors.to_hex(cellcolors[x]) for x in vocab]}).to_csv(F/'composition-legend.csv',index=False)
pd.DataFrame({'raw_pathology_label':labels,'plot_color':[matplotlib.colors.to_hex(pathcolors[x]) for x in labels]}).to_csv(F/'pathology-legend.csv',index=False)
fig,axs=plt.subplots(6,6,figsize=(19,18));columns=['H&E','Producer pathology','Frozen B2 / core','Tangram dominant','NNLS dominant','Niche (k=10)']
for row,sec in enumerate(sections):
 m=metadata[sec];xy=m[['px_col','px_row']].to_numpy();lims=[xy[:,0].min()-60,xy[:,0].max()+60,xy[:,1].max()+60,xy[:,1].min()-60]
 for col in range(6):
  ax=axs[row,col];ax.set_aspect('equal');ax.axis('off');ax.set_xlim(lims[:2]);ax.set_ylim(lims[2:]);
  if row==0:ax.set_title(columns[col],weight='bold',size=12,pad=14)
 axs[row,0].text(-.05,.5,sec,transform=axs[row,0].transAxes,ha='right',va='center',rotation=90,weight='bold',size=13)
 base=R/f'01_inputs/zenodo4739739/spatial-extracted/spatial/{sec}_spatial'
 im=plt.imread(base/'tissue_lowres_image.png');scale=read(base/'scalefactors_json.json')['tissue_lowres_scalef']
 axs[row,0].imshow(im,extent=[0,im.shape[1]/scale,im.shape[0]/scale,0])
 axs[row,1].scatter(*xy.T,c=[pathcolors.get(str(x),'#cccccc') for x in m.Classification],s=3,rasterized=True)
 if sec=='CID4535':
  mask=pd.read_csv(S3/sec/'geometry-boundary-core-masks.csv').set_index('barcode').reindex(m.index)
  axs[row,2].scatter(*xy.T,c='#d3dae0',s=3)
  for key,color,label in [('boundary_invasive_d2',teal,'B2'),('core_invasive_d_gt_3',navy,'core')]:
   z=mask[key].fillna(False).astype(bool).to_numpy();axs[row,2].scatter(*xy[z].T,c=color,s=5,label=label)
  axs[row,2].legend(fontsize=8,loc='lower left',frameon=False)
 else:axs[row,2].text(.5,.5,'Not boundary-eligible',ha='center',va='center',transform=axs[row,2].transAxes,size=10,color='#647789')
 for col,df in [(3,tang),(4,nnls)]:
  z=df[df.section==sec].set_index('barcode').reindex(m.index);dom=z[vocab].idxmax(axis=1);axs[row,col].scatter(*xy.T,c=[cellcolors[x] for x in dom],s=3,rasterized=True)
 nz=nl[nl.section==sec].set_index('barcode').reindex(m.index).niche.astype(str).str.replace('N','').astype(int);axs[row,5].scatter(*xy.T,c=nz,cmap='tab10',vmin=0,vmax=9,s=3,rasterized=True)
fig.suptitle('Six-section spatial workflow',size=26,weight='bold',color=navy,y=.995)
fig.text(.5,.963,'One preregistered boundary-eligible section • Original producer labels and frozen geometry preserved',ha='center',size=14)
fig.text(.5,.025,'Tangram / NNLS: shared-reference dominant components, not calibrated cell fractions • Cross-method dominant agreement 4.79%',ha='center',size=13)
fig.text(.5,.009,'Shared composition colors across methods; exact raw-label legends provided in captions and CSV • Niche colors N0–N9 • Local Python/scverse execution',ha='center',size=10)
fig.subplots_adjust(top=.93,bottom=.05,wspace=.06,hspace=.08);save(fig,'02-six-section-spatial-atlas')
fig,axs=plt.subplots(2,2,figsize=(16,11));fig.subplots_adjust(hspace=.55,wspace=.4,top=.85,bottom=.1)
ds=[float(effect[x]) for x in ['B1_boundary_minus_core','B2_boundary_minus_core_primary','B3_boundary_minus_core']]
ax=axs[0,0];ax.bar(['B1','B2 (primary)','B3'],ds,color=[navy,teal,navy]);ax.set_ylim(0,.064);ax.set_ylabel('Mean log2(CPM+1): boundary − core');ax.set_title('Frozen IFN program • 196 / 200 genes',weight='bold')
for j,v in enumerate(ds):ax.text(j,v+.002,f'+{v:.5f}',ha='center',size=12)
ax=axs[0,1];vals=six.B2_boundary_minus_core.to_numpy();ax.barh(six.gene,vals,color=[teal if v>0 else red for v in vals]);ax.axvline(0,c='#888',lw=.7);ax.set_title('Six prespecified genes • B2 − core',weight='bold');ax.set_xlabel('log2(CPM+1) difference');ax.invert_yaxis()
ax=axs[1,0];ax.axis('off');ax.set_title('LIANA • reference-wide communication',weight='bold',loc='left');ax.text(0,.85,'CXCL9 / CXCL10 → CXCR3\nCD274 → PDCD1\nTGFB1 → receptor complexes\nSPP1 → CD44',transform=ax.transAxes,size=16,linespacing=1.6,color=navy);ax.text(0,.28,'Prespecified records retained; presence ≠ causal support\nTop 10 ranked records: MIF → CD74_CXCR4\nBoundary cell-type-specific signal: NOT_IDENTIFIABLE',transform=ax.transAxes,size=11,linespacing=1.6,color=red)
prog=pd.read_csv(PB/'pathway-progeny-results.full.csv');top=prog.assign(mag=prog.boundary_minus_core.abs()).sort_values(['mag','pathway'],ascending=[False,True]).head(5)
ax=axs[1,1];ax.barh(top.pathway,top.boundary_minus_core,color=teal);ax.invert_yaxis();ax.set_title('PROGENy • top 5 absolute differences',weight='bold');ax.set_xlabel('Descriptive ULM activity: boundary − core')
fig.suptitle('CID4535: a small, preregistered descriptive effect',size=25,weight='bold',color=navy,y=.97)
fig.text(.5,.908,'One preregistered boundary-eligible section • Descriptive effect, not population inference',ha='center',size=15)
fig.text(.5,.04,'No inferential DE, population p values or confidence intervals • Mixed gene directions retained • No causal or clinical inference',ha='center',size=12)
save(fig,'03-S6-descriptive-evidence')
fig,ax=plt.subplots(figsize=(17,11));ax.set(xlim=(0,1),ylim=(0,1));ax.axis('off')
ax.text(.02,.95,'Claims, evidence debt & actual audit behavior',size=28,weight='bold',color=navy)
left=[('C1','Six-section spatial description'),('C2','Strong cross-method sensitivity'),('C3','Four-component target not observed'),('C4','One-section descriptive effect'),('C5','Causal recruitment not established'),('C6','Treatment prediction unsupported'),('T1','Population mechanism unsupported'),('T2','Local hashes / joins rechecked')]
for j,(code,msg) in enumerate(left):
 y=.84-j*.068;ax.text(.035,y,code,weight='bold',color=teal,size=16);ax.text(.09,y,msg,size=14,color=navy)
card(ax,.54,.50,.425,.35,'Real BioNexus MCP responses','Population mechanism  → NEEDS_DATA\nCausal recruitment       → NEEDS_DATA\nTreatment prediction    → NEEDS_DATA\nTechnical hashes          → NEEDS_DATA\nClaim layer for all four: ABSTAIN',red)
card(ax,.54,.18,.425,.26,'Audit defect retained','All four parsed as descriptive claims\nIntended higher tiers: NOT_APPLICABLE\nNot a successful semantic refusal demo\nNo authenticated external receipt',red)
ax.text(.035,.23,'Open Evidence Debt',weight='bold',size=18,color=navy)
ax.text(.035,.18,'Independent replication • causal perturbation\nOutcome-linked validation • primary-paper review\nParser repair • authenticated receipt',size=12.5,linespacing=1.7,color=navy)
ax.text(.035,.045,'Shared Wu study → reference → methods / niches / LIANA: dependent evidence\nHuman Scientific Adjudication: PENDING • Local passive VALID is internal consistency only',size=12,color=navy)
save(fig,'04-claims-debt-actual-audit')
print('FIGURES_AND_LEDGER_WRITTEN',flush=True)
main='''SpatialWarrant follows six public breast-cancer Visium sections and the same-study scRNA reference through spatial QC, deconvolution sensitivity, niches, a frozen IFN endpoint, LIANA, pathways, literature lookups and BioNexus auditing.

NGS Analysis Workbench supported data understanding, design and routing; computation used local Python/scverse execution. Actual plugins used: NGS Analysis Workbench, Life Sciences Literature, Life Sciences Databases and BioNexus Reliability. This was not a registered NGS workflow run.

The value is the separation of observed results, method sensitivity and claims the evidence cannot support. Only CID4535 qualified for the preregistered boundary endpoint: B2−core +0.05151 mean log2(CPM+1), a single-section descriptive effect. Cross-method dominant agreement was about 5%; no niche simultaneously enriched all four prespecified components.

The audit also exposed a real limitation: BioNexus returned NEEDS_DATA/ABSTAIN but misclassified the overclaims. We retain that failure and the literature-review debt. No population mechanism, causality, immunotherapy prediction or independent biological validation is claimed. Human scientific adjudication remains pending.'''
txt(S/'english-main-post.md',main+'\n')
posts=[
 'SpatialWarrant: six public breast-cancer Visium sections + same-study scRNA, from spatial QC to a frozen IFN endpoint and evidence audit. We separate observed results, method sensitivity and unsupported claims—including a real audit-parser failure. Draft; human review pending.',
 'NGS Analysis Workbench supported data understanding, design and routing. Life Sciences Literature, Life Sciences Databases and BioNexus Reliability supplied lookups and passive audits. Computation: local Python/scverse, not a registered NGS workflow run.',
 'All six sections have spatial and method-sensitivity results. Only CID4535 was eligible for the preregistered boundary endpoint: B2−core +0.05151 mean log2(CPM+1), 196/200 IFN genes. One-section description—not population inference.',
 'Tangram, NNLS and ingest share one reference. Dominant-label agreement across methods was about 5%; ingest is label transfer, not proportions. No niche enriched all four prespecified components. The 10x transfer demonstrates technical compatibility only.',
 'LIANA, pathways and database/literature lookups add context, not causal proof. External queries: 163/180 successful; primary-paper support/contradiction review remains incomplete. We make no causal recruitment or immunotherapy-response prediction claim.',
 'BioNexus returned NEEDS_DATA / claim-layer ABSTAIN, but parsed population, causal and clinical overclaims as descriptive. That is an audit defect, not successful semantic refusal. Raw returns and evidence debt remain visible. No independent biological validation.'
]
txt(S/'optional-short-thread.md','\n\n'.join(f'{j+1}/{len(posts)} ({len(p)} characters before numbering)\n{p}' for j,p in enumerate(posts))+'\n')
dump(S/'draft-character-counts.json',{'main_post_characters':len(main),'main_requires_long_post_or_thread':len(main)>280,'thread':[{'index':j+1,'characters_with_numbering':len(f'{j+1}/{len(posts)} '+p),'within_280':len(f'{j+1}/{len(posts)} '+p)<=280} for j,p in enumerate(posts)],'posted':False,'event_specific_submission_rules':'Not provided; not asserted verified'})
txt(F/'figure-captions.md','''# Four selected competition figures

These are artifact-based summaries rendered from existing outputs, not screenshots of an app or fabricated tool responses. No scientific stages were rerun. PNG and vector PDF supplied. For image 2, a stable shared palette maps exact producer labels across Tangram/NNLS; numerical niche labels N0–N9 map to tab10 colors. Color similarity is not evidence of biological equivalence. Full raw pathology and composition labels are in accompanying legend CSVs; original S3 images remain available.

1. **Workflow and roles.** Six-section workflow, one eligible endpoint, real plugin roles and local execution route. Workbench understanding/design skills and catalog calls do not imply a registered workflow run.
2. **Six-section spatial atlas.** Original H&E, exact publisher pathology labels, existing frozen B2/core masks (CID4535 only), Tangram and NNLS dominant components, and saved niches. Panels share per-section full-resolution image coordinates; no mask, expression or clustering was re-estimated. Dominant-component maps are visual encodings of saved results, not cell fractions. Missing pathology is grey. The five other sections remain technically/spatially informative without a fabricated boundary endpoint.
3. **S6 descriptive evidence.** Saved program differences, all six prespecified genes, reference-wide LIANA context and top five absolute PROGENy ULM differences. Hallmark mean log2(CPM+1) and PROGENy ULM are different scales. The full S6 Hallmark and PROGENy tables remain authoritative. No error bars, p values or DE volcano are supplied because biological replication is insufficient. Required interaction records do not imply significant or causal signaling; receptor complexes retain subunits in S6 full tables.
4. **Claim ledger and actual audit.** Host scientific review states are separate from BioNexus MCP responses. The semantic parsing defect and absent authenticated receipt are explicit. Passive local VALID means internal consistency, not accepted biology. Human adjudication remains unfilled.
''')
txt(A/'human-scientific-adjudication.template.md',f'''# One centralized Human Scientific Adjudication

Status: PENDING — the assistant has not supplied or signed a human decision.

Scope: SpatialWarrant S7, C1–C6 and T1–T2, all four figures and draft submission. Review claim-ledger.json (SHA-256 `{sha(A/'claim-ledger.json')}`), evidence-card.md, adversarial-review.md, actual BioNexus returns and debt-graph.md together. No biological conclusion was accepted by execution permission.

| Field | Human entry |
|---|---|
| Decision: accept / accept-with-limits / do-not-accept | |
| Full name | |
| Date | |
| Reasons and any claim-specific limits (C1–C6, T1–T2) | |
| Acknowledgment of open debts and unaccepted population/causal/clinical claims | |

One decision covers the entire package; claim-specific limitations belong in the single reasons field. Acceptance does not create missing replication, causal evidence, treatment outcomes or an authenticated receipt. No public posting is authorized or performed by this template.
''')
limits=['BioNexus Chinese semantic classification failed; cannot advertise successful automatic overclaim refusal','Authenticated external receipt unavailable; local VALID is internal consistency only','Target-wise primary-paper supporting/contradictory review incomplete; 17 external query failures retained','One eligible section; no population, patient-level, causal or clinical inference','No independent biological replication; 10x is technical transfer']
result={'stage':'S7','status':'COMPLETED_WITH_AUDIT_DEFECTS_AND_EVIDENCE_DEBT','scope':'S7 only','created_at_utc':utc(),'plan_sha256':inspection['plan_sha256'],'technical_integrity':'PASS','scientific_review':{x['claim_id']:x['host_review_state'] for x in ledger},'bionexus_MCP_status':'NEEDS_DATA for 4/4 corrected calls; claim layer ABSTAIN; descriptive misclassification defect','passive_audits':audits,'human_scientific_adjudication':'PENDING','biological_conclusion_acceptance':'PENDING','submission_readiness':'DRAFT_WITH_DISCLOSED_LIMITS; HUMAN_DECISION_PENDING','submission_defects':limits,'final_images':[str(F/(x+'.png')) for x in ['01-workflow-and-roles','02-six-section-spatial-atlas','03-S6-descriptive-evidence','04-claims-debt-actual-audit']],'S1_S6_rerun':False,'posted':False,'future_stage_started':False}
dump(A/'S7-result.json',result)
dump(A/'execution-environment.json',{'python':sys.version,'executable':sys.executable,'platform':platform.platform(),'packages':{'numpy':np.__version__,'pandas':pd.__version__,'matplotlib':matplotlib.__version__},'command':sys.argv,'new_dependencies_installed':False,'resource_scope':'S7 rendering/package build only; excludes earlier read-only tool calls and hashing inspection','elapsed_seconds':time.perf_counter()-start,'start_free_C_bytes':startfree,'end_free_C_bytes':shutil.disk_usage('C:\\').free,'peak_process_working_set_bytes':getattr(psutil.Process().memory_info(),'peak_wset',None)})
prov=sidecar(activity_name='SpatialWarrant S7 completed-artifact review and figure rendering',input_files=[R/'00_plan/analysis-plan.lock.md',PB/'S6-result.json',LR/'S6-result.json',S4/'postcompletion-audit.v1.json',A/'technical-reverification.json'],output_files=[A/'claim-ledger.json',A/'overclaim-tests.json'],parameters={'stage':'S7 only','scientific_analyses_repeated':False},method='Passive review of completed scientific outputs; actual MCP overclaim tests; existing-data figure rendering',backend='local Python/scverse execution; local BioNexus shared kernel; no registered NGS workflow run')
dump(A/'provenance.sidecar.json',prov)
checkpoint=f'''# SpatialWarrant S7 checkpoint

S7: COMPLETED_WITH_AUDIT_DEFECTS_AND_EVIDENCE_DEBT. Formal S1–S6 artifacts were read only. Plan hash `{inspection['plan_sha256']}` unchanged. Original claim register equals its locked plan CSV appendix; no separate historic CSV lock was invented.

Claim review: C1 study-bound; C2 method-sensitive; C3 target niche not observed; C4 single-section descriptive; C5 causal claim not established; C6 clinical claim rejected for this data; T1 population mechanism not established; T2 same-host technical re-verification passes.

Four real BioNexus MCP calls returned NEEDS_DATA / claim-layer ABSTAIN but misclassified all as descriptive. Initial four invalid-purpose request errors are retained. This is an audit defect, not successful semantic refusal. Local passive audit raw statuses are unmodified; no authenticated external receipt. S6 prior VALID states preserved. Human Scientific Adjudication and biological acceptance remain PENDING.

Six sections remain the technical/spatial study scope; one eligible section is the main endpoint scope. Frozen IFN coverage196/200; B2−core +0.051510939; B1/B3 +0.034906652/+0.022163777. No inferential DE or population p/CI. Strong cross-method disagreement and negative four-component niche finding retained. 163/180 external queries succeeded; primary-paper support/contradiction adjudication and exact database-release provenance remain debts.

Four PNG/PDF figures: `{F}`. English master post and optional short thread: `{S}`. Drafts only; no posting. One unfilled centralized human-scientific-adjudication.template.md in `{A}`. Raw responses, lineage, per-claim SHA-256 links, evidence debt and manifests are saved. No additional stage started.

Submission: a transparent descriptive-workflow draft is prepared. Claims of accurate automatic semantic overclaim rejection, authenticated scientific certification, completed primary-paper triangulation, independent biological validation, population mechanism, causality or treatment prediction remain disallowed by the observed evidence. See adversarial-review.md for repair list.
'''
txt(A/'S7-checkpoint.md',checkpoint)
if not (R/'S7-checkpoint.md').exists():txt(R/'S7-checkpoint.md',checkpoint)
dump(A/'build-session.json',{'status':'COMPLETED','finished_at_utc':utc(),'start_free_C_bytes':startfree,'end_free_C_bytes':shutil.disk_usage('C:\\').free})
print(json.dumps({'status':result['status'],'images':result['final_images'],'elapsed_seconds':time.perf_counter()-start,'free_C_bytes':shutil.disk_usage('C:\\').free}),flush=True)
