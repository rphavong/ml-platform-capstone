"""SageMaker "bring your own container" server for endpoint3 (spatial).

Separate from services/endpoint3-spatial/main.py on purpose - this runs INSIDE SageMaker,
main.py (after Module 4b) runs INSIDE Kubernetes as a thin proxy that CALLS this. The
prediction logic below (_build_spatial_features + the /invocations handler) mirrors
main.py's /predict exactly - same neighbor-fraction reconstruction of squidpy's
KNN graph, same feature stacking - so this endpoint behaves identically to the version
you already tested locally and in Docker (Module 3), just now hosted by SageMaker.

SageMaker's only two rules for a custom container: answer GET /ping with 200 if healthy,
and answer POST /invocations with the prediction.
"""
import json
import logging
import os
from typing import List

import joblib
import numpy as np
from fastapi import FastAPI, HTTPException, Request, Response
from sklearn.neighbors import NearestNeighbors

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("endpoint3-sagemaker")

MODEL_DIR = "/opt/ml/model"
N_NEIGHBORS = 10  # matches training's squidpy sq.gr.spatial_neighbors(n_neighs=10)

MODEL = None
LABEL_ENCODER = None
SCHEMA = None
READY = False

app = FastAPI(title="Endpoint 3 - SageMaker BYOC server")


@app.on_event("startup")
def load_artifacts():
    global MODEL, LABEL_ENCODER, SCHEMA, READY
    try:
        MODEL = joblib.load(os.path.join(MODEL_DIR, "endpoint3_model.joblib"))
        LABEL_ENCODER = joblib.load(os.path.join(MODEL_DIR, "endpoint3_label_encoder.joblib"))
        with open(os.path.join(MODEL_DIR, "schema.json")) as f:
            SCHEMA = json.load(f)
        READY = True
        logger.info(
            f"Model loaded. Expects {SCHEMA['n_gene_features']} gene features "
            f"+ {SCHEMA['n_spatial_features']} spatial features."
        )
    except Exception as e:
        logger.error(f"Failed to load model artifacts: {e}")
        READY = False


@app.get("/ping")
def ping():
    if not READY:
        return Response(status_code=503)
    return Response(status_code=200)


def _build_spatial_features(coords: np.ndarray, upstream_labels: List[str], class_order: List[str]) -> np.ndarray:
    """Same reconstruction as main.py's _build_spatial_features - see that file's
    docstring for the squidpy-vs-sklearn caveat. Kept identical on purpose so this
    hosted endpoint's behavior matches what you already validated in Module 3.
    """
    n_cells = coords.shape[0]
    k = min(N_NEIGHBORS, n_cells - 1)

    nn = NearestNeighbors(n_neighbors=k + 1)
    nn.fit(coords)
    _, neighbor_idx = nn.kneighbors(coords)
    neighbor_idx = neighbor_idx[:, 1:]

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


@app.post("/invocations")
async def invocations(request: Request):
    if not READY:
        raise HTTPException(status_code=503, detail="Model not ready")

    content_type = request.headers.get("content-type", "")
    if "application/json" not in content_type:
        raise HTTPException(status_code=415, detail=f"Unsupported content type: {content_type}")

    body = await request.json()
    cells = body["cells"]

    n_cells = len(cells)
    min_cells = N_NEIGHBORS + 1
    if n_cells < min_cells:
        raise HTTPException(
            status_code=400,
            detail=f"Need at least {min_cells} cells to build a {N_NEIGHBORS}-neighbor spatial graph, got {n_cells}",
        )

    try:
        X_genes = np.asarray([c["expression"] for c in cells], dtype=np.float32)
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

    coords = np.array([[c["x"], c["y"]] for c in cells], dtype=np.float64)
    if not np.isfinite(coords).all():
        raise HTTPException(status_code=400, detail="x/y coordinates must be finite")

    upstream_labels = [c["predicted_label"] for c in cells]

    try:
        X_spatial = _build_spatial_features(coords, upstream_labels, SCHEMA["output_classes"])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    X_combined = np.hstack([X_genes, X_spatial])

    y_pred = MODEL.predict(X_combined)
    y_proba = MODEL.predict_proba(X_combined)
    labels = LABEL_ENCODER.inverse_transform(y_pred).tolist()
    confidence = y_proba.max(axis=1).tolist()

    return {"predicted_labels": labels, "confidence_scores": confidence}
