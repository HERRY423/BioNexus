from __future__ import annotations
import gzip, hashlib, importlib.metadata, json, math, os, shutil, sys, time, traceback
from datetime import datetime, timezone
from pathlib import Path
import anndata as ad
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np, pandas as pd, psutil
from scipy import io, sparse

ROOT=Path(sys.argv[1]); PB=ROOT/'08_pseudobulk'/'S6-run-01'; LR=ROOT/'09_liana_literature'/'S6-run-01'
RAW=ROOT/'01_inputs/zenodo4739739/raw_count_matrices-extracted/raw_count_matrices/CID4535_raw_feature_bc_matrix'
HIST=PB/'historical-filtered-matrix-attempt1'; HIST.mkdir(exist_ok=True)
def sha(p):
 h=hashlib.sha256(); f=open(p,'rb')
 for b in iter(lambda:f.read(8*1024*1024),b''): h.update(b)
 f.close(); return h.hexdigest()
def native(v):
 if isinstance(v,dict): return {str(k):native(x) for k,x in v.items()}
 if isinstance(v,(list,tuple,np.ndarray)): return [native(x) for x in list(v)]
 if isinstance(v,(np.integer,)): return int(v)
 if isinstance(v,(np.floating,float)): return float(v) if math.isfinite(float(v)) else None
 if isinstance(v,(np.bool_,bool)): return bool(v)
 return v
def dump(p,v): Path(p).write_text(json.dumps(native(v),indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf-8')
def gmt(path):
 z={}
 for line in path.read_text(encoding='utf-8').splitlines():
  x=line.split('\t'); z[x[0]]=x[2:]
 return z

affected=['primary-program-gene-coverage.json','primary-program-matched-genes.csv','primary-program-missing-genes.csv','primary-program-region-scores.csv','primary-program-B1-B2-B3-sensitivity.csv','prespecified-six-genes.csv','region-pseudobulk-raw-counts.full.csv.gz','descriptive-whole-gene-table.full.csv.gz','pseudobulk-design-status.csv','pathway-hallmark-results.full.csv','pathway-progeny-results.full.csv','pathway-resource-and-coverage.json','S6-integrated-figure.png','S6-local-result.json','S6-result.json','bionexus.provenance.sidecar.json','output-manifest.json','SHA256SUMS.txt']
for n in affected:
 p=PB/n
 if p.exists() and not (HIST/n).exists(): shutil.copy2(p,HIST/n)
if (ROOT/'S6-checkpoint.md').exists() and not (HIST/'S6-checkpoint.initial-filtered-attempt.md').exists(): shutil.copy2(ROOT/'S6-checkpoint.md',HIST/'S6-checkpoint.initial-filtered-attempt.md')

t0=time.perf_counter(); start= datetime.now(timezone.utc).isoformat(); free0=shutil.disk_usage('C:\\').free
if free0<20*1024**3: raise RuntimeError('disk below 20 GiB')
expected={'matrix.mtx.gz':'c0b37824b8647b11da77054939e1215e60664d2eb480202feaeab78a1dbc2be9','barcodes.tsv.gz':'856fa22b6fb346931480b232fef560dec4a42ce7ea8237ffa207d2499b8d7274','features.tsv.gz':'0a6e9f09c1343264d465b73d0e3b93efa9ccb3d7643cccf0600d81f5b20478d7'}
for n,h in expected.items():
 if sha(RAW/n)!=h: raise RuntimeError(f'raw input hash mismatch {n}')
features=pd.read_csv(RAW/'features.tsv.gz',sep='\t',header=None,names=['gene_id','gene_symbol','feature_type'],dtype=str)
barcodes=pd.read_csv(RAW/'barcodes.tsv.gz',sep='\t',header=None,names=['barcode'],dtype=str)
with gzip.open(RAW/'matrix.mtx.gz','rb') as f: X=io.mmread(f)
if not sparse.issparse(X): raise RuntimeError('raw mtx did not remain sparse')
X=X.tocsc(copy=False)
if X.shape!=(len(features),len(barcodes)): raise RuntimeError(f'raw dimensions mismatch {X.shape}')
if not np.all(np.isfinite(X.data)) or np.any(X.data<0) or np.any(X.data!=np.floor(X.data)): raise RuntimeError('raw count values invalid')
mask=pd.read_csv(ROOT/'04_visium_qc/S3-run-03/CID4535/geometry-boundary-core-masks.csv').set_index('barcode')
bmap=pd.Series(np.arange(len(barcodes)),index=barcodes.barcode)
if mask.index.duplicated().any() or barcodes.barcode.duplicated().any(): raise RuntimeError('duplicate barcodes')
if not mask.index.isin(bmap.index).all(): raise RuntimeError('mask barcode absent from raw matrix')
colidx=bmap.loc[mask.index].to_numpy()
Xsel=X[:,colidx]
regions={'B1_boundary_D_le_1':mask.boundary_invasive_d1.astype(bool).to_numpy(),'B2_boundary_D_le_2':mask.boundary_invasive_d2.astype(bool).to_numpy(),'B3_boundary_D_le_3':mask.boundary_invasive_d3.astype(bool).to_numpy(),'core_D_gt_3':mask.core_invasive_d_gt_3.astype(bool).to_numpy()}
counts={k:np.asarray(Xsel[:,m].sum(axis=1)).ravel().astype(np.int64) for k,m in regions.items()}
totals={k:int(v.sum()) for k,v in counts.items()}; spots={k:int(m.sum()) for k,m in regions.items()}
for k in regions:
 if spots[k]<20 or totals[k]<100000: raise RuntimeError(f'eligibility failed {k}')
cpm={k:v.astype(float)/totals[k]*1e6 for k,v in counts.items()}; logcpm={k:np.log2(v+1) for k,v in cpm.items()}
sets=gmt(ROOT/'01_inputs/resources/h.all.v2024.1.Hs.symbols.gmt'); primary=sets['HALLMARK_INTERFERON_GAMMA_RESPONSE']
sym_to_idx={s:int(ix[0]) for s,ix in features.groupby('gene_symbol').indices.items() if len(ix)==1}
matched=[g for g in primary if g in sym_to_idx]; missing=[g for g in primary if g not in sym_to_idx]; idx=np.array([sym_to_idx[g] for g in matched])
if len(matched)!=196: raise RuntimeError(f'expected reverified 196/200, got {len(matched)}/200 missing={missing}')
scores={k:float(logcpm[k][idx].mean()) for k in regions}; delta={'B1_boundary_minus_core':scores['B1_boundary_D_le_1']-scores['core_D_gt_3'],'B2_boundary_minus_core_primary':scores['B2_boundary_D_le_2']-scores['core_D_gt_3'],'B3_boundary_minus_core':scores['B3_boundary_D_le_3']-scores['core_D_gt_3']}
coverage={'program':'HALLMARK_INTERFERON_GAMMA_RESPONSE','systematic_id':'M5913','release':'2024.1.Hs','full_gene_count':200,'matched_gene_count':196,'coverage_fraction':0.98,'matched_genes':matched,'missing_genes':missing,'alias_substitution':'NONE','score_denominator':'196 exact-symbol unambiguous features','score_formula':'mean_gene(log2(1 + 1e6 * region raw gene count / region total raw UMI))','count_source':'publisher raw_feature_bc_matrix, not S3 filtered-feature h5ad','raw_input_hashes':expected,'correction_lineage':str(HIST)}
dump(PB/'primary-program-gene-coverage.json',coverage); pd.DataFrame({'gene':matched}).to_csv(PB/'primary-program-matched-genes.csv',index=False); pd.DataFrame({'gene':missing}).to_csv(PB/'primary-program-missing-genes.csv',index=False)
pd.DataFrame([{'section':'CID4535','region':k,'spots':spots[k],'total_UMI':totals[k],'matched_program_genes':196,'mean_log2_CPM_plus_1_score':scores[k],'single_section_descriptive':True} for k in regions]).to_csv(PB/'primary-program-region-scores.csv',index=False)
pd.DataFrame([{'section':'CID4535',**delta,'eligible_sections':1,'population_CI':np.nan,'population_p_value':np.nan,'sign_test':'NOT_RUN_SINGLE_ELIGIBLE_SECTION','patient_level_inference':'BLOCKED'}]).to_csv(PB/'primary-program-B1-B2-B3-sensitivity.csv',index=False)
display=[]
for g in ['CXCL9','CXCL10','CXCL11','IDO1','STAT1','IRF1']:
 j=sym_to_idx.get(g); row={'gene':g,'matched':j is not None}
 if j is not None:
  for k in regions: row.update({f'{k}_raw_count':int(counts[k][j]),f'{k}_CPM':float(cpm[k][j]),f'{k}_log2_CPM_plus_1':float(logcpm[k][j])})
  row['B2_boundary_minus_core']=float(logcpm['B2_boundary_D_le_2'][j]-logcpm['core_D_gt_3'][j])
 else: row['B2_boundary_minus_core']=np.nan
 display.append(row)
pd.DataFrame(display).to_csv(PB/'prespecified-six-genes.csv',index=False)
rawtab=pd.DataFrame({'gene_id':features.gene_id,'gene_symbol':features.gene_symbol,'feature_type':features.feature_type,**{f'{k}_raw_count':v for k,v in counts.items()}}); rawtab.to_csv(PB/'region-pseudobulk-raw-counts.full.csv.gz',index=False,compression='gzip')
whole=pd.DataFrame({'gene_id':features.gene_id,'gene_symbol':features.gene_symbol,'feature_type':features.feature_type,'B2_boundary_raw_count':counts['B2_boundary_D_le_2'],'core_raw_count':counts['core_D_gt_3'],'B2_boundary_CPM':cpm['B2_boundary_D_le_2'],'core_CPM':cpm['core_D_gt_3'],'B2_boundary_log2_CPM_plus_1':logcpm['B2_boundary_D_le_2'],'core_log2_CPM_plus_1':logcpm['core_D_gt_3']})
whole['B2_boundary_minus_core_log2_CPM_plus_1']=whole.B2_boundary_log2_CPM_plus_1-whole.core_log2_CPM_plus_1; whole['absolute_descriptive_difference']=whole.B2_boundary_minus_core_log2_CPM_plus_1.abs(); whole=whole.sort_values(['absolute_descriptive_difference','gene_id'],ascending=[False,True],kind='mergesort').reset_index(drop=True); whole.insert(0,'deterministic_rank',np.arange(1,len(whole)+1)); whole['inferential_DE_status']='NOT_RUN_INSUFFICIENT_REPLICATION'; whole['p_value']=np.nan; whole['padj']=np.nan; whole.to_csv(PB/'descriptive-whole-gene-table.full.csv.gz',index=False,compression='gzip')
pd.DataFrame([{'section':'CID4535','B2_boundary_spots':spots['B2_boundary_D_le_2'],'core_spots':spots['core_D_gt_3'],'B2_boundary_total_UMI':totals['B2_boundary_D_le_2'],'core_total_UMI':totals['core_D_gt_3'],'inferential_DE_status':'NOT_RUN_INSUFFICIENT_REPLICATION','reason':'one boundary/core pseudobulk pair; no biological replication and no full-rank inferential design','p_value':np.nan,'padj':np.nan}]).to_csv(PB/'pseudobulk-design-status.csv',index=False)
# Symbol-aggregated matrix for secondary pathway scoring; total library denominator remains full raw UMI.
symbol_order=sorted(features.gene_symbol.unique()); sym_counts={k:pd.Series(v,index=features.gene_symbol).groupby(level=0).sum().reindex(symbol_order).to_numpy() for k,v in counts.items()}; sym_cpm={k:v/totals[k]*1e6 for k,v in sym_counts.items()}; sym_log={k:np.log2(v+1) for k,v in sym_cpm.items()}; symindex=pd.Index(symbol_order)
rows=[]
for name,members in sets.items():
 use=[g for g in members if g in symindex]; gi=symindex.get_indexer(use); b=float(sym_log['B2_boundary_D_le_2'][gi].mean()) if len(gi) else np.nan; c=float(sym_log['core_D_gt_3'][gi].mean()) if len(gi) else np.nan
 rows.append({'resource':'MSigDB Hallmark','release':'2024.1.Hs','pathway':name,'full_genes':len(members),'matched_genes':len(use),'coverage_fraction':len(use)/len(members),'boundary_activity_mean_log2_CPM_plus_1':b,'core_activity_mean_log2_CPM_plus_1':c,'boundary_minus_core':b-c,'method':'symbol-aggregated raw counts, unweighted matched-gene mean; descriptive'})
pd.DataFrame(rows).sort_values('pathway').to_csv(PB/'pathway-hallmark-results.full.csv',index=False)
pr=pd.read_csv(ROOT/'01_inputs/resources/PROGENy-omnipath-snapshot.tsv',sep='\t',dtype=str); w=pr[pr.label.isin(['pathway','weight'])].pivot_table(index=['record_id','genesymbol'],columns='label',values='value',aggfunc='first').reset_index().dropna(subset=['pathway','weight']); w['weight']=pd.to_numeric(w.weight,errors='coerce'); net=w.dropna(subset=['weight']).rename(columns={'pathway':'source','genesymbol':'target'})[['source','target','weight']]; net=net[net.target.isin(symindex)].groupby(['source','target'],as_index=False).weight.mean(); expr=pd.DataFrame([sym_log['B2_boundary_D_le_2'],sym_log['core_D_gt_3']],index=['B2_boundary_D_le_2','core_D_gt_3'],columns=symindex)
import decoupler as dc
score=dc.mt.ulm(expr,net,tmin=5,raw=False,empty=False,bsize=250000,verbose=False)
if not isinstance(score,pd.DataFrame): score=pd.DataFrame(score[0] if isinstance(score,tuple) else score,index=expr.index)
if score.shape[0]==2: score.index=expr.index
prows=[{'resource':'PROGENy OmniPath frozen snapshot','pathway':str(p),'boundary_activity':float(score.loc['B2_boundary_D_le_2',p]),'core_activity':float(score.loc['core_D_gt_3',p]),'boundary_minus_core':float(score.loc['B2_boundary_D_le_2',p]-score.loc['core_D_gt_3',p]),'matched_targets':int(net.loc[net.source==p,'target'].nunique()),'method':'decoupler ULM; descriptive'} for p in score.columns]
pd.DataFrame(prows).sort_values('pathway').to_csv(PB/'pathway-progeny-results.full.csv',index=False)
dump(PB/'pathway-resource-and-coverage.json',{'hallmark':{'source':str(ROOT/'01_inputs/resources/h.all.v2024.1.Hs.symbols.gmt'),'sha256':sha(ROOT/'01_inputs/resources/h.all.v2024.1.Hs.symbols.gmt'),'sets':len(sets)},'progeny':{'source':str(ROOT/'01_inputs/resources/PROGENy-omnipath-snapshot.tsv'),'sha256':sha(ROOT/'01_inputs/resources/PROGENy-omnipath-snapshot.tsv'),'network_edges_after_feature_intersection':len(net),'status':{'status':'COMPLETED','decoupler_version':importlib.metadata.version('decoupler'),'pathways':len(prows)}},'primary_set_unchanged':True,'count_source':'publisher raw feature matrix'})
top20=whole.head(20)[['deterministic_rank','gene_id','gene_symbol','B2_boundary_minus_core_log2_CPM_plus_1','absolute_descriptive_difference']]; top20.to_csv(LR/'top20-descriptive-genes-for-external-evidence.raw-source-v2.csv',index=False); top20.to_csv(LR/'top20-descriptive-genes-for-external-evidence.csv',index=False)
# Replace only gene targets; keep the already-computed LIANA and prespecified targets.
qt=json.loads((LR/'external-evidence-query-targets.json').read_text(encoding='utf-8')); qt['top20_genes']=[{'deterministic_rank':int(r.deterministic_rank),'gene_id':str(r.gene_symbol) if pd.notna(r.gene_symbol) else str(r.gene_id),'ensembl_gene_id':str(r.gene_id),'B2_boundary_minus_core_log2_CPM_plus_1':float(r.B2_boundary_minus_core_log2_CPM_plus_1),'absolute_descriptive_difference':float(r.absolute_descriptive_difference)} for _,r in top20.iterrows()]; qt['selection_rule']='genes: publisher raw-matrix feature effects by absolute descriptive B2-core difference descending, Ensembl gene_id tie-break; interactions unchanged'; dump(LR/'external-evidence-query-targets.raw-source-v2.json',qt); dump(LR/'external-evidence-query-targets.json',qt)
# Figure refresh from corrected raw counts; LIANA panel retained.
tlr=pd.read_csv(LR/'liana-top10-for-external-evidence.csv'); fig,ax=plt.subplots(2,2,figsize=(13,9),constrained_layout=True); order=list(regions); ax[0,0].bar(['B1','B2','B3','Core'],[scores[x] for x in order],color=['#7B6FD0','#4C78A8','#72B7B2','#B9B9B9']); ax[0,0].set_ylabel('Mean log2(CPM+1)'); ax[0,0].set_title('Frozen IFN-γ program (196/200 matched)'); dd=pd.DataFrame(display); ax[0,1].barh(dd.gene,dd.B2_boundary_minus_core,color=['#E45756' if x>=0 else '#4C78A8' for x in dd.B2_boundary_minus_core]); ax[0,1].axvline(0,color='black',lw=.8); ax[0,1].set_title('Prespecified display genes'); t=whole.head(10).iloc[::-1]; labs=[f'{s}\n{g}' for s,g in zip(t.gene_symbol,t.gene_id)]; ax[1,0].barh(labs,t.B2_boundary_minus_core_log2_CPM_plus_1,color=['#F58518' if x>=0 else '#54A24B' for x in t.B2_boundary_minus_core_log2_CPM_plus_1]); ax[1,0].axvline(0,color='black',lw=.8); ax[1,0].set_title('Largest raw-matrix descriptive effects'); labs=[f"{r.ligand_complex}→{r.receptor_complex}\n{r.source}→{r.target}" for _,r in tlr.head(6).iterrows()][::-1]; vals=(-np.log10(np.maximum(tlr.head(6).magnitude_rank.to_numpy(),1e-300)))[::-1]; ax[1,1].barh(range(len(labs)),vals,color='#B279A2'); ax[1,1].set_yticks(range(len(labs)),labels=labs,fontsize=7); ax[1,1].set_title('Top inferred interactions'); fig.suptitle('SpatialWarrant S6 | CID4535 descriptive boundary analysis',fontsize=15,fontweight='bold'); fig.savefig(PB/'S6-integrated-figure.png',dpi=220,bbox_inches='tight'); plt.close(fig)
local=json.loads((HIST/'S6-local-result.json').read_text()); local.update({'status':'LOCAL_COMPUTATION_COMPLETED_RAW_SOURCE_CORRECTED','ended_at_utc':datetime.now(timezone.utc).isoformat(),'elapsed_seconds':float(local['elapsed_seconds'])+time.perf_counter()-t0,'peak_process_memory_bytes':max(int(local['peak_process_memory_bytes']),int(getattr(psutil.Process().memory_info(),'peak_wset',psutil.Process().memory_info().rss))),'current_free_C_bytes':shutil.disk_usage('C:\\').free,'primary_program':coverage,'region_spots':spots,'region_total_UMI':totals,'program_scores':scores,'program_differences':delta,'decoupler':{'status':'COMPLETED','resource_sha256':sha(ROOT/'01_inputs/resources/PROGENy-omnipath-snapshot.tsv'),'network_edges':len(net),'decoupler_version':importlib.metadata.version('decoupler'),'pathways':len(prows)},'correction':'Publisher raw_feature_bc_matrix used for pseudobulk and pathway calculations; prior filtered-h5ad attempt preserved under historical-filtered-matrix-attempt1.'}); dump(PB/'S6-local-result.json',local); dump(LR/'S6-local-result.json',local)
dump(PB/'raw-count-source-correction.v2.json',{'status':'COMPLETED','reason':'S3 h5ad contained filtered 19,237-feature matrix and yielded 195/200; the frozen feature lock and S6 raw-count requirement bind publisher raw_feature_bc_matrix with 36,601 features and 196/200 exact coverage.','historical_attempt':str(HIST),'raw_input_hashes':expected,'matrix_shape':list(X.shape),'selected_mask_barcodes':len(mask),'matched_program_genes':196,'missing_program_genes':missing,'completed_at_utc':datetime.now(timezone.utc).isoformat()})
print(json.dumps({'status':'COMPLETED','matched':196,'missing':missing,'scores':scores,'deltas':delta,'spots':spots,'totals':totals,'top20':top20[['gene_id','gene_symbol','B2_boundary_minus_core_log2_CPM_plus_1']].to_dict('records')}))
