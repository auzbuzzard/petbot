# --- The edge's ECR repository (shared by both host options) -------------------
#
# The edge holds the Discord gateway (an outbound WebSocket) and dispatches each
# @mention to the core worker Lambda. Where it RUNS is var.edge_host:
#   lightsail - a Lightsail container service (this file). Flat-rate, IPv4
#               bundled, immutable push; but new accounts can have a 0 quota.
#   fargate   - an ECS Fargate service (edge_fargate.tf). No Lightsail quota; the
#               task gets an IAM role (no static key).
# Both pull the same amd64 edge image from this ECR repo.

resource "aws_ecr_repository" "edge" {
  name                 = local.edge_name
  image_tag_mutability = "MUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }
}

# The Discord token's SSM parameter ARN — both hosts reference it (Lightsail reads
# the value into env; Fargate hands the ARN to ECS to fetch at task launch).
locals {
  discord_token_arn = "arn:aws:ssm:${var.aws_region}:${data.aws_caller_identity.current.account_id}:parameter${var.discord_token_ssm_parameter}"
}

# --- Lightsail host (var.edge_host == "lightsail") ----------------------------
# Serves no HTTP (no public_endpoint); the container runs reachable only on the
# private domain it never needs. Image is linux/amd64 (Lightsail is amd64-only).
# Pulls from ECR via an "image puller" principal granted read on the repo.

locals {
  on_lightsail = var.edge_host == "lightsail"
}

resource "aws_lightsail_container_service" "edge" {
  count = local.on_lightsail ? 1 : 0
  name  = local.edge_name
  power = var.edge_power
  scale = var.edge_scale

  private_registry_access {
    ecr_image_puller_role {
      is_active = true
    }
  }
}

resource "aws_ecr_repository_policy" "edge" {
  count      = local.on_lightsail ? 1 : 0
  repository = aws_ecr_repository.edge.name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "AllowLightsailPull"
      Effect    = "Allow"
      Principal = { AWS = aws_lightsail_container_service.edge[0].private_registry_access[0].ecr_image_puller_role[0].principal_arn }
      Action    = ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"]
    }]
  })
}

# The deployment — only once an image tag is supplied (CI pushes, then passes it).
resource "aws_lightsail_container_service_deployment_version" "edge" {
  count        = local.on_lightsail && var.edge_image_tag != "" ? 1 : 0
  service_name = aws_lightsail_container_service.edge[0].name

  container {
    container_name = "edge"
    image          = "${aws_ecr_repository.edge.repository_url}:${var.edge_image_tag}"

    environment = {
      LOG_LEVEL             = var.log_level
      ENV                   = var.lambda_environment
      WORKER__KIND          = "lambda"
      WORKER__FUNCTION_NAME = aws_lambda_function.this.function_name
      AWS_REGION            = var.aws_region
      # Lightsail has no IAM instance role, so a scoped static key is the
      # mechanism; boto3's default credential chain reads it.
      AWS_ACCESS_KEY_ID     = aws_iam_access_key.edge[0].id
      AWS_SECRET_ACCESS_KEY = aws_iam_access_key.edge[0].secret
      DISCORD_TOKEN         = data.aws_ssm_parameter.discord_token[0].value
    }
  }

  depends_on = [aws_ecr_repository_policy.edge]
}

data "aws_ssm_parameter" "discord_token" {
  count           = local.on_lightsail ? 1 : 0
  name            = var.discord_token_ssm_parameter
  with_decryption = true
}

# The Lightsail edge's scoped AWS identity (Fargate uses a task role instead).
resource "aws_iam_user" "edge" {
  count = local.on_lightsail ? 1 : 0
  name  = local.edge_name
}

resource "aws_iam_access_key" "edge" {
  count = local.on_lightsail ? 1 : 0
  user  = aws_iam_user.edge[0].name
}

resource "aws_iam_user_policy" "edge_invoke" {
  count = local.on_lightsail ? 1 : 0
  name  = "${local.edge_name}-invoke-core"
  user  = aws_iam_user.edge[0].name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "lambda:InvokeFunction"
      Resource = aws_lambda_function.this.arn
    }]
  })
}
