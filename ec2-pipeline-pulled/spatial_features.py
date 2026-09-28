import scanpy as sc
import squidpy as sq
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report
import xgboost as xgb
import joblib

adata = sc.read_h5ad("xenium_region.h5ad")

# Build a spatial graph: connect each cell to its 10 nearest physical neighbors
sq.gr.spatial_neighbors(adata, n_neighs=10, coord_type="generic")

# Engineer neighborhood-composition features: for each cell, what fraction
# of its physical neighbors belong to each predicted cell type.
# Intuition: a cell surrounded by other malignant cells is more confidently
# "in tumor territory" than an identical-looking cell surrounded by immune cells -
# this is context gene expression alone can't see.
conn = adata.obsp["spatial_connectivities"]
labels = adata.obs["predicted_label"].values
categories = adata.obs["predicted_label"].cat.categories if hasattr(labels, "cat") else pd.unique(labels)

label_dummies = pd.get_dummies(adata.obs["predicted_label"])
neighbor_composition = conn.dot(label_dummies.values)
neighbor_counts = np.asarray(conn.sum(axis=1)).flatten()
neighbor_counts[neighbor_counts == 0] = 1  # avoid divide-by-zero for isolated cells
neighbor_fractions = neighbor_composition / neighbor_counts[:, None]

comp_df = pd.DataFrame(
    neighbor_fractions,
    columns=[f"nbr_frac_{c}" for c in label_dummies.columns],
    index=adata.obs_names,
)
adata.obs = adata.obs.join(comp_df)

print("Engineered neighborhood features:", list(comp_df.columns))

# Train model 2: same malignancy target, but features = gene expression + spatial context
feature_genes = joblib.load("endpoint1_feature_genes.joblib")
X_genes = adata[:, feature_genes].X
if not isinstance(X_genes, np.ndarray):
    X_genes = X_genes.toarray()
X_spatial = comp_df.values
X_combined = np.hstack([X_genes, X_spatial])

y_raw = adata.obs["predicted_label"].values
from sklearn.preprocessing import LabelEncoder
le2 = LabelEncoder()
y = le2.fit_transform(y_raw)

X_train, X_test, y_train, y_test = train_test_split(
    X_combined, y, test_size=0.2, random_state=42, stratify=y
)

clf2 = xgb.XGBClassifier(
    n_estimators=150, max_depth=6, learning_rate=0.1,
    eval_metric="mlogloss", n_jobs=1, random_state=42,
)
clf2.fit(X_train, y_train)

y_pred = clf2.predict(X_test)
print("\nModel 2 (spatial-aware) classification report:")
print(classification_report(y_test, y_pred, target_names=le2.classes_))

joblib.dump(clf2, "endpoint3_model.joblib")
joblib.dump(le2, "endpoint3_label_encoder.joblib")
joblib.dump(feature_genes, "endpoint3_feature_genes.joblib")
joblib.dump(list(comp_df.columns), "endpoint3_spatial_features.joblib")
print("\nSaved endpoint3 artifacts")
