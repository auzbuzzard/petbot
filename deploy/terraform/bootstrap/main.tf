# The root of trust: the remote-state bucket, the GitHub OIDC provider, the CI roles
# (deploy, and bootstrap's own plan/apply pipeline in pipeline.tf), the workload
# permissions boundary and the operator's access (operator.tf).
#
# Every OIDC role trusts exactly one GitHub environment, never a branch or a PR. Each
# deploy environment (var.environments) gets its own deploy role and workload boundary,
# scoped to its own <name_prefix>-* resources and state, and no environment's prefix
# contains another's: the deploy workflow assumes petbot-github-deploy-prod from
# `production` (main only) and petbot-github-deploy-dev from `dev` (any branch; see
# docs/adr/0014). The bootstrap workflow plans this stack from
# `bootstrap-plan` and applies the reviewed plan from `bootstrap`, which needs a required
# reviewer's approval; both admit only main. An admin applies this stack by hand exactly
# once, to seed it in a new account. See README "Bootstrap" and docs/adr/0012.
#
# Its own state lives in the bucket it manages (key bootstrap/terraform.tfstate),
# locked natively by S3 (`use_lockfile`, Terraform >= 1.11).

terraform {
  required_version = ">= 1.11"

  # Partial configuration: bucket/key/region come from backend.hcl.
  backend "s3" {}

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "state_bucket" {
  type        = string
  description = "Globally-unique S3 bucket name for Terraform state."
}

variable "github_repo" {
  type        = string
  description = "owner/name of the repo allowed to assume the deploy role via OIDC."
  default     = "auzbuzzard/petbot"
}

variable "name_prefix" {
  type        = string
  description = "Prefix of the root of trust: the CI roles (<name_prefix>-github-*) and the operator's role and policies."
  default     = "petbot"
}

variable "environments" {
  type = map(object({
    # The root stack's var.name_prefix there; its deploy role manages <name_prefix>-*
    # resources and the state under <name_prefix>/.
    name_prefix = string
    # GitHub environment whose jobs may assume its deploy role (deploy.yml's `environment:`).
    github_environment = string
    # Whether its stack runs the Discord edge (the root stack's var.edge_enabled): the
    # edge's IAM user and Lightsail service are only in scope where it does.
    edge = optional(bool, true)
    # Whether its deploy role manages AWS Budgets (the root stack's monthly_budget_usd).
    budget = optional(bool, true)
    # Whether its workloads may call Bedrock's mantle endpoint with their own IAM identity
    # (the root stack's chat_llm_kind = "bedrock_mantle").
    bedrock_mantle = optional(bool, false)
    # Parameters outside its prefix that its stack copies into its own (the root stack's
    # var.ssm_parameters): its deploy role may read exactly these.
    adopt_parameters = optional(list(string), [])
    # The stack from before environments, under the bare prefix: its role keeps the name
    # petbot-github-deploy, and its prefix may contain the others'. It exists only until
    # that stack is destroyed (docs/adr/0014, "Migrating production").
    legacy = optional(bool, false)
  }))
  description = "Each deploy environment, by name: prod deploys from main; dev deploys any branch's core, with no edge; legacy is the pre-migration production stack."
  default = {
    prod = {
      name_prefix        = "petbot-prod"
      github_environment = "production"
      bedrock_mantle     = true
      adopt_parameters   = ["/petbot/edge/discord_token", "/petbot/core/tavily_api_key"]
    }
    dev = {
      name_prefix        = "petbot-dev"
      github_environment = "dev"
      edge               = false
      budget             = false
      bedrock_mantle     = true
    }
    legacy = {
      name_prefix        = "petbot"
      github_environment = "production"
      legacy             = true
    }
  }

  validation {
    condition = alltrue(flatten([
      for a_name, a in var.environments : [
        for b_name, b in var.environments :
        a_name == b_name || a.legacy || b.legacy || !startswith("${a.name_prefix}-", "${b.name_prefix}-")
      ]
    ]))
    error_message = "No environment's name_prefix may contain another's (petbot-prod and petbot-dev, not petbot and petbot-dev): each deploy role and boundary covers its own stage only."
  }

  validation {
    condition = alltrue([
      for e in values(var.environments) : !startswith("${e.name_prefix}-", "${var.name_prefix}-github-")
    ]) && length([for e in values(var.environments) : e if e.legacy]) <= 1
    error_message = "An environment's name_prefix must stay outside <name_prefix>-github-* (the CI roles), and at most one environment is legacy."
  }
}

resource "aws_s3_bucket" "state" {
  bucket = var.state_bucket

  # Every stack's state lives here; losing it orphans all of them.
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_versioning" "state" {
  bucket = aws_s3_bucket.state.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "state" {
  bucket = aws_s3_bucket.state.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "state" {
  bucket = aws_s3_bucket.state.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# TLS only: refuse any request to the state over plain HTTP.
data "aws_iam_policy_document" "state_bucket" {
  statement {
    sid       = "DenyInsecureTransport"
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = [aws_s3_bucket.state.arn, "${aws_s3_bucket.state.arn}/*"]

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "state" {
  bucket = aws_s3_bucket.state.id
  policy = data.aws_iam_policy_document.state_bucket.json

  # S3 rejects a bucket policy while the public-access block is still being applied.
  depends_on = [aws_s3_bucket_public_access_block.state]
}

output "state_bucket" {
  value = aws_s3_bucket.state.id
}

# --- GitHub Actions OIDC: the one irreducible bit of trust --------------------
# CI cannot bootstrap its own trust: AWS must already trust GitHub before any
# workflow can assume a role, so an admin seeds this stack once (see the header).

data "aws_caller_identity" "current" {}

resource "aws_iam_openid_connect_provider" "github" {
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
  # AWS validates GitHub's OIDC cert against its trust store now, but the
  # argument is still required; this is GitHub's documented thumbprint.
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]
}

# The GitHub environment each CI role is assumed from. Each role trusts exactly its
# environment's `sub`: the claim names the environment whenever a job references one, so a
# job in no environment, a pull request, or any other workflow (including the AI review
# bots, which hold id-token: write) cannot assume it. The branch rules of `production` and
# the bootstrap environments admit only main.
locals {
  github_role_environments = merge(
    { for name, env in var.environments : "deploy-${name}" => env.github_environment },
    {
      "bootstrap-plan"  = var.bootstrap_plan_environment
      "bootstrap-apply" = var.bootstrap_apply_environment
    },
  )

  # Each environment's deploy role is suffixed with its name; the legacy one keeps the
  # name it was created with. All of them fall under <name_prefix>-github-*, which no
  # deploy role may edit (DenyAccessPrincipals) and bootstrap's pipeline manages.
  deploy_role_names = {
    for name, env in var.environments :
    name => env.legacy ? "${var.name_prefix}-github-deploy" : "${var.name_prefix}-github-deploy-${name}"
  }

  # The resource names each environment's deploy role and workload boundary cover. The
  # legacy prefix (petbot) contains every other environment's, so the legacy environment
  # covers only its own two deployables' names and never a petbot-prod-* or petbot-dev-*
  # resource.
  env_name_patterns = {
    for name, env in var.environments :
    name => env.legacy ? ["${env.name_prefix}-core*", "${env.name_prefix}-edge*"] : ["${env.name_prefix}-*"]
  }

  # The workflow that may assume each deploy role: a job in its GitHub environment that
  # runs any other workflow file is refused.
  deploy_role_workflows = {
    for name, env in var.environments :
    "deploy-${name}" => env.legacy ? "legacy.yml" : "deploy.yml"
  }
}

data "aws_iam_policy_document" "github_trust" {
  for_each = local.github_role_environments

  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_repo}:environment:${each.value}"]
    }

    # A deploy role is assumed only by its workflow file, so a job elsewhere (another
    # workflow on any branch) that names the same environment is refused. IfExists: GitHub
    # documents job_workflow_ref for jobs in reusable workflows; where a token carries it,
    # it must name this workflow.
    dynamic "condition" {
      for_each = contains(keys(local.deploy_role_workflows), each.key) ? [local.deploy_role_workflows[each.key]] : []
      content {
        test     = "StringLikeIfExists"
        variable = "token.actions.githubusercontent.com:job_workflow_ref"
        values   = ["${var.github_repo}/.github/workflows/${condition.value}@*"]
      }
    }
  }
}

resource "aws_iam_role" "github_deploy" {
  for_each = var.environments

  name               = local.deploy_role_names[each.key]
  assume_role_policy = data.aws_iam_policy_document.github_trust["deploy-${each.key}"].json
}

locals {
  account_id = data.aws_caller_identity.current.account_id
  # ARN prefixes for "any resource of this stack": everything a root stack creates is
  # named <its name_prefix>-*, so new resources fall inside its deploy role's scope as long
  # as they follow the convention.
  arn_region = "${var.aws_region}:${local.account_id}"
  stack      = "${var.name_prefix}-*"
  # Every environment's resources, for the operator: <name_prefix>-*, plus the pattern of
  # any environment whose prefix falls outside it.
  stacks = concat([local.stack], [
    for env in values(var.environments) : "${env.name_prefix}-*"
    if !startswith("${env.name_prefix}-", "${var.name_prefix}-")
  ])
}

# --- The workload boundary ----------------------------------------------------
# One per environment: the ceiling for every role and user its stack creates. Its deploy
# role may create and edit IAM principals only with this boundary attached (see
# ManageStackRoles and ManageStackUsers), and only bootstrap can change it, so whatever
# policy CI writes, a workload can never do more than this: no IAM, and data-plane access
# to its own stack's resources only. A workload needing more is a bootstrap change.
data "aws_iam_policy_document" "workload_boundary" {
  for_each = var.environments

  statement {
    sid       = "WriteLogs"
    actions   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["*"]
  }

  # PutMetricData and the X-Ray writes have no resource-level scoping.
  statement {
    sid       = "PublishTelemetry"
    actions   = ["xray:PutTraceSegments", "xray:PutTelemetryRecords", "cloudwatch:PutMetricData"]
    resources = ["*"]
  }

  statement {
    sid       = "InvokeModels"
    actions   = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
    resources = ["*"]
  }

  # Bedrock's OpenAI-compatible endpoint, signed with the workload's own identity (SigV4).
  dynamic "statement" {
    for_each = each.value.bedrock_mantle ? [1] : []
    content {
      sid       = "InvokeMantleModels"
      actions   = ["bedrock-mantle:CreateInference"]
      resources = ["arn:aws:bedrock-mantle:${local.arn_region}:project/*"]
    }
  }

  statement {
    sid       = "InvokeStackFunctions"
    actions   = ["lambda:InvokeFunction", "lambda:GetFunctionConfiguration"]
    resources = [for p in local.env_name_patterns[each.key] : "arn:aws:lambda:${local.arn_region}:function:${p}"]
  }

  statement {
    sid = "UseStackTables"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
      "dynamodb:DeleteItem",
      "dynamodb:Query",
    ]
    resources = [for p in local.env_name_patterns[each.key] : "arn:aws:dynamodb:${local.arn_region}:table/${p}"]
  }

  statement {
    sid       = "ReadStackSecrets"
    actions   = ["ssm:GetParameter", "ssm:GetParameters"]
    resources = ["arn:aws:ssm:${local.arn_region}:parameter/${each.value.name_prefix}/*"]
  }

  statement {
    sid       = "DecryptSecretsViaSSM"
    actions   = ["kms:Decrypt"]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values   = ["ssm.${var.aws_region}.amazonaws.com"]
    }
  }
}

resource "aws_iam_policy" "workload_boundary" {
  for_each = var.environments

  name        = "${each.value.name_prefix}-workload-boundary"
  description = "Permissions boundary for every IAM role and user the ${each.value.name_prefix} stack creates."
  policy      = data.aws_iam_policy_document.workload_boundary[each.key].json
}

output "workload_boundary_arns" {
  description = "Each environment's workload boundary (the root stack derives it from name_prefix)."
  value       = { for name, policy in aws_iam_policy.workload_boundary : name => policy.arn }
}

# Each deploy role's permissions. Service-level action wildcards (e.g. ecr:*) are kept
# where enumerating every Terraform-issued call is brittle; each statement is scoped to
# resources named after its environment's <name_prefix>-*, so a stolen CI token reaches that
# stack and nothing else in the account. IAM writes require the environment's workload
# boundary, and the CI roles are carved out (DenyAccessPrincipals), so a deploy role can
# never widen its own permissions.
data "aws_iam_policy_document" "deploy_permissions" {
  for_each = var.environments

  # The root stack's state only (deploy.yml: key=<name_prefix>/terraform.tfstate);
  # bootstrap's own state, in the same bucket, stays out of CI's reach.
  statement {
    sid       = "ListState"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.state.arn]
  }

  statement {
    sid       = "TerraformState"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = ["${aws_s3_bucket.state.arn}/${each.value.name_prefix}/*"]
  }

  statement {
    sid       = "ReadRuntimeSecrets"
    actions   = ["ssm:GetParameter", "ssm:GetParameters"]
    resources = ["arn:aws:ssm:${local.arn_region}:parameter/${each.value.name_prefix}/*"]
  }

  # The stack's own parameters, under /<name_prefix>/ (the root stack's ssm_parameters,
  # and a retired stack's removal of its parameters). Listing has no resource form.
  statement {
    sid = "ManageStackParameters"
    actions = [
      "ssm:PutParameter",
      "ssm:DeleteParameter",
      "ssm:DeleteParameters",
      "ssm:AddTagsToResource",
      "ssm:RemoveTagsFromResource",
      "ssm:ListTagsForResource",
    ]
    resources = ["arn:aws:ssm:${local.arn_region}:parameter/${each.value.name_prefix}/*"]
  }

  statement {
    sid       = "DescribeParameters"
    actions   = ["ssm:DescribeParameters"]
    resources = ["*"]
  }

  dynamic "statement" {
    for_each = length(each.value.adopt_parameters) > 0 ? [1] : []
    content {
      sid     = "ReadAdoptedParameters"
      actions = ["ssm:GetParameter", "ssm:GetParameters"]
      resources = [
        for name in each.value.adopt_parameters : "arn:aws:ssm:${local.arn_region}:parameter/${trimprefix(name, "/")}"
      ]
    }
  }

  # SecureString parameters are KMS-encrypted; reading and writing them needs kms:Decrypt
  # and kms:Encrypt. Scoped via kms:ViaService so the role can only use KMS through
  # SSM — never to decrypt arbitrary data directly.
  statement {
    sid       = "DecryptSecretsViaSSM"
    actions   = ["kms:Decrypt", "kms:Encrypt", "kms:GenerateDataKey"]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values   = ["ssm.${var.aws_region}.amazonaws.com"]
    }
  }

  # ECR login is an account-level call with no resource to scope to.
  statement {
    sid       = "EcrAuth"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  statement {
    sid       = "ManageEcrRepos"
    actions   = ["ecr:*"]
    resources = [for p in local.env_name_patterns[each.key] : "arn:aws:ecr:${local.arn_region}:repository/${p}"]
  }

  statement {
    sid     = "ManageLambda"
    actions = ["lambda:*"]
    # The trailing wildcard also covers qualified ARNs (versions, aliases).
    resources = [for p in local.env_name_patterns[each.key] : "arn:aws:lambda:${local.arn_region}:function:${p}"]
  }

  statement {
    sid     = "ManageLogs"
    actions = ["logs:*"]
    # The trailing wildcard also covers the groups' streams (":log-stream:...").
    resources = [for p in local.env_name_patterns[each.key] : "arn:aws:logs:${local.arn_region}:log-group:/aws/lambda/${p}"]
  }

  # logs:DescribeLogGroups is a list operation that AWS only authorizes on "*"
  # (it has no per-log-group resource form). Terraform calls it to check whether
  # the log group already exists, so it must be granted account-wide — it's a
  # read-only listing, so the blast radius is just visibility of log-group names.
  statement {
    sid       = "DescribeLogGroups"
    actions   = ["logs:DescribeLogGroups"]
    resources = ["*"]
  }

  statement {
    sid       = "ManageDynamoTables"
    actions   = ["dynamodb:*"]
    resources = [for p in local.env_name_patterns[each.key] : "arn:aws:dynamodb:${local.arn_region}:table/${p}"]
  }

  # Budgets are account-wide (any budget/* is in scope), so only an environment that sets
  # one may manage them.
  dynamic "statement" {
    for_each = each.value.budget ? [1] : []
    content {
      sid       = "ManageBudget"
      actions   = ["budgets:*"]
      resources = ["arn:aws:budgets::${local.account_id}:budget/*"]
    }
  }

  # The stack's IAM roles (the Lambda execution role). Creating one, or changing what it
  # may do, requires the workload boundary on it.
  statement {
    sid = "ManageStackRoles"
    actions = [
      "iam:CreateRole",
      "iam:PutRolePermissionsBoundary",
      "iam:AttachRolePolicy",
      "iam:DetachRolePolicy",
      "iam:PutRolePolicy",
      "iam:DeleteRolePolicy",
    ]
    resources = [for p in local.env_name_patterns[each.key] : "arn:aws:iam::${local.account_id}:role/${p}"]
    condition {
      test     = "StringEquals"
      variable = "iam:PermissionsBoundary"
      values   = [aws_iam_policy.workload_boundary[each.key].arn]
    }
  }

  statement {
    sid = "MaintainStackRoles"
    actions = [
      "iam:GetRole",
      "iam:DeleteRole",
      "iam:GetRolePolicy",
      "iam:ListRolePolicies",
      "iam:ListAttachedRolePolicies",
      "iam:ListInstanceProfilesForRole",
      "iam:TagRole",
      "iam:UntagRole",
    ]
    resources = [for p in local.env_name_patterns[each.key] : "arn:aws:iam::${local.account_id}:role/${p}"]
  }

  # PassRole is the classic privilege-escalation lever, so it is doubly fenced:
  # only the stack's roles, and only when handed to the Lambda service.
  statement {
    sid       = "PassStackRolesToLambda"
    actions   = ["iam:PassRole"]
    resources = [for p in local.env_name_patterns[each.key] : "arn:aws:iam::${local.account_id}:role/${p}"]
    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values   = ["lambda.amazonaws.com"]
    }
  }

  # The stack's IAM users (the edge's identity for invoking the core Lambda — see
  # edge.tf), with their access keys and inline policies. As for roles, creating one or
  # changing what it may do requires the workload boundary on it. Only where the stack
  # runs the edge.
  dynamic "statement" {
    for_each = each.value.edge ? [1] : []
    content {
      sid = "ManageStackUsers"
      actions = [
        "iam:CreateUser",
        "iam:PutUserPermissionsBoundary",
        "iam:PutUserPolicy",
        "iam:DeleteUserPolicy",
      ]
      resources = [for p in local.env_name_patterns[each.key] : "arn:aws:iam::${local.account_id}:user/${p}"]
      condition {
        test     = "StringEquals"
        variable = "iam:PermissionsBoundary"
        values   = [aws_iam_policy.workload_boundary[each.key].arn]
      }
    }
  }

  dynamic "statement" {
    for_each = each.value.edge ? [1] : []
    content {
      sid = "MaintainStackUsers"
      actions = [
        "iam:GetUser",
        "iam:DeleteUser",
        "iam:TagUser",
        "iam:UntagUser",
        "iam:CreateAccessKey",
        "iam:DeleteAccessKey",
        "iam:ListAccessKeys",
        "iam:GetUserPolicy",
        "iam:ListUserPolicies",
        "iam:ListAttachedUserPolicies",
        # Deleting a user: the provider lists its groups to remove it from them first.
        "iam:ListGroupsForUser",
      ]
      resources = [for p in local.env_name_patterns[each.key] : "arn:aws:iam::${local.account_id}:user/${p}"]
    }
  }

  # The edge runs on Lightsail's container service. Lightsail resources are
  # identified by random-GUID ARNs, so there is no name-based ARN to scope to: the
  # blast radius is the account's Lightsail, which holds only the production edge, so
  # an environment without an edge gets none of it.
  dynamic "statement" {
    for_each = each.value.edge ? [1] : []
    content {
      sid       = "ManageEdgeContainerService"
      actions   = ["lightsail:*"]
      resources = ["*"]
    }
  }

  # The access principals: CI's roles (<name_prefix>-github-*), and the operator's role
  # and user (operator.tf). An explicit deny keeps the deploy role from editing them,
  # i.e. from granting itself, or anyone, more.
  statement {
    sid     = "DenyAccessPrincipals"
    effect  = "Deny"
    actions = ["iam:*"]
    resources = [
      "arn:aws:iam::${local.account_id}:role/${var.name_prefix}-github-*",
      aws_iam_role.operator.arn,
      aws_iam_user.operator.arn,
    ]
  }
}

resource "aws_iam_role_policy" "github_deploy" {
  for_each = var.environments

  name   = "deploy"
  role   = aws_iam_role.github_deploy[each.key].id
  policy = data.aws_iam_policy_document.deploy_permissions[each.key].json
}

output "deploy_role_arns" {
  description = "Each environment's deploy role. deploy.yml derives each ARN from its role name (.github/scripts/deploy-role.sh), so nothing needs setting."
  value       = { for name, role in aws_iam_role.github_deploy : name => role.arn }
}

# The unkeyed deploy role, its policy and the workload boundary map onto the legacy
# environment's instances.
moved {
  from = aws_iam_role.github_deploy
  to   = aws_iam_role.github_deploy["legacy"]
}

moved {
  from = aws_iam_role_policy.github_deploy
  to   = aws_iam_role_policy.github_deploy["legacy"]
}

moved {
  from = aws_iam_policy.workload_boundary
  to   = aws_iam_policy.workload_boundary["legacy"]
}
