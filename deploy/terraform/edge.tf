# --- The always-on edge: a Lightsail container service ------------------------
#
# The edge holds the Discord gateway (an outbound WebSocket) and dispatches each
# @mention to the core worker Lambda. Lightsail container service is the host:
# flat-rate, public IPv4 + data bundled, immutable container push (no box to
# patch). It serves no HTTP — it only dials out to Discord and to the worker — so
# the deployment configures NO public endpoint. Lightsail supports this: the
# container still runs, reachable only on the private `<name>.service.local`
# domain (which the edge never needs), and no health-check port is required.
#
# Image must be linux/amd64 (Lightsail container services are amd64-only; an
# arm64 image fails with "exec format error") — see Dockerfile.edge. Measured edge
# footprint ~76 MB RSS (discord.py + httpx + boto3), so `nano` (512 MB) is ample;
# bump var.edge_power to `micro` if it ever OOMs.

resource "aws_lightsail_container_service" "edge" {
  name  = local.edge_name
  power = var.edge_power
  scale = var.edge_scale
}

# The container deployment. Skipped until an image has been pushed (var.edge_image
# empty), so the service can be created first, then the image pushed, then this
# set — mirroring the ECR-first two-step for the worker.
resource "aws_lightsail_container_service_deployment_version" "edge" {
  count        = var.edge_image != "" ? 1 : 0
  service_name = aws_lightsail_container_service.edge.name

  container {
    container_name = "edge"
    image          = var.edge_image

    environment = {
      LOG_LEVEL             = var.log_level
      ENV                   = var.lambda_environment
      WORKER__KIND          = "lambda"
      WORKER__FUNCTION_NAME = aws_lambda_function.this.function_name
      AWS_REGION            = var.aws_region
      # Scoped identity for boto3's default credential chain (Lightsail container
      # services have no IAM instance roles, so a static key is the mechanism).
      AWS_ACCESS_KEY_ID     = aws_iam_access_key.edge.id
      AWS_SECRET_ACCESS_KEY = aws_iam_access_key.edge.secret
      DISCORD_TOKEN         = data.aws_ssm_parameter.discord_token.value
    }
  }
}

data "aws_ssm_parameter" "discord_token" {
  name            = var.discord_token_ssm_parameter
  with_decryption = true
}

# --- The edge's scoped AWS identity -------------------------------------------
# Least privilege: invoke exactly the core worker Lambda, nothing else.

resource "aws_iam_user" "edge" {
  name = local.edge_name
}

resource "aws_iam_access_key" "edge" {
  user = aws_iam_user.edge.name
}

resource "aws_iam_user_policy" "edge_invoke" {
  name = "${local.edge_name}-invoke-core"
  user = aws_iam_user.edge.name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "lambda:InvokeFunction"
      Resource = aws_lambda_function.this.arn
    }]
  })
}
