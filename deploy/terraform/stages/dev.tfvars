# Dev (GitHub environment `dev`, any branch; deploy.yml sets name_prefix = "petbot-dev").
# The core alone, on production's model with its own role: no edge, no secret.

lambda_environment = "dev"

chat_llm_kind     = "bedrock_mantle"
chat_llm_model    = "google.gemma-4-31b"
chat_llm_base_url = "https://bedrock-mantle.us-east-1.api.aws/openai/v1"
chat_thinking     = "high"

edge_enabled = false
