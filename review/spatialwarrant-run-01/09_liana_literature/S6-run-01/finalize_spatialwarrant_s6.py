from __future__ import annotations
import hashlib, json, math, os, shutil, sys, time
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd

ROOT=Path(sys.argv[1]); PB=ROOT/'08_pseudobulk'/'S6-run-01'; LR=ROOT/'09_liana_literature'/'S6-run-01'
sys.path.insert(0,r'C:\Plugin\BioNexus\src')
from bionexus.provenance import sidecar
from bionexus.ecosystem_intake import ExternalCapabilityFamily, ExternalEvidenceEnvelope, ExternalProducerIdentity, audit_external_evidence

def utc(): return datetime.now(timezone.utc).isoformat()
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(8*1024*1024),b''): h.update(b)
    return h.hexdigest()
def canon(v): return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()
def native(v):
    if isinstance(v,dict): return {str(k):native(x) for k,x in v.items()}
    if isinstance(v,(list,tuple)): return [native(x) for x in v]
    if isinstance(v,float) and not math.isfinite(v): return None
    if pd.isna(v): return None
    return v
def dump(p,v): Path(p).write_text(json.dumps(native(v),indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf-8')
def size_tree(p): return sum(x.stat().st_size for x in Path(p).rglob('*') if x.is_file())

local=json.loads((PB/'S6-local-result.json').read_text(encoding='utf-8'))
ext_initial=json.loads((LR/'external-evidence-summary.json').read_text(encoding='utf-8'))
ext_retry=json.loads((LR/'external-evidence-summary.v2.json').read_text(encoding='utf-8'))
ext=json.loads((LR/'external-evidence-summary.final.json').read_text(encoding='utf-8'))
qlog=pd.read_csv(LR/'external-query-log.final.csv')
topgenes=pd.read_csv(LR/'top20-descriptive-genes-for-external-evidence.csv')
toplr=pd.read_csv(LR/'liana-top10-for-external-evidence.csv')
six=pd.read_csv(PB/'prespecified-six-genes.csv')
hall=pd.read_csv(PB/'pathway-hallmark-results.full.csv')
prog=pd.read_csv(PB/'pathway-progeny-results.full.csv')

inputs=[ROOT/'00_plan'/'analysis-plan.lock.md',ROOT/'S4-S5-checkpoint.md',ROOT/'03_scrna_reference'/'S2-run-01'/'ref_40k.h5ad',
        ROOT/'03_scrna_reference'/'S2-run-01'/'annotation_evidence.csv',ROOT/'04_visium_qc'/'S3-run-03'/'CID4535'/'CID4535.h5ad',
        ROOT/'04_visium_qc'/'S3-run-03'/'CID4535'/'geometry-boundary-core-masks.csv',ROOT/'06_deconvolution'/'S4-run-02'/'proportions_tangram.csv.gz',
        ROOT/'07_niches'/'S5-run-02'/'niche_labels.csv.gz',ROOT/'07_niches'/'S5-run-02'/'co-occurrence.csv',
        ROOT/'01_inputs'/'resources'/'h.all.v2024.1.Hs.symbols.gmt',ROOT/'01_inputs'/'resources'/'liana-consensus-frozen.csv',ROOT/'01_inputs'/'resources'/'PROGENy-omnipath-snapshot.tsv']
inputs += [ROOT/'01_inputs'/'zenodo4739739'/'raw_count_matrices-extracted'/'raw_count_matrices'/'CID4535_raw_feature_bc_matrix'/n for n in ['matrix.mtx.gz','barcodes.tsv.gz','features.tsv.gz']]
input_hashes={str(p):sha(p) for p in inputs}
params={"primary_boundary":"CID4535 B2 D<=2","sensitivities":["B1 D<=1","B3 D<=3"],"core":"D>3","program":"HALLMARK_INTERFERON_GAMMA_RESPONSE M5913 2024.1.Hs",
        "score":"mean matched-gene log2(CPM+1)","liana":{"method":"rank_aggregate","groupby":"producer_celltype_minor","expr_prop":0.1,"min_cells":5,"n_perms":1000,"seed":20260904},
        "pathway":{"Hallmark":"unweighted mean log2(CPM+1)","PROGENy":"decoupler ULM"}}

key_outputs=[PB/'primary-program-region-scores.csv',PB/'primary-program-B1-B2-B3-sensitivity.csv',PB/'prespecified-six-genes.csv',
             PB/'region-pseudobulk-raw-counts.full.csv.gz',PB/'descriptive-whole-gene-table.full.csv.gz',PB/'pathway-hallmark-results.full.csv',PB/'pathway-progeny-results.full.csv',
             LR/'liana-rank-aggregate.full.csv.gz',LR/'liana-prespecified-interactions.csv',LR/'liana-spatial-niche-context.csv',LR/'external-query-log.final.csv',PB/'S6-integrated-figure.png']
for outdir in [PB,LR]:
    prov=sidecar(activity_name='SpatialWarrant S6 descriptive boundary pseudobulk, LIANA, pathway, and external-context analysis',input_files=inputs,output_files=key_outputs,
                 parameters=params,method='Locked S6 local Python/scverse execution with fixed S3 geometry masks and frozen resources',backend='local Python/scverse; LIANA 1.10.0; decoupler 2.2.0; not a registered NGS workflow run')
    dump(outdir/'bionexus.provenance.sidecar.json',prov)

# BioNexus passive envelopes and audits. These prove internal consistency only.
envdir=LR/'bionexus-external-evidence'; envdir.mkdir(exist_ok=True)
analysis_payload=local
analysis_env=ExternalEvidenceEnvelope.create(evidence_id='SPATIALWARRANT-S6-LOCAL-ANALYSIS',family=ExternalCapabilityFamily.ANALYSIS,
    producer=ExternalProducerIdentity(plugin_id='local-python-scverse',capability='spatial-transcriptomics-analysis',tool_name='run_spatialwarrant_s6.py',plugin_version='script-sha256:'+sha(PB/'run_spatialwarrant_s6.py')),
    source_context={'backend_name':'local Python/scverse','backend_version':json.loads((PB/'execution-environment.json').read_text())['python'].split()[0],
                    'input_artifact_sha256':canon(input_hashes),'parameters_sha256':canon(params),'execution_receipt_sha256':sha(PB/'S6-local-result.json')},
    payload=analysis_payload,request={'locked_plan_sha256':sha(ROOT/'00_plan'/'analysis-plan.lock.md'),'parameters':params})
envelopes=[analysis_env]
source_meta={
 'reactome':('Reactome','database','reactome-skill','0.1.5','Reactome stable IDs or query targets','live ContentService query 2026-09-06'),
 'string':('STRING','database','string-skill','0.1.5','STRING protein identifiers or query targets','live STRING API query 2026-09-06'),
 'opentargets':('Open Targets Platform','database','opentargets-skill','0.1.5','Ensembl/Platform entities or query targets','live Platform GraphQL query 2026-09-06'),
 'uniprot':('UniProtKB','database','uniprot-skill','0.1.5','UniProtKB accessions or query targets','live UniProt REST query 2026-09-06'),
 'pubmed':('PubMed','literature','ncbi-entrez-skill','0.1.5','PMID','live Entrez query 2026-09-06')}
for source,meta in source_meta.items():
    srcrows=qlog[qlog.source==source]
    payload=[]; requests=[]
    for _,r in srcrows.iterrows():
        rp=Path(r.response_path); qp=Path(r.request_path)
        if rp.exists(): payload.append(json.loads(rp.read_text(encoding='utf-8')))
        if qp.exists(): requests.append(json.loads(qp.read_text(encoding='utf-8')))
    if source=='pubmed':
        ids=[]
        for x in payload:
            raw=Path(x.get('raw_output_path',''))
            if raw.exists():
                try:
                    z=json.loads(raw.read_text(encoding='utf-8')); ids += z.get('esearchresult',{}).get('idlist',[])
                except Exception: pass
        ctx={'source_name':meta[0],'identifiers':sorted(set(ids)) or ['no PMID returned for some preserved queries'],'publication_status':'PubMed-indexed search returns; individual publication status not adjudicated','study_design':'not assessed from search-only retrieval'}
    else:
        ctx={'source_name':meta[0],'record_ids':sorted(srcrows.target.astype(str).unique().tolist()),'database_release':meta[5],
             'identifier_namespace':meta[4],'organism_taxon':'NCBI:9606'}
    env=ExternalEvidenceEnvelope.create(evidence_id=f'SPATIALWARRANT-S6-{source.upper()}',family=meta[1],
        producer=ExternalProducerIdentity(plugin_id='life-sciences-databases' if source!='pubmed' else 'life-sciences-literature',capability='external-context-query',tool_name=meta[2],plugin_version=meta[3]),
        source_context=ctx,payload=payload,request=requests)
    envelopes.append(env)
audits=[]
for e in envelopes:
    ep=envdir/f'{e.evidence_id}.envelope.json'; ap=envdir/f'{e.evidence_id}.audit.json'
    dump(ep,e.to_dict()); a=audit_external_evidence(e); dump(ap,a.to_dict()); audits.append(a.to_dict())
dump(LR/'bionexus-external-evidence-audit.json',{'status':'COMPLETED','audits':audits,'interpretation':'VALID means schema/hash/context consistency only; producer identity remains declared, not authenticated; no envelope is accepted as claim support without human adjudication.'})
dump(LR/'bionexus-mcp-host-probe-attempts.json',{
 'attempts':[{'attempt':1,'status':'FAILED','request':{'host_name':'Codex desktop local'},'return':'Error executing tool bionexus_host_probe: host_name must be a lowercase host identifier'},
             {'attempt':2,'status':'TIMED_OUT_AFTER_180_SECONDS','request':{'host_name':'codex-desktop-local','challenge_local_result_sha256':'df855eff07a586f78484618ced195c964ac32b14554d2fda76e235cff2799e2e'},'return':None}],
 'post_correction_local_result_sha256':sha(PB/'S6-local-result.json'),
 'interpretation':'MCP receipt was not obtained. Attempt 2 bound the preserved filtered-matrix attempt before raw-source correction and is not valid for the final result. Local BioNexus sidecar and passive intake audits bind the final outputs; no successful host-probe claim is made.'})

claim_audit={'schema':'SpatialWarrant.S6.claim-bound-audit.v1','created_at_utc':utc(),'locked_plan_sha256':sha(ROOT/'00_plan'/'analysis-plan.lock.md'),
 'claims':[{'claim_id':'C4','scope':'CID4535 single-section descriptive boundary effect','status':'COMPUTED_DESCRIPTIVE','effect':local['program_differences']['B2_boundary_minus_core_primary'],
            'evidence_ceiling':'SINGLE_SECTION_DESCRIPTIVE','machine_verdict':'PENDING','biological_conclusion':'PENDING'},
           {'claim_id':'C5','scope':'CXCL9/10-CXCR3 drives T-cell recruitment','status':'ABSTAIN_CAUSAL','reason':'no perturbation, temporal ordering, or independent causal validation'},
           {'claim_id':'patient-level','status':'BLOCKED','reason':'one eligible section and no verified patient-level independent units'},
           {'claim_id':'boundary-celltype-LIANA','status':'NOT_IDENTIFIABLE','reason':'mixed Visium spots do not contain cell-type-resolved boundary expression'},
           {'claim_id':'clinical','status':'REFUSED','reason':'no treatment outcome, independent test cohort, calibration, or clinical validation'}],
 'external_context':'UNASSESSED_NOT_CLAIM_SUPPORT','human_scientific_adjudication':'PENDING'}
dump(LR/'bionexus-claim-bound-audit.json',claim_audit)

if shutil.disk_usage('C:\\').free < 20*1024**3: raise RuntimeError('disk below 20 GiB stop line before finalization')
end=utc(); end_free=shutil.disk_usage('C:\\').free
total_elapsed=float(local['elapsed_seconds'])+float(ext_initial['elapsed_seconds'])+float(ext_retry['elapsed_seconds'])+float(ext['elapsed_seconds'])
result={'status':'COMPLETED_WITH_PRESERVED_EXTERNAL_QUERY_FAILURES','started_at_utc':local['started_at_utc'],'ended_at_utc':end,'local_compute_elapsed_seconds':local['elapsed_seconds'],
 'external_query_elapsed_seconds':ext['elapsed_seconds'],'total_measured_runtime_seconds':total_elapsed,'peak_process_memory_bytes':local['peak_process_memory_bytes'],
 'start_free_C_bytes':local['start_free_C_bytes'],'end_free_C_bytes':end_free,'output_bytes':size_tree(PB)+size_tree(LR),
 'primary_endpoint':{'section':'CID4535','eligible_sections':1,'matched_program_genes':local['primary_program']['matched_gene_count'],'full_program_genes':local['primary_program']['full_gene_count'],
                     'missing_genes':local['primary_program']['missing_genes'],'scores':local['program_scores'],'differences':local['program_differences'],'interpretation':'single-section descriptive effect only'},
 'six_genes':six[['gene','matched','B2_boundary_minus_core']].to_dict('records'),'pseudobulk_inferential_DE':'NOT_RUN_INSUFFICIENT_REPLICATION',
 'liana':local['liana'],'decoupler':local['decoupler'],'top10_liana_interactions':toplr.to_dict('records'),
 'external_queries':ext,'bionexus':{'provenance_sidecar':'COMPLETED','external_envelope_audits':[a['status'] for a in audits],'mcp_host_probe':'FAILED_THEN_TIMED_OUT','machine_verdict':'PENDING'},
 'failed_modules':[{'module':'BioNexus MCP host probe','status':'FAILED_THEN_TIMED_OUT','impact':'No MCP receipt; local sidecar and intake audits completed'},
                   {'module':'external individual lookups','status':f"{ext['final_failures']}_OF_{ext['final_requests']}_FAILED",'impact':'Failures retained; no failed lookup interpreted as absence'}],
 'patient_level_inference':'BLOCKED','machine_verdict':'PENDING','biological_conclusion':'PENDING','S7':'NOT_STARTED'}
dump(PB/'S6-result.json',result); dump(LR/'S6-result.json',result)

def manifest(outdir):
    items=[]
    for p in sorted(outdir.rglob('*'),key=lambda x:str(x).lower()):
        if p.is_file() and p.name not in {'output-manifest.json','SHA256SUMS.txt'} and not p.name.endswith('.tmp'):
            items.append({'path':p.relative_to(outdir).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)})
    dump(outdir/'output-manifest.json',{'created_at_utc':utc(),'root':str(outdir),'files':items,'total_bytes_excluding_manifest':sum(x['bytes'] for x in items)})
    lines=[]
    for p in sorted(outdir.rglob('*'),key=lambda x:str(x).lower()):
        if p.is_file() and p.name!='SHA256SUMS.txt' and not p.name.endswith('.tmp'): lines.append(f'{sha(p)}  {p.relative_to(outdir).as_posix()}')
    (outdir/'SHA256SUMS.txt').write_text('\n'.join(lines)+'\n',encoding='utf-8')
manifest(PB); manifest(LR)
result['output_bytes']=size_tree(PB)+size_tree(LR); result['end_free_C_bytes']=shutil.disk_usage('C:\\').free
dump(PB/'S6-result.json',result); dump(LR/'S6-result.json',result)
# Refresh manifests once after final result rewrite.
manifest(PB); manifest(LR)

if len(prog): prog_top=prog.iloc[prog.boundary_minus_core.abs().sort_values(ascending=False).index[:5]][['pathway','boundary_minus_core']].to_dict('records')
else: prog_top=[]
hall_top=hall.iloc[hall.boundary_minus_core.abs().sort_values(ascending=False).index[:5]][['pathway','boundary_minus_core']].to_dict('records')
checkpoint=f'''# SpatialWarrant S6 checkpoint\n\n- Status: COMPLETED_WITH_PRESERVED_EXTERNAL_QUERY_FAILURES\n- Locked plan SHA-256: `{sha(ROOT/'00_plan'/'analysis-plan.lock.md')}`\n- Execution route: local Python/scverse; not a registered NGS workflow run.\n- Formal S2 path resolved to `03_scrna_reference/S2-run-01`; the user-stated `02_reference/S2-run-01` path was absent and was not substituted with a new dataset.\n- CID4535 region eligibility: B1 {local['region_spots']['B1_boundary_D_le_1']} spots/{local['region_total_UMI']['B1_boundary_D_le_1']:,} UMI; B2 {local['region_spots']['B2_boundary_D_le_2']} spots/{local['region_total_UMI']['B2_boundary_D_le_2']:,} UMI; B3 {local['region_spots']['B3_boundary_D_le_3']} spots/{local['region_total_UMI']['B3_boundary_D_le_3']:,} UMI; core {local['region_spots']['core_D_gt_3']} spots/{local['region_total_UMI']['core_D_gt_3']:,} UMI.\n- Frozen IFN program coverage: {local['primary_program']['matched_gene_count']}/{local['primary_program']['full_gene_count']}; missing: {', '.join(local['primary_program']['missing_genes'])}.\n- Primary B2 boundary − core: {local['program_differences']['B2_boundary_minus_core_primary']:.9f} mean log2(CPM+1). Sensitivities: B1 {local['program_differences']['B1_boundary_minus_core']:.9f}; B3 {local['program_differences']['B3_boundary_minus_core']:.9f}.\n- This is one eligible section and is descriptive only. Population CI, population p value, sign test, and patient-level inference were not computed.\n- Whole-gene table: complete deterministic absolute-effect ranking; PyDESeq2 `NOT_RUN_INSUFFICIENT_REPLICATION`; p and padj blank.\n- LIANA: {local['liana']['status']}, {local['liana'].get('rows',0):,} rows, version {local['liana'].get('liana_version')}; boundary cell-type-specific communication `NOT_IDENTIFIABLE`.\n- Pathways: Hallmark 2024.1.Hs complete; PROGENy decoupler ULM {local['decoupler']['status']} ({local['decoupler'].get('pathways',0)} pathways).\n- External evidence: {ext['final_successes']}/{ext['final_requests']} successful source calls after source-wrapper and raw-source corrections; {ext['final_failures']} true failures retained. Returned context remains UNASSESSED.\n- BioNexus: provenance sidecars and six passive envelope audits completed; MCP host probe failed validation once and then timed out before raw-source correction, so no MCP receipt is claimed.\n- Peak measured process memory: {local['peak_process_memory_bytes']:,} bytes. Start/end C free: {local['start_free_C_bytes']:,}/{result['end_free_C_bytes']:,} bytes. Combined S6 output: {result['output_bytes']:,} bytes.\n- Machine verdict: PENDING. Biological conclusion: PENDING. Human Scientific Adjudication: PENDING.\n- S7: NOT_STARTED. Required inputs are both S6 output directories, their SHA256SUMS/output manifests, `S6-result.json`, this checkpoint, the locked plan, S0-S5 checkpoints, and the preregistered claim file.\n'''
(ROOT/'S6-checkpoint.md').write_text(checkpoint,encoding='utf-8')
(PB/'S6-checkpoint.md').write_text(checkpoint,encoding='utf-8'); (LR/'S6-checkpoint.md').write_text(checkpoint,encoding='utf-8')
manifest(PB); manifest(LR)
print(json.dumps(result,ensure_ascii=False))

