# --- Agent observability (OpenTelemetry) — OFF by default ---------------------
#
# Gated entirely by var.observability_enabled. When off (the default) this file adds no env,
# IAM, or data sources, so applying it changes nothing for an existing deploy. When on, each
# deployable exports OTLP *directly to AWS's collector-less endpoints* — traces to the X-Ray
# OTLP endpoint, metrics to the CloudWatch (monitoring) OTLP endpoint — each POST SigV4-signed
# by the runtime's own credentials (see petbot.observability). No collector runs anywhere — the
# worker image bakes in no extension and the edge has no sidecar. The app reads the standard
# OTEL_* env plus OBS_* (see petbot.observability.ObservabilitySettings).

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
  description = "SSM SecureString name holding the salt for the telemetry user-id hash (read at start through SSM_SECRETS; see secrets.tf). Empty => unsalted."
  default     = ""
}

locals {
  # AWS's collector-less OTLP endpoints (SigV4). The app derives the signing service + Region
  # from each host (xray | monitoring.<region>.amazonaws.com), so the Region lives only here.
  otlp_traces_endpoint  = "https://xray.${var.aws_region}.amazonaws.com/v1/traces"
  otlp_metrics_endpoint = "https://monitoring.${var.aws_region}.amazonaws.com/v1/metrics"

  observability_common_env = var.observability_enabled ? {
    OBS_ENABLED                         = "true"
    OBS_SAMPLE_RATIO                    = tostring(var.observability_sample_ratio)
    OTEL_EXPORTER_OTLP_TRACES_ENDPOINT  = local.otlp_traces_endpoint
    OTEL_EXPORTER_OTLP_METRICS_ENDPOINT = local.otlp_metrics_endpoint
  } : {}

  observability_core_env = var.observability_enabled ? merge(
    local.observability_common_env,
    { OBS_SERVICE_NAME = local.core_name, OTEL_SERVICE_NAME = local.core_name },
  ) : {}

  observability_edge_env = var.observability_enabled ? merge(
    local.observability_common_env,
    { OBS_SERVICE_NAME = local.edge_name, OTEL_SERVICE_NAME = local.edge_name },
  ) : {}
}

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

resource "aws_iam_user_policy" "edge_observability" {
  count = var.observability_enabled && var.edge_enabled ? 1 : 0
  name  = "${local.edge_name}-observability"
  user  = aws_iam_user.edge[0].name

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
