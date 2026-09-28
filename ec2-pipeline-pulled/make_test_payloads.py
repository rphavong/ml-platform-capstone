import scanpy as sc
import joblib
import json
import numpy as np

# Endpoint 1/2 test payload: a few real Xenium cells with known predicted labels
adata = sc.read_h5ad("xenium_predicted.h5ad")
feature_genes = joblib.load("model_artifacts/endpoint1_flex/endpoint1_feature_genes.joblib")

sample = adata[:5, feature_genes].copy()
X = sample.X
if not isinstance(X, np.ndarray):
    X = X.toarray()

payload = {
    "example_cells": X.tolist(),
    "expected_labels": sample.obs["predicted_label"].tolist(),
}
with open("model_artifacts/endpoint2_xenium/test_payload.json", "w") as f:
    json.dump(payload, f)
with open("model_artifacts/endpoint1_flex/test_payload.json", "w") as f:
    json.dump(payload, f)

print("Test payloads saved. Expected labels:", payload["expected_labels"])
