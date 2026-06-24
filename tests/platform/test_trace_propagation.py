"""Distributed tracing across the dispatch wire: the client injects its context into the
``Dispatch`` payload, and ``serve`` extracts it so the compute side's spans re-parent into
one edge->core trace. All via the OTel API, so it is a no-op when no SDK is configured.

The spans are read from the process-wide ``span_exporter`` (see ``tests/conftest.py``), the
same global provider the platform tracers resolve to.
"""

from __future__ import annotations

import json

from opentelemetry import trace
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from petbot.domain import Input, Platform, Process, SkillContext, SkillResult, TextInput, User
from petbot.platform import serve
from petbot.platform.dispatch import Dispatch
from petbot.platform.transport import _wire


def _ctx() -> SkillContext:
    return SkillContext(
        platform=Platform.DISCORD,
        user=User(platform=Platform.DISCORD, id="42", display_name="t"),
        conversation_id="discord:1",
    )


class _Echo(Process):
    async def respond(self, inp: Input, ctx: SkillContext) -> SkillResult:
        return SkillResult.message("ok")


def test_wire_always_carries_a_trace_key() -> None:
    wire = _wire(Dispatch(input=TextInput(text="hi"), context=_ctx()))
    assert "trace" in wire and isinstance(wire["trace"], dict)


def test_wire_injects_the_active_span_context() -> None:
    with trace.get_tracer("client").start_as_current_span("dispatch"):
        wire = _wire(Dispatch(input=TextInput(text="hi"), context=_ctx()))
    assert "traceparent" in wire["trace"]


async def test_serve_reparents_into_the_client_trace(span_exporter: InMemorySpanExporter) -> None:
    with trace.get_tracer("client").start_as_current_span("dispatch") as client_span:
        body = json.dumps(_wire(Dispatch(input=TextInput(text="hi"), context=_ctx())))
        client_trace_id = client_span.get_span_context().trace_id
        client_span_id = client_span.get_span_context().span_id

    await serve(_Echo(), body)

    serve_spans = [s for s in span_exporter.get_finished_spans() if s.name == "serve"]
    assert serve_spans, "serve span not recorded"
    assert serve_spans[0].context.trace_id == client_trace_id  # one trace edge->core
    assert serve_spans[0].parent is not None
    assert serve_spans[0].parent.span_id == client_span_id  # child of the client span
