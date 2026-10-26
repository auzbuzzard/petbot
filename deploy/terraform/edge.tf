# --- The always-on edge: a Lightsail container service ------------------------
#
# The edge holds the Discord gateway (an outbound WebSocket) and dispatches each
# @mention to the core worker Lambda. It serves no HTTP — it only dials out to Discord
# and to the worker — so the deployment configures NO public endpoint. Lightsail
# supports this: the container still runs, reachable only on the private
# `<name>.service.local` domain (which the edge never needs), and no health-check port
# is required.

resource "aws_lightsail_container_service" "edge" {
  count = local.edge_count

  name  = local.edge_name
  power = var.edge_power
  scale = var.edge_scale

  # A disabled service shuts its containers down, so the edge leaves the Discord gateway.
  is_disabled = var.edge_paused

  # A container service's ARN carries an id, not its name, so IAM can tell stacks' services
  # apart only by tag:
  # https://docs.aws.amazon.com/service-authorization/latest/reference/list_amazonlightsail.html
  tags = {
    Stack = var.name_prefix
  }

  # Activating this creates an AWS-managed ECR "image puller" principal for the
  # service; we grant it read on the edge repo below. (Same-Region requirement:
  # the repo and the service are both in var.aws_region.)
  private_registry_access {
    ecr_image_puller_role {
      is_active = true
    }
  }
}

resource "aws_ecr_repository" "edge" {
  count = local.edge_count

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
  count = local.edge_count

  repository = aws_ecr_repository.edge[0].name

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

# The container deployment. Skipped until an image tag is supplied (CI pushes the
# image to ECR, then passes its tag), so the service + puller can be created
# first. Lightsail pulls from ECR using the puller role, so the repo policy must
# exist before the deployment is created.
resource "aws_lightsail_container_service_deployment_version" "edge" {
  count        = var.edge_enabled && var.edge_image_tag != "" ? 1 : 0
  service_name = aws_lightsail_container_service.edge[0].name

  container {
    container_name = "edge"
    image          = "${aws_ecr_repository.edge[0].repository_url}:${var.edge_image_tag}"

    environment = merge({
      LOG_LEVEL              = var.log_level
      ENV                    = var.lambda_environment
      SERVICE__KIND          = "lambda"
      SERVICE__FUNCTION_NAME = aws_lambda_function.this.function_name
      AWS_REGION             = var.aws_region
      HISTORY_MAX_TURNS      = tostring(var.history_max_turns)
      AWS_ACCESS_KEY_ID      = aws_iam_access_key.edge[0].id
      AWS_SECRET_ACCESS_KEY  = aws_iam_access_key.edge[0].secret
      SSM_SECRETS            = jsonencode(local.edge_secret_parameters)
      CLAIMS_TABLE           = aws_dynamodb_table.claims[0].name
      KEYLESS_PROBE = jsonencode({
        service = aws_lightsail_container_service.edge[0].principal_arn
        puller  = aws_lightsail_container_service.edge[0].private_registry_access[0].ecr_image_puller_role[0].principal_arn
      })
    }, local.observability_edge_env)
  }

  depends_on = [aws_ecr_repository_policy.edge, aws_iam_user_policy.edge_secrets, aws_ssm_parameter.owned]
}

resource "aws_iam_user" "edge" {
  count = local.edge_count

  name                 = local.edge_name
  permissions_boundary = local.workload_boundary_arn
}

# The new key exists before the new container deployment carries it, and the old key is
# deleted only after.
resource "time_rotating" "edge_key" {
  count = local.edge_count

  rotation_days = var.edge_key_rotation_days
}

resource "aws_iam_access_key" "edge" {
  count = local.edge_count

  user = aws_iam_user.edge[0].name

  lifecycle {
    create_before_destroy = true
    replace_triggered_by  = [time_rotating.edge_key[count.index]]
  }
}

resource "aws_iam_user_policy" "edge_invoke" {
  count = local.edge_count

  name = "${local.edge_name}-invoke-core"
  user = aws_iam_user.edge[0].name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["lambda:InvokeFunction", "lambda:GetFunctionConfiguration"]
        Resource = aws_lambda_function.this.arn
      },
      {
        Effect   = "Allow"
        Action   = ["dynamodb:PutItem", "dynamodb:UpdateItem"]
        Resource = aws_dynamodb_table.claims[0].arn
      },
    ]
  })
}
