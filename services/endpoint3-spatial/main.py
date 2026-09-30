"""Module 4b: endpoint3, rewritten as a thin proxy in front of the real SageMaker endpoint.

Simpler than endpoint1/2's proxy in one respect: the spatial neighbor-composition math
(_build_spatial_features in the old main.py) now lives entirely inside the SageMaker
endpoint3-byoc container (see sagemaker-packaging/endpoint3-byoc/sagemaker_serve.py).
This service just validates the incoming batch shape and forwards it - no NearestNeighbors
computation happens here anymore.
"""
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List
import json
import logging
import os

import boto3
import numpy as np
from botocore.config import Config
from botocore.exceptions import ClientError, ReadTimeoutError, ConnectTimeoutError, EndpointConnectionError
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

logging.basicConfig(level=logging.INFO)

SERVICE_NAME = "endpoint3-spatial"
SERVICE_TITLE = "Endpoint 3 - Spatial-Aware Malignancy Classifier (SageMaker proxy)"
DATA_SOURCE = "10x Xenium Prime 5K spatial, cervical cancer FFPE, with neighborhood context"

SAGEMAKER_ENDPOINT_NAME = os.environ.get("SAGEMAKER_ENDPOINT_NAME", "assessment4-robert-endpoint3-spatial")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
N_NEIGHBORS = 10  # must match training AND the SageMaker container - used only for the min-cells check here

logger = logging.getLogger(SERVICE_NAME)

MODEL_DIR = Path(os.environ.get("MODEL_DIR", Path(__file__).parent / "model_artifacts"))

SCHEMA = None
READY = False

_boto_config = Config(connect_timeout=5, read_timeout=20, retries={"max_attempts": 2})
runtime = boto3.client("sagemaker-runtime", region_name=AWS_REGION, config=_boto_config)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global SCHEMA, READY
    try:
        with open(MODEL_DIR / "schema.json") as f:
            SCHEMA = json.load(f)
        READY = True
        logger.info(
            f"Schema loaded. Expects {SCHEMA['n_gene_features']} gene features "
            f"+ {SCHEMA['n_spatial_features']} spatial features. "
            f"Routing predictions to SageMaker endpoint: {SAGEMAKER_ENDPOINT_NAME}"
        )
    except Exception as e:
        logger.error(f"Failed to load schema.json: {e}")
        READY = False
    yield


app = FastAPI(title=SERVICE_TITLE, lifespan=lifespan)


class Cell(BaseModel):
    expression: List[float] = Field(..., description="Log-normalized gene expression values")
    x: float
    y: float
    predicted_label: str = Field(..., description="Cell type / malignancy call from endpoint1 or endpoint2")


class PredictRequest(BaseModel):
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
        raise HTTPException(status_code=503, detail="Schema not loaded")
    return {
        "status": "ready",
        "n_gene_features_expected": SCHEMA["n_gene_features"],
        "n_spatial_features_expected": SCHEMA["n_spatial_features"],
        "min_cells_per_request": N_NEIGHBORS + 1,
        "sagemaker_endpoint": SAGEMAKER_ENDPOINT_NAME,
    }


@app.get("/info")
def info():
    if not READY:
        raise HTTPException(status_code=503, detail="Schema not loaded")
    return {
        "service": SERVICE_NAME,
        "data_source": DATA_SOURCE,
        "n_gene_features": SCHEMA["n_gene_features"],
        "n_spatial_features": SCHEMA["n_spatial_features"],
        "output_classes": SCHEMA["output_classes"],
        "n_neighbors": N_NEIGHBORS,
        "sagemaker_endpoint": SAGEMAKER_ENDPOINT_NAME,
        "note": (
            "Each cell's predicted_label must come from endpoint1 or endpoint2 first. "
            "This service is a thin proxy - spatial feature construction and classification "
            "both happen inside the named SageMaker endpoint, not here."
        ),
    }


@app.post("/predict", response_model=PredictResponse)
def predict(request: PredictRequest):
    if not READY:
        raise HTTPException(status_code=503, detail="Service not ready - check /ready")

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

    body = json.dumps({"cells": [c.model_dump() for c in request.cells]})

    try:
        response = runtime.invoke_endpoint(
            EndpointName=SAGEMAKER_ENDPOINT_NAME,
            ContentType="application/json",
            Accept="application/json",
            Body=body,
        )
    except (ReadTimeoutError, ConnectTimeoutError):
        logger.error(f"Timed out waiting for SageMaker endpoint {SAGEMAKER_ENDPOINT_NAME}")
        raise HTTPException(status_code=504, detail="Timed out waiting for the model endpoint")
    except EndpointConnectionError:
        logger.error(f"Could not reach SageMaker endpoint {SAGEMAKER_ENDPOINT_NAME}")
        raise HTTPException(status_code=502, detail="Could not reach the model endpoint")
    except ClientError as e:
        logger.error(f"SageMaker invoke_endpoint failed: {e}")
        detail = "Model endpoint returned an error"
        # A validation error inside the container (e.g. an unseen predicted_label) comes
        # back as a SageMaker ModelError wrapping our own 400 - surface it as a 400 here
        # too, rather than masking it as a generic 502.
        if "ModelError" in str(e) and "400" in str(e):
            raise HTTPException(status_code=400, detail="Invalid predicted_label value for one or more cells")
        raise HTTPException(status_code=502, detail=detail)

    try:
        result = json.loads(response["Body"].read())
    except (json.JSONDecodeError, KeyError) as e:
        logger.error(f"Malformed response from SageMaker: {e}")
        raise HTTPException(status_code=502, detail="Model endpoint returned a malformed response")

    return PredictResponse(**result)
