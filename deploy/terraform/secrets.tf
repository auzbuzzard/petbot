# Runtime secrets are stored as SSM SecureString parameters created out-of-band
# (see README) and read here to populate the Lambda's environment. The worker only
# ever reads os.environ, so the app stays platform-agnostic.
#
# Trade-off (flagged for review): injecting via the Lambda environment means the
# decrypted values land in the Lambda's config and therefore in Terraform state.
# The S3 backend is encrypted, versioned, and access-controlled to contain this.
# Keeping state fully secret-free would require the function to fetch SSM at
# runtime instead — a documented future hardening (tracked with secrets/ops #17).

locals {
  # Both key-based providers carry the chat API key (an OpenRouter key, or a
  # Bedrock API key for the openai_compatible "mantle" endpoint). Plain bedrock
  # (Converse + IAM) needs no key.
  chat_needs_api_key = contains(["openrouter", "openai_compatible"], var.chat_llm_kind)
}

data "aws_ssm_parameter" "chat_api_key" {
  count           = local.chat_needs_api_key ? 1 : 0
  name            = var.chat_llm_api_key_ssm_parameter
  with_decryption = true

  # Fail at plan with a clear message instead of an opaque "name is required"
  # SSM error when the param name was left empty for a key-based provider.
  lifecycle {
    precondition {
      condition     = trimspace(var.chat_llm_api_key_ssm_parameter) != ""
      error_message = "chat_llm_kind=${var.chat_llm_kind} requires chat_llm_api_key_ssm_parameter (the SSM SecureString holding the key)."
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
      # ChatSettings reads (CHAT_LLM__KIND / CHAT_LLM__MODEL[ / __BASE_URL / __API_KEY]).
      CHAT_LLM__KIND  = var.chat_llm_kind
      CHAT_LLM__MODEL = var.chat_llm_model
      # How an over-long conversation is compacted when the model rejects it for
      # length (reactive). Default sliding_window; summarize uses the stylizer tier.
      CHAT_CONTEXT__KIND = var.context_kind
    },
    var.chat_llm_base_url != "" ? { CHAT_LLM__BASE_URL = var.chat_llm_base_url } : {},
    var.user_agent != "" ? { USER_AGENT = var.user_agent } : {},
  )

  secret_env = merge(
    local.chat_needs_api_key ? { CHAT_LLM__API_KEY = data.aws_ssm_parameter.chat_api_key[0].value } : {},
    { for env_name, param in data.aws_ssm_parameter.booru : env_name => param.value },
  )

  lambda_env = merge(local.base_env, local.secret_env)
}
