# --- Agent observability (OpenTelemetry) — OFF by default ---------------------
#
# Gated entirely by var.observability_enabled. When off (the default) this file adds
# no env, IAM, or data sources, so applying it changes nothing for an existing deploy.
# When on, each deployable exports OTLP to the collector at var.otel_otlp_endpoint,
# which forwards to AWS X-Ray (traces) + CloudWatch EMF (metrics). The app reads the
# standard OTEL_* env plus OBS_* (see petbot.observability.ObservabilitySettings).
#
# Collector placement:
#   * Edge (Lightsail container service, always-on): an `aws-otel-collector` sidecar
#     container is added to the deployment in edge.tf (gated on observability_enabled)
#     and the edge exports to it at http://localhost:4318. Its config is
#     local.collector_config_yaml, passed inline via the collector's AOT_CONFIG_CONTENT.
#   * Core worker: a *container-image* arm64 Lambda, so the ADOT *Lambda layer* (zip-only)
#     does NOT apply — the collector is baked into the worker image as an internal extension
#     (Dockerfile.lambda, OTEL_VARIANT=otel, which CI sets when this var is on). The env
#     (OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318 + OPENTELEMETRY_COLLECTOR_CONFIG_URI
#     pointing at the baked config) and IAM are wired here.
#
# Note (always-on, collector-independent): the per-turn run-outcome record ChatProcess
# emits (tools called, tokens, finish reason) is a plain structured *log*, captured by
# CloudWatch Logs straight off the Lambda's stdout regardless of this collector or
# OBS_ENABLED. The collector here is only for X-Ray traces + CloudWatch EMF metrics.

variable "observability_enabled" {
  type        = bool
  description = "Emit OpenTelemetry telemetry (traces/metrics) over OTLP. Off by default."
  default     = false
}

variable "otel_otlp_endpoint" {
  type        = string
  description = "OTLP HTTP endpoint of the collector the app exports to. Defaults to the local sidecar/extension collector both deployables now run."
  default     = "http://localhost:4318"
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
  # The ADOT collector pipeline, one source of truth in deploy/collector-config.yaml. The
  # edge sidecar takes it inline (AOT_CONFIG_CONTENT); the core worker bakes the same file
  # into its image. Region-less — the exporters read AWS_REGION from the env.
  collector_config_yaml = file("${path.module}/../collector-config.yaml")

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
    {
      OBS_SERVICE_NAME  = local.core_name
      OTEL_SERVICE_NAME = local.core_name
      # Where the baked-in collector extension reads its config (Dockerfile.lambda writes
      # deploy/collector-config.yaml here when built with OTEL_VARIANT=otel).
      OPENTELEMETRY_COLLECTOR_CONFIG_URI = "/var/task/collector-config.yaml"
    },
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
