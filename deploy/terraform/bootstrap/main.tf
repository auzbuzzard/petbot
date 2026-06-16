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

variable "name_prefix" {
  type        = string
  description = "Must match var.name_prefix in the root stack; used to scope the deploy role's permissions to exactly that stack's resources."
  default     = "petbot-interactions"
}

# Deploy-role name is an explicit variable (NOT derived from name_prefix) so the
# existing prod role keeps its exact current name `petbot-github-deploy` even
# though prod's name_prefix is `petbot-interactions`. A second environment passes
# a distinct name (e.g. `petbot-interactions-dev-github-deploy`) to provision its
# own role + scoped permissions without clobbering prod's.
variable "deploy_role_name" {
  type        = string
  description = "IAM role name for the CI deploy role. Default keeps the existing prod role; override per non-prod env."
  default     = "petbot-github-deploy"
}

# The GitHub OIDC provider is account-global: exactly one
# `token.actions.githubusercontent.com` provider can exist per account, and prod
# bootstrap already created it. A second environment in the SAME account must NOT
# try to create a duplicate — set this to false there and the role's trust policy
# references the existing provider by its (deterministic) ARN instead.
variable "manage_oidc_provider" {
  type        = bool
  description = "Whether THIS apply owns the account-global GitHub OIDC provider. true for the first/prod bootstrap; false for additional same-account envs."
  default     = true
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

# Owned by the first/prod bootstrap only (manage_oidc_provider = true). Account
# can hold exactly one provider for this URL, so additional same-account envs
# reference the existing one instead of recreating it.
resource "aws_iam_openid_connect_provider" "github" {
  count          = var.manage_oidc_provider ? 1 : 0
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
  # AWS validates GitHub's OIDC cert against its trust store now, but the
  # argument is still required; this is GitHub's documented thumbprint.
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]
}

# Adding `count` above re-indexes the resource address from `.github` to
# `.github[0]`. This `moved` block migrates the EXISTING prod state entry to the
# new address automatically, so prod's next `terraform plan` is a true no-op
# (no destroy/recreate of the live OIDC provider) with no manual `state mv`.
moved {
  from = aws_iam_openid_connect_provider.github
  to   = aws_iam_openid_connect_provider.github[0]
}

locals {
  # The provider ARN is deterministic for a given account, so non-managing envs
  # can reference the already-existing provider without a data lookup or import.
  oidc_provider_arn = var.manage_oidc_provider ? aws_iam_openid_connect_provider.github[0].arn : "arn:aws:iam::${data.aws_caller_identity.current.account_id}:oidc-provider/token.actions.githubusercontent.com"
}

# Trust policy: only this repo's workflows (any ref) may assume the role.
data "aws_iam_policy_document" "deploy_trust" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [local.oidc_provider_arn]
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
  name               = var.deploy_role_name
  assume_role_policy = data.aws_iam_policy_document.deploy_trust.json
}

locals {
  account_id = data.aws_caller_identity.current.account_id

  # Every resource the deploy role may touch is one of the named stack resources
  # below; scoping to these ARNs means a stolen CI token can't reach anything
  # else in the account.
  lambda_arn    = "arn:aws:lambda:${var.aws_region}:${local.account_id}:function:${var.name_prefix}"
  ecr_repo_arn  = "arn:aws:ecr:${var.aws_region}:${local.account_id}:repository/${var.name_prefix}"
  log_group_arn = "arn:aws:logs:${var.aws_region}:${local.account_id}:log-group:/aws/lambda/${var.name_prefix}"
  exec_role_arn = "arn:aws:iam::${local.account_id}:role/${var.name_prefix}-role"
}

# Least-privilege permissions for the deploy workflow. Service-level action
# wildcards (e.g. ecr:*) are kept where enumerating every Terraform-issued call
# is brittle, but each statement is pinned to this stack's resource ARNs so the
# role's blast radius is exactly the interactions stack and nothing more.
data "aws_iam_policy_document" "deploy_permissions" {
  statement {
    sid       = "TerraformState"
    actions   = ["s3:ListBucket", "s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = [aws_s3_bucket.state.arn, "${aws_s3_bucket.state.arn}/*"]
  }

  statement {
    sid       = "ReadRuntimeSecrets"
    actions   = ["ssm:GetParameter", "ssm:GetParameters"]
    resources = ["arn:aws:ssm:${var.aws_region}:${local.account_id}:parameter/petbot/interactions/*"]
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
    sid       = "ManageEcrRepo"
    actions   = ["ecr:*"]
    resources = [local.ecr_repo_arn]
  }

  statement {
    sid       = "ManageLambda"
    actions   = ["lambda:*"]
    resources = [local.lambda_arn, "${local.lambda_arn}:*"]
  }

  statement {
    sid       = "ManageLogs"
    actions   = ["logs:*"]
    resources = [local.log_group_arn, "${local.log_group_arn}:*"]
  }

  statement {
    sid       = "ManageBudget"
    actions   = ["budgets:*"]
    resources = ["arn:aws:budgets::${local.account_id}:budget/*"]
  }

  # Create/manage only the Lambda execution role this stack owns.
  statement {
    sid = "ManageExecRole"
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
    resources = [local.exec_role_arn]
  }

  # PassRole is the classic privilege-escalation lever, so it is doubly fenced:
  # only the one exec role, and only when handed to the Lambda service.
  statement {
    sid       = "PassExecRoleToLambda"
    actions   = ["iam:PassRole"]
    resources = [local.exec_role_arn]
    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values   = ["lambda.amazonaws.com"]
    }
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
