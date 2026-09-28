import scanpy as sc

adata = sc.read_h5ad("flex_cnv.h5ad")

malignant_cnv_clusters = ["3", "4"]

# Start from existing cell_type labels, then override epithelial cells
# that fall in a malignant CNV-cluster
adata.obs["malignancy_status"] = "normal"
is_epithelial = adata.obs["cell_type"].isin(
    ["Epithelial_basal", "Epithelial_differentiated", "Epithelial_glandular"]
)
is_malignant_cluster = adata.obs["cnv_leiden"].isin(malignant_cnv_clusters)
adata.obs.loc[is_epithelial & is_malignant_cluster, "malignancy_status"] = "malignant_epithelial"
adata.obs.loc[is_epithelial & ~is_malignant_cluster, "malignancy_status"] = "normal_epithelial"

print(adata.obs["malignancy_status"].value_counts())

adata.write("flex_final.h5ad")
print("Saved flex_final.h5ad")
