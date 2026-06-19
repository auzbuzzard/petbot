variable "aws_region" {
  type        = string
  description = <<-EOT
    Region for every regional resource in this stack (Lambda, ECR, CloudWatch,
    SSM, and the state bucket). This is the single knob — you decide; all
    resources inherit it (IAM is global and unaffected). Default us-east-1: it's
    AWS's cheapest US region (the pricing baseline) and where the global pieces a
    future custom domain needs (ACM for CloudFront) must live, avoiding
    cross-region friction. us-east-2 / us-west-2 cost the same if you prefer one
    of those. NOTE: the SSM secret parameters must be created in this region, and
    the state-bucket region in backend.hcl should match.
  EOT
  default     = "us-east-1"
}

variable "name_prefix" {
  type        = string
  description = "Base name for the stack; resources derive <name_prefix>-core / -edge (see locals.tf)."
  default     = "petbot"
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
  description = "Value of the bot's ENV variable (drives logging profile)."
  default     = "prod"
}

variable "log_level" {
  type        = string
  description = "Root log level: DEBUG | INFO | WARNING | ERROR | CRITICAL."
  default     = "INFO"
}

variable "user_agent" {
  type        = string
  description = "Optional override for the booru User-Agent; empty uses the app default."
  default     = ""
}

variable "memory_size" {
  type        = number
  description = "Lambda memory (MB); also scales CPU, which helps cold starts and numpy."
  default     = 1024
}

variable "timeout" {
  type        = number
  description = <<-EOT
    Lambda timeout (seconds). The edge invokes the worker synchronously and the
    chat agent runs an LLM tool-loop, so this is generous — not the old 3s
    Discord-interaction bound (the edge holds the gateway, not this function).
  EOT
  default     = 60
}

# --- Chat LLM (the worker's agent) --------------------------------------------

variable "chat_llm_kind" {
  type        = string
  description = "Chat provider discriminator: \"bedrock\" (IAM-auth) or \"openrouter\" (API key)."
  default     = "bedrock"

  validation {
    condition     = contains(["bedrock", "openrouter"], var.chat_llm_kind)
    error_message = "chat_llm_kind must be \"bedrock\" or \"openrouter\"."
  }
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
  description = "SSM SecureString holding the OpenRouter API key. Required only when chat_llm_kind=openrouter; ignored for bedrock."
  default     = ""
}

variable "booru_ssm_parameters" {
  type        = map(string)
  description = <<-EOT
    Optional booru auth, as a map of ENV-VAR-NAME => SSM-parameter-name, e.g.
    { DERPIBOORU_API_KEY = "/petbot/interactions/derpibooru_api_key" }. Each
    referenced parameter must already exist as a SecureString.
  EOT
  default     = {}
}

# --- Retention / cost controls ------------------------------------------------

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

# --- Edge (Lightsail container service) ---------------------------------------

variable "discord_token_ssm_parameter" {
  type        = string
  description = "SSM SecureString holding the edge's Discord bot token; injected into the container's environment."
  default     = "/petbot/edge/discord_token"
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

variable "edge_image" {
  type        = string
  description = <<-EOT
    Image ref for the edge container, as returned by `aws lightsail
    push-container-image` (e.g. ":petbot-edge.edge.1"). CI pushes the image and
    passes this in; empty leaves the service with no deployment (apply the
    service first, then push + set this — see README).
  EOT
  default     = ""
}
