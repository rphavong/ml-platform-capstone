# Module 5a: Terraform setup. Pinning the AWS provider version (not just Terraform
# itself) matters the same way pinning xgboost/numpy did earlier in this project -
# without it, a `terraform init` run months from now could silently pull a newer
# provider with different defaults and produce a different plan than what you tested.
terraform {
  required_version = ">= 1.7.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}
