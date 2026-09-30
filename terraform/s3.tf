# The bucket you created by hand in Module 4a with `aws s3 mb`. Declared here with
# no extra settings (no ACL, no versioning) to match exactly what already exists -
# importing a resource and then immediately having Terraform want to "fix" settings
# you never configured is a common first-import surprise, so keep this minimal on
# purpose until you deliberately decide to add something like versioning.
resource "aws_s3_bucket" "sagemaker_artifacts" {
  bucket = "${var.project_name}-sagemaker"
}
