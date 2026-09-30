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
from sklearn.neighbors import NearestNeighbors
 
logging.basicConfig(level=logging.INFO)
 
SERVICE_NAME = "endpoint3-spatial"
SERVICE_TITLE = "Endpoint 3 - Spatial-Aware Malignancy Classifier"
DATA_SOURCE = "10x Xenium Prime 5K spatial, cervical cancer FFPE, with neighborhood context"
 
logger = logging.getLogger(SERVICE_NAME)
 
MODEL_DIR = Path(os.environ.get("MODEL_DIR", Path(__file__).parent / "model_artifacts"))
N_NEIGHBORS = 10  # matches the training script's squidpy sq.gr.spatial_neighbors(n_neighs=10)
 
MODEL = None
LABEL_ENCODER = None
SCHEMA = None
READY = False
 
 
@asynccontextmanager
async def lifespan(app: FastAPI):
    global MODEL, LABEL_ENCODER, SCHEMA, READY
    try:
        MODEL = joblib.load(MODEL_DIR / "endpoint3_model.joblib")
        LABEL_ENCODER = joblib.load(MODEL_DIR / "endpoint3_label_encoder.joblib")
        with open(MODEL_DIR / "schema.json") as f:
            SCHEMA = json.load(f)
        READY = True
        logger.info(
            f"Model loaded. Expects {SCHEMA['n_gene_features']} gene features "
            f"+ {SCHEMA['n_spatial_features']} spatial features."
        )
    except Exception as e:
        logger.error(f"Failed to load model artifacts: {e}")
        READY = False
    yield
 
 
app = FastAPI(title=SERVICE_TITLE, lifespan=lifespan)
 
 
# --- Request/response schemas ---
class Cell(BaseModel):
    # Gene expression, same 4512-gene order as endpoint1/endpoint2 (see schema.json "gene_order")
    expression: List[float] = Field(..., description="Log-normalized gene expression values")
    x: float = Field(..., description="Spatial x coordinate (same units as training, e.g. microns)")
    y: float = Field(..., description="Spatial y coordinate")
    # The cell-type call from endpoint1 or endpoint2 for THIS cell. Endpoint3 does not
    # run that classification itself - it consumes it, the way the training pipeline did
    # (apply_classifier.py's output became spatial_features.py's input). The caller
    # (dashboard/orchestrator) is expected to have already called endpoint1 or endpoint2.
    predicted_label: str = Field(..., description="Cell type / malignancy call from endpoint1 or endpoint2")
 
 
class PredictRequest(BaseModel):
    # A BATCH of cells forming one spatial neighborhood/region. Spatial context is
    # relative to the other cells in the same request - a single cell has no neighbors,
    # so this endpoint (unlike endpoint1/2) requires a batch of at least N_NEIGHBORS + 1 cells.
    cells: List[Cell]
 
 
class PredictResponse(BaseModel):
    predicted_labels: List[str]
    confidence_scores: List[float]
 
 
@app.get("/health")
def health():
    return {"status": "ok"}
 
 
@app.get("/ready")
def ready():
    if not READY:
        raise HTTPException(status_code=503, detail="Model not loaded")
    return {
        "status": "ready",
        "n_gene_features_expected": SCHEMA["n_gene_features"],
        "n_spatial_features_expected": SCHEMA["n_spatial_features"],
        "min_cells_per_request": N_NEIGHBORS + 1,
    }
 
 
@app.get("/info")
def info():
    if not READY:
        raise HTTPException(status_code=503, detail="Model not loaded")
    return {
        "service": SERVICE_NAME,
        "data_source": DATA_SOURCE,
        "n_gene_features": SCHEMA["n_gene_features"],
        "n_spatial_features": SCHEMA["n_spatial_features"],
        "output_classes": SCHEMA["output_classes"],
        "spatial_feature_order": SCHEMA["spatial_feature_order"],
        "n_neighbors": N_NEIGHBORS,
        "note": (
            "Each cell's predicted_label must come from endpoint1 or endpoint2 first - "
            "this service adds spatial neighborhood context on top of that call, it does "
            "not classify cells from expression alone."
        ),
    }
 
 
def _build_spatial_features(coords: np.ndarray, upstream_labels: List[str], class_order: List[str]) -> np.ndarray:
    """Reproduces spatial_features.py's neighbor-composition features for a live batch.
 
    Training used squidpy's KNN graph (n_neighs=10) then, per cell, the fraction of its
    physical neighbors belonging to each predicted class. Here we rebuild an equivalent
    KNN graph with scikit-learn: this is a faithful re-implementation of the same idea,
    not squidpy's exact output byte-for-byte (squidpy may symmetrize edges slightly
    differently) - close enough for serving, and documented here so it isn't mistaken
    for an exact match.
    """
    n_cells = coords.shape[0]
    k = min(N_NEIGHBORS, n_cells - 1)
 
    nn = NearestNeighbors(n_neighbors=k + 1)  # +1 because a point is its own nearest neighbor
    nn.fit(coords)
    _, neighbor_idx = nn.kneighbors(coords)
    neighbor_idx = neighbor_idx[:, 1:]  # drop self
 
    label_to_col = {label: i for i, label in enumerate(class_order)}
    label_ids = np.array([label_to_col.get(lbl, -1) for lbl in upstream_labels])
    if (label_ids == -1).any():
        bad = sorted({lbl for lbl in upstream_labels if lbl not in label_to_col})
        raise ValueError(f"predicted_label contains values outside the trained classes: {bad}")
 
    n_classes = len(class_order)
    fractions = np.zeros((n_cells, n_classes), dtype=np.float32)
    for i in range(n_cells):
        neighbor_labels = label_ids[neighbor_idx[i]]
        counts = np.bincount(neighbor_labels, minlength=n_classes)
        fractions[i] = counts / counts.sum()
    return fractions
 
 
@app.post("/predict", response_model=PredictResponse)
def predict(request: PredictRequest):
    if not READY:
        raise HTTPException(status_code=503, detail="Model not ready - check /ready")
 
    n_cells = len(request.cells)
    min_cells = N_NEIGHBORS + 1
    if n_cells < min_cells:
        raise HTTPException(
            status_code=400,
            detail=f"Need at least {min_cells} cells to build a {N_NEIGHBORS}-neighbor spatial graph, got {n_cells}",
        )
 
    try:
        X_genes = np.asarray([c.expression for c in request.cells], dtype=np.float32)
    except ValueError:
        raise HTTPException(status_code=400, detail="Every cell's expression list must have the same length")
 
    expected_genes = SCHEMA["n_gene_features"]
    if X_genes.ndim != 2 or X_genes.shape[1] != expected_genes:
        raise HTTPException(
            status_code=400,
            detail=f"Expected each cell to have {expected_genes} gene features, got shape {X_genes.shape}",
        )
    if not np.isfinite(X_genes).all():
        raise HTTPException(status_code=400, detail="Expression values must be finite (no NaN or Infinity)")
 
    coords = np.array([[c.x, c.y] for c in request.cells], dtype=np.float64)
    if not np.isfinite(coords).all():
        raise HTTPException(status_code=400, detail="x/y coordinates must be finite")
 
    upstream_labels = [c.predicted_label for c in request.cells]
 
    try:
        X_spatial = _build_spatial_features(coords, upstream_labels, SCHEMA["output_classes"])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
 
    X_combined = np.hstack([X_genes, X_spatial])
 
    try:
        y_pred = MODEL.predict(X_combined)
        y_proba = MODEL.predict_proba(X_combined)
        labels = LABEL_ENCODER.inverse_transform(y_pred).tolist()
        confidence = y_proba.max(axis=1).tolist()
    except Exception as e:
        logger.error(f"Prediction failed: {e}")
        raise HTTPException(status_code=500, detail="Internal error during prediction")
 
    return PredictResponse(predicted_labels=labels, confidence_scores=confidence)