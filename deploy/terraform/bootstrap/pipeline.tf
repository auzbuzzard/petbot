# --- Bootstrap's own pipeline: plan, then apply after review -----------------------
# After the one-time seed, CI applies this stack too, through .github/workflows/bootstrap.yml
# and two roles kept apart from the deploy role:
#
#   petbot-github-bootstrap-plan   read-only; trusted from the `bootstrap-plan` environment
#   petbot-github-bootstrap-apply  writes; trusted from the `bootstrap` environment, whose
#                                  required reviewer approves each run after reading the plan
#
# Their trust policies are main.tf's github_trust.

variable "bootstrap_plan_environment" {
  type        = string
  description = "GitHub environment whose jobs may assume the bootstrap plan role."
  default     = "bootstrap-plan"
}

variable "retiring_users" {
  type        = list(string)
  description = "IAM users this stack deletes; its pipeline roles keep permission to manage them until the apply that deletes them has run."
  default     = ["petbot-bedrock-key"]
}

variable "bootstrap_apply_environment" {
  type        = string
  description = "GitHub environment, with a required reviewer, whose jobs may assume the bootstrap apply role."
  default     = "bootstrap"
}

locals {
  # What this stack manages, by ARN: the access roles and the policies (an environment's
  # boundary by name when its prefix falls outside <name_prefix>-*), the operator user, the
  # OIDC provider. Its plan and apply roles are scoped to exactly these.
  bootstrap_iam_arns = concat(
    [
      "arn:aws:iam::${local.account_id}:role/${var.name_prefix}-github-*",
      aws_iam_role.operator.arn,
      "arn:aws:iam::${local.account_id}:policy/${var.name_prefix}-*",
      aws_iam_user.operator.arn,
      aws_iam_openid_connect_provider.github.arn,
    ],
    [
      for env in values(var.environments) : "arn:aws:iam::${local.account_id}:policy/${env.name_prefix}-workload-boundary"
      if !startswith("${env.name_prefix}-", "${var.name_prefix}-")
    ],
    [for name in var.retiring_users : "arn:aws:iam::${local.account_id}:user/${name}"],
  )

  bootstrap_role_policies = {
    plan  = data.aws_iam_policy_document.bootstrap_read.json
    apply = data.aws_iam_policy_document.bootstrap_apply.json
  }
}

resource "aws_iam_role" "github_bootstrap" {
  for_each = local.bootstrap_role_policies

  name                 = "${var.name_prefix}-github-bootstrap-${each.key}"
  assume_role_policy   = data.aws_iam_policy_document.github_trust["bootstrap-${each.key}"].json
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
# can't be deleted (prevent_destroy, and no s3:DeleteBucket here). Terraform never creates
# the operator user's credentials (its keys stay out of band), so an applied plan can't
# either. That is not a bound on what this role can grant: it edits every access policy,
# its own included, and the reviewer's approval is what guards that.
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

  # Deleting a force_destroy user lists the account's virtual MFA devices first.
  dynamic "statement" {
    for_each = length(var.retiring_users) > 0 ? [1] : []
    content {
      sid       = "ListMfaForRetiringUsers"
      actions   = ["iam:ListVirtualMFADevices"]
      resources = ["arn:aws:iam::${local.account_id}:mfa/*"]
    }
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
    resources = [aws_iam_user.operator.arn]
  }
}

resource "aws_iam_role_policy" "github_bootstrap" {
  for_each = local.bootstrap_role_policies

  name   = "bootstrap-${each.key}"
  role   = aws_iam_role.github_bootstrap[each.key].id
  policy = each.value
}

output "bootstrap_plan_role_arn" {
  description = "Set as the BOOTSTRAP_PLAN_ROLE_ARN GitHub Actions variable."
  value       = aws_iam_role.github_bootstrap["plan"].arn
}

output "bootstrap_apply_role_arn" {
  description = "Set as the BOOTSTRAP_APPLY_ROLE_ARN GitHub Actions variable."
  value       = aws_iam_role.github_bootstrap["apply"].arn
}
