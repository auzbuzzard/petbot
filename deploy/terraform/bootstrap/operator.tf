# --- Operator access: read-only triage (plus invoking the core for integration tests) --
# The operator (an agent or a human on call) reads logs, deployments and tables to
# triage incidents, and invokes the core worker to test prompts end to end. It is part
# of the root of trust, like the CI role: an admin grants it here and CI can never edit
# it (DenyAccessRoles). The operator's IAM user holds long-lived keys, created out of
# band and never in Terraform state; the user may only assume petbot-operator, whose
# sessions last at most an hour. Secrets stay out of reach: no ssm:GetParameter, and
# no access to the state bucket (Terraform state holds the injected secrets).

variable "operator_user" {
  type        = string
  description = "IAM user that may assume the read-only operator role. Its access keys are managed out of band."
  default     = "claude"
}

resource "aws_iam_user" "operator" {
  name = var.operator_user

  # The user's tags are the account owner's labels, not part of this policy.
  lifecycle {
    ignore_changes = [tags]
  }
}

data "aws_iam_policy_document" "operator_trust" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "AWS"
      identifiers = [aws_iam_user.operator.arn]
    }
  }
}

resource "aws_iam_role" "operator" {
  name                 = "${var.name_prefix}-operator"
  assume_role_policy   = data.aws_iam_policy_document.operator_trust.json
  max_session_duration = 3600
}

data "aws_iam_policy_document" "operator_permissions" {
  statement {
    sid = "ReadStackLogs"
    actions = [
      "logs:FilterLogEvents",
      "logs:GetLogEvents",
      "logs:DescribeLogStreams",
      "logs:StartQuery",
      "logs:StopQuery",
    ]
    # The trailing wildcard also covers the groups' streams.
    resources = ["arn:aws:logs:${local.arn_region}:log-group:/aws/lambda/${local.stack}"]
  }

  # Listing log groups and fetching Logs Insights results have no resource form.
  statement {
    sid       = "ListLogs"
    actions   = ["logs:DescribeLogGroups", "logs:GetQueryResults"]
    resources = ["*"]
  }

  # Lightsail resources have GUID ARNs, so there is no name to scope to (as for CI).
  statement {
    sid = "ReadEdge"
    actions = [
      "lightsail:GetContainerLog",
      "lightsail:GetContainerServices",
      "lightsail:GetContainerServiceDeployments",
      "lightsail:GetContainerServiceMetricData",
    ]
    resources = ["*"]
  }

  statement {
    sid = "ReadStackFunctions"
    actions = [
      "lambda:GetFunction",
      "lambda:GetFunctionConfiguration",
      "lambda:ListVersionsByFunction",
      "lambda:ListAliases",
    ]
    resources = ["arn:aws:lambda:${local.arn_region}:function:${local.stack}"]
  }

  # Integration tests send a prompt to the deployed core worker, exactly as the edge does.
  statement {
    sid       = "InvokeCore"
    actions   = ["lambda:InvokeFunction"]
    resources = ["arn:aws:lambda:${local.arn_region}:function:${var.name_prefix}-core"]
  }

  statement {
    sid = "ReadStackTables"
    actions = [
      "dynamodb:DescribeTable",
      "dynamodb:DescribeTimeToLive",
      "dynamodb:GetItem",
      "dynamodb:Query",
      "dynamodb:Scan",
    ]
    resources = ["arn:aws:dynamodb:${local.arn_region}:table/${local.stack}"]
  }

  statement {
    sid       = "ReadStackImages"
    actions   = ["ecr:DescribeRepositories", "ecr:DescribeImages"]
    resources = ["arn:aws:ecr:${local.arn_region}:repository/${local.stack}"]
  }

  statement {
    sid = "ReadStackIam"
    actions = [
      "iam:GetRole",
      "iam:GetRolePolicy",
      "iam:ListRolePolicies",
      "iam:ListAttachedRolePolicies",
      "iam:GetUser",
      "iam:GetUserPolicy",
      "iam:ListUserPolicies",
      "iam:ListAttachedUserPolicies",
      "iam:GetPolicy",
      "iam:GetPolicyVersion",
      "iam:SimulatePrincipalPolicy",
    ]
    resources = [
      "arn:aws:iam::${local.account_id}:role/${local.stack}",
      "arn:aws:iam::${local.account_id}:user/${local.stack}",
      "arn:aws:iam::${local.account_id}:policy/${local.stack}",
    ]
  }

  # Account-level reads with no resource form: metrics, traces, the API audit trail,
  # policy simulation of a draft document, and the budget.
  statement {
    sid = "ReadAccountTelemetry"
    actions = [
      "cloudwatch:GetMetricData",
      "cloudwatch:ListMetrics",
      "xray:GetTraceSummaries",
      "xray:BatchGetTraces",
      "cloudtrail:LookupEvents",
      "iam:SimulateCustomPolicy",
      "budgets:ViewBudget",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "operator" {
  name   = "operator"
  role   = aws_iam_role.operator.id
  policy = data.aws_iam_policy_document.operator_permissions.json
}

# The operator user's only permission: assume the role above. It must hold nothing else
# (no group, no attached policy): a broad grant such as ReadOnlyAccess would also read the
# state bucket, and with it every secret Terraform injected.
resource "aws_iam_user_policy" "operator_assume" {
  name = "assume-${aws_iam_role.operator.name}"
  user = aws_iam_user.operator.name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "sts:AssumeRole"
      Resource = aws_iam_role.operator.arn
    }]
  })
}

output "operator_role_arn" {
  description = "Role the operator assumes; see README \"Operator access\"."
  value       = aws_iam_role.operator.arn
}
