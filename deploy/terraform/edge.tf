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
# Image delivery is ECR-pull: the edge image lives in its own ECR repo (the same
# registry the worker uses), and the service pulls it via an "image puller" IAM
# role (the declarative equivalent of what the Lightsail console wires up). The
# image must be linux/amd64 (Lightsail container services are amd64-only; an
# arm64 image fails with "exec format error") — see Dockerfile.edge. Measured edge
# footprint ~76 MB RSS, so `nano` (512 MB) is ample; bump var.edge_power to
# `micro` if it ever OOMs.

resource "aws_lightsail_container_service" "edge" {
  name  = local.edge_name
  power = var.edge_power
  scale = var.edge_scale

  # Activating this creates an AWS-managed ECR "image puller" principal for the
  # service; we grant it read on the edge repo below. (Same-Region requirement:
  # the repo and the service are both in var.aws_region.)
  private_registry_access {
    ecr_image_puller_role {
      is_active = true
    }
  }
}

# The edge's own ECR repository.
resource "aws_ecr_repository" "edge" {
  name                 = local.edge_name
  image_tag_mutability = "MUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }
}

# Grant the service's puller principal read access on the edge repo — exactly the
# statement the Lightsail console would add for you, here as code. The principal
# ARN is populated once the puller role is active; Terraform orders this after the
# service create because it references that attribute.
resource "aws_ecr_repository_policy" "edge" {
  repository = aws_ecr_repository.edge.name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "AllowLightsailPull"
      Effect    = "Allow"
      Principal = { AWS = aws_lightsail_container_service.edge.private_registry_access[0].ecr_image_puller_role[0].principal_arn }
      Action    = ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"]
    }]
  })
}

# The container deployment. Skipped until an image tag is supplied (CI pushes the
# image to ECR, then passes its tag), so the service + puller can be created
# first. Lightsail pulls from ECR using the puller role, so the repo policy must
# exist before the deployment is created.
resource "aws_lightsail_container_service_deployment_version" "edge" {
  count        = var.edge_image_tag != "" ? 1 : 0
  service_name = aws_lightsail_container_service.edge.name

  container {
    container_name = "edge"
    image          = "${aws_ecr_repository.edge.repository_url}:${var.edge_image_tag}"

    environment = {
      LOG_LEVEL              = var.log_level
      ENV                    = var.lambda_environment
      SERVICE__KIND          = "lambda"
      SERVICE__FUNCTION_NAME = aws_lambda_function.this.function_name
      AWS_REGION             = var.aws_region
      # Reply-chain fetch depth for conversation-history reconstruction (a Discord-API
      # cost bound, not a model-context bound).
      HISTORY_MAX_TURNS = tostring(var.history_max_turns)
      # Scoped identity for boto3's default credential chain (Lightsail container
      # services have no IAM instance roles, so a static key is the mechanism).
      AWS_ACCESS_KEY_ID     = aws_iam_access_key.edge.id
      AWS_SECRET_ACCESS_KEY = aws_iam_access_key.edge.secret
      DISCORD_TOKEN         = data.aws_ssm_parameter.discord_token.value
    }
  }

  depends_on = [aws_ecr_repository_policy.edge]
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
