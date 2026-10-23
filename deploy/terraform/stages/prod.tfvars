# Production (GitHub environment `production`; deploy.yml sets name_prefix = "petbot-prod").
# Every deploy setting lives here, reviewed like code; the pipeline reads nothing else.

lambda_environment = "prod"

chat_llm_kind     = "bedrock_mantle"
chat_llm_model    = "google.gemma-4-31b"
chat_llm_base_url = "https://bedrock-mantle.us-east-1.api.aws/openai/v1"
chat_thinking     = "high"

# Off while this core runs beside the legacy stack, whose edge still holds the gateway:
# two connected edges would both answer every message (docs/adr/0014).
edge_enabled = false

# The web_search tool's Tavily key.
tavily_api_key_ssm_parameter = "/petbot-prod/core/tavily_api_key"

# The edge's bot token and the Tavily key, copied from the legacy stack's parameters.
ssm_parameters = {
  "/petbot-prod/edge/discord_token"  = "/petbot/edge/discord_token"
  "/petbot-prod/core/tavily_api_key" = "/petbot/core/tavily_api_key"
}
