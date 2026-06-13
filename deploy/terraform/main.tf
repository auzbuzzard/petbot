data "aws_caller_identity" "current" {}

# --- Container image registry -------------------------------------------------

resource "aws_ecr_repository" "this" {
  name                 = var.name_prefix
  image_tag_mutability = "MUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }
}

# Resolve the tag to an immutable digest so re-pushing the same tag and
# re-applying actually updates the function. Requires the image to exist before
# the main apply (see the two-step bootstrap in README).
data "aws_ecr_image" "this" {
  repository_name = aws_ecr_repository.this.name
  image_tag       = var.image_tag
}

# --- Execution role -----------------------------------------------------------

data "aws_iam_policy_document" "assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda" {
  name               = "${var.name_prefix}-role"
  assume_role_policy = data.aws_iam_policy_document.assume.json
}

# CloudWatch Logs only — secrets are injected as env at deploy, so the function
# needs no runtime SSM/KMS access. (A future runtime-fetch model would add a
# scoped ssm:GetParameter policy here.)
resource "aws_iam_role_policy_attachment" "logs" {
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# --- Function + public URL ----------------------------------------------------

resource "aws_lambda_function" "this" {
  function_name = var.name_prefix
  role          = aws_iam_role.lambda.arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.this.repository_url}@${data.aws_ecr_image.this.image_digest}"
  architectures = ["arm64"]
  memory_size   = var.memory_size
  timeout       = var.timeout

  environment {
    variables = local.lambda_env
  }
}

resource "aws_lambda_function_url" "this" {
  function_name      = aws_lambda_function.this.function_name
  authorization_type = "NONE"
}

# AUTH_NONE still requires an explicit public-invoke permission; the security
# boundary is the Ed25519 signature the handler verifies, not IAM.
resource "aws_lambda_permission" "function_url" {
  statement_id           = "FunctionURLAllowPublicAccess"
  action                 = "lambda:InvokeFunctionUrl"
  function_name          = aws_lambda_function.this.function_name
  principal              = "*"
  function_url_auth_type = "NONE"
}
