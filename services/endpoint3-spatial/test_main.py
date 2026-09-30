"""Automated checks for the endpoint3 PROXY service. Run from this folder with: pytest -v

Same mocking approach as endpoint1/2's proxy tests. One extra thing worth testing here
that endpoint1/2 don't have: the min-11-cells check must still happen locally (fast,
free) rather than being discovered only after a round trip to SageMaker.
"""
import io
import json
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest
from botocore.exceptions import ClientError, EndpointConnectionError, ReadTimeoutError
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
    side = int(np.ceil(np.sqrt(n)))
    return [
        {
            "expression": rng.random(N_GENES).tolist(),
            "x": float(i % side),
            "y": float(i // side),
            "predicted_label": classes[i % len(classes)],
        }
        for i in range(n)
    ]


def _fake_sagemaker_response(body_dict):
    return {"Body": io.BytesIO(json.dumps(body_dict).encode())}


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_ready_reports_feature_counts(client, schema):
    r = client.get("/ready")
    assert r.status_code == 200
    body = r.json()
    assert body["n_gene_features_expected"] == N_GENES
    assert body["min_cells_per_request"] == 11
    assert body["sagemaker_endpoint"] == main.SAGEMAKER_ENDPOINT_NAME


def test_info(client):
    body = client.get("/info").json()
    assert body["service"] == "endpoint3-spatial"
    assert len(body["output_classes"]) == N_CLASSES


def test_predict_forwards_to_sagemaker(client, schema, monkeypatch):
    cells = _synthetic_cells(30, schema)
    fake_result = {
        "predicted_labels": [c["predicted_label"] for c in cells],
        "confidence_scores": [0.8] * len(cells),
    }
    mock_invoke = MagicMock(return_value=_fake_sagemaker_response(fake_result))
    monkeypatch.setattr(main.runtime, "invoke_endpoint", mock_invoke)

    r = client.post("/predict", json={"cells": cells})
    assert r.status_code == 200
    body = r.json()
    assert len(body["predicted_labels"]) == 30

    _, kwargs = mock_invoke.call_args
    assert kwargs["EndpointName"] == main.SAGEMAKER_ENDPOINT_NAME
    sent_cells = json.loads(kwargs["Body"])["cells"]
    assert len(sent_cells) == 30
    assert "predicted_label" in sent_cells[0]  # spatial context forwarded, not stripped


def test_too_few_cells_returns_400_without_calling_sagemaker(client, schema, monkeypatch):
    mock_invoke = MagicMock()
    monkeypatch.setattr(main.runtime, "invoke_endpoint", mock_invoke)

    cells = _synthetic_cells(5, schema)  # fewer than the 11-cell minimum
    r = client.post("/predict", json={"cells": cells})
    assert r.status_code == 400
    mock_invoke.assert_not_called()


def test_wrong_gene_count_returns_400(client, schema):
    cells = _synthetic_cells(15, schema)
    cells[0]["expression"] = [0.1, 0.2]
    r = client.post("/predict", json={"cells": cells})
    assert r.status_code == 400


def test_sagemaker_timeout_returns_504(client, schema, monkeypatch):
    cells = _synthetic_cells(15, schema)
    mock_invoke = MagicMock(side_effect=ReadTimeoutError(endpoint_url="fake"))
    monkeypatch.setattr(main.runtime, "invoke_endpoint", mock_invoke)

    r = client.post("/predict", json={"cells": cells})
    assert r.status_code == 504


def test_sagemaker_unreachable_returns_502(client, schema, monkeypatch):
    cells = _synthetic_cells(15, schema)
    mock_invoke = MagicMock(side_effect=EndpointConnectionError(endpoint_url="fake"))
    monkeypatch.setattr(main.runtime, "invoke_endpoint", mock_invoke)

    r = client.post("/predict", json={"cells": cells})
    assert r.status_code == 502


def test_unknown_predicted_label_surfaces_as_400(client, schema, monkeypatch):
    """The SageMaker container itself rejects an unseen predicted_label with a 400
    (see sagemaker_serve.py's ValueError -> HTTPException(400) path), which SageMaker
    wraps as a ModelError. The proxy should unwrap that back to a 400, not a generic 502."""
    cells = _synthetic_cells(15, schema)
    error_response = {
        "Error": {
            "Code": "ModelError",
            "Message": "Received client error (400) from primary and could not load the entire response body",
        }
    }
    mock_invoke = MagicMock(side_effect=ClientError(error_response, "InvokeEndpoint"))
    monkeypatch.setattr(main.runtime, "invoke_endpoint", mock_invoke)

    r = client.post("/predict", json={"cells": cells})
    assert r.status_code == 400


def test_not_ready_returns_503(client, monkeypatch):
    monkeypatch.setattr(main, "READY", False)
    assert client.get("/ready").status_code == 503
    assert client.get("/info").status_code == 503
