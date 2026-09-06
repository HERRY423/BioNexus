import json,hashlib,re,io,csv,sys,shutil
from pathlib import Path
import pandas as pd,numpy as np,h5py
from anndata.io import read_elem
R=Path(r'C:\Plugin\BioNexus\review\spatialwarrant-run-01')
W=Path(__file__).parent
cache={}
def h(p):
 p=Path(p)
 if str(p) in cache:return cache[str(p)]
 s=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(8*1024*1024),b''):s.update(b)
 cache[str(p)]=s.hexdigest();return s.hexdigest()
stages={'S2':R/'03_scrna_reference/S2-run-01','S3':R/'04_visium_qc/S3-run-03','S4':R/'06_deconvolution/S4-run-02','S5':R/'07_niches/S5-run-02','S6pb':R/'08_pseudobulk/S6-run-01','S6lr':R/'09_liana_literature/S6-run-01'}
report={'free_C_bytes':shutil.disk_usage('C:\\').free,'plan_sha256':h(R/'00_plan/analysis-plan.lock.md'),'manifests':{},'input_verifications':[],'joins':[],'notes':[],'inventory':{}}
for s,d in stages.items():
 for name in ['SHA256SUMS.txt','SHA256SUMS.postaudit.v1.txt']:
  m=d/name
  if not m.exists():continue
  bad=[];n=0
  for line in m.read_text(encoding='utf-8-sig').splitlines():
   if not line.strip():continue
   expected,rel=line.split(maxsplit=1);p=d/rel.lstrip('* ')
   n+=1
   if not p.exists() or h(p)!=expected.lower():bad.append({'path':str(p),'expected':expected,'observed':h(p) if p.exists() else None})
  report['manifests'][s+'/'+name]={'checked':n,'mismatches':bad,'manifest_sha256':h(m)}
 for nm in ['input-manifest.json','output-manifest.json','S6-result.json',s+'-result.json']:
  p=d/nm
  if p.exists():
   val=json.loads(p.read_text(encoding='utf-8-sig'));report['inventory'][str(p)]={'sha256':h(p),'top_keys':list(val)}
   if nm=='input-manifest.json':
    for row in val.get('files',[]):
     pp=Path(row.get('path',''));eh=row.get('sha256')
     if eh:report['input_verifications'].append({'path':str(pp),'matches':pp.exists() and h(pp)==eh.lower(),'sha256':h(pp) if pp.exists() else None})
summary=pd.read_csv(stages['S3']/'section-summary.csv')
t=pd.read_csv(stages['S4']/'proportions_tangram.csv.gz');n=pd.read_csv(stages['S4']/'proportions_marker_nnls.csv.gz');i=pd.read_csv(stages['S4']/'ingest_labels.csv.gz');ni=pd.read_csv(stages['S5']/'niche_labels.csv.gz')
for sec in summary.section:
 d=stages['S3']/sec
 with h5py.File(d/f'{sec}.h5ad','r') as f: obs=read_elem(f['obs']); coords=read_elem(f['obsm']['spatial']) if 'spatial' in f['obsm'] else obs[['px_col','px_row']].to_numpy()
 def compare(df):
  z=df[df.section.astype(str)==sec];return {'rows':len(z),'duplicate_barcode':int(z.barcode.duplicated().sum()),'keyset_matches_s3':set(z.barcode)==set(obs.index)}
 report['joins'].append({'section':sec,'s3_spots':len(obs),'s3_barcodes_unique':obs.index.is_unique,'coordinates_finite':bool(np.isfinite(coords).all()),'coordinates_rows':len(coords),'S4_tangram':compare(t),'S4_nnls':compare(n),'S4_ingest':compare(i),'S5_niche':compare(ni),'obs_columns':list(obs.columns)})
 report['inventory'][str(d/'spot-QC-and-metadata.csv.gz')]={'columns':pd.read_csv(d/'spot-QC-and-metadata.csv.gz',nrows=1).columns.tolist()}
rawclaim=Path(r'C:\Plugin\BioNexus\review\spatialwarrant-revised-design\CLAIMS_PREREGISTERED.csv')
plan=(R/'00_plan/analysis-plan.lock.md').read_text(encoding='utf-8-sig')
block=re.search(r'(claim_id,stage,claim_class,preregistered_statement[^\n]*\n.*?)(?:\n```|\Z)',plan,re.S).group(1)
cp=list(csv.DictReader(io.StringIO(block)));src=list(csv.DictReader(io.StringIO(rawclaim.read_text(encoding='utf-8-sig'))))
report['claims']={'source':str(rawclaim),'source_sha256':h(rawclaim),'locked_copy':'CSV appendix in analysis-plan.lock.md','semantic_equal':cp==src,'rows':src,'standalone_locked_copy_found':False}
report['s6']=json.loads((stages['S6pb']/'S6-result.json').read_text(encoding='utf-8-sig'))
cap=json.loads((R/'00_plan/plugin-capability-check.json').read_text(encoding='utf-8-sig'));report['plugin_roles']=[{k:v for k,v in p.items() if k in ['name','manifest_version','role','observed','calls','compatible_registered_workflow_found']} for p in cap['plugins']]
q=pd.read_csv(stages['S6lr']/'external-query-log.final.csv'); pm=[]
for _,row in q[q.source=='pubmed'].iterrows():
 raw=Path(row.raw_path)
 if raw.exists():
  try:z=json.loads(raw.read_text(encoding='utf-8-sig'));pm.append({'target':row.target,'keys':list(z),'ids':z.get('esearchresult',{}).get('idlist',[]),'count':z.get('esearchresult',{}).get('count'),'warnings':z.get('esearchresult',{}).get('warninglist')})
  except Exception as e:pm.append({'target':row.target,'read_error':str(e)})
report['literature_retrieval']=pm
report['s6_query_script']=str(stages['S6lr']/'run_s6_external_queries.py')
report['pseudobulk_table_rows']=len(pd.read_csv(stages['S6pb']/'descriptive-whole-gene-table.full.csv.gz'))
report['hashes']=cache
(W/'s7_inspection.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
print(json.dumps({'manifests':report['manifests'],'input_hash_mismatches':[x for x in report['input_verifications'] if not x['matches']],'claims':report['claims'],'joins':report['joins'],'literature':pm[:3],'pseudobulk_table_rows':report['pseudobulk_table_rows'],'coordinate_csv_columns':report['inventory'][str(stages['S3']/'CID4535'/'spot-QC-and-metadata.csv.gz')]},ensure_ascii=False))
