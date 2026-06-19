# Runtime secrets are stored as SSM SecureString parameters created out-of-band
# (see README) and read here to populate the Lambda's environment. The worker only
# ever reads os.environ, so the app stays platform-agnostic.
#
# Trade-off (flagged for review): injecting via the Lambda environment means the
# decrypted values land in the Lambda's config and therefore in Terraform state.
# The S3 backend is encrypted, versioned, and access-controlled to contain this.
# Keeping state fully secret-free would require the function to fetch SSM at
# runtime instead — a documented future hardening (tracked with secrets/ops #17).

# OpenRouter API key — only when that provider is selected. Bedrock authenticates
# with the exec role's IAM policy (main.tf), so it needs no secret here.
data "aws_ssm_parameter" "chat_api_key" {
  count           = var.chat_llm_kind == "openrouter" ? 1 : 0
  name            = var.chat_llm_api_key_ssm_parameter
  with_decryption = true

  # Fail at plan with a clear message instead of an opaque "name is required"
  # SSM error when the param name was left empty for the openrouter provider.
  lifecycle {
    precondition {
      condition     = trimspace(var.chat_llm_api_key_ssm_parameter) != ""
      error_message = "chat_llm_kind=openrouter requires chat_llm_api_key_ssm_parameter (the SSM SecureString holding the key)."
    }
  }
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
      # The chat agent's provider config, as the nested env the worker's
      # ChatSettings reads (CHAT_LLM__KIND / CHAT_LLM__MODEL[ / __API_KEY]).
      CHAT_LLM__KIND  = var.chat_llm_kind
      CHAT_LLM__MODEL = var.chat_llm_model
    },
    var.user_agent != "" ? { USER_AGENT = var.user_agent } : {},
  )

  secret_env = merge(
    var.chat_llm_kind == "openrouter" ? { CHAT_LLM__API_KEY = data.aws_ssm_parameter.chat_api_key[0].value } : {},
    { for env_name, param in data.aws_ssm_parameter.booru : env_name => param.value },
  )

  lambda_env = merge(local.base_env, local.secret_env)
}
