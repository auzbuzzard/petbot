# Runtime secrets are stored as SSM SecureString parameters created out-of-band
# (see README) and read here to populate the Lambda's environment. The bot only
# ever reads os.environ, so the app stays platform-agnostic.
#
# Trade-off (flagged for review): injecting via the Lambda environment means the
# decrypted values land in the Lambda's config and therefore in Terraform state.
# The S3 backend is encrypted, versioned, and access-controlled to contain this.
# Keeping state fully secret-free would require the function to fetch SSM at
# runtime instead — a documented future hardening (tracked with secrets/ops #17).

data "aws_ssm_parameter" "public_key" {
  name            = var.public_key_ssm_parameter
  with_decryption = true
}

data "aws_ssm_parameter" "booru" {
  for_each        = var.booru_ssm_parameters
  name            = each.value
  with_decryption = true
}

locals {
  base_env = merge(
    {
      ENV       = var.lambda_environment
      LOG_LEVEL = var.log_level
    },
    var.user_agent != "" ? { USER_AGENT = var.user_agent } : {},
  )

  secret_env = merge(
    { DISCORD_PUBLIC_KEY = data.aws_ssm_parameter.public_key.value },
    { for env_name, param in data.aws_ssm_parameter.booru : env_name => param.value },
  )

  lambda_env = merge(local.base_env, local.secret_env)
}
