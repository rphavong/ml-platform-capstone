"""
The apples-to-apples endpoint1-model-vs-endpoint3-model comparison on the SAME
held-out Xenium test cells. No retraining - loads both already-saved models and
re-predicts.

Why this is the right comparison (and why a plain "endpoint2 accuracy" number
would be misleading): the only label available for Xenium cells is
`predicted_label`, which was itself produced by the gene-only model
(apply_classifier.py) before the spatial region was even cropped
(select_region.py). spatial_features.py then trains endpoint3 to match that SAME
label. So a gene-only model evaluated against `predicted_label` is circular -
it will score ~100% almost by construction, because that label IS its own
earlier call on the same gene features. That's confirmed below as a sanity
check, but it's not the number that matters.

What actually matters: does adding spatial neighborhood context change the
model's call, and does it change it specifically on the cells the gene-only
model was LEAST confident about (the genuinely hard cases validate_hard_cases.py
flagged but never finished comparing)? That's what this script reports.

Run with: python evaluate_gene_only_vs_spatial.py
Needs: anndata (or scanpy), squidpy, pandas, joblib, numpy, scikit-learn
"""
import numpy as np
import pandas as pd
import joblib
import squidpy as sq
from sklearn.model_selection import train_test_split

try:
    import anndata as ad
    read_h5ad = ad.read_h5ad
except ImportError:
    import scanpy as sc
    read_h5ad = sc.read_h5ad

adata = read_h5ad("xenium_region.h5ad")

# Rebuild the identical spatial-composition features spatial_features.py used
sq.gr.spatial_neighbors(adata, n_neighs=10, coord_type="generic")
conn = adata.obsp["spatial_connectivities"]
label_dummies = pd.get_dummies(adata.obs["predicted_label"])
neighbor_composition = conn.dot(label_dummies.values)
neighbor_counts = np.asarray(conn.sum(axis=1)).flatten()
neighbor_counts[neighbor_counts == 0] = 1
neighbor_fractions = neighbor_composition / neighbor_counts[:, None]
comp_df = pd.DataFrame(
    neighbor_fractions,
    columns=[f"nbr_frac_{c}" for c in label_dummies.columns],
    index=adata.obs_names,
)
adata.obs = adata.obs.join(comp_df)

# Load both models - endpoint1's gene-only model, endpoint3's gene+spatial model
clf1 = joblib.load("endpoint1_model.joblib")
le1 = joblib.load("endpoint1_label_encoder.joblib")
clf3 = joblib.load("endpoint3_model.joblib")
le3 = joblib.load("endpoint3_label_encoder.joblib")
feature_genes = joblib.load("endpoint3_feature_genes.joblib")

X_genes = adata[:, feature_genes].X
if not isinstance(X_genes, np.ndarray):
    X_genes = X_genes.toarray()
X_combined = np.hstack([X_genes, comp_df.values])

y = le3.transform(adata.obs["predicted_label"].values)
idx = np.arange(len(y))

# Identical split to spatial_features.py / evaluate_endpoint3.py (same random_state)
_, _, _, _, idx_train, idx_test = train_test_split(
    X_combined, y, idx, test_size=0.2, random_state=42, stratify=y
)

X_genes_test = X_genes[idx_test]
X_combined_test = X_combined[idx_test]
obs_test = adata.obs.iloc[idx_test]

# Gene-only model's call on these test cells, re-derived fresh right now
gene_only_pred = le1.inverse_transform(clf1.predict(X_genes_test))
# Spatial model's call on the same cells
spatial_pred = le3.inverse_transform(clf3.predict(X_combined_test))
# The label these cells were already carrying (from apply_classifier.py, pre-crop)
stored_label = obs_test["predicted_label"].values
stored_confidence = obs_test["prediction_confidence"].values

sanity_agreement = (gene_only_pred == stored_label).mean()
overall_agreement = (gene_only_pred == spatial_pred).mean()

median_conf = np.median(stored_confidence)
hard_mask = stored_confidence < median_conf
hard_agreement = (gene_only_pred[hard_mask] == spatial_pred[hard_mask]).mean()
n_hard = hard_mask.sum()
n_changed_on_hard = (gene_only_pred[hard_mask] != spatial_pred[hard_mask]).sum()

lines = []
lines.append("Gene-only (endpoint1/2 model) vs spatially-aware (endpoint3 model)")
lines.append(f"Same held-out Xenium test split: {len(idx_test)} cells\n")

lines.append(
    f"Sanity check - gene-only model re-predicting now vs the `predicted_label` "
    f"it originally produced (pre-crop, in apply_classifier.py): "
    f"{sanity_agreement:.1%} agreement. (Expected ~100% - confirms this label "
    f"isn't independent ground truth, it's literally this model's own earlier call.)\n"
)

lines.append(
    f"Gene-only vs spatial model, ALL {len(idx_test)} test cells: "
    f"{overall_agreement:.1%} agreement "
    f"({(gene_only_pred != spatial_pred).sum()} cells where spatial context changed the call)\n"
)

lines.append(
    f"Restricting to the {n_hard} cells the gene-only model was LEAST confident "
    f"about (bottom 50% of its own confidence scores, median={median_conf:.3f}):\n"
    f"  Gene-only vs spatial agreement on just these hard cells: {hard_agreement:.1%}\n"
    f"  Spatial model changed the call on {n_changed_on_hard} / {n_hard} hard cells "
    f"({n_changed_on_hard/n_hard:.1%})\n"
)

lines.append("Gene-only model's calls on the hard cells:")
lines.append(pd.Series(gene_only_pred[hard_mask]).value_counts().to_string())
lines.append("\nSpatial model's calls on the SAME hard cells:")
lines.append(pd.Series(spatial_pred[hard_mask]).value_counts().to_string())

report = "\n".join(lines)
print(report)
with open("endpoint3_vs_gene_only_report.txt", "w") as f:
    f.write(report + "\n")
print("\nSaved endpoint3_vs_gene_only_report.txt")
