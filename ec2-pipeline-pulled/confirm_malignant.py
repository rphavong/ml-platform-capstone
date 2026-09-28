import scanpy as sc

adata = sc.read_h5ad("flex_cnv.h5ad")

# CDKN2A (p16) is the clinical gold-standard surrogate marker for HPV-driven
# cervical transformation. MKI67/TOP2A are proliferation markers — malignant
# cells divide more than their normal counterparts.
malignancy_markers = ["CDKN2A", "MKI67", "TOP2A"]
present = [g for g in malignancy_markers if g in adata.var_names]
print("Markers found in data:", present)

sc.tl.score_genes(adata, present, score_name="malignancy_score")

print("\nMean malignancy score by CNV-cluster (sorted):")
print(adata.obs.groupby("cnv_leiden", observed=True)["malignancy_score"].mean().sort_values())

adata.write("flex_cnv.h5ad")
