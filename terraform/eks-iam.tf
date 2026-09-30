# Two SEPARATE IAM roles here, easy to mix up if you're new to EKS:
#   - eks_cluster: assumed by the EKS SERVICE itself, to manage the control plane
#     (talk to EC2/ELB/etc on your behalf).
#   - eks_node_group: assumed by the actual EC2 WORKER NODES, so kubelet running on
#     each instance can register with the cluster, pull images from ECR, and use the
#     VPC CNI networking plugin.
# Neither of these is the assessment4-robert-sagemaker-role from iam.tf - that one is
# for SageMaker specifically and has nothing to do with Kubernetes.

resource "aws_iam_role" "eks_cluster" {
  name = "${var.project_name}-eks-cluster-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Principal = { Service = "eks.amazonaws.com" }
        Action    = "sts:AssumeRole"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "eks_cluster_policy" {
  role       = aws_iam_role.eks_cluster.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy"
}

resource "aws_iam_role" "eks_node_group" {
  name = "${var.project_name}-eks-node-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Principal = { Service = "ec2.amazonaws.com" }
        Action    = "sts:AssumeRole"
      }
    ]
  })
}

# Three AWS-managed policies a worker node needs: run as a kubelet, use the VPC CNI
# networking plugin, and pull container images (your 3 proxy service images) from ECR.
resource "aws_iam_role_policy_attachment" "eks_node_worker_policy" {
  role       = aws_iam_role.eks_node_group.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy"
}

resource "aws_iam_role_policy_attachment" "eks_node_cni_policy" {
  role       = aws_iam_role.eks_node_group.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy"
}

resource "aws_iam_role_policy_attachment" "eks_node_ecr_readonly" {
  role       = aws_iam_role.eks_node_group.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
}

# The proxy services need to call sagemaker-runtime.invoke_endpoint() (Module 4b). The
# textbook-correct pattern is IRSA (IAM Roles for Service Accounts) - a role only a
# specific Kubernetes ServiceAccount can assume, so this permission stays scoped to just
# the proxy pods, not every pod on the node. That needs iam:CreateOpenIDConnectProvider,
# which this class AWS account's IAM user does not have - confirmed by a real AccessDenied
# error when we tried it. Rather than block progress on getting that permission granted,
# this policy is attached directly to the NODE's role instead: every pod on the node
# technically shares it (a real tradeoff worth naming out loud - IRSA exists specifically
# to avoid this), but it's still scoped to exactly the 3 endpoints below, not a blanket
# SageMaker grant, and it works with the permissions already available.
locals {
  sagemaker_endpoint_names = [
    "${var.project_name}-endpoint1-flex",
    "${var.project_name}-endpoint2-xenium",
    "${var.project_name}-endpoint3-spatial",
  ]
}

resource "aws_iam_role_policy" "node_invoke_sagemaker" {
  name = "invoke-sagemaker-endpoints"
  role = aws_iam_role.eks_node_group.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "InvokeOurThreeEndpointsOnly"
        Effect   = "Allow"
        Action   = "sagemaker:InvokeEndpoint"
        Resource = [for name in local.sagemaker_endpoint_names :
          "arn:aws:sagemaker:${var.aws_region}:*:endpoint/${name}"
        ]
      }
    ]
  })
}
