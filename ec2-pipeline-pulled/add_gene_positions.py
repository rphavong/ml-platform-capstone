import scanpy as sc
import infercnvpy as cnv

adata_flex = sc.read_h5ad("flex_clustered.h5ad")

cnv.io.genomic_position_from_gtf(
    "gencode.v44.genes_only.gtf.gz",
    adata=adata_flex,
)

# Check how many genes got positions assigned vs. dropped
has_position = adata_flex.var["chromosome"].notna().sum()
print(f"Genes with genomic position: {has_position} / {adata_flex.n_vars}")

adata_flex.write("flex_clustered.h5ad")
print("Saved with genomic positions")
