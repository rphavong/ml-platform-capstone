# The execution role you created by hand for SageMaker to assume, plus its two
# inline policies (S3+CloudWatch from Module 4a, ECR pull from Module 4a's later
# step). The exact policy NAMES below are placeholders - run the command in the
# accompanying instructions to get your real ones, then edit the two
# aws_iam_role_policy "name" values below to match before importing.

resource "aws_iam_role" "sagemaker_execution" {
  name = "${var.project_name}-sagemaker-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Principal = { Service = "sagemaker.amazonaws.com" }
        Action    = "sts:AssumeRole"
      }
    ]
  })
}

# --- Inline policy 1: S3 read/write on the artifacts bucket, CloudWatch Logs write ---
resource "aws_iam_role_policy" "s3_and_logs" {
  name = "sagemaker-model-bucket-access"
  role = aws_iam_role.sagemaker_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "ReadWriteModelBucket"
        Effect = "Allow"
        Action = ["s3:GetObject", "s3:PutObject", "s3:ListBucket"]
        Resource = [
          aws_s3_bucket.sagemaker_artifacts.arn,
          "${aws_s3_bucket.sagemaker_artifacts.arn}/*",
        ]
      },
      {
        Sid    = "WriteCloudWatchLogs"
        Effect = "Allow"
        Action = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents", "logs:DescribeLogStreams"]
        # Account ID wildcarded on purpose, matching the policy you applied by hand in
        # Module 4a - a CloudWatch Logs ARN is internal-only (unlike an S3 bucket name,
        # which is a public global DNS name), so wildcarding it here is a deliberate
        # privacy choice you made, not a mistake to "fix" by filling in the real ID.
        Resource = "arn:aws:logs:${var.aws_region}:*:log-group:/aws/sagemaker/*"
      },
    ]
  })
}

# --- Inline policy 2: pull permission for the 3 BYOC images from Module 4a ---
resource "aws_iam_role_policy" "ecr_pull" {
  name = "ecr-pull-endpoint1-image" 
  role = aws_iam_role.sagemaker_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "PullEndpointImages"
        Effect   = "Allow"
        Action   = ["ecr:GetAuthorizationToken"]
        Resource = "*"
      },
      {
        Sid    = "PullEndpointImageLayers"
        Effect = "Allow"
        Action = ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer", "ecr:BatchCheckLayerAvailability"]
        Resource = [for name in local.endpoint_names :
          "arn:aws:ecr:${var.aws_region}:*:repository/${var.project_name}-${name}"
        ]
      },
    ]
  })
}
