import scanpy as sc
sc.pp.normalize_total(adata)
sc.pp.log1p(adata)
sc.tl.score_genes(adata, gene_list=panel, score_name='panel_score')
