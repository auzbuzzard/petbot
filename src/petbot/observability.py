"""OpenTelemetry setup — configured once, at each entrypoint, like ``configure_logging``.

PetBot instruments with the OpenTelemetry **API** everywhere (it is a no-op until a
provider is installed), and wires the **SDK** here, in one place, called by each process
entrypoint after :func:`~petbot.logging_setup.configure_logging`. The model/agent spans
come free from pydantic-ai's own instrumentation (see
:mod:`petbot.services.core`); this module owns the provider/exporter plumbing and the two
tiny helpers the rest of the code needs.

Telemetry is **metadata-only**: pydantic-ai is told ``include_content=False`` (built in the
core composition root, not here — the edge has no pydantic-ai), so message bodies, tags, and
replies are never recorded. The single user identifier we attach is a salted hash
(:func:`hash_user_id`), never the raw id or a display name. See
``docs/adr/0011-agent-observability.md``.

Export is **AWS-native**: spans/metrics go out over OTLP to a co-located ADOT collector,
which fans them to X-Ray + CloudWatch EMF. Trace context crosses the edge->core
:class:`~petbot.platform.dispatch.Dispatch` wire as plain **W3C tracecontext** (the default
global propagator); :class:`AwsXRayIdGenerator` makes the trace ids X-Ray-valid, so no
AWS-specific propagator is needed (we never cross an ``X-Amzn-Trace-Id`` hop). Endpoint and
headers come from the standard ``OTEL_*`` environment, read by the SDK.

Nothing here reads the environment except :class:`ObservabilitySettings`; the SDK imports
are lazy so a process without the ``observability`` extra (or with telemetry disabled) never
pays for them.
"""

from __future__ import annotations

import hashlib
import logging

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

__all__ = [
    "ObservabilitySettings",
    "configure_observability",
    "flush_observability",
    "hash_user_id",
]


class ObservabilitySettings(BaseSettings):
    """Whether and how to emit telemetry (``OBS_*``); the OTLP endpoint itself is the
    SDK's standard ``OTEL_*`` env, so it is not duplicated here.

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


def configure_observability(settings: ObservabilitySettings) -> bool:
    """Install global tracer + meter providers exporting over OTLP. Idempotent-enough for
    a single entrypoint call; returns whether telemetry was actually enabled.

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
    tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(tracer_provider)

    meter_provider = MeterProvider(
        resource=resource,
        metric_readers=[PeriodicExportingMetricReader(OTLPMetricExporter())],
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
