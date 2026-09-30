output "sagemaker_execution_role_arn" {
  value = aws_iam_role.sagemaker_execution.arn
}

output "sagemaker_bucket_name" {
  value = aws_s3_bucket.sagemaker_artifacts.bucket
}

output "ecr_repository_urls" {
  value = { for name, repo in aws_ecr_repository.endpoint : name => repo.repository_url }
}

output "eks_cluster_name" {
  value = aws_eks_cluster.main.name
}

output "eks_cluster_endpoint" {
  value = aws_eks_cluster.main.endpoint
}

output "configure_kubectl_command" {
  description = "Run this after apply to point kubectl at the new cluster."
  value       = "aws eks update-kubeconfig --region ${var.aws_region} --name ${aws_eks_cluster.main.name}"
}
