# --- Agent observability (OpenTelemetry) — OFF by default ---------------------
#
# Gated entirely by var.observability_enabled. When off (the default) this file adds
# no env, IAM, or data sources, so applying it changes nothing for an existing deploy.
# When on, each deployable exports OTLP to the collector at var.otel_otlp_endpoint,
# which forwards to AWS X-Ray (traces) + CloudWatch EMF (metrics). The app reads the
# standard OTEL_* env plus OBS_* (see petbot.observability.ObservabilitySettings).
#
# Collector placement (the one piece that needs a real plan/apply to validate):
#   * Edge (Lightsail container service, always-on): add an `aws-otel-collector`
#     sidecar container to the deployment in edge.tf and point the edge's
#     OTEL_EXPORTER_OTLP_ENDPOINT at http://localhost:4318.
#   * Core worker: it is a *container-image* arm64 Lambda, so the ADOT *Lambda layer*
#     (a zip-only extension) does NOT apply. Either bake the ADOT collector extension
#     into the worker image (then endpoint = http://localhost:4318) or point the
#     endpoint at a reachable shared collector. Plumbing (env + IAM) is here; the
#     collector image/extension wiring is the remaining deploy step.

variable "observability_enabled" {
  type        = bool
  description = "Emit OpenTelemetry telemetry (traces/metrics) over OTLP. Off by default."
  default     = false
}

variable "otel_otlp_endpoint" {
  type        = string
  description = "OTLP HTTP endpoint of the collector the app exports to (e.g. http://localhost:4318)."
  default     = ""
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
  # Shared OTLP/OBS env for any deployable; service_name is set per process below.
  observability_common_env = var.observability_enabled ? merge(
    {
      OBS_ENABLED                 = "true"
      OBS_SAMPLE_RATIO            = tostring(var.observability_sample_ratio)
      OTEL_EXPORTER_OTLP_ENDPOINT = var.otel_otlp_endpoint
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

# X-Ray + CloudWatch publishing for the core worker role. (PutMetricData has no
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
