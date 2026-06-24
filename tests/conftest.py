"""Shared test setup.

Provide a minimal chat LLM config so ``ChatSettings`` (which requires one) is
constructible offline — the agent is exercised with ``TestModel``, so the id is
never dialed. ``setdefault`` leaves a real environment untouched.

Also install a process-wide in-memory OpenTelemetry tracer provider (OTel only allows
one ``set_tracer_provider`` per process), exposed via the ``span_exporter`` fixture, so
tracing tests can read the spans the platform/process code emits without a live collector.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

os.environ.setdefault("CHAT_LLM__KIND", "bedrock")
os.environ.setdefault("CHAT_LLM__MODEL", "test/model")

_SPAN_EXPORTER = InMemorySpanExporter()
_PROVIDER = TracerProvider()
_PROVIDER.add_span_processor(SimpleSpanProcessor(_SPAN_EXPORTER))
trace.set_tracer_provider(_PROVIDER)  # once per process; the global the platform tracers use


@pytest.fixture
def span_exporter() -> Iterator[InMemorySpanExporter]:
    """The shared in-memory span exporter, cleared around each test that reads spans."""
    _SPAN_EXPORTER.clear()
    yield _SPAN_EXPORTER
    _SPAN_EXPORTER.clear()
