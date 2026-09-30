from contextlib import asynccontextmanager
from pathlib import Path
from typing import List
import json
import logging
import os
 
import joblib
import numpy as np
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
 
logging.basicConfig(level=logging.INFO)
 
# --- Service identity: the ONLY lines that differ between endpoint1 and endpoint2 ---
SERVICE_NAME = "endpoint1-flex"
SERVICE_TITLE = "Endpoint 1 - Flex Cell Type & Malignancy Classifier"
DATA_SOURCE = "10x Flex single-cell, cervical cancer FFPE"
ARTIFACT_PREFIX = "endpoint1"  # model files are named <prefix>_model.joblib etc.
 
logger = logging.getLogger(SERVICE_NAME)
 
# --- Where the model files live ---
# Default: the model_artifacts/ folder sitting next to this file, so the service
# works no matter which directory you launch it from. The MODEL_DIR environment
# variable overrides it - Docker, Kubernetes and SageMaker will use that later.
MODEL_DIR = Path(os.environ.get("MODEL_DIR", Path(__file__).parent / "model_artifacts"))
 
# --- Model artifacts are loaded ONCE at startup, not per request ---
# Loading a model file is slow (disk I/O + deserialization); doing it once and
# keeping it in memory keeps /predict fast.
MODEL = None
LABEL_ENCODER = None
SCHEMA = None
READY = False
 
 
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Runs once when the server starts (before the yield) and once when it stops (after)."""
    global MODEL, LABEL_ENCODER, SCHEMA, READY
    try:
        MODEL = joblib.load(MODEL_DIR / f"{ARTIFACT_PREFIX}_model.joblib")
        LABEL_ENCODER = joblib.load(MODEL_DIR / f"{ARTIFACT_PREFIX}_label_encoder.joblib")
        with open(MODEL_DIR / "schema.json") as f:
            SCHEMA = json.load(f)
        READY = True
        logger.info(f"Model loaded successfully. Expects {SCHEMA['n_gene_features']} features.")
    except Exception as e:
        # Deliberately NOT raising: the container starts and reports unhealthy via
        # /ready, rather than crash-looping - easier to debug with kubectl describe pod.
        logger.error(f"Failed to load model artifacts: {e}")
        READY = False
    yield
    # Nothing to clean up on shutdown.
 
 
app = FastAPI(title=SERVICE_TITLE, lifespan=lifespan)
 
 
# --- Request/response schemas ---
class PredictRequest(BaseModel):
    # One cell = one row of log-normalized gene expression values, in the exact
    # gene order the model was trained on (see schema.json)
    cells: List[List[float]] = Field(..., description="List of cells, each a list of gene expression values")
 
 
class PredictResponse(BaseModel):
    predicted_labels: List[str]
    confidence_scores: List[float]
 
 
# --- Liveness: is the process alive at all? (Kubernetes restarts the container if not) ---
@app.get("/health")
def health():
    return {"status": "ok"}
 
 
# --- Readiness: can the service actually serve requests yet? (Kubernetes withholds traffic if not) ---
@app.get("/ready")
def ready():
    if not READY:
        raise HTTPException(status_code=503, detail="Model not loaded")
    return {"status": "ready", "n_features_expected": SCHEMA["n_gene_features"]}
 
 
# --- Metadata: what does this service do? (the ops dashboard will read this later) ---
@app.get("/info")
def info():
    if not READY:
        raise HTTPException(status_code=503, detail="Model not loaded")
    return {
        "service": SERVICE_NAME,
        "data_source": DATA_SOURCE,
        "n_gene_features": SCHEMA["n_gene_features"],
        "output_classes": SCHEMA["output_classes"],
        "preprocessing": SCHEMA["preprocessing"],
    }
 
 
@app.post("/predict", response_model=PredictResponse)
def predict(request: PredictRequest):
    if not READY:
        raise HTTPException(status_code=503, detail="Model not ready - check /ready")
 
    # --- Failure paths: reject malformed input with a clear 400 instead of
    # crashing inside numpy/the model (which would surface as a vague 500) ---
    try:
        X = np.asarray(request.cells, dtype=np.float32)
    except ValueError:
        # Happens when rows have different lengths ("ragged" input)
        raise HTTPException(status_code=400, detail="Every cell must have the same number of values")
 
    expected_features = SCHEMA["n_gene_features"]
    if X.ndim != 2 or X.shape[1] != expected_features:
        raise HTTPException(
            status_code=400,
            detail=f"Expected each cell to have {expected_features} features, got shape {X.shape}",
        )
 
    if not np.isfinite(X).all():
        raise HTTPException(status_code=400, detail="Expression values must be finite (no NaN or Infinity)")
 
    try:
        y_pred = MODEL.predict(X)
        y_proba = MODEL.predict_proba(X)
        labels = LABEL_ENCODER.inverse_transform(y_pred).tolist()
        confidence = y_proba.max(axis=1).tolist()
    except Exception as e:
        logger.error(f"Prediction failed: {e}")
        raise HTTPException(status_code=500, detail="Internal error during prediction")
 
    return PredictResponse(predicted_labels=labels, confidence_scores=confidence)