import scanpy as sc

adata = sc.read_h5ad("xenium_predicted.h5ad")

# Center a window on the malignant cell centroid - guarantees our
# subset actually contains real tumor tissue, not an arbitrary crop
malignant_coords = adata.obsm["spatial"][adata.obs["predicted_label"] == "malignant_epithelial"]
center_x, center_y = malignant_coords.mean(axis=0)
half_window = 1000  # microns in each direction from center

x, y = adata.obsm["spatial"][:, 0], adata.obsm["spatial"][:, 1]
in_region = (
    (x > center_x - half_window) & (x < center_x + half_window) &
    (y > center_y - half_window) & (y < center_y + half_window)
)

adata_region = adata[in_region].copy()
print("Region subset:", adata_region.shape)
print(adata_region.obs["predicted_label"].value_counts())

adata_region.write("xenium_region.h5ad")
print("Saved xenium_region.h5ad")
