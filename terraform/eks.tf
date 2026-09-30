resource "aws_eks_cluster" "main" {
  name     = "${var.project_name}-cluster"
  role_arn = aws_iam_role.eks_cluster.arn
  version  = var.eks_kubernetes_version

  vpc_config {
    subnet_ids = data.aws_subnets.default.ids
  }

  # Terraform must wait for the IAM policy to actually be attached before EKS tries to
  # assume the role - without this, cluster creation can fail intermittently on a fresh
  # apply (IAM changes aren't always instantly consistent across AWS).
  depends_on = [aws_iam_role_policy_attachment.eks_cluster_policy]
}

# Why this exists: our proxy pods get their AWS credentials from the NODE's IAM role
# (the eks-iam.tf fallback, since IRSA was blocked by a missing permission). That role's
# credentials are only reachable through the EC2 instance metadata service (IMDS) at
# 169.254.169.254 - but IMDSv2 ships with a default "hop limit" of 1, meaning only a
# process running directly on the host can reach it. A process inside a pod is one
# extra network hop away (through the pod's own network namespace), so with the
# default hop limit, boto3 running in a pod gets NoCredentialsError even though the
# node's role has the right permissions - the credentials exist, the pod just can't
# reach them. Raising the hop limit to 2 lets pod-level processes reach IMDS too. This
# is a direct consequence of the node-role fallback: with real IRSA, pods would get
# credentials through a webhook instead of IMDS at all, and this wouldn't be needed.
resource "aws_launch_template" "node" {
  name_prefix = "${var.project_name}-node-"

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required" # IMDSv2 only, not the older/less secure IMDSv1
    http_put_response_hop_limit = 2
  }

  tag_specifications {
    resource_type = "instance"
    tags = {
      Name = "${var.project_name}-node"
    }
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_eks_node_group" "main" {
  cluster_name    = aws_eks_cluster.main.name
  node_group_name = "${var.project_name}-node-group"
  node_role_arn   = aws_iam_role.eks_node_group.arn
  subnet_ids      = data.aws_subnets.default.ids

  instance_types = [var.node_instance_type]

  launch_template {
    id      = aws_launch_template.node.id
    version = aws_launch_template.node.latest_version
  }

  scaling_config {
    desired_size = var.node_desired_size
    min_size     = var.node_min_size
    max_size     = var.node_max_size
  }

  # Same reasoning as the cluster's depends_on - the node IAM role needs its 3 policies
  # attached before EC2 instances try to launch and join the cluster with that role.
  depends_on = [
    aws_iam_role_policy_attachment.eks_node_worker_policy,
    aws_iam_role_policy_attachment.eks_node_cni_policy,
    aws_iam_role_policy_attachment.eks_node_ecr_readonly,
  ]
}
