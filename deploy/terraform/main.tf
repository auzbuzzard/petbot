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
  name                 = "${local.core_name}-role"
  assume_role_policy   = data.aws_iam_policy_document.assume.json
  permissions_boundary = local.workload_boundary_arn
}

resource "aws_iam_role_policy_attachment" "logs" {
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

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

# Bedrock's OpenAI-compatible mantle endpoint, SigV4-signed with this role, so the agent
# holds no API key. CreateInference is authorized against a mantle project; the stack names
# none, so the grant covers the Region's projects, for the configured model only. The
# reference lists bedrock-mantle:Model without its value's format, so the condition matches
# the model ID anywhere in it:
# https://docs.aws.amazon.com/service-authorization/latest/reference/list_bedrock-mantle.html
# Only attached for bedrock_mantle.
resource "aws_iam_role_policy" "bedrock_mantle" {
  count = var.chat_llm_kind == "bedrock_mantle" ? 1 : 0
  name  = "${local.core_name}-bedrock-mantle"
  role  = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "bedrock-mantle:CreateInference"
      Resource  = "arn:aws:bedrock-mantle:${var.aws_region}:${data.aws_caller_identity.current.account_id}:project/*"
      Condition = { StringLike = { "bedrock-mantle:Model" = "*${var.chat_llm_model}*" } }
    }]
  })
}

resource "aws_lambda_function" "this" {
  function_name = local.core_name
  role          = aws_iam_role.lambda.arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.this.repository_url}@${data.aws_ecr_image.this.image_digest}"
  architectures = ["arm64"]
  memory_size   = var.memory_size
  timeout       = var.timeout

  environment {
    variables = merge(local.lambda_env, local.observability_core_env)
  }

  # Ensure our retention-managed log group exists before the function can be
  # invoked, so Lambda doesn't auto-create an unmanaged, never-expiring one, and that
  # its secrets exist and it may read them before its first cold start.
  depends_on = [aws_cloudwatch_log_group.lambda, aws_iam_role_policy.core_secrets, aws_ssm_parameter.owned]

  lifecycle {
    precondition {
      condition     = !local.chat_needs_api_key || trimspace(var.chat_llm_api_key_ssm_parameter) != ""
      error_message = "chat_llm_kind=${var.chat_llm_kind} requires chat_llm_api_key_ssm_parameter (the SSM SecureString holding the key)."
    }
    precondition {
      condition     = !contains(["bedrock_mantle", "openai_compatible"], var.chat_llm_kind) || trimspace(var.chat_llm_base_url) != ""
      error_message = "chat_llm_kind=${var.chat_llm_kind} requires chat_llm_base_url (the endpoint)."
    }
  }
}

# No Function URL: the worker is private. The edge invokes it with the AWS SDK
# (boto3 `invoke`), authenticated by the edge's scoped IAM identity (see edge.tf).
