# --- The stack's own SSM parameters ----------------------------------------------
#
# A secret this stack needs but can't mint (the Discord bot token) is copied from an
# existing parameter when its own is created: the source is read through an ephemeral
# resource and written with the write-only `value_wo`, so the value is in neither the plan
# nor the state (secrets.tf). value_wo is written only when value_wo_version changes, so
# later applies read the source but write nothing. With no source ("") a parameter reads
# itself, which keeps it once the parameter it was copied from is gone.

ephemeral "aws_ssm_parameter" "source" {
  for_each = var.ssm_parameters

  arn = "arn:aws:ssm:${var.aws_region}:${data.aws_caller_identity.current.account_id}:parameter/${trimprefix(coalesce(each.value, each.key), "/")}"
}

resource "aws_ssm_parameter" "owned" {
  for_each = var.ssm_parameters

  name             = each.key
  type             = "SecureString"
  value_wo         = ephemeral.aws_ssm_parameter.source[each.key].value
  value_wo_version = 1
}
