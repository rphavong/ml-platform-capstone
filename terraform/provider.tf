provider "aws" {
  region = var.aws_region
}

# Used throughout instead of a hardcoded account ID - the same privacy preference
# you applied by hand to the IAM/CloudWatch ARNs in Module 4a's JSON policies.
data "aws_caller_identity" "current" {}
