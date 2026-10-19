# The root of trust for CI: the remote-state bucket, the GitHub OIDC provider and the
# deploy role CI assumes. CI cannot grant itself trust or permissions, so an admin
# applies this stack, and only when it changes: the deploy role is scoped by the stack's
# naming convention (<name_prefix>-*), so adding resources to the root stack never needs
# a bootstrap change; only adding a new AWS service does. See README "Bootstrap".
#
# Its own state lives in the bucket it manages (key bootstrap/terraform.tfstate),
# locked natively by S3 (`use_lockfile`, Terraform >= 1.11):
#
#   terraform init -backend-config=backend.hcl
#   terraform apply -var "state_bucket=petbot-tfstate-<your-account-id>"

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
  description = "Must match var.name_prefix in the root stack; the deploy role may manage resources named <name_prefix>-*."
  default     = "petbot"
}

resource "aws_s3_bucket" "state" {
  bucket = var.state_bucket
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

output "state_bucket" {
  value = aws_s3_bucket.state.id
}

# --- GitHub Actions OIDC: the one irreducible bit of trust --------------------
# CI cannot bootstrap its own trust: AWS must already trust GitHub before any
# workflow can assume a role. This (and the SSM secrets) is the single manual,
# in-browser CloudShell step; after it, 100% of deploys are CI.

data "aws_caller_identity" "current" {}

resource "aws_iam_openid_connect_provider" "github" {
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
  # AWS validates GitHub's OIDC cert against its trust store now, but the
  # argument is still required; this is GitHub's documented thumbprint.
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]
}

# Trust policy: only this repo's workflows (any ref) may assume the role.
data "aws_iam_policy_document" "deploy_trust" {
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
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_repo}:*"]
    }
  }
}

resource "aws_iam_role" "github_deploy" {
  name               = "${var.name_prefix}-github-deploy"
  assume_role_policy = data.aws_iam_policy_document.deploy_trust.json
}

locals {
  account_id = data.aws_caller_identity.current.account_id
  # ARN prefixes for "any resource of this stack": everything the root stack creates is
  # named <name_prefix>-*, so new resources fall inside the deploy role's scope as long
  # as they follow the convention.
  arn_region = "${var.aws_region}:${local.account_id}"
  stack      = "${var.name_prefix}-*"
}

# The deploy role's permissions. Service-level action wildcards (e.g. ecr:*) are kept
# where enumerating every Terraform-issued call is brittle; each statement is scoped to
# resources named <name_prefix>-*, so a stolen CI token reaches this stack and nothing
# else in the account. The CI roles themselves are carved out (DenyCiRoles), so the
# deploy role can never widen its own permissions.
data "aws_iam_policy_document" "deploy_permissions" {
  statement {
    sid       = "TerraformState"
    actions   = ["s3:ListBucket", "s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = [aws_s3_bucket.state.arn, "${aws_s3_bucket.state.arn}/*"]
  }

  statement {
    sid       = "ReadRuntimeSecrets"
    actions   = ["ssm:GetParameter", "ssm:GetParameters"]
    resources = ["arn:aws:ssm:${local.arn_region}:parameter/${var.name_prefix}/*"]
  }

  # SecureString parameters are KMS-encrypted; reading them with decryption needs
  # kms:Decrypt. Scoped via kms:ViaService so the role can only use KMS through
  # SSM — never to decrypt arbitrary data directly.
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

  # ECR login is an account-level call with no resource to scope to.
  statement {
    sid       = "EcrAuth"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  statement {
    sid       = "ManageEcrRepos"
    actions   = ["ecr:*"]
    resources = ["arn:aws:ecr:${local.arn_region}:repository/${local.stack}"]
  }

  statement {
    sid     = "ManageLambda"
    actions = ["lambda:*"]
    resources = [
      "arn:aws:lambda:${local.arn_region}:function:${local.stack}",
      "arn:aws:lambda:${local.arn_region}:function:${local.stack}:*",
    ]
  }

  statement {
    sid     = "ManageLogs"
    actions = ["logs:*"]
    resources = [
      "arn:aws:logs:${local.arn_region}:log-group:/aws/lambda/${local.stack}",
      "arn:aws:logs:${local.arn_region}:log-group:/aws/lambda/${local.stack}:*",
    ]
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
    resources = ["arn:aws:dynamodb:${local.arn_region}:table/${local.stack}"]
  }

  statement {
    sid       = "ManageBudget"
    actions   = ["budgets:*"]
    resources = ["arn:aws:budgets::${local.account_id}:budget/*"]
  }

  # The stack's IAM roles (the Lambda execution role).
  statement {
    sid = "ManageStackRoles"
    actions = [
      "iam:GetRole",
      "iam:CreateRole",
      "iam:DeleteRole",
      "iam:AttachRolePolicy",
      "iam:DetachRolePolicy",
      "iam:PutRolePolicy",
      "iam:DeleteRolePolicy",
      "iam:GetRolePolicy",
      "iam:ListRolePolicies",
      "iam:ListAttachedRolePolicies",
      "iam:ListInstanceProfilesForRole",
      "iam:TagRole",
      "iam:UntagRole",
    ]
    resources = ["arn:aws:iam::${local.account_id}:role/${local.stack}"]
  }

  # PassRole is the classic privilege-escalation lever, so it is doubly fenced:
  # only the stack's roles, and only when handed to the Lambda service.
  statement {
    sid       = "PassStackRolesToLambda"
    actions   = ["iam:PassRole"]
    resources = ["arn:aws:iam::${local.account_id}:role/${local.stack}"]
    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values   = ["lambda.amazonaws.com"]
    }
  }

  # The stack's IAM users (the edge's identity for invoking the core Lambda — see
  # edge.tf), with their access keys and inline policies.
  statement {
    sid = "ManageStackUsers"
    actions = [
      "iam:GetUser",
      "iam:CreateUser",
      "iam:DeleteUser",
      "iam:TagUser",
      "iam:UntagUser",
      "iam:CreateAccessKey",
      "iam:DeleteAccessKey",
      "iam:ListAccessKeys",
      "iam:GetUserPolicy",
      "iam:PutUserPolicy",
      "iam:DeleteUserPolicy",
      "iam:ListUserPolicies",
      "iam:ListAttachedUserPolicies",
    ]
    resources = ["arn:aws:iam::${local.account_id}:user/${local.stack}"]
  }

  # The edge runs on Lightsail's container service. Lightsail resources are
  # identified by random-GUID ARNs, so there is no name-based ARN to scope to.
  # The blast radius is the account's Lightsail, which holds only this edge.
  statement {
    sid       = "ManageEdgeContainerService"
    actions   = ["lightsail:*"]
    resources = ["*"]
  }

  # The CI roles share the stack's prefix (<name_prefix>-github-*); an explicit deny
  # keeps the deploy role from editing them, i.e. from granting itself more.
  statement {
    sid       = "DenyCiRoles"
    effect    = "Deny"
    actions   = ["iam:*"]
    resources = ["arn:aws:iam::${local.account_id}:role/${var.name_prefix}-github-*"]
  }
}

resource "aws_iam_role_policy" "github_deploy" {
  name   = "deploy"
  role   = aws_iam_role.github_deploy.id
  policy = data.aws_iam_policy_document.deploy_permissions.json
}

output "deploy_role_arn" {
  description = "Set as the DEPLOY_ROLE_ARN GitHub Actions variable."
  value       = aws_iam_role.github_deploy.arn
}
