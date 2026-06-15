# One-time bootstrap for the remote state backend: an encrypted, versioned S3
# bucket for state. State locking is handled natively by S3 (`use_lockfile`,
# Terraform >= 1.11), so no DynamoDB table is needed. Uses LOCAL state itself
# (chicken-and-egg), so just keep the small state file it produces.
#
#   cd deploy/terraform/bootstrap
#   terraform init
#   terraform apply -var "state_bucket=petbot-tfstate-<your-account-id>"

terraform {
  required_version = ">= 1.11"

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
  name               = "petbot-github-deploy"
  assume_role_policy = data.aws_iam_policy_document.deploy_trust.json
}

# Permissions the deploy workflow needs: Terraform state in S3, read the runtime
# secrets in SSM, and manage the interactions stack (Lambda/ECR/role/logs/budget).
# Wildcarded on the service actions for a single-stack bootstrap; tighten to ARNs
# if this account ever hosts more than petbot.
data "aws_iam_policy_document" "deploy_permissions" {
  statement {
    sid       = "TerraformState"
    actions   = ["s3:ListBucket", "s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = [aws_s3_bucket.state.arn, "${aws_s3_bucket.state.arn}/*"]
  }

  statement {
    sid       = "ReadRuntimeSecrets"
    actions   = ["ssm:GetParameter", "ssm:GetParameters"]
    resources = ["arn:aws:ssm:*:${data.aws_caller_identity.current.account_id}:parameter/petbot/interactions/*"]
  }

  statement {
    sid = "ManageInteractionsStack"
    actions = [
      "lambda:*",
      "ecr:*",
      "logs:*",
      "budgets:*",
      "iam:GetRole",
      "iam:PassRole",
      "iam:CreateRole",
      "iam:DeleteRole",
      "iam:AttachRolePolicy",
      "iam:DetachRolePolicy",
      "iam:PutRolePolicy",
      "iam:DeleteRolePolicy",
      "iam:GetRolePolicy",
      "iam:ListRolePolicies",
      "iam:ListAttachedRolePolicies",
      "iam:TagRole",
      "iam:UntagRole",
    ]
    resources = ["*"]
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
