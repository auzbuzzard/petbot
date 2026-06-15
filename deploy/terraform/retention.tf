# Data-growth controls. Without these, pushed images and logs accumulate
# forever. Managing the log group here also means `terraform destroy` removes it
# (otherwise Lambda auto-creates a never-expiring group that TF wouldn't own).

resource "aws_ecr_lifecycle_policy" "this" {
  repository = aws_ecr_repository.this.name

  policy = jsonencode({
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

resource "aws_cloudwatch_log_group" "lambda" {
  # Lambda writes to /aws/lambda/<function-name>; creating it explicitly lets us
  # set retention (and own its lifecycle) instead of the never-expire default.
  name              = "/aws/lambda/${var.name_prefix}"
  retention_in_days = var.log_retention_days
}
