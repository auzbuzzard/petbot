# --- Agent observability (OpenTelemetry) — OFF by default ---------------------
#
# Gated entirely by var.observability_enabled. When off (the default) this file adds no env,
# IAM, or data sources, so applying it changes nothing for an existing deploy. When on, each
# deployable exports OTLP *directly to AWS's collector-less endpoints* — traces to the X-Ray
# OTLP endpoint, metrics to the CloudWatch (monitoring) OTLP endpoint — each POST SigV4-signed
# by the runtime's own credentials (see petbot.observability). No collector runs anywhere — the
# worker image bakes in no extension and the edge has no sidecar. The app reads the standard
# OTEL_* env plus OBS_* (see petbot.observability.ObservabilitySettings).
#
# PREREQUISITE (traces only): CloudWatch Transaction Search must be on, which is two parts —
#   1. a CloudWatch Logs resource policy letting X-Ray write spans to the aws/spans log group
#      (aws_cloudwatch_log_resource_policy.xray_transaction_search below, created with this
#      stack when the var is on); and
#   2. pointing the X-Ray trace-segment *destination* at CloudWatch Logs — an account + Region
#      toggle with no Terraform resource yet (hashicorp/terraform-provider-aws#44994), so run it
#      once after an observability-on deploy:
#        aws xray update-trace-segment-destination --destination CloudWatchLogs --region <region>
# Until both are done the X-Ray OTLP endpoint rejects spans (InvalidRequestException). Metrics
# (the monitoring endpoint) need neither step. See docs/adr/0011-agent-observability.md.
#
# Note (always-on, telemetry-independent): the per-turn run-outcome record ChatProcess emits
# (tools called, tokens, finish reason) is a plain structured *log*, captured by CloudWatch
# Logs straight off the Lambda's stdout regardless of OBS_ENABLED.

variable "observability_enabled" {
  type        = bool
  description = "Emit OpenTelemetry telemetry (traces/metrics) over OTLP to AWS's collector-less endpoints. Off by default."
  default     = false
}

variable "observability_sample_ratio" {
  type        = number
  description = "Head sampling ratio for root traces (1.0 = all)."
  default     = 1.0
}

variable "telemetry_id_salt_ssm_parameter" {
  type        = string
  description = "SSM SecureString name holding the salt for the telemetry user-id hash. Empty => unsalted."
  default     = ""
}

data "aws_ssm_parameter" "telemetry_id_salt" {
  count           = var.observability_enabled && trimspace(var.telemetry_id_salt_ssm_parameter) != "" ? 1 : 0
  name            = var.telemetry_id_salt_ssm_parameter
  with_decryption = true
}

locals {
  # AWS's collector-less OTLP endpoints (SigV4). The app derives the signing service + Region
  # from each host (xray | monitoring.<region>.amazonaws.com), so the Region lives only here.
  otlp_traces_endpoint  = "https://xray.${var.aws_region}.amazonaws.com/v1/traces"
  otlp_metrics_endpoint = "https://monitoring.${var.aws_region}.amazonaws.com/v1/metrics"

  # Shared OTLP/OBS env for any deployable; service_name is set per process below.
  observability_common_env = var.observability_enabled ? merge(
    {
      OBS_ENABLED                         = "true"
      OBS_SAMPLE_RATIO                    = tostring(var.observability_sample_ratio)
      OTEL_EXPORTER_OTLP_TRACES_ENDPOINT  = local.otlp_traces_endpoint
      OTEL_EXPORTER_OTLP_METRICS_ENDPOINT = local.otlp_metrics_endpoint
    },
    length(data.aws_ssm_parameter.telemetry_id_salt) > 0
    ? { OBS_ID_SALT = data.aws_ssm_parameter.telemetry_id_salt[0].value }
    : {},
  ) : {}

  observability_core_env = var.observability_enabled ? merge(
    local.observability_common_env,
    { OBS_SERVICE_NAME = local.core_name, OTEL_SERVICE_NAME = local.core_name },
  ) : {}

  observability_edge_env = var.observability_enabled ? merge(
    local.observability_common_env,
    { OBS_SERVICE_NAME = local.edge_name, OTEL_SERVICE_NAME = local.edge_name },
  ) : {}
}

# Publishing rights for the core worker role: exactly the actions the X-Ray (/v1/traces) and
# CloudWatch monitoring (/v1/metrics) OTLP endpoints authorize against. (PutMetricData has no
# resource-level scoping, so "*" is the only valid resource for it.)
resource "aws_iam_role_policy" "core_observability" {
  count = var.observability_enabled ? 1 : 0
  name  = "${local.core_name}-observability"
  role  = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "xray:PutTraceSegments",
        "xray:PutTelemetryRecords",
        "cloudwatch:PutMetricData",
      ]
      Resource = "*"
    }]
  })
}

# The same publishing rights for the edge's scoped IAM user (see edge.tf).
resource "aws_iam_user_policy" "edge_observability" {
  count = var.observability_enabled ? 1 : 0
  name  = "${local.edge_name}-observability"
  user  = aws_iam_user.edge.name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "xray:PutTraceSegments",
        "xray:PutTelemetryRecords",
        "cloudwatch:PutMetricData",
      ]
      Resource = "*"
    }]
  })
}

# Transaction Search (step 1 of the header prerequisite): X-Ray itself needs permission to
# write spans into the aws/spans CloudWatch log group. The console's "enable Transaction
# Search" flow creates this resource policy implicitly; here it is as code. PutResourcePolicy
# is an upsert, so it is safe to (re)apply. The destination toggle (step 2) has no TF resource.
resource "aws_cloudwatch_log_resource_policy" "xray_transaction_search" {
  count       = var.observability_enabled ? 1 : 0
  policy_name = "${var.name_prefix}-xray-transaction-search"

  policy_document = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "TransactionSearchXRayAccess"
      Effect    = "Allow"
      Principal = { Service = "xray.amazonaws.com" }
      Action    = ["logs:CreateLogStream", "logs:PutLogEvents"]
      Resource  = "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:aws/spans:*"
      Condition = {
        StringEquals = { "aws:SourceAccount" = data.aws_caller_identity.current.account_id }
        ArnLike      = { "aws:SourceArn" = "arn:aws:xray:${var.aws_region}:${data.aws_caller_identity.current.account_id}:*" }
      }
    }]
  })
}
