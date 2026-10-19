# --- Bootstrap's own pipeline: plan, then apply after review -----------------------
# After the one-time seed, CI applies this stack too, through .github/workflows/bootstrap.yml
# and two roles kept apart from the deploy role:
#
#   petbot-github-bootstrap-plan   read-only; trusted from the `bootstrap-plan` environment
#   petbot-github-bootstrap-apply  writes; trusted from the `bootstrap` environment, whose
#                                  required reviewer approves each run after reading the plan
#
# Both environments admit only main. The apply role can edit every resource here,
# itself included, so it is as powerful as this stack: the reviewer's approval is the
# control that guards it, which is why the deploy role (no approval) can never assume or
# edit it.

variable "bootstrap_plan_environment" {
  type        = string
  description = "GitHub environment whose jobs may assume the bootstrap plan role."
  default     = "bootstrap-plan"
}

variable "bootstrap_apply_environment" {
  type        = string
  description = "GitHub environment, with a required reviewer, whose jobs may assume the bootstrap apply role."
  default     = "bootstrap"
}

locals {
  bootstrap_environments = {
    plan  = var.bootstrap_plan_environment
    apply = var.bootstrap_apply_environment
  }

  # What this stack manages, by ARN: the access roles and the policies, the operator user,
  # the OIDC provider. Its plan and apply roles are scoped to exactly these.
  bootstrap_iam_arns = [
    "arn:aws:iam::${local.account_id}:role/${var.name_prefix}-github-*",
    "arn:aws:iam::${local.account_id}:role/${var.name_prefix}-operator",
    "arn:aws:iam::${local.account_id}:policy/${var.name_prefix}-*",
    "arn:aws:iam::${local.account_id}:user/${var.operator_user}",
    aws_iam_openid_connect_provider.github.arn,
  ]
}

data "aws_iam_policy_document" "bootstrap_trust" {
  for_each = local.bootstrap_environments

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
  }
}

resource "aws_iam_role" "github_bootstrap" {
  for_each = local.bootstrap_environments

  name                 = "${var.name_prefix}-github-bootstrap-${each.key}"
  assume_role_policy   = data.aws_iam_policy_document.bootstrap_trust[each.key].json
  max_session_duration = 3600
}

# Reading everything the stack manages, and taking the state lock (plan locks too).
data "aws_iam_policy_document" "bootstrap_read" {
  statement {
    sid = "ReadStateBucket"
    actions = [
      "s3:ListBucket",
      "s3:GetBucket*",
      "s3:GetEncryptionConfiguration",
      "s3:GetLifecycleConfiguration",
      "s3:GetReplicationConfiguration",
      "s3:GetAccelerateConfiguration",
      "s3:GetObjectLockConfiguration",
    ]
    resources = [aws_s3_bucket.state.arn]
  }

  statement {
    sid       = "ReadState"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.state.arn}/bootstrap/*"]
  }

  statement {
    sid       = "LockState"
    actions   = ["s3:PutObject", "s3:DeleteObject"]
    resources = ["${aws_s3_bucket.state.arn}/bootstrap/terraform.tfstate.tflock"]
  }

  statement {
    sid       = "ReadIam"
    actions   = ["iam:Get*", "iam:List*"]
    resources = local.bootstrap_iam_arns
  }
}

# On top of reading: writing the state and changing what the stack manages. The bucket
# can't be deleted (prevent_destroy, and no s3:DeleteBucket here), and no credential can be
# minted for the operator user: its keys stay out of band.
data "aws_iam_policy_document" "bootstrap_apply" {
  source_policy_documents = [data.aws_iam_policy_document.bootstrap_read.json]

  statement {
    sid = "ConfigureStateBucket"
    actions = [
      "s3:PutBucket*",
      "s3:DeleteBucketPolicy",
      "s3:PutEncryptionConfiguration",
    ]
    resources = [aws_s3_bucket.state.arn]
  }

  statement {
    sid       = "WriteState"
    actions   = ["s3:PutObject", "s3:DeleteObject"]
    resources = ["${aws_s3_bucket.state.arn}/bootstrap/*"]
  }

  statement {
    sid       = "ManageTrust"
    actions   = ["iam:*"]
    resources = local.bootstrap_iam_arns
  }

  statement {
    sid    = "NoOperatorCredentials"
    effect = "Deny"
    actions = [
      "iam:CreateAccessKey",
      "iam:UpdateAccessKey",
      "iam:CreateLoginProfile",
      "iam:UpdateLoginProfile",
      "iam:CreateServiceSpecificCredential",
      "iam:UploadSSHPublicKey",
      "iam:UploadSigningCertificate",
    ]
    resources = ["arn:aws:iam::${local.account_id}:user/${var.operator_user}"]
  }
}

resource "aws_iam_role_policy" "github_bootstrap" {
  for_each = local.bootstrap_environments

  name = "bootstrap-${each.key}"
  role = aws_iam_role.github_bootstrap[each.key].id
  policy = (each.key == "apply"
    ? data.aws_iam_policy_document.bootstrap_apply.json
  : data.aws_iam_policy_document.bootstrap_read.json)
}

output "bootstrap_plan_role_arn" {
  description = "Set as the BOOTSTRAP_PLAN_ROLE_ARN GitHub Actions variable."
  value       = aws_iam_role.github_bootstrap["plan"].arn
}

output "bootstrap_apply_role_arn" {
  description = "Set as the BOOTSTRAP_APPLY_ROLE_ARN GitHub Actions variable."
  value       = aws_iam_role.github_bootstrap["apply"].arn
}
