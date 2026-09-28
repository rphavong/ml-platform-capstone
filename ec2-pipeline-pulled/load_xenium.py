import scanpy as sc
import pandas as pd

# Load expression matrix
adata_xen = sc.read_10x_h5("cell_feature_matrix.h5")
adata_xen.var_names_make_unique()
print("Loaded expression matrix:", adata_xen)

# Load per-cell spatial coordinates and QC metadata
cells_df = pd.read_parquet("cells.parquet")
print("\ncells.parquet columns:", cells_df.columns.tolist())
print(cells_df.head())

# Align cells_df to adata's cell order (critical - must match exactly)
cells_df = cells_df.set_index("cell_id")
cells_df = cells_df.loc[adata_xen.obs_names]

# Attach spatial coordinates (column names can vary slightly by Xenium version,
# we'll confirm from the printed columns above before trusting this)
adata_xen.obsm["spatial"] = cells_df[["x_centroid", "y_centroid"]].values
adata_xen.obs = adata_xen.obs.join(cells_df)

print("\nFinal object:", adata_xen)
adata_xen.write("xenium_raw.h5ad")
print("Saved xenium_raw.h5ad")
