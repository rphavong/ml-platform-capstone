# Module 6c end-to-end testing turned up a real infrastructure bug: this account's
# default VPC already has a SageMaker Runtime PrivateLink interface endpoint
# (com.amazonaws.us-east-1.sagemaker.runtime) with private DNS enabled - meaning
# runtime.sagemaker.us-east-1.amazonaws.com resolves to a PRIVATE IP inside the VPC for
# everything in it, not SageMaker's real public endpoint. That's normally a good thing
# (traffic never leaves AWS's network), but this endpoint's security group only allowed
# inbound on ports 80, 8000, 30000-32767, and 30917 - never 443, the port SageMaker's
# API actually needs. Every invoke_endpoint() call from inside the cluster was silently
# timing out at the TCP layer trying to reach it, which is what "Timed out waiting for
# the model endpoint" in the proxy services was actually coming from underneath the
# generic error message.
#
# This endpoint - and its security group - already existed in the account before this
# project touched anything (it's not something our own Terraform created), so rather
# than import the whole security group into state (risky - it may be shared by other
# students' work in this class account, and Terraform would then think it fully owns
# and can rewrite every rule on it), this adds exactly one new rule as its own
# standalone resource. That only ever creates/destroys this one rule, and never
# touches anything else already attached to that security group.
resource "aws_security_group_rule" "allow_eks_to_sagemaker_vpc_endpoint" {
  type                     = "ingress"
  from_port                = 443
  to_port                  = 443
  protocol                 = "tcp"
  security_group_id        = "sg-0a7437c8886573758" # pre-existing sagemaker.runtime VPC endpoint SG
  source_security_group_id = aws_eks_cluster.main.vpc_config[0].cluster_security_group_id
  description               = "Allow this project EKS cluster to reach the SageMaker Runtime PrivateLink endpoint (443/tcp) - added after real end-to-end testing surfaced the gap"
}
