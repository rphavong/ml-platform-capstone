"""
Builds a GENUINE Flex-derived test payload for endpoint1, replacing the copy-pasted
Xenium payload that endpoint1 and endpoint2 previously shared.

Reconstructs the exact same 80/20 train_test_split used in train_classifier.py
(same gene order, same LabelEncoder, same random_state=42/test_size=0.2/stratify)
so the 5 sampled cells are guaranteed to come from the held-out test split -
cells endpoint1_model.joblib never saw during training. No retraining happens here;
the existing model/encoder/feature-gene artifacts are loaded as-is and untouched.

Writes:
  model_artifacts/endpoint1_flex/test_payload.json
    { "example_cells": [...],          # 5 real Flex cells, held-out split
      "expected_labels": [...],        # ground-truth label from the Flex annotation pipeline
      "model_predicted_labels": [...] }# what endpoint1_model.joblib itself calls these same cells

Run with: python make_flex_test_payload.py
Needs: anndata (or scanpy), joblib, numpy, scikit-learn
    pip install anndata joblib numpy scikit-learn
"""
import json

import numpy as np
import joblib
from sklearn.model_selection import train_test_split

try:
    import anndata as ad
    read_h5ad = ad.read_h5ad
except ImportError:
    import scanpy as sc
    read_h5ad = sc.read_h5ad

adata = read_h5ad("flex_final.h5ad")
clf = joblib.load("endpoint1_model.joblib")
le = joblib.load("endpoint1_label_encoder.joblib")
feature_genes = joblib.load("endpoint1_feature_genes.joblib")

# Rebuild the exact same combined label used at training time (train_classifier.py)
adata.obs["final_label"] = adata.obs["cell_type"].astype(str)
is_epithelial = adata.obs["cell_type"].isin(
    ["Epithelial_basal", "Epithelial_differentiated", "Epithelial_glandular"]
)
adata.obs.loc[is_epithelial, "final_label"] = adata.obs.loc[is_epithelial, "malignancy_status"]

adata_panel = adata[:, feature_genes].copy()
X_all = adata_panel.X
if not isinstance(X_all, np.ndarray):
    X_all = X_all.toarray()
y_all_raw = adata_panel.obs["final_label"].values
y_all = le.transform(y_all_raw)

# Same split call, same random_state -> X_test/y_test below is IDENTICAL to the
# held-out 20% train_classifier.py evaluated against after clf.fit()
idx = np.arange(len(y_all))
_, _, _, _, idx_train, idx_test = train_test_split(
    X_all, y_all, idx, test_size=0.2, random_state=42, stratify=y_all
)

sample_idx = idx_test[:5]
sample_X = X_all[sample_idx]
sample_true = le.inverse_transform(y_all[sample_idx])
sample_pred = le.inverse_transform(clf.predict(sample_X))

payload = {
    "example_cells": sample_X.tolist(),
    "expected_labels": sample_true.tolist(),
    "model_predicted_labels": sample_pred.tolist(),
}

with open("model_artifacts/endpoint1_flex/test_payload.json", "w") as f:
    json.dump(payload, f)

print(f"Sampled {len(sample_idx)} held-out Flex test cells (never seen during training).")
print("Ground-truth labels:      ", payload["expected_labels"])
print("Model's own predictions:  ", payload["model_predicted_labels"])
print("Saved model_artifacts/endpoint1_flex/test_payload.json")
