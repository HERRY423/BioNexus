"""Inspect this completed run; no model refit or threshold changes."""
import json, hashlib
from pathlib import Path
import numpy as np
import pandas as pd
from formulaic import model_matrix
rec=Path(__file__).resolve().parent; out=rec.with_name('workbench-run-01')
def sha(p):
    with p.open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()
m=json.loads((out/'analysis_manifest.json').read_text())
hash_checks={n:sha(out/n)==v for n,v in m['output_sha256'].items()}
assert all(hash_checks.values())
d=pd.read_csv(out/'pseudobulk_design.csv',dtype=str).set_index('sample_id'); c=pd.read_csv(out/'pseudobulk_counts.csv.gz',index_col=0)
de=pd.read_csv(out/'paired_pseudobulk_de.csv'); scores=pd.read_csv(out/'prespecified_genes_by_donor.csv',dtype={'donor':str}); cells=pd.read_csv(out/'cell_metadata_and_qc.csv.gz',index_col=0,dtype={'donor':str})
assert c.index.is_unique and d.index.is_unique and c.index.equals(d.index)
assert d.shape[0]==16 and d.donor.nunique()==8 and d.groupby('donor').condition.nunique().eq(2).all()
assert np.isfinite(c.values).all() and (c.values>=0).all() and np.equal(c.values,np.floor(c.values)).all()
matrix=model_matrix('~ donor + condition',d); rank=int(np.linalg.matrix_rank(matrix)); assert rank==matrix.shape[1]
kept=(c>=10).sum(axis=0)>=4; assert set(c.columns[kept])==set(de.ensembl_id)
rows=[]
for gene in ['ISG15','IFIT1','MX1','STAT1']:
    paired=scores[scores.gene.eq(gene)].pivot(index='donor',columns='condition',values='value'); delta=paired.stim-paired.ctrl
    item=de[de.gene_symbol.eq(gene)].iloc[0].to_dict(); item.update(donors_increasing=int(delta.gt(0).sum()),donors_decreasing=int(delta.lt(0).sum()),paired_log2cpm_delta_min=float(delta.min()),paired_log2cpm_delta_max=float(delta.max()),paired_log2cpm_delta_median=float(delta.median())); rows.append(item)
mono=cells[cells.source_cell_type.eq('CD14+ Monocytes')]
sample_qc=d.copy(); sample_qc['n_cells']=mono.groupby(['donor','condition']).size().reindex(pd.MultiIndex.from_frame(d[['donor','condition']])).to_numpy(); sample_qc['total_umi']=c.sum(axis=1); sample_qc['detected_genes']=(c>0).sum(axis=1)
sample_qc.to_csv(rec/'sample_qc_verified.csv')
pd.DataFrame(rows).to_csv(rec/'prespecified_gene_results_verified.csv',index=False)
report={'scope':'completed-output integrity and descriptive checks only; no independent biological replication','output_hashes_match_manifest':hash_checks,'samples':len(d),'donors':d.donor.nunique(),'design_matrix_columns':list(matrix.columns),'design_matrix_rank':rank,'condition_library_confounding_resolved':False,'input_genes':c.shape[1],'genes_passing_fixed_filter':int(kept.sum()),'genes_filtered_before_model':int((~kept).sum()),'de_rows':len(de),'nonmissing_pvalue':int(de.pvalue.notna().sum()),'nonmissing_padj':int(de.padj.notna().sum()),'padj_missing':int(de.padj.isna().sum()),'significant_padj_005':int(de.padj.lt(.05).sum()),'significant_padj_005_abs_lfc_1':int((de.padj.lt(.05)&de.log2FoldChange.abs().ge(1)).sum()),'significant_up':int((de.padj.lt(.05)&de.log2FoldChange.gt(0)).sum()),'significant_down':int((de.padj.lt(.05)&de.log2FoldChange.lt(0)).sum()),'prespecified_genes':rows,'sample_umi_min':int(c.sum(axis=1).min()),'sample_umi_max':int(c.sum(axis=1).max()),'monocyte_n_genes_min':int(mono.n_genes.min()),'monocyte_n_genes_median':float(mono.n_genes.median()),'monocyte_n_genes_lt_200':int(mono.n_genes.lt(200).sum()),'mitochondrial_qc':'NOT_ASSESSED_ZERO_OBSERVED_MITO_COUNTS'}
(rec/'verification.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
print(json.dumps(report,indent=2,allow_nan=False))
