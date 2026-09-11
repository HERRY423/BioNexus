summary = metadata.groupby('donor').size()
sc.tl.rank_genes_groups(adata, groupby='condition')
