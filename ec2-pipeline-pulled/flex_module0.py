import scanpy as sc

# --- 0.2: Load ---
adata_flex = sc.read_10x_h5("9k_Cervical_Cancer_scFFPE_count_filtered_feature_bc_matrix.h5")
adata_flex.var_names_make_unique()
print("Loaded:", adata_flex)

# --- 0.3: QC ---
adata_flex.var["mt"] = adata_flex.var_names.str.startswith("MT-")
sc.pp.calculate_qc_metrics(adata_flex, qc_vars=["mt"], inplace=True, percent_top=None)

sc.pp.filter_cells(adata_flex, min_genes=200)
sc.pp.filter_genes(adata_flex, min_cells=3)
adata_flex = adata_flex[adata_flex.obs["pct_counts_mt"] < 20].copy()
print("After QC filtering:", adata_flex.shape)

# --- Normalize ---
sc.pp.normalize_total(adata_flex, target_sum=1e4)
sc.pp.log1p(adata_flex)
adata_flex.raw = adata_flex

# --- Cluster ---
sc.pp.highly_variable_genes(adata_flex, n_top_genes=2000)
sc.pp.pca(adata_flex, n_comps=50, use_highly_variable=True)
sc.pp.neighbors(adata_flex, n_neighbors=15)
sc.tl.leiden(adata_flex, resolution=1.0)

print("Cluster counts:")
print(adata_flex.obs["leiden"].value_counts())

# --- Save for next steps ---
adata_flex.write("flex_clustered.h5ad")
print("Saved flex_clustered.h5ad")
