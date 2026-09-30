# Using the account's default VPC/subnets rather than building a dedicated VPC module.
# A from-scratch VPC (custom CIDR, public/private subnet split, NAT gateway) is the
# "real" production pattern, but NAT gateways alone run ~$0.045/hr on top of everything
# else - not worth it for a class account building toward a demo. The default VPC's
# subnets are public (have a route to an internet gateway already), which is fine here
# since nothing sensitive is exposed - your services stay behind Kubernetes/SageMaker's
# own access controls either way.
data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }

  # AWS randomizes which physical availability zone each account's "us-east-1a",
  # "us-east-1e", etc. names map to - so one account's us-east-1e can be a zone EKS
  # doesn't support control planes in, even though that's not true for every account.
  # This filters to the 5 zones THIS account's EKS confirmed it supports (from the
  # UnsupportedAvailabilityZoneException error), rather than guessing an AZ list that
  # would work for everyone.
  filter {
    name   = "availability-zone"
    values = ["us-east-1a", "us-east-1b", "us-east-1c", "us-east-1d", "us-east-1f"]
  }
}
