"""Automated checks for the endpoint3 (spatial) service. Run from this folder with: pytest -v
 
Two kinds of test here:
  - Structural tests (shapes, status codes, response format) use SYNTHETIC coordinates
    and labels via _synthetic_cells() below - fast, deterministic, no data dependency.
  - test_predict_on_real_xenium_cells_is_self_consistent uses a REAL 60-cell payload
    built from xenium_region.h5ad (see make_endpoint3_test_payload.py, run on EC2) and
    checks the model's agreement with the upstream endpoint1/2 label. Last run: 95.0%
    (57/60) agreement. It skips gracefully if model_artifacts/test_payload.json is
    missing, so the suite still runs clean on a machine that never pulled that file.
"""
import json
from pathlib import Path
 
import numpy as np
import pytest
from fastapi.testclient import TestClient
 
import main
 
HERE = Path(__file__).parent
N_GENES = 4512
N_CLASSES = 15
 
 
@pytest.fixture(scope="module")
def client():
    with TestClient(main.app) as c:
        yield c
 
 
@pytest.fixture(scope="module")
def schema():
    return json.loads((HERE / "model_artifacts" / "schema.json").read_text())
 
 
def _synthetic_cells(n, schema, seed=0):
    rng = np.random.default_rng(seed)
    classes = schema["output_classes"]
    cells = []
    # lay cells out on a grid so the nearest-neighbor graph is well defined
    side = int(np.ceil(np.sqrt(n)))
    for i in range(n):
        cells.append(
            {
                "expression": rng.random(N_GENES).tolist(),
                "x": float(i % side),
                "y": float(i // side),
                "predicted_label": classes[i % len(classes)],
            }
        )
    return cells
 
 
def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}
 
 
def test_ready_reports_feature_counts(client, schema):
    r = client.get("/ready")
    assert r.status_code == 200
    body = r.json()
    assert body["n_gene_features_expected"] == N_GENES
    assert body["n_spatial_features_expected"] == N_CLASSES
    assert body["min_cells_per_request"] == 11
 
 
def test_info(client):
    body = client.get("/info").json()
    assert body["service"] == "endpoint3-spatial"
    assert len(body["output_classes"]) == N_CLASSES
 
 
def test_predict_on_real_xenium_cells_is_self_consistent(client):
    """If a real test_payload.json exists (built from xenium_region.h5ad via
    make_endpoint3_test_payload.py on EC2), run it and check the model's output
    against the predicted_label already embedded in each cell.
 
    IMPORTANT caveat: those predicted_label values are the same field
    spatial_features.py trained endpoint3's target on (see train_classifier's
    sibling script). So this measures self-consistency with the upstream
    endpoint1/2 model, not independent ground truth. High agreement is
    expected and good; 100% is neither expected nor required, since some of
    these cells were held out of endpoint3's own training split.
    """
    payload_path = HERE / "model_artifacts" / "test_payload.json"
    if not payload_path.exists():
        pytest.skip("No real test_payload.json yet - see make_endpoint3_test_payload.py")
 
    payload = json.loads(payload_path.read_text())
    cells = payload["cells"]
    assert len(cells) >= 11, "Real payload must meet the 11-cell spatial minimum"
 
    upstream_labels = [c["predicted_label"] for c in cells]
 
    r = client.post("/predict", json={"cells": cells})
    assert r.status_code == 200
    body = r.json()
 
    predicted = body["predicted_labels"]
    assert len(predicted) == len(cells)
 
    agree = sum(1 for a, b in zip(predicted, upstream_labels) if a == b)
    accuracy = agree / len(cells)
    print(f"\nSelf-consistency on {len(cells)} real Xenium cells: {accuracy:.1%} ({agree}/{len(cells)})")
 
    # Loose threshold - this is a regression/smoke check, not a hard accuracy bar.
    # If this starts failing, the drop itself is the useful signal (paste the
    # printed accuracy so we can decide whether 50% is still the right bar).
    assert accuracy >= 0.50, f"Self-consistency dropped to {accuracy:.1%} - investigate before trusting this build"
 
 
def test_predict_returns_one_label_per_cell(client, schema):
    cells = _synthetic_cells(30, schema)
    r = client.post("/predict", json={"cells": cells})
    assert r.status_code == 200
    body = r.json()
    assert len(body["predicted_labels"]) == 30
    assert len(body["confidence_scores"]) == 30
    assert all(0.0 <= c <= 1.0 for c in body["confidence_scores"])
    assert all(lbl in schema["output_classes"] for lbl in body["predicted_labels"])
 
 
def test_too_few_cells_returns_400(client, schema):
    cells = _synthetic_cells(5, schema)  # fewer than the 11-cell minimum
    r = client.post("/predict", json={"cells": cells})
    assert r.status_code == 400
 
 
def test_unknown_predicted_label_returns_400(client, schema):
    cells = _synthetic_cells(15, schema)
    cells[0]["predicted_label"] = "not_a_real_class"
    r = client.post("/predict", json={"cells": cells})
    assert r.status_code == 400
 
 
def test_wrong_gene_count_returns_400(client, schema):
    cells = _synthetic_cells(15, schema)
    cells[0]["expression"] = [0.1, 0.2]  # too short
    r = client.post("/predict", json={"cells": cells})
    assert r.status_code == 400
 
 
def test_not_ready_returns_503(client, monkeypatch):
    monkeypatch.setattr(main, "READY", False)
    assert client.get("/ready").status_code == 503
    assert client.get("/info").status_code == 503
 
 
# --- To build a REAL test payload later (with genuine expected labels), run something
# like this on the machine that still has xenium_region.h5ad (EC2 or your Mac's venv
# with scanpy installed):
#
#   import scanpy as sc, joblib, json
#   adata = sc.read_h5ad("xenium_region.h5ad")
#   sample = adata[:30].copy()
#   feature_genes = joblib.load("endpoint1_feature_genes.joblib")
#   X = sample[:, feature_genes].X
#   if not isinstance(X, np.ndarray): X = X.toarray()
#   payload = {
#       "cells": [
#           {
#               "expression": X[i].tolist(),
#               "x": float(sample.obsm["spatial"][i, 0]),
#               "y": float(sample.obsm["spatial"][i, 1]),
#               "predicted_label": sample.obs["predicted_label"].iloc[i],
#           }
#           for i in range(sample.n_obs)
#       ],
#   }
#   json.dump(payload, open("model_artifacts/test_payload.json", "w"))