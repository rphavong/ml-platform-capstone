"""Module 4a: package endpoint1's model for SageMaker, deploy a real endpoint, test it.
 
Run this from services/endpoint1-flex/ on your Mac (that's where model_artifacts/ lives).
Needs: pip install boto3   (that's the only dependency - the container image URI below
is a fixed string, not looked up through the heavier sagemaker SDK, which keeps this
script simple to read and easy to port into Terraform in Module 5).
 
What this script does, in order:
  1. Bundles your model files + inference.py into model.tar.gz (the shape SageMaker's
     XGBoost framework container expects: artifacts at the root, your inference code
     under code/).
  2. Uploads that tar.gz to your new S3 bucket.
  3. Creates a SageMaker Model, EndpointConfig, and Endpoint (the three-step SageMaker
     API - a Model is "here's the code+weights", an EndpointConfig is "here's how much
     compute", an Endpoint is "actually go live with that combination").
  4. Waits for it to become InService (takes several minutes - SageMaker is spinning up
     a real container on a real instance behind the scenes).
  5. Sends one real invoke_endpoint request using your test_payload.json cells, so you
     can see it work end-to-end before we touch main.py at all.
"""
import json
import tarfile
import time
from pathlib import Path
 
import boto3
 
# --- Fill these in / confirm before running ---
REGION = "us-east-1"
ROLE_ARN = "arn:aws:iam::388691194728:role/assessment4-robert-sagemaker-role"
BUCKET = "assessment4-robert-sagemaker"
ENDPOINT_NAME = "assessment4-robert-endpoint1-flex"
S3_KEY = "endpoint1/model.tar.gz"
INSTANCE_TYPE = "ml.t2.medium"  # small/cheap - plenty for a single joblib model at this scale
 
HERE = Path(__file__).parent
MODEL_ARTIFACTS = HERE / "model_artifacts"
BUILD_DIR = HERE / "_sagemaker_build"
 
session = boto3.Session(region_name=REGION)
sm = session.client("sagemaker")
s3 = session.client("s3")
 
 
def build_tarball():
    BUILD_DIR.mkdir(exist_ok=True)
    tar_path = BUILD_DIR / "model.tar.gz"
    with tarfile.open(tar_path, "w:gz") as tar:
        for fname in ["endpoint1_model.joblib", "endpoint1_label_encoder.joblib", "schema.json"]:
            tar.add(MODEL_ARTIFACTS / fname, arcname=fname)
        # inference.py goes under code/ - that's the convention SAGEMAKER_SUBMIT_DIRECTORY
        # below points at, which is how the container finds your custom handlers.
        tar.add(HERE / "inference.py", arcname="code/inference.py")
    print(f"Built {tar_path} ({tar_path.stat().st_size / 1024:.0f} KB)")
    return tar_path
 
 
def upload(tar_path):
    s3.upload_file(str(tar_path), BUCKET, S3_KEY)
    s3_uri = f"s3://{BUCKET}/{S3_KEY}"
    print(f"Uploaded to {s3_uri}")
    return s3_uri
 
 
# AWS publishes a pre-built XGBoost container per region, hosted in an AWS-owned ECR
# registry. "683313688378" is AWS's account ID for SageMaker's built-in algorithm images
# in us-east-1 specifically - it's a different number in other regions (AWS's docs list
# them all under "Docker Registry Paths for SageMaker Built-in Algorithms"). Same image
# serves both algorithm-mode and framework/script-mode - which one it runs as depends on
# whether SAGEMAKER_PROGRAM is set in the model's Environment (we set it, below).
XGBOOST_IMAGE_URI = "683313688378.dkr.ecr.us-east-1.amazonaws.com/sagemaker-xgboost:1.7-1"
 
 
def deploy(s3_uri):
    image_uri = XGBOOST_IMAGE_URI
    print(f"Using container image: {image_uri}")
 
    model_name = f"{ENDPOINT_NAME}-model"
    config_name = f"{ENDPOINT_NAME}-config"
 
    sm.create_model(
        ModelName=model_name,
        ExecutionRoleArn=ROLE_ARN,
        PrimaryContainer={
            "Image": image_uri,
            "ModelDataUrl": s3_uri,
            "Environment": {
                "SAGEMAKER_PROGRAM": "inference.py",
                "SAGEMAKER_SUBMIT_DIRECTORY": "/opt/ml/model/code",
            },
        },
    )
    print(f"Created model: {model_name}")
 
    sm.create_endpoint_config(
        EndpointConfigName=config_name,
        ProductionVariants=[
            {
                "VariantName": "AllTraffic",
                "ModelName": model_name,
                "InstanceType": INSTANCE_TYPE,
                "InitialInstanceCount": 1,
            }
        ],
    )
    print(f"Created endpoint config: {config_name}")
 
    sm.create_endpoint(EndpointName=ENDPOINT_NAME, EndpointConfigName=config_name)
    print(f"Creating endpoint: {ENDPOINT_NAME} (this takes several minutes)...")
 
    while True:
        status = sm.describe_endpoint(EndpointName=ENDPOINT_NAME)["EndpointStatus"]
        print(f"  status: {status}")
        if status in ("InService", "Failed"):
            break
        time.sleep(30)
 
    if status == "Failed":
        reason = sm.describe_endpoint(EndpointName=ENDPOINT_NAME)["FailureReason"]
        raise SystemExit(f"Endpoint failed to deploy: {reason}")
    print("Endpoint is InService")
 
 
def test_invoke():
    runtime = session.client("sagemaker-runtime")
    payload = json.loads((MODEL_ARTIFACTS / "test_payload.json").read_text())
    body = json.dumps({"cells": payload["example_cells"]})
 
    response = runtime.invoke_endpoint(
        EndpointName=ENDPOINT_NAME,
        ContentType="application/json",
        Accept="application/json",
        Body=body,
    )
    result = json.loads(response["Body"].read())
    print("\nReal SageMaker endpoint response:")
    print("  predicted:", result["predicted_labels"])
    print("  expected: ", payload["expected_labels"])
    print("  match:    ", result["predicted_labels"] == payload["expected_labels"])
 
 
if __name__ == "__main__":
    tar_path = build_tarball()
    s3_uri = upload(tar_path)
    deploy(s3_uri)
    test_invoke()