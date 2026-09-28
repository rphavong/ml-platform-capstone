import scanpy as sc
import pandas as pd

pd.set_option("display.max_columns", None)
pd.set_option("display.width", 250)

adata = sc.read_h5ad("flex_cnv.h5ad")

print("Cells per CNV-cluster:")
print(adata.obs["cnv_leiden"].value_counts().sort_index())

print("\nFull cell type composition per CNV-cluster:")
composition = adata.obs.groupby(["cnv_leiden", "cell_type"], observed=True).size().unstack(fill_value=0)
print(composition)
composition.to_csv("cnv_composition_full.csv")

print("\nCNV score per cluster (sorted):")
print(adata.obs.groupby("cnv_leiden", observed=True)["cnv_score"].mean().sort_values())
