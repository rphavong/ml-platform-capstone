import scanpy as sc
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import classification_report
import xgboost as xgb
import joblib

adata = sc.read_h5ad("flex_final.h5ad")

# Build the combined label: malignancy status for epithelial cells,
# original cell type for everything else
adata.obs["final_label"] = adata.obs["cell_type"].astype(str)
is_epithelial = adata.obs["cell_type"].isin(
    ["Epithelial_basal", "Epithelial_differentiated", "Epithelial_glandular"]
)
adata.obs.loc[is_epithelial, "final_label"] = adata.obs.loc[is_epithelial, "malignancy_status"]

print("Final label distribution:")
print(adata.obs["final_label"].value_counts())

# Restrict to genes present in BOTH Flex data and the Xenium panel
with open("xenium_panel_genes.txt") as f:
    panel_genes = set(line.strip() for line in f)

shared_genes = sorted(set(adata.var_names) & panel_genes)
print(f"\nShared genes (Flex ∩ Xenium panel): {len(shared_genes)} / {len(panel_genes)} panel genes")

adata_panel = adata[:, shared_genes].copy()

# Build feature matrix
X = adata_panel.X
if not isinstance(X, np.ndarray):
    X = X.toarray()
y_raw = adata_panel.obs["final_label"].values

le = LabelEncoder()
y = le.fit_transform(y_raw)

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
)

clf = xgb.XGBClassifier(
    n_estimators=200,
    max_depth=6,
    learning_rate=0.1,
    eval_metric="mlogloss",
    n_jobs=1,          # keep it modest given our memory history
    random_state=42,
)
clf.fit(X_train, y_train)

y_pred = clf.predict(X_test)
print("\nClassification report:")
print(classification_report(y_test, y_pred, target_names=le.classes_))

# Save everything Module 1 (FastAPI) will need
joblib.dump(clf, "endpoint1_model.joblib")
joblib.dump(le, "endpoint1_label_encoder.joblib")
joblib.dump(shared_genes, "endpoint1_feature_genes.joblib")
print("\nSaved endpoint1_model.joblib, endpoint1_label_encoder.joblib, endpoint1_feature_genes.joblib")
