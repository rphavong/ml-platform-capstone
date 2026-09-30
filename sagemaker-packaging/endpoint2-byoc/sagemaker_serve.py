"""SageMaker "bring your own container" server for endpoint2 (reuses endpoint1's model - same classifier, applied to Xenium cells instead of Flex).

Separate from services/endpoint2-xenium/main.py on purpose - this runs INSIDE SageMaker,
main.py (after Module 4b) runs INSIDE Kubernetes as a thin proxy that CALLS this. Two
different jobs, two different containers.

SageMaker's only two rules for a custom container: answer GET /ping with 200 if healthy,
and answer POST /invocations with the prediction. Everything else (port 8080, model files
appearing at /opt/ml/model/) is also part of that contract, handled below.
"""
import json
import logging
import os

import joblib
import numpy as np
from fastapi import FastAPI, HTTPException, Request, Response

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("endpoint2-sagemaker")

# SageMaker always extracts model.tar.gz to this exact path before starting the container.
MODEL_DIR = "/opt/ml/model"

MODEL = None
LABEL_ENCODER = None
SCHEMA = None
READY = False

app = FastAPI(title="Endpoint 2 - SageMaker BYOC server")


@app.on_event("startup")
def load_artifacts():
    global MODEL, LABEL_ENCODER, SCHEMA, READY
    try:
        MODEL = joblib.load(os.path.join(MODEL_DIR, "endpoint1_model.joblib"))
        LABEL_ENCODER = joblib.load(os.path.join(MODEL_DIR, "endpoint1_label_encoder.joblib"))
        with open(os.path.join(MODEL_DIR, "schema.json")) as f:
            SCHEMA = json.load(f)
        READY = True
        logger.info(f"Model loaded. Expects {SCHEMA['n_gene_features']} features.")
    except Exception as e:
        logger.error(f"Failed to load model artifacts: {e}")
        READY = False


@app.get("/ping")
def ping():
    # SageMaker polls this repeatedly until it returns 200 - that's what "InService" waits on.
    if not READY:
        return Response(status_code=503)
    return Response(status_code=200)


@app.post("/invocations")
async def invocations(request: Request):
    if not READY:
        raise HTTPException(status_code=503, detail="Model not ready")

    content_type = request.headers.get("content-type", "")
    if "application/json" not in content_type:
        raise HTTPException(status_code=415, detail=f"Unsupported content type: {content_type}")

    body = await request.json()
    cells = body["cells"]

    try:
        X = np.asarray(cells, dtype=np.float32)
    except ValueError:
        raise HTTPException(status_code=400, detail="Every cell must have the same number of values")

    expected_features = SCHEMA["n_gene_features"]
    if X.ndim != 2 or X.shape[1] != expected_features:
        raise HTTPException(
            status_code=400,
            detail=f"Expected each cell to have {expected_features} features, got shape {X.shape}",
        )
    if not np.isfinite(X).all():
        raise HTTPException(status_code=400, detail="Expression values must be finite (no NaN or Infinity)")

    y_pred = MODEL.predict(X)
    y_proba = MODEL.predict_proba(X)
    labels = LABEL_ENCODER.inverse_transform(y_pred).tolist()
    confidence = y_proba.max(axis=1).tolist()

    return {"predicted_labels": labels, "confidence_scores": confidence}
