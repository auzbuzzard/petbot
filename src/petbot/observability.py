"""OpenTelemetry setup — configured once, at each entrypoint, like ``configure_logging``.

Library code instruments with the OpenTelemetry **API** (a no-op until a provider is
installed); ``configure_observability`` wires the **SDK** in one place, exporting OTLP
collector-less to AWS's endpoints — traces to the X-Ray OTLP endpoint, metrics to the
CloudWatch (monitoring) OTLP endpoint, each POST SigV4-signed from the runtime's own
credentials (:func:`_aws_sigv4_session`). A non-AWS ``OTEL_*`` endpoint (a dev collector) is
left unsigned. ``flush_observability`` force-flushes (the Lambda freezes between invocations);
the agent's ``InstrumentationSettings`` is built in the core composition root.

Traces require CloudWatch Transaction Search, or the X-Ray OTLP endpoint rejects spans; see
``docs/adr/0011-agent-observability.md``.

Telemetry is metadata-only: bodies, tags, and replies are never recorded; the one user
identifier is a salted hash (:func:`hash_user_id`). :class:`AwsXRayIdGenerator` keeps trace ids
X-Ray-valid across the W3C-tracecontext edge->core hop. The endpoints come from the standard
``OTEL_*`` env, and the SDK imports are lazy, so a process without the ``observability`` extra
(or with telemetry off) never pays for them.
"""

from __future__ import annotations

import hashlib
import logging
import os
from typing import Any
from urllib.parse import urlparse

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

__all__ = [
    "ObservabilitySettings",
    "configure_observability",
    "flush_observability",
    "hash_user_id",
]


class ObservabilitySettings(BaseSettings):
    """Whether and how to emit telemetry (``OBS_*``); the OTLP endpoints themselves are the
    SDK's standard ``OTEL_*`` env, so they are not duplicated here.

    Off by default: a process emits nothing until ``OBS_ENABLED=true``, so dev and tests
    stay zero-config and the privacy posture is opt-in for an operator.
    """

    model_config = SettingsConfigDict(
        env_prefix="obs_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    #: Master switch. Off ⇒ :func:`configure_observability` is a no-op and the API stays no-op.
    enabled: bool = False
    #: ``service.name`` on every span/metric (the X-Ray service node).
    service_name: str = "petbot"
    #: Head sampling ratio for root traces (1.0 = all); children follow the parent.
    sample_ratio: float = 1.0
    #: Salt for :func:`hash_user_id`. Keep it secret + stable (SSM); empty ⇒ unsalted (dev).
    id_salt: str = ""


def _aws_sigv4_session(service: str, region: str) -> Any:
    """A ``requests`` session that SigV4-signs every OTLP POST, so the OTel SDK can export
    directly to an AWS ``*.amazonaws.com`` OTLP endpoint with no collector in between.

    The signature is computed from the runtime's ambient AWS credentials (the Lambda role or
    the edge's IAM-user key) over the request's exact body, so it works for both the
    uncompressed-protobuf default and a gzipped payload. Imported lazily: only the enabled,
    AWS-endpoint path pulls ``requests``/``botocore`` in.
    """
    import requests
    from botocore.auth import SigV4Auth
    from botocore.awsrequest import AWSRequest
    from botocore.session import Session

    credentials = Session().get_credentials()

    class _SigV4Session(requests.Session):
        def send(self, request: Any, **kwargs: Any) -> Any:
            body = request.body or b""
            if isinstance(body, str):
                body = body.encode()
            signed = AWSRequest(method=request.method, url=request.url, data=body)
            signed.headers["Content-Type"] = request.headers.get(
                "Content-Type", "application/x-protobuf"
            )
            encoding = request.headers.get("Content-Encoding")
            if encoding:
                signed.headers["Content-Encoding"] = encoding
            SigV4Auth(credentials, service, region).add_auth(signed)
            request.headers.update(signed.headers)
            return super().send(request, **kwargs)

    return _SigV4Session()


def _otlp_aws_kwargs(signal: str) -> dict[str, Any]:
    """Exporter kwargs for one signal (``TRACES``/``METRICS``): when its ``OTEL_*`` endpoint is
    an AWS OTLP endpoint, sign it (deriving the service + Region from the host, e.g.
    ``xray.us-east-1.amazonaws.com`` ⇒ service ``xray``); otherwise return nothing and let the
    exporter use its plain default (a non-AWS collector in dev)."""
    endpoint = os.environ.get(f"OTEL_EXPORTER_OTLP_{signal}_ENDPOINT")
    host = urlparse(endpoint).hostname or "" if endpoint else ""
    if host.endswith(".amazonaws.com"):
        service, region, *_ = host.split(".")
        return {"endpoint": endpoint, "session": _aws_sigv4_session(service, region)}
    return {}


def configure_observability(settings: ObservabilitySettings) -> bool:
    """Install global tracer + meter providers exporting over OTLP to AWS's collector-less
    endpoints. Idempotent-enough for a single entrypoint call; returns whether telemetry was
    actually enabled.

    The SDK is imported lazily so this is import-safe without the ``observability`` extra.
    The model/agent ``InstrumentationSettings`` is built by the caller (the core service)
    from these now-global providers — kept out of here so the edge needn't import
    pydantic-ai.
    """
    if not settings.enabled:
        logger.debug("observability disabled (OBS_ENABLED unset); telemetry is a no-op")
        return False

    from opentelemetry import metrics, trace
    from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.extension.aws.trace import AwsXRayIdGenerator
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased

    resource = Resource.create({"service.name": settings.service_name})

    tracer_provider = TracerProvider(
        resource=resource,
        id_generator=AwsXRayIdGenerator(),  # X-Ray-valid trace ids; W3C propagation carries them
        sampler=ParentBased(TraceIdRatioBased(settings.sample_ratio)),
    )
    span_exporter = OTLPSpanExporter(**_otlp_aws_kwargs("TRACES"))
    tracer_provider.add_span_processor(BatchSpanProcessor(span_exporter))
    trace.set_tracer_provider(tracer_provider)

    metric_exporter = OTLPMetricExporter(**_otlp_aws_kwargs("METRICS"))
    meter_provider = MeterProvider(
        resource=resource,
        metric_readers=[PeriodicExportingMetricReader(metric_exporter)],
    )
    metrics.set_meter_provider(meter_provider)

    logger.info(
        "observability enabled (service=%s, sample=%.2f)",
        settings.service_name,
        settings.sample_ratio,
    )
    return True


def flush_observability() -> None:
    """Force-flush spans + metrics. Call in a ``finally`` per Lambda invocation: the
    :class:`BatchSpanProcessor` would otherwise lose un-exported spans when the runtime
    freezes. A no-op when no SDK provider is installed."""
    from opentelemetry import metrics, trace

    for provider in (trace.get_tracer_provider(), metrics.get_meter_provider()):
        flush = getattr(provider, "force_flush", None)
        if callable(flush):
            flush()


def hash_user_id(raw: str, salt: str) -> str:
    """A short, salted, one-way hash of a user id — the only identifier we attach to
    telemetry. Pseudonymous (correlate one user's turns) without storing the raw id."""
    return hashlib.sha256(f"{salt}:{raw}".encode()).hexdigest()[:16]
