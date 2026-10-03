# Module 7: a dedicated IAM user for the GitHub Actions CD pipeline, scoped to exactly
# what cd.yml needs and nothing else - push images to this project's 3 ECR repos. This
# is deliberately its own IAM user rather than reusing your own AWS CLI credentials
# if this key ever
# leaked from a GitHub secret, the blast radius is "can push to 3 ECR repos," not
# "can do anything you personally can do in this account."
resource "aws_iam_user" "github_actions" {
  name = "${var.project_name}-github-actions"
}

resource "aws_iam_access_key" "github_actions" {
  user = aws_iam_user.github_actions.name
}

# ecr:GetAuthorizationToken is required for `docker login` to ECR, but AWS does not
# support scoping it to specific repositories - it's always account-wide by design
# (the token it returns is a general docker-login credential, not repo-specific), so
# this one action necessarily has Resource = "*". Everything else below - the actual
# push/pull actions - IS scoped to just this project's 3 repo ARNs.
resource "aws_iam_user_policy" "github_actions_ecr_push" {
  name = "push-to-project-ecr-repos"
  user = aws_iam_user.github_actions.name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "EcrAuthToken"
        Effect   = "Allow"
        Action   = "ecr:GetAuthorizationToken"
        Resource = "*"
      },
      {
        Sid    = "EcrPushPullThisProjectOnly"
        Effect = "Allow"
        Action = [
          "ecr:BatchCheckLayerAvailability",
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage",
          "ecr:PutImage",
          "ecr:InitiateLayerUpload",
          "ecr:UploadLayerPart",
          "ecr:CompleteLayerUpload",
        ]
        Resource = [for repo in aws_ecr_repository.endpoint : repo.arn]
      }
    ]
  })
}

output "github_actions_access_key_id" {
  description = "Add this as the AWS_ACCESS_KEY_ID secret in GitHub repo settings."
  value       = aws_iam_access_key.github_actions.id
}

output "github_actions_secret_access_key" {
  description = "Add this as the AWS_SECRET_ACCESS_KEY secret in GitHub repo settings. Only ever shown once via `terraform output` - AWS does not let you retrieve an existing secret key again, only rotate to a new one."
  value       = aws_iam_access_key.github_actions.secret
  sensitive   = true
}
