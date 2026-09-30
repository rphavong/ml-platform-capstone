"""Module 4b: endpoint1, rewritten as a thin proxy in front of the real SageMaker endpoint.

This is the version that will run in Kubernetes. It no longer loads a model or predicts
in-process - MODEL.predict() is gone entirely, replaced by a call to SageMaker's
invoke_endpoint(), which forwards the request to the endpoint1-byoc container built in
Module 4a. The /health, /ready, /info, /predict contract (and error behavior) stays the
same on purpose, so nothing calling this service needs to change.

schema.json is still bundled here (it's tiny metadata, not the model itself) so this
service can validate request shape and answer /info without a round trip to SageMaker.
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
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

logging.basicConfig(level=logging.INFO)

SERVICE_NAME = "endpoint2-xenium"
SERVICE_TITLE = "Endpoint 2 - Xenium Cell Type & Malignancy Classifier (SageMaker proxy)"
DATA_SOURCE = "10x Xenium Prime spatial, cervical cancer FFPE (same classifier as endpoint1, applied to Xenium cells)"

# The real prediction endpoint this service routes to - the "explicit routing" the
# rubric asks for. Overridable via env var so the same image works across environments
# (dev/staging/prod SageMaker endpoints) without a rebuild.
SAGEMAKER_ENDPOINT_NAME = os.environ.get("SAGEMAKER_ENDPOINT_NAME", "assessment4-robert-endpoint2-xenium")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")

logger = logging.getLogger(SERVICE_NAME)

MODEL_DIR = Path(os.environ.get("MODEL_DIR", Path(__file__).parent / "model_artifacts"))

SCHEMA = None
READY = False

# Explicit, short timeouts: if SageMaker is slow or unreachable, fail fast with a clear
# error instead of letting the caller hang. 2 retries covers a transient network blip
# without turning a real outage into a long stall.
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
            f"Schema loaded. Expects {SCHEMA['n_gene_features']} features. "
            f"Routing predictions to SageMaker endpoint: {SAGEMAKER_ENDPOINT_NAME}"
        )
    except Exception as e:
        logger.error(f"Failed to load schema.json: {e}")
        READY = False
    yield


app = FastAPI(title=SERVICE_TITLE, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # the React dashboard's dev server
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


class PredictRequest(BaseModel):
    cells: List[List[float]] = Field(..., description="List of cells, each a list of gene expression values")


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
        "n_features_expected": SCHEMA["n_gene_features"],
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
        "output_classes": SCHEMA["output_classes"],
        "preprocessing": SCHEMA["preprocessing"],
        "sagemaker_endpoint": SAGEMAKER_ENDPOINT_NAME,
        "note": "This service is a thin proxy - the model itself runs in the named SageMaker endpoint.",
    }


@app.post("/predict", response_model=PredictResponse)
def predict(request: PredictRequest):
    if not READY:
        raise HTTPException(status_code=503, detail="Service not ready - check /ready")

    # Same input validation as before - catching bad requests here means SageMaker
    # never sees malformed input, and the caller gets the same clear 400s as always.
    try:
        X = np.asarray(request.cells, dtype=np.float32)
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

    body = json.dumps({"cells": X.tolist()})

    # --- This is the "explicit routing" step: hand the validated request to the real
    # model, which lives entirely inside the SageMaker endpoint, not this process. ---
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
        raise HTTPException(status_code=502, detail="Model endpoint returned an error")

    try:
        result = json.loads(response["Body"].read())
    except (json.JSONDecodeError, KeyError) as e:
        logger.error(f"Malformed response from SageMaker: {e}")
        raise HTTPException(status_code=502, detail="Model endpoint returned a malformed response")

    return PredictResponse(**result)
