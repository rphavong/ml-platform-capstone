# The names "endpoint1", "endpoint2", "endpoint3" are used repeatedly across this
# file and iam.tf - defined once here (local, not variable, since these three don't
# change) rather than spelling out three nearly-identical resource blocks by hand.
locals {
  endpoint_names = ["endpoint1", "endpoint2", "endpoint3"]
}

resource "aws_ecr_repository" "endpoint" {
  for_each = toset(local.endpoint_names)

  name = "${var.project_name}-${each.key}"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = false
  }
}
