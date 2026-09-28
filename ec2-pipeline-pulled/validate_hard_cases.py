import scanpy as sc
import numpy as np

adata = sc.read_h5ad("xenium_region.h5ad")

# The genuinely hard cases: cells Model 1 itself was unsure about
low_confidence = adata.obs["prediction_confidence"] < adata.obs["prediction_confidence"].median()
print(f"Low-confidence cells: {low_confidence.sum()} / {adata.n_obs}")
print("\nTheir Model 1 predicted labels:")
print(adata.obs.loc[low_confidence, "predicted_label"].value_counts())
