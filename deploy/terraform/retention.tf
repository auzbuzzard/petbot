# Data-growth controls. Without these, pushed images and logs accumulate
# forever. Managing the log group here also means `terraform destroy` removes it
# (otherwise Lambda auto-creates a never-expiring group that TF wouldn't own).

locals {
  ecr_lifecycle_policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Expire untagged images"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = var.ecr_untagged_expire_days
        }
        action = { type = "expire" }
      },
      {
        rulePriority = 2
        description  = "Keep only the most recent tagged images"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = var.ecr_keep_last_images
        }
        action = { type = "expire" }
      },
    ]
  })
}

resource "aws_ecr_lifecycle_policy" "this" {
  repository = aws_ecr_repository.this.name
  policy     = local.ecr_lifecycle_policy
}

resource "aws_ecr_lifecycle_policy" "edge" {
  count = local.edge_count

  repository = aws_ecr_repository.edge[0].name
  policy     = local.ecr_lifecycle_policy
}

resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${local.core_name}"
  retention_in_days = var.log_retention_days
}
