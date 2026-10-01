"""
Reproduces train_classifier.py's held-out classification_report WITHOUT retraining -
loads the already-saved endpoint1_model.joblib/label_encoder/feature_genes as-is and
reconstructs the identical 80/20 split (same random_state=42/test_size=0.2/stratify)
to predict against. Zero risk to the already-deployed SageMaker model: clf.fit() is
never called here.

This evaluation covers endpoint1 AND endpoint2, since they are the same model
(see DESIGN_DECISIONS.md / README.md for why) - there is no separate endpoint2 report.

Run with: python evaluate_endpoint1.py
Needs: anndata (or scanpy), joblib, numpy, scikit-learn
"""
import numpy as np
import joblib
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report

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

adata.obs["final_label"] = adata.obs["cell_type"].astype(str)
is_epithelial = adata.obs["cell_type"].isin(
    ["Epithelial_basal", "Epithelial_differentiated", "Epithelial_glandular"]
)
adata.obs.loc[is_epithelial, "final_label"] = adata.obs.loc[is_epithelial, "malignancy_status"]

adata_panel = adata[:, feature_genes].copy()
X = adata_panel.X
if not isinstance(X, np.ndarray):
    X = X.toarray()
y = le.transform(adata_panel.obs["final_label"].values)

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
)

y_pred = clf.predict(X_test)
report = classification_report(y_test, y_pred, target_names=le.classes_)

header = (
    "Endpoint 1/2 shared model (endpoint1_model.joblib)\n"
    f"Held-out test split: {len(y_test)} cells "
    f"(20% of {len(y)} total Flex cells, stratified, random_state=42)\n"
    "No retraining performed - evaluating the already-deployed model artifact.\n\n"
)
print(header + report)
with open("endpoint1_classification_report.txt", "w") as f:
    f.write(header + report)
print("Saved endpoint1_classification_report.txt")
