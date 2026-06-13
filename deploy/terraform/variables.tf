variable "aws_region" {
  type        = string
  description = "AWS region for all resources."
  default     = "us-east-1"
}

variable "name_prefix" {
  type        = string
  description = "Name applied to the Lambda, ECR repo, and IAM role."
  default     = "petbot-interactions"
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
  description = "Lambda timeout (seconds). The handler caps skills well under Discord's 3s."
  default     = 10
}

variable "public_key_ssm_parameter" {
  type        = string
  description = <<-EOT
    Name of the SSM SecureString parameter holding DISCORD_PUBLIC_KEY. Created
    out-of-band (see README) so its value is never committed; Terraform reads it
    to populate the Lambda's environment.
  EOT
  default     = "/petbot/interactions/discord_public_key"
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
