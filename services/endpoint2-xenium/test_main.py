"""Automated checks for the endpoint1 service. Run from this folder with:  pytest -v"""
import json
from pathlib import Path
 
import pytest
from fastapi.testclient import TestClient
 
import main
 
HERE = Path(__file__).parent
N_GENES = 4512
 
 
@pytest.fixture(scope="module")
def client():
    # The `with` block matters: it triggers the startup (lifespan) code that loads the model.
    with TestClient(main.app) as c:
        yield c
 
 
@pytest.fixture(scope="module")
def payload():
    return json.loads((HERE / "model_artifacts" / "test_payload.json").read_text())
 
 
def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}
 
 
def test_ready_reports_feature_count(client):
    r = client.get("/ready")
    assert r.status_code == 200
    assert r.json()["n_features_expected"] == N_GENES
 
 
def test_info_describes_the_service(client):
    body = client.get("/info").json()
    assert body["service"] == main.SERVICE_NAME
    assert body["n_gene_features"] == N_GENES
    assert "malignant_epithelial" in body["output_classes"]
 
 
def test_predict_matches_expected_labels(client, payload):
    r = client.post("/predict", json={"cells": payload["example_cells"]})
    assert r.status_code == 200
    body = r.json()
    assert body["predicted_labels"] == payload["expected_labels"]
    assert len(body["confidence_scores"]) == len(payload["example_cells"])
    assert all(0.0 <= c <= 1.0 for c in body["confidence_scores"])
 
 
def test_wrong_feature_count_returns_400(client):
    assert client.post("/predict", json={"cells": [[0.1] * 10]}).status_code == 400
 
 
def test_empty_request_returns_400(client):
    assert client.post("/predict", json={"cells": []}).status_code == 400
 
 
def test_ragged_rows_return_400(client):
    r = client.post("/predict", json={"cells": [[0.1] * N_GENES, [0.1] * 5]})
    assert r.status_code == 400
 
 
def test_nan_values_return_400(client):
    # NaN is not valid strict JSON, so we send the raw text ourselves.
    body = '{"cells": [[' + ",".join(["NaN"] * N_GENES) + "]]}"
    r = client.post("/predict", content=body, headers={"Content-Type": "application/json"})
    assert r.status_code == 400
 
 
def test_not_ready_returns_503(client, monkeypatch):
    monkeypatch.setattr(main, "READY", False)  # simulate "model failed to load"
    assert client.get("/ready").status_code == 503
    assert client.get("/info").status_code == 503
    assert client.post("/predict", json={"cells": [[0.1] * N_GENES]}).status_code == 503