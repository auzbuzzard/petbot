variable "aws_region" {
  type        = string
  description = <<-EOT
    Region of every regional resource in this stack: the Lambda function, ECR
    repositories, CloudWatch log group, SSM parameters, and the edge's Lightsail
    service and claims table. IAM is global. The SSM parameters this stack reads must
    exist in this region. The state bucket belongs to bootstrap; backend.hcl names
    its region.
  EOT
  default     = "us-east-1"
}

variable "name_prefix" {
  type        = string
  description = "Base name for the stack; resources derive <name_prefix>-core / -edge (see locals.tf). petbot-prod or petbot-dev (deploy.yml sets it)."
  default     = "petbot-prod"
}

variable "image_tag" {
  type        = string
  description = <<-EOT
    ECR image tag to deploy. The image must be built and pushed before the main
    apply (the function is pinned to the tag's digest); use a unique tag per
    deploy (e.g. the git SHA) so a re-push is picked up. See README.
  EOT
  default     = "latest"
}

variable "lambda_environment" {
  type        = string
  description = "Value of ENV in the core function and the edge container. Nothing in src/petbot reads ENV."
  default     = "prod"
}

variable "log_level" {
  type        = string
  description = "Root log level: DEBUG | INFO | WARNING | ERROR | CRITICAL."
  default     = "INFO"
}

variable "user_agent" {
  type        = string
  description = "Optional User-Agent for the booru and web_fetch requests (USER_AGENT in the worker); empty uses the app default."
  default     = ""
}

# https://docs.aws.amazon.com/lambda/latest/dg/configuration-memory.html
variable "memory_size" {
  type        = number
  description = "Memory (MB) of the core Lambda function. Lambda allocates CPU in proportion to it."
  default     = 1024
}

variable "timeout" {
  type        = number
  description = <<-EOT
    Timeout (seconds) of the core Lambda function, which the edge invokes
    synchronously. The worker gives each chat turn the remaining invocation time,
    minus a small reserve, as its budget, so a turn that runs long answers with a
    fallback line instead of being killed.
  EOT
  default     = 120
}

variable "chat_llm_kind" {
  type        = string
  description = <<-EOT
    Chat provider discriminator:
      bedrock           - Converse API, IAM-auth, no key (Nova / Claude).
      bedrock_mantle    - Bedrock's OpenAI-compatible "mantle" endpoint (Gemma 4) by base
                          URL, SigV4-signed with the function's role: no key.
      openai_compatible - any OpenAI-compatible endpoint by base URL + key
                          (the mantle endpoint with a Bedrock API key, or Ollama/vLLM).
      openrouter        - OpenRouter (API key).
  EOT
  default     = "bedrock"

  validation {
    condition     = contains(["bedrock", "bedrock_mantle", "openai_compatible", "openrouter"], var.chat_llm_kind)
    error_message = "chat_llm_kind must be one of: bedrock, bedrock_mantle, openai_compatible, openrouter."
  }
}

variable "chat_llm_base_url" {
  type        = string
  description = "Base URL for the bedrock_mantle and openai_compatible providers, e.g. https://bedrock-mantle.<region>.api.aws/openai/v1. Required for those kinds; ignored otherwise."
  default     = ""
}

variable "chat_llm_model" {
  type        = string
  description = "Model id for the chosen provider (e.g. a Bedrock model/inference-profile id, or an OpenRouter model)."

  validation {
    condition     = trimspace(var.chat_llm_model) != ""
    error_message = "chat_llm_model must be set to the chosen provider's model id."
  }
}

variable "chat_llm_api_key_ssm_parameter" {
  type        = string
  description = "SSM SecureString holding the chat API key (OpenRouter key, or a Bedrock API key for openai_compatible). Required for openrouter + openai_compatible; ignored for bedrock."
  default     = ""
}

variable "chat_thinking" {
  type        = string
  description = <<-EOT
    Whether the chat agent reasons before answering, passed to pydantic-ai's thinking
    setting. Sets CHAT_THINKING in the worker: "" leaves it unset (the model's
    default); otherwise true, false, minimal, low, medium or high.
  EOT
  default     = "high"

  validation {
    condition     = contains(["", "true", "false", "minimal", "low", "medium", "high"], var.chat_thinking)
    error_message = "chat_thinking must be empty, true, false, minimal, low, medium or high."
  }
}

variable "context_kind" {
  type        = string
  description = <<-EOT
    How the chat agent compacts an over-long conversation *when the model rejects it
    for length* (reactive — there is no token budget to set):
      sliding_window - drop the oldest half (zero cost; default).
      summarize      - summarise the oldest half with the stylizer-tier model.
    Sets CHAT_CONTEXT__KIND in the worker.
  EOT
  default     = "sliding_window"

  validation {
    condition     = contains(["sliding_window", "summarize"], var.context_kind)
    error_message = "context_kind must be one of: sliding_window, summarize."
  }
}

variable "tavily_api_key_ssm_parameter" {
  type        = string
  description = <<-EOT
    Optional SSM SecureString holding a Tavily API key for the chat agent's web_search
    tool. Empty (default) runs search on the keyless ddgs fallback alone. Sets
    TAVILY_API_KEY in the worker.
  EOT
  default     = ""
}

variable "booru_ssm_parameters" {
  type        = map(string)
  description = <<-EOT
    Optional booru auth, as a map of ENV-VAR-NAME => SSM-parameter-name, e.g.
    { DERPIBOORU_API_KEY = "/petbot-prod/core/derpibooru_api_key" }. Each
    referenced parameter must already exist as a SecureString.
  EOT
  default     = {}
}

variable "ssm_parameters" {
  type        = map(string)
  description = <<-EOT
    SecureString parameters this stack owns, by name under /<name_prefix>/, each mapped to
    the existing parameter its value is copied from when it is created: read through an
    ephemeral resource and written write-only, so the value reaches neither the plan nor the
    state (parameters.tf). Once it exists it keeps its own value and no longer reads the
    source (var.existing_ssm_parameters).
  EOT
  default     = {}

  validation {
    condition     = alltrue([for name in keys(var.ssm_parameters) : startswith(name, "/${var.name_prefix}/")])
    error_message = "Every owned parameter must be under /<name_prefix>/."
  }
}

variable "existing_ssm_parameters" {
  type        = list(string)
  description = "The names in var.ssm_parameters that already exist, so each reads its own value rather than its source. deploy.yml lists them before planning."
  default     = []
}

variable "log_retention_days" {
  type        = number
  description = "CloudWatch Logs retention for the function (a valid CloudWatch value, e.g. 7/14/30/90)."
  default     = 30
}

variable "ecr_keep_last_images" {
  type        = number
  description = "Keep this many of the most-recent tagged images; older ones are expired."
  default     = 10
}

variable "ecr_untagged_expire_days" {
  type        = number
  description = "Expire untagged images older than this many days."
  default     = 7
}

variable "monthly_budget_usd" {
  type        = number
  description = "Monthly AWS Budgets alert limit (USD). 0 (default) creates no budget."
  default     = 0
}

variable "budget_alert_emails" {
  type        = list(string)
  description = "Emails notified at 80% and 100% of monthly_budget_usd; required to enable the budget."
  default     = []
}

variable "edge_enabled" {
  type        = bool
  description = <<-EOT
    Whether this stack runs the Discord edge. false deploys the core alone (a dev core,
    exercised through the chat harness's --lambda): no Lightsail service, edge IAM user,
    access key, edge ECR repo or claims table.
  EOT
  default     = true
}

variable "discord_token_ssm_parameter" {
  type        = string
  description = "SSM SecureString holding the edge's Discord bot token, read by the edge at start. Empty => /<name_prefix>/edge/discord_token."
  default     = ""
}

variable "edge_paused" {
  type        = bool
  description = "Disable the edge's Lightsail service: its containers shut down and it leaves the Discord gateway, while every resource stays. Re-enabling is setting it back."
  default     = false
}

variable "edge_power" {
  type        = string
  description = "Lightsail container service power. nano (0.25 vCPU/512MB) fits the edge; bump to micro if it OOMs."
  default     = "nano"
}

variable "edge_scale" {
  type        = number
  description = "Number of container nodes (replicas). 1 always-on holder."
  default     = 1
}

variable "edge_key_rotation_days" {
  type        = number
  description = "Days after which the edge's static AWS access key is replaced, on the next deploy after that."
  default     = 90

  validation {
    condition     = var.edge_key_rotation_days >= 1
    error_message = "edge_key_rotation_days must be at least 1."
  }
}

variable "edge_image_tag" {
  type        = string
  description = <<-EOT
    Tag of the edge image in its ECR repo (CI sets this to the git SHA). The
    Lightsail service pulls `<edge-ecr-repo>:<tag>`. Empty leaves the service
    with no deployment (apply the service first, then push + set this).
  EOT
  default     = ""
}

variable "history_max_turns" {
  type        = number
  description = <<-EOT
    How many reply-chain ancestors the edge fetches when reconstructing conversation
    history (a Discord-API cost bound, not a model-context bound). Sets
    HISTORY_MAX_TURNS in the edge container.
  EOT
  default     = 25
}
