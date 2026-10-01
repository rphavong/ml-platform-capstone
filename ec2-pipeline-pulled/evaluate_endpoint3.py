"""
Reproduces spatial_features.py's held-out classification_report WITHOUT retraining -
loads the already-saved endpoint3_model.joblib/label_encoder/feature artifacts as-is
and reconstructs the identical spatial-neighbor features + 80/20 split to predict
against. Zero risk to the already-deployed SageMaker model: clf2.fit() is never
called here.

Run with: python evaluate_endpoint3.py
Needs: anndata (or scanpy), squidpy, pandas, joblib, numpy, scikit-learn
    pip install anndata squidpy pandas joblib numpy scikit-learn
"""
import numpy as np
import pandas as pd
import joblib
import squidpy as sq
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report

try:
    import anndata as ad
    read_h5ad = ad.read_h5ad
except ImportError:
    import scanpy as sc
    read_h5ad = sc.read_h5ad

adata = read_h5ad("xenium_region.h5ad")

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

clf2 = joblib.load("endpoint3_model.joblib")
le2 = joblib.load("endpoint3_label_encoder.joblib")
feature_genes = joblib.load("endpoint3_feature_genes.joblib")

X_genes = adata[:, feature_genes].X
if not isinstance(X_genes, np.ndarray):
    X_genes = X_genes.toarray()
X_combined = np.hstack([X_genes, comp_df.values])
y = le2.transform(adata.obs["predicted_label"].values)

X_train, X_test, y_train, y_test = train_test_split(
    X_combined, y, test_size=0.2, random_state=42, stratify=y
)

y_pred = clf2.predict(X_test)
report = classification_report(y_test, y_pred, target_names=le2.classes_)

header = (
    "Endpoint 3 spatial-aware model (endpoint3_model.joblib)\n"
    f"Held-out test split: {len(y_test)} cells "
    f"(20% of {len(y)} total, stratified, random_state=42)\n"
    "No retraining performed - evaluating the already-deployed model artifact.\n\n"
)
print(header + report)
with open("endpoint3_classification_report.txt", "w") as f:
    f.write(header + report)
print("Saved endpoint3_classification_report.txt")
