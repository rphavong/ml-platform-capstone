"""SageMaker script-mode entry point for endpoint1 (Flex classifier).
 
SageMaker's XGBoost framework container calls these four functions in order for
every request: model_fn (once, at startup) -> input_fn -> predict_fn -> output_fn.
This mirrors exactly what services/endpoint1-flex/main.py's /predict does today -
the model, the label encoder, and the validation logic are unchanged. Only WHERE
this code runs is different: inside a SageMaker-managed container instead of your
own FastAPI process.
"""
import json
import os
 
import joblib
import numpy as np
 
 
def model_fn(model_dir):
    """Called once when the endpoint's container starts. Loads everything into memory."""
    model = joblib.load(os.path.join(model_dir, "endpoint1_model.joblib"))
    label_encoder = joblib.load(os.path.join(model_dir, "endpoint1_label_encoder.joblib"))
    with open(os.path.join(model_dir, "schema.json")) as f:
        schema = json.load(f)
    return {"model": model, "label_encoder": label_encoder, "schema": schema}
 
 
def input_fn(request_body, request_content_type):
    """Parses the incoming request body. We only accept JSON, same as the FastAPI service."""
    if request_content_type != "application/json":
        raise ValueError(f"Unsupported content type: {request_content_type}")
    payload = json.loads(request_body)
    cells = payload["cells"]
 
    try:
        X = np.asarray(cells, dtype=np.float32)
    except ValueError:
        raise ValueError("Every cell must have the same number of values")
    return X
 
 
def predict_fn(X, loaded):
    """Runs the actual prediction. Same validation + logic as main.py's /predict."""
    model = loaded["model"]
    label_encoder = loaded["label_encoder"]
    schema = loaded["schema"]
 
    expected_features = schema["n_gene_features"]
    if X.ndim != 2 or X.shape[1] != expected_features:
        raise ValueError(f"Expected each cell to have {expected_features} features, got shape {X.shape}")
    if not np.isfinite(X).all():
        raise ValueError("Expression values must be finite (no NaN or Infinity)")
 
    y_pred = model.predict(X)
    y_proba = model.predict_proba(X)
    labels = label_encoder.inverse_transform(y_pred).tolist()
    confidence = y_proba.max(axis=1).tolist()
    return {"predicted_labels": labels, "confidence_scores": confidence}
 
 
def output_fn(prediction, accept):
    """Serializes the result back to JSON."""
    if accept != "application/json":
        raise ValueError(f"Unsupported accept type: {accept}")
    return json.dumps(prediction), accept