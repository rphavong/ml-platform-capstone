import scanpy as sc

adata_flex = sc.read_h5ad("flex_clustered.h5ad")

# Find marker genes for each cluster
sc.tl.rank_genes_groups(adata_flex, groupby="leiden", method="wilcoxon")

# Print top 10 marker genes per cluster
for cluster in adata_flex.obs["leiden"].cat.categories:
    top_genes = [adata_flex.uns["rank_genes_groups"]["names"][cluster][i] for i in range(10)]
    print(f"Cluster {cluster}: {top_genes}")

adata_flex.write("flex_clustered.h5ad")  # save with marker gene results included
