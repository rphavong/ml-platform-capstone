"""Module 4a (BYOC) for endpoint2. Same pattern as endpoint1's package_and_deploy.py -
the only real differences are the names/paths below and which model_artifacts/ folder
we read from. The model files themselves are byte-identical to endpoint1's (confirmed
earlier via md5) - endpoint2 just applies that same Flex-trained classifier to Xenium
cells, so it gets its own dedicated SageMaker endpoint to match the rubric's "3 separate
endpoints" requirement, even though the model inside is the same one.

Run this from sagemaker-packaging/endpoint2-byoc/.
Needs: pip install boto3
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
ENDPOINT_NAME = "assessment4-robert-endpoint2-xenium"
S3_KEY = "endpoint2/model.tar.gz"
INSTANCE_TYPE = "ml.t2.medium"

ECR_IMAGE_URI = f"{ACCOUNT_ID}.dkr.ecr.{REGION}.amazonaws.com/assessment4-robert-endpoint2:latest"

HERE = Path(__file__).parent
# endpoint2-xenium's model_artifacts/ folder - it holds the same files as endpoint1's
# (still named endpoint1_model.joblib etc. inside), just copied into its own service dir.
MODEL_ARTIFACTS = HERE.parent.parent / "services" / "endpoint2-xenium" / "model_artifacts"
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
