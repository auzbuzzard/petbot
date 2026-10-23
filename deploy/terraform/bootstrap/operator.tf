# --- Operator access: read-only triage (plus invoking the core for integration tests) --
# The operator (an agent or a human on call) reads logs, deployments and tables to
# triage incidents, and invokes each environment's core worker to test prompts end to end
# (the chat harness's --lambda). It is part
# of the root of trust, like the CI roles: bootstrap grants it, and the deploy role can never
# edit it (DenyAccessPrincipals). The operator's IAM user holds long-lived keys, created out
# of band and never in Terraform state; the user may only assume petbot-operator, whose
# sessions last at most an hour. Secrets stay out of reach: no ssm:GetParameter, and
# no access to the state bucket (Terraform state holds the edge's AWS access key).

variable "operator_user" {
  type        = string
  description = "IAM user that may assume the read-only operator role. Its access keys are managed out of band."
  default     = "claude"

  # The deploy role manages users named <name_prefix>-*; the operator must stay outside it.
  validation {
    condition     = !startswith(var.operator_user, "${var.name_prefix}-")
    error_message = "operator_user must not start with \"<name_prefix>-\": the deploy role manages those users."
  }
}

resource "aws_iam_user" "operator" {
  name                 = var.operator_user
  permissions_boundary = aws_iam_policy.operator_user_boundary.arn

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

locals {
  operator_role_name = "${var.name_prefix}-operator"
}

resource "aws_iam_role" "operator" {
  name                 = local.operator_role_name
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
    # The stack's Lambda log groups (the trailing wildcard also covers their streams), and
    # aws/spans, where X-Ray Transaction Search writes traces (observability.tf).
    resources = concat(
      [for stack in local.stacks : "arn:aws:logs:${local.arn_region}:log-group:/aws/lambda/${stack}"],
      [
        "arn:aws:logs:${local.arn_region}:log-group:aws/spans",
        "arn:aws:logs:${local.arn_region}:log-group:aws/spans:*",
      ],
    )
  }

  # Listing resources and fetching Logs Insights results have no resource form; listing
  # shows names and configuration, not data.
  statement {
    sid = "ListResources"
    actions = [
      "logs:DescribeLogGroups",
      "logs:GetQueryResults",
      "lambda:ListFunctions",
      "dynamodb:ListTables",
      "ecr:DescribeRepositories",
    ]
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
    resources = [for stack in local.stacks : "arn:aws:lambda:${local.arn_region}:function:${stack}"]
  }

  # Integration tests send a prompt to a deployed core worker, exactly as the edge does.
  statement {
    sid     = "InvokeCore"
    actions = ["lambda:InvokeFunction"]
    resources = [
      for env in values(var.environments) : "arn:aws:lambda:${local.arn_region}:function:${env.name_prefix}-core"
    ]
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
    resources = [for stack in local.stacks : "arn:aws:dynamodb:${local.arn_region}:table/${stack}"]
  }

  statement {
    sid       = "ReadStackImages"
    actions   = ["ecr:DescribeRepositories", "ecr:DescribeImages"]
    resources = [for stack in local.stacks : "arn:aws:ecr:${local.arn_region}:repository/${stack}"]
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
    resources = flatten([
      for stack in local.stacks : [
        "arn:aws:iam::${local.account_id}:role/${stack}",
        "arn:aws:iam::${local.account_id}:user/${stack}",
        "arn:aws:iam::${local.account_id}:policy/${stack}",
      ]
    ])
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
      "xray:GetServiceGraph",
      "xray:GetTraceGraph",
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

# The operator user's only permission: assume the role above. Nothing else may reach it:
# a broad grant such as ReadOnlyAccess would also read the state bucket, and with it the
# edge's AWS access key. Three layers keep it that way:
#   - its permissions boundary allows only this sts:AssumeRole, so a group, attached or
#     inline policy added by hand grants nothing;
#   - its inline policies are exactly operator_assume, and it has no attached policies:
#     every plan shows any other as drift, and the next apply removes it;
#   - the deploy role is denied all IAM on it (DenyAccessPrincipals).
# By name, not by reference: the role's trust names the user, which carries this boundary.
data "aws_iam_policy_document" "operator_user" {
  statement {
    actions   = ["sts:AssumeRole"]
    resources = ["arn:aws:iam::${local.account_id}:role/${local.operator_role_name}"]
  }
}

resource "aws_iam_policy" "operator_user_boundary" {
  name        = "${var.name_prefix}-operator-user-boundary"
  description = "Permissions boundary for the operator user: assuming ${local.operator_role_name}, nothing else."
  policy      = data.aws_iam_policy_document.operator_user.json
}

resource "aws_iam_user_policies_exclusive" "operator" {
  user_name    = aws_iam_user.operator.name
  policy_names = [aws_iam_user_policy.operator_assume.name]
}

resource "aws_iam_user_policy_attachments_exclusive" "operator" {
  user_name   = aws_iam_user.operator.name
  policy_arns = []
}

resource "aws_iam_user_policy" "operator_assume" {
  name = "assume-${aws_iam_role.operator.name}"
  user = aws_iam_user.operator.name

  policy = data.aws_iam_policy_document.operator_user.json
}

output "operator_role_arn" {
  description = "Role the operator assumes; see README \"Operator access\"."
  value       = aws_iam_role.operator.arn
}
