"""Module 4a (BYOC version): package endpoint1's model for SageMaker, deploy a real
endpoint using OUR OWN container image, test it.
 
Run this from sagemaker-packaging/endpoint1-byoc/ (adjust MODEL_ARTIFACTS below if your
folder layout differs - it currently expects services/endpoint1-flex/model_artifacts/ two
levels up, matching the ml-platform-capstone repo layout).
 
Needs: pip install boto3
 
What changed vs. the first attempt (package_and_deploy.py under sagemaker-packaging/endpoint1/):
  - No more inference.py bundling, no SAGEMAKER_PROGRAM / SAGEMAKER_SUBMIT_DIRECTORY env
    vars. Those were only needed to tell AWS's pre-built framework container how to load
    your custom code. Our own image already knows how to serve the model - it has no
    "framework mode" to configure, it just runs sagemaker_serve.py.
  - Image is ECR_IMAGE_URI (your own pushed image) instead of AWS's XGBOOST_IMAGE_URI.
  - model.tar.gz now only contains the 3 artifact files - no code/ subfolder.
 
Steps, in order:
  1. Bundle endpoint1_model.joblib, endpoint1_label_encoder.joblib, schema.json into
     model.tar.gz.
  2. Upload that tar.gz to S3.
  3. Create a SageMaker Model (pointing at your ECR image + the tar.gz), EndpointConfig,
     and Endpoint.
  4. Wait for it to become InService.
  5. Send one real invoke_endpoint request using test_payload.json, compare against
     expected_labels.
"""
import json
import tarfile
import time
from pathlib import Path
 
import boto3
 
# --- Fill these in / confirm before running ---
REGION = "us-east-1"
ACCOUNT_ID = "388691194728"
ROLE_ARN = f"arn:aws:iam::{ACCOUNT_ID}:role/assessment4-robert-sagemaker-role"
BUCKET = "assessment4-robert-sagemaker"
ENDPOINT_NAME = "assessment4-robert-endpoint1-flex"
S3_KEY = "endpoint1/model.tar.gz"
INSTANCE_TYPE = "ml.t2.medium"
 
# Your own image, pushed to ECR in Step 3 of this module.
ECR_IMAGE_URI = f"{ACCOUNT_ID}.dkr.ecr.{REGION}.amazonaws.com/assessment4-robert-endpoint1:latest"
 
HERE = Path(__file__).parent
# Adjust this if your model_artifacts/ folder lives somewhere else relative to this script.
MODEL_ARTIFACTS = HERE.parent.parent / "services" / "endpoint1-flex" / "model_artifacts"
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
    print(f"Built {tar_path} ({tar_path.stat().st_size / 1024:.0f} KB)")
    return tar_path
 
 
def upload(tar_path):
    s3.upload_file(str(tar_path), BUCKET, S3_KEY)
    s3_uri = f"s3://{BUCKET}/{S3_KEY}"
    print(f"Uploaded to {s3_uri}")
    return s3_uri
 
 
def deploy(s3_uri):
    print(f"Using container image: {ECR_IMAGE_URI}")
 
    model_name = f"{ENDPOINT_NAME}-model"
    config_name = f"{ENDPOINT_NAME}-config"
 
    sm.create_model(
        ModelName=model_name,
        ExecutionRoleArn=ROLE_ARN,
        PrimaryContainer={
            "Image": ECR_IMAGE_URI,
            "ModelDataUrl": s3_uri,
            # No Environment block needed - this is our own image, not AWS's framework
            # container, so there's no SAGEMAKER_PROGRAM to point at custom code.
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