import scanpy as sc
import infercnvpy as cnv

adata = sc.read_h5ad("flex_clustered.h5ad")

# Drop genes with no genomic position (can't place them on a chromosome)
adata = adata[:, adata.var["chromosome"].notna()].copy()
print("Genes used for CNV inference:", adata.n_vars)

# Immune cell types = our "normal/diploid" reference.
# Rationale: immune cells infiltrating a tumor are still genetically normal —
# they didn't originate from the malignant clone, so they should show no
# systematic copy-number pattern. Epithelial cells get compared against this baseline.
reference_cats = [
    "T_cell", "T_cell_exhausted", "Dendritic_cell", "Macrophage",
    "B_cell", "pDC", "Plasma_cell", "Mast_cell",
]

# n_jobs=1: deliberately not parallelizing across chromosomes here.
# infercnvpy's parallelism trades memory for speed (each worker holds its own
# copy of data) — given our memory history today, slower-but-safe wins.
cnv.tl.infercnv(
    adata,
    reference_key="cell_type",
    reference_cat=reference_cats,
    window_size=100,
    n_jobs=1,
)

# Cluster cells by their CNV profile (not by gene expression this time —
# by how abnormal their chromosome-level pattern looks)
cnv.tl.pca(adata, n_comps=20)
cnv.pp.neighbors(adata)
cnv.tl.leiden(adata, key_added="cnv_leiden")

# A single summary number per cell: overall "how abnormal is this CNV profile"
cnv.tl.cnv_score(adata, groupby="cnv_leiden")

print("\nMean CNV score per CNV-cluster:")
print(adata.obs.groupby("cnv_leiden")["cnv_score"].mean().sort_values())

print("\nCell type composition of each CNV-cluster:")
print(adata.obs.groupby(["cnv_leiden", "cell_type"]).size().unstack(fill_value=0))

adata.write("flex_cnv.h5ad")
print("\nSaved flex_cnv.h5ad")
