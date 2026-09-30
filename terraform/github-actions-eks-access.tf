# Module 7 (rubric gap fix): lets the SAME scoped-down GitHub Actions IAM user
# (github-actions-iam.tf, already used for ECR push) also run kubectl against the
# live cluster from cd.yml's new deploy job - without handing it admin access.
#
# EKS Access Entries (not the older aws-auth ConfigMap) are the modern way to map an
# IAM principal to in-cluster permissions - they're an EKS API resource, so Terraform
# manages the mapping directly instead of editing a ConfigMap by hand. The policy
# association below is scoped to exactly the 2 namespaces this project uses
# (single-cell-genomics, spatial-analysis) - same least-privilege pattern as
# pod-fallback-iam.tf and the ECR-push policy: this user can `kubectl set image` /
# `rollout status` / `get pods` there, nothing else, nowhere else in the cluster.
resource "aws_eks_access_entry" "github_actions" {
  cluster_name  = aws_eks_cluster.main.name
  principal_arn = aws_iam_user.github_actions.arn
}

resource "aws_eks_access_policy_association" "github_actions_edit" {
  cluster_name  = aws_eks_cluster.main.name
  principal_arn = aws_iam_user.github_actions.arn
  policy_arn    = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSEditPolicy"

  access_scope {
    type       = "namespace"
    namespaces = ["single-cell-genomics", "spatial-analysis"]
  }
}

# aws eks update-kubeconfig (which cd.yml's deploy job runs before any kubectl
# command) needs eks:DescribeCluster on top of the access entry above - the access
# entry controls what kubectl can DO once connected, this controls whether the AWS
# CLI can even look up the cluster's endpoint/certificate to connect in the first place.
resource "aws_iam_user_policy" "github_actions_eks_describe" {
  name = "describe-cluster-for-kubeconfig"
  user = aws_iam_user.github_actions.name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "DescribeClusterForKubeconfig"
        Effect   = "Allow"
        Action   = "eks:DescribeCluster"
        Resource = aws_eks_cluster.main.arn
      }
    ]
  })
}
