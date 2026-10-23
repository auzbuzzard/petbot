# The pre-migration production stack (name_prefix "petbot", state petbot/terraform.tfstate),
# operated by .github/workflows/legacy.yml until it is destroyed (docs/adr/0014). Only its
# edge's pause (a targeted apply) and its retirement (a destroy) are applied, so the other
# settings here need only be valid; they describe the stack as it runs.

lambda_environment = "prod"

chat_llm_kind                  = "openai_compatible"
chat_llm_model                 = "google.gemma-4-31b"
chat_llm_base_url              = "https://bedrock-mantle.us-east-1.api.aws/openai/v1"
chat_llm_api_key_ssm_parameter = "/petbot/core/bedrock_api_key"
chat_thinking                  = "high"

tavily_api_key_ssm_parameter = "/petbot/core/tavily_api_key"

discord_token_ssm_parameter = "/petbot/edge/discord_token"

edge_paused = false

retired = false
retired_parameters = [
  "/petbot/edge/discord_token",
  "/petbot/core/bedrock_api_key",
  "/petbot/core/tavily_api_key",
]
