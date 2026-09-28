import scanpy as sc

adata_flex = sc.read_h5ad("flex_clustered.h5ad")

cluster_to_celltype = {
    "0": "Fibroblast", "3": "Fibroblast_CAF",
    "1": "Epithelial_basal", "12": "Epithelial_basal",
    "9": "Epithelial_differentiated",
    "16": "Epithelial_glandular",
    "2": "T_cell", "4": "T_cell", "5": "T_cell_exhausted",
    "6": "Dendritic_cell",
    "7": "Macrophage",
    "8": "B_cell",
    "11": "pDC",
    "13": "Plasma_cell",
    "10": "Endothelial_vascular",
    "15": "Endothelial_lymphatic",
    "14": "Pericyte",
    "17": "Mast_cell",
}

adata_flex.obs["cell_type"] = adata_flex.obs["leiden"].map(cluster_to_celltype).astype("category")
print(adata_flex.obs["cell_type"].value_counts())

adata_flex.write("flex_clustered.h5ad")
print("Saved with cell_type annotations")
