# Runtime secrets are SSM SecureString parameters created out-of-band (see README).
# Terraform passes each process only their *names*, as SSM_SECRETS (a JSON object of
# ENV-VAR-NAME => parameter name), and the process reads the values when it starts
# (petbot.platform.secrets). No secret value reaches the function's configuration or
# Terraform state, and the process's IAM identity may read exactly these parameters.

locals {
  # Both key-based providers carry the chat API key (an OpenRouter key, or a
  # Bedrock API key for the openai_compatible "mantle" endpoint). Plain bedrock
  # (Converse + IAM) and bedrock_mantle (SigV4 with the function's role) need no key.
  chat_needs_api_key = contains(["openrouter", "openai_compatible"], var.chat_llm_kind)

  # The salt for the telemetry user-id hash, read by both processes when telemetry is on.
  telemetry_secret_parameters = (
    var.observability_enabled && trimspace(var.telemetry_id_salt_ssm_parameter) != ""
    ? { OBS_ID_SALT = var.telemetry_id_salt_ssm_parameter }
    : {}
  )

  core_secret_parameters = merge(
    local.chat_needs_api_key ? { CHAT_LLM__API_KEY = var.chat_llm_api_key_ssm_parameter } : {},
    trimspace(var.tavily_api_key_ssm_parameter) != "" ? { TAVILY_API_KEY = var.tavily_api_key_ssm_parameter } : {},
    var.booru_ssm_parameters,
    local.telemetry_secret_parameters,
  )

  edge_secret_parameters = merge(
    { DISCORD_TOKEN = coalesce(var.discord_token_ssm_parameter, "/${var.name_prefix}/edge/discord_token") },
    local.telemetry_secret_parameters,
  )

  base_env = merge(
    {
      ENV       = var.lambda_environment
      LOG_LEVEL = var.log_level
      # The chat agent's provider config, as the nested env the worker's
      # ChatSettings reads (CHAT_LLM__KIND / CHAT_LLM__MODEL[ / __BASE_URL]); the key
      # (CHAT_LLM__API_KEY) arrives through SSM_SECRETS.
      CHAT_LLM__KIND  = var.chat_llm_kind
      CHAT_LLM__MODEL = var.chat_llm_model
      # How an over-long conversation is compacted when the model rejects it for
      # length (reactive). Default sliding_window; summarize uses the stylizer tier.
      CHAT_CONTEXT__KIND = var.context_kind
    },
    var.chat_llm_base_url != "" ? { CHAT_LLM__BASE_URL = var.chat_llm_base_url } : {},
    var.chat_thinking != "" ? { CHAT_THINKING = var.chat_thinking } : {},
    var.user_agent != "" ? { USER_AGENT = var.user_agent } : {},
  )

  lambda_env = merge(
    local.base_env,
    length(local.core_secret_parameters) > 0 ? { SSM_SECRETS = jsonencode(local.core_secret_parameters) } : {},
  )
}

# Read access to exactly the named parameters, decrypted through SSM only.
data "aws_iam_policy_document" "core_secrets" {
  count = length(local.core_secret_parameters) > 0 ? 1 : 0

  statement {
    actions = ["ssm:GetParameters"]
    resources = [
      for name in distinct(values(local.core_secret_parameters)) :
      "arn:aws:ssm:${var.aws_region}:${data.aws_caller_identity.current.account_id}:parameter/${trimprefix(name, "/")}"
    ]
  }

  statement {
    actions   = ["kms:Decrypt"]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values   = ["ssm.${var.aws_region}.amazonaws.com"]
    }
  }
}

resource "aws_iam_role_policy" "core_secrets" {
  count  = length(local.core_secret_parameters) > 0 ? 1 : 0
  name   = "${local.core_name}-secrets"
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.core_secrets[0].json
}

data "aws_iam_policy_document" "edge_secrets" {
  count = local.edge_count

  statement {
    actions = ["ssm:GetParameters"]
    resources = [
      for name in distinct(values(local.edge_secret_parameters)) :
      "arn:aws:ssm:${var.aws_region}:${data.aws_caller_identity.current.account_id}:parameter/${trimprefix(name, "/")}"
    ]
  }

  statement {
    actions   = ["kms:Decrypt"]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values   = ["ssm.${var.aws_region}.amazonaws.com"]
    }
  }
}

resource "aws_iam_user_policy" "edge_secrets" {
  count = local.edge_count

  name   = "${local.edge_name}-secrets"
  user   = aws_iam_user.edge[0].name
  policy = data.aws_iam_policy_document.edge_secrets[0].json
}
