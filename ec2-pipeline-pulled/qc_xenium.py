import scanpy as sc

adata = sc.read_h5ad("xenium_raw.h5ad")
print("Before QC:", adata.shape)

# Xenium-appropriate thresholds: targeted panel, low counts/cell are normal.
# Standard Xenium QC convention: keep cells with at least 10 total transcripts
# and at least 5 distinct genes detected.
sc.pp.calculate_qc_metrics(adata, percent_top=None, inplace=True)

sc.pp.filter_cells(adata, min_counts=10)
sc.pp.filter_cells(adata, min_genes=5)

# Drop cells with zero nuclei detected (segmentation artifacts - a "cell"
# with no nucleus is likely a fragment, not a real cell)
adata = adata[adata.obs["nucleus_count"] > 0].copy()

# Drop cells with unusually high control-probe counts relative to real signal
# (indicates noisy/unreliable segmentation for that cell)
adata = adata[adata.obs["control_probe_counts"] < adata.obs["total_counts"] * 0.1].copy()

sc.pp.filter_genes(adata, min_cells=3)

print("After QC:", adata.shape)
print("\nMedian transcripts/cell after QC:", adata.obs["total_counts"].median())

adata.write("xenium_qc.h5ad")
print("Saved xenium_qc.h5ad")
