from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List
import joblib
import json
import numpy as np
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("endpoint1-flex")

app = FastAPI(title="Endpoint 1 - Flex Cell Type & Malignancy Classifier")

# --- Load model artifacts once, at startup, not per-request ---
# Loading a model file is relatively slow (disk I/O + deserialization);
# doing it once when the service starts, then keeping it in memory for
# every subsequent request, is standard practice - re-loading per-request
# would make /predict unnecessarily slow and is the kind of mistake the
# assessment's health/readiness probe design is meant to catch.
MODEL = None
LABEL_ENCODER = None
SCHEMA = None
READY = False

@app.on_event("startup")
def load_artifacts():
    global MODEL, LABEL_ENCODER, SCHEMA, READY
    try:
        MODEL = joblib.load("model_artifacts/endpoint1_model.joblib")
        LABEL_ENCODER = joblib.load("model_artifacts/endpoint1_label_encoder.joblib")
        with open("model_artifacts/schema.json") as f:
            SCHEMA = json.load(f)
        READY = True
        logger.info(f"Model loaded successfully. Expects {SCHEMA['n_gene_features']} features.")
    except Exception as e:
        # Deliberately NOT raising here - we want the container to start
        # and report unhealthy via /ready, rather than crash-looping,
        # which is easier to debug from kubectl describe pod
        logger.error(f"Failed to load model artifacts: {e}")
        READY = False

# --- Request/response schemas ---
class PredictRequest(BaseModel):
    # One cell = one row of gene expression values, in the exact
    # gene order the model was trained on (see schema.json)
    cells: List[List[float]] = Field(..., description="List of cells, each a list of gene expression values")

class PredictResponse(BaseModel):
    predicted_labels: List[str]
    confidence_scores: List[float]

# --- Health check: is the process alive at all? ---
# Kubernetes uses this for liveness probes - "should this container be restarted?"
# Deliberately simple and fast - doesn't check the model, just that the web server responds.
@app.get("/health")
def health():
    return {"status": "ok"}

# --- Readiness check: is the service actually able to serve real requests? ---
# Kubernetes uses this for readiness probes - "should traffic be routed here yet?"
# This DOES check the model is loaded, since a pod can be "alive" but not
# yet ready (e.g., still loading a large model file).
@app.get("/ready")
def ready():
    if not READY:
        raise HTTPException(status_code=503, detail="Model not loaded")
    return {"status": "ready", "n_features_expected": SCHEMA["n_gene_features"]}

@app.post("/predict", response_model=PredictResponse)
def predict(request: PredictRequest):
    if not READY:
        raise HTTPException(status_code=503, detail="Model not ready - check /ready")

    X = np.array(request.cells)

    # --- Failure path: reject malformed input clearly, rather than
    # letting it crash inside the model or silently return garbage ---
    expected_features = SCHEMA["n_gene_features"]
    if X.ndim != 2 or X.shape[1] != expected_features:
        raise HTTPException(
            status_code=400,
            detail=f"Expected each cell to have {expected_features} features, got shape {X.shape}",
        )

    try:
        y_pred = MODEL.predict(X)
        y_proba = MODEL.predict_proba(X)
        labels = LABEL_ENCODER.inverse_transform(y_pred).tolist()
        confidence = y_proba.max(axis=1).tolist()
    except Exception as e:
        logger.error(f"Prediction failed: {e}")
        raise HTTPException(status_code=500, detail="Internal error during prediction")

    return PredictResponse(predicted_labels=labels, confidence_scores=confidence)