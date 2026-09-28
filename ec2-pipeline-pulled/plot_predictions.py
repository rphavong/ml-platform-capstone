import scanpy as sc
import matplotlib
matplotlib.use("Agg")  # headless server, no display available
import matplotlib.pyplot as plt

adata = sc.read_h5ad("xenium_predicted.h5ad")

fig, ax = plt.subplots(figsize=(14, 14))

# Plot everything else faintly, malignant cells prominently on top
is_malignant = adata.obs["predicted_label"] == "malignant_epithelial"

ax.scatter(
    adata.obsm["spatial"][~is_malignant, 0],
    adata.obsm["spatial"][~is_malignant, 1],
    s=0.5, c="lightgray", alpha=0.3, label="other"
)
ax.scatter(
    adata.obsm["spatial"][is_malignant, 0],
    adata.obsm["spatial"][is_malignant, 1],
    s=0.5, c="red", alpha=0.6, label="malignant_epithelial"
)

ax.set_title("Predicted malignant regions - Xenium Prime cervical cancer")
ax.legend(markerscale=20)
ax.set_aspect("equal")
ax.invert_yaxis()  # image coordinates typically have y increasing downward

plt.savefig("malignant_spatial_map.png", dpi=150, bbox_inches="tight")
print("Saved malignant_spatial_map.png")
