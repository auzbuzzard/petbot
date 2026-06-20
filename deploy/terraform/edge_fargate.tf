# --- Fargate host (var.edge_host == "fargate") --------------------------------
#
# An ECS Fargate service runs the edge container. No Lightsail quota; the task
# carries an IAM *task role* (so the edge invokes the worker Lambda without any
# static key — cleaner than the Lightsail path). Outbound-only: a public IP for
# IPv4 egress to Discord + AWS, an egress-all security group, no inbound. The
# Discord token is fetched by ECS from SSM at task launch (never in TF state).

locals {
  on_fargate = var.edge_host == "fargate"
}

# Run in the account's default VPC so no networking has to be built.
data "aws_vpc" "default" {
  count   = local.on_fargate ? 1 : 0
  default = true
}

data "aws_subnets" "default" {
  count = local.on_fargate ? 1 : 0
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default[0].id]
  }
}

resource "aws_security_group" "edge" {
  count       = local.on_fargate ? 1 : 0
  name        = "${local.edge_name}-egress"
  description = "Edge task: outbound only (Discord gateway + AWS APIs)."
  vpc_id      = data.aws_vpc.default[0].id

  egress {
    from_port        = 0
    to_port          = 0
    protocol         = "-1"
    cidr_blocks      = ["0.0.0.0/0"]
    ipv6_cidr_blocks = ["::/0"]
  }
}

resource "aws_cloudwatch_log_group" "edge" {
  count             = local.on_fargate ? 1 : 0
  name              = "/ecs/${local.edge_name}"
  retention_in_days = var.log_retention_days
}

# --- Task roles ---------------------------------------------------------------

data "aws_iam_policy_document" "ecs_assume" {
  count = local.on_fargate ? 1 : 0
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

# Execution role: ECS itself uses it to pull the image + write logs + read the
# token secret. (Distinct from the task role the app runs as.)
resource "aws_iam_role" "edge_exec" {
  count              = local.on_fargate ? 1 : 0
  name               = "${local.edge_name}-exec"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume[0].json
}

resource "aws_iam_role_policy_attachment" "edge_exec" {
  count      = local.on_fargate ? 1 : 0
  role       = aws_iam_role.edge_exec[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role_policy" "edge_exec_secrets" {
  count = local.on_fargate ? 1 : 0
  name  = "read-discord-token"
  role  = aws_iam_role.edge_exec[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["ssm:GetParameters"]
      Resource = [local.discord_token_arn]
    }]
  })
}

# Task role: the edge's runtime identity — invoke exactly the worker Lambda.
resource "aws_iam_role" "edge_task" {
  count              = local.on_fargate ? 1 : 0
  name               = "${local.edge_name}-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume[0].json
}

resource "aws_iam_role_policy" "edge_task_invoke" {
  count = local.on_fargate ? 1 : 0
  name  = "invoke-core"
  role  = aws_iam_role.edge_task[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "lambda:InvokeFunction"
      Resource = aws_lambda_function.this.arn
    }]
  })
}

# --- Cluster, task, service ---------------------------------------------------

resource "aws_ecs_cluster" "edge" {
  count = local.on_fargate ? 1 : 0
  name  = local.edge_name
}

# Task + service need the image; created once CI has pushed it (edge_image_tag).
resource "aws_ecs_task_definition" "edge" {
  count                    = local.on_fargate && var.edge_image_tag != "" ? 1 : 0
  family                   = local.edge_name
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.edge_cpu
  memory                   = var.edge_memory
  execution_role_arn       = aws_iam_role.edge_exec[0].arn
  task_role_arn            = aws_iam_role.edge_task[0].arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64" # the edge image is amd64 (see Dockerfile.edge)
  }

  container_definitions = jsonencode([{
    name      = "edge"
    image     = "${aws_ecr_repository.edge.repository_url}:${var.edge_image_tag}"
    essential = true
    environment = [
      { name = "LOG_LEVEL", value = var.log_level },
      { name = "ENV", value = var.lambda_environment },
      { name = "WORKER__KIND", value = "lambda" },
      { name = "WORKER__FUNCTION_NAME", value = aws_lambda_function.this.function_name },
      { name = "AWS_REGION", value = var.aws_region },
    ]
    secrets = [
      { name = "DISCORD_TOKEN", valueFrom = local.discord_token_arn },
    ]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.edge[0].name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "edge"
      }
    }
  }])
}

resource "aws_ecs_service" "edge" {
  count           = local.on_fargate && var.edge_image_tag != "" ? 1 : 0
  name            = local.edge_name
  cluster         = aws_ecs_cluster.edge[0].id
  task_definition = aws_ecs_task_definition.edge[0].arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = data.aws_subnets.default[0].ids
    security_groups  = [aws_security_group.edge[0].id]
    assign_public_ip = true # gives the task a routable IPv4 for the Discord gateway
  }
}
