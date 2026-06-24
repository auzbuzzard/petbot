# --- Container image registry -------------------------------------------------

resource "aws_ecr_repository" "this" {
  name                 = local.core_name
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

data "aws_caller_identity" "current" {}

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
  name               = "${local.core_name}-role"
  assume_role_policy = data.aws_iam_policy_document.assume.json
}

# CloudWatch Logs only — secrets are injected as env at deploy, so the function
# needs no runtime SSM/KMS access. (A future runtime-fetch model would add a
# scoped ssm:GetParameter policy here.)
resource "aws_iam_role_policy_attachment" "logs" {
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Bedrock chat: the agent invokes a foundation model / inference profile in this
# region. Only attached when the chat provider is bedrock (openrouter authes with
# an API key in the environment instead, so it needs no AWS permission).
resource "aws_iam_role_policy" "bedrock" {
  count = var.chat_llm_kind == "bedrock" ? 1 : 0
  name  = "${local.core_name}-bedrock"
  role  = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
      Resource = [
        "arn:aws:bedrock:${var.aws_region}::foundation-model/*",
        "arn:aws:bedrock:${var.aws_region}:${data.aws_caller_identity.current.account_id}:inference-profile/*",
      ]
    }]
  })
}

# --- Function -----------------------------------------------------------------

resource "aws_lambda_function" "this" {
  function_name = local.core_name
  role          = aws_iam_role.lambda.arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.this.repository_url}@${data.aws_ecr_image.this.image_digest}"
  architectures = ["arm64"]
  memory_size   = var.memory_size
  timeout       = var.timeout

  environment {
    # Observability env is empty unless var.observability_enabled (see observability.tf).
    variables = merge(local.lambda_env, local.observability_core_env)
  }

  # Ensure our retention-managed log group exists before the function can be
  # invoked, so Lambda doesn't auto-create an unmanaged, never-expiring one.
  depends_on = [aws_cloudwatch_log_group.lambda]
}

# No Function URL: the worker is private. The edge invokes it with the AWS SDK
# (boto3 `invoke`), authenticated by the edge's scoped IAM identity (see edge.tf).
