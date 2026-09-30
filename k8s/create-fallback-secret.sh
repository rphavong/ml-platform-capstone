#!/bin/bash
# Creates the sagemaker-invoke-fallback Secret in BOTH namespaces from Terraform's
# outputs. Never commit the actual key values to git - this script pulls them fresh
# from `terraform output` each time, and `kubectl create secret` is imperative (no
# YAML manifest with real values ever touches disk or the repo).
#
# Run this once after `terraform apply` has created pod-fallback-iam.tf's resources,
# and again any time you rotate the key (re-run `terraform apply -replace=...` first).
set -euo pipefail
cd "$(dirname "$0")/../terraform"

AK=$(terraform output -raw pod_fallback_access_key_id)
SK=$(terraform output -raw pod_fallback_secret_access_key)

for ns in single-cell-genomics spatial-analysis; do
  kubectl create secret generic sagemaker-invoke-fallback \
    --namespace "$ns" \
    --from-literal=access_key_id="$AK" \
    --from-literal=secret_access_key="$SK" \
    --dry-run=client -o yaml | kubectl apply -f -
  echo "Secret sagemaker-invoke-fallback created/updated in namespace $ns"
done
