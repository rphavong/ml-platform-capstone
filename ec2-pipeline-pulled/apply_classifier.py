import scanpy as sc
import numpy as np
import joblib

adata = sc.read_h5ad("xenium_qc.h5ad")

# Same normalization recipe used for Flex training - keeps values on a
# comparable relative scale despite Xenium's much lower raw counts/cell
sc.pp.normalize_total(adata, target_sum=1e4)
sc.pp.log1p(adata)

# Load the exact artifacts saved from training
clf = joblib.load("endpoint1_model.joblib")
le = joblib.load("endpoint1_label_encoder.joblib")
feature_genes = joblib.load("endpoint1_feature_genes.joblib")

print(f"Model expects {len(feature_genes)} features")

# Check how many of those genes actually exist in the Xenium panel
available = [g for g in feature_genes if g in adata.var_names]
missing = [g for g in feature_genes if g not in adata.var_names]
print(f"Available in Xenium data: {len(available)}")
print(f"Missing (will be zero-filled): {len(missing)}")

# Build a feature matrix with EXACTLY the training gene order,
# filling any missing genes with 0 (no expression signal, not an error)
adata_aligned = sc.AnnData(
    np.zeros((adata.n_obs, len(feature_genes)), dtype=np.float32),
    obs=adata.obs.copy(),
    var=None,
)
adata_aligned.var_names = feature_genes

for gene in available:
    adata_aligned[:, gene].X = adata[:, gene].X

X = adata_aligned.X
if not isinstance(X, np.ndarray):
    X = X.toarray()

# Predict
y_pred = clf.predict(X)
y_pred_proba = clf.predict_proba(X)
labels = le.inverse_transform(y_pred)
confidence = y_pred_proba.max(axis=1)

adata.obs["predicted_label"] = labels
adata.obs["prediction_confidence"] = confidence

print("\nPredicted label distribution:")
print(adata.obs["predicted_label"].value_counts())

print("\nMean confidence by predicted label:")
print(adata.obs.groupby("predicted_label", observed=True)["prediction_confidence"].mean().sort_values())

adata.write("xenium_predicted.h5ad")
print("\nSaved xenium_predicted.h5ad")
