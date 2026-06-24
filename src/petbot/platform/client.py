"""The process client: the frontend's handle to a (possibly remote) process.

A frontend doesn't run a :class:`~petbot.domain.process.Process` itself — it holds a
:class:`ProcessClient` over a :class:`~petbot.platform.dispatch.Transport` and calls
:meth:`respond`. ``ProcessClient`` *is* a ``Process`` (same ``respond`` shape), so the
frontend programs against the neutral verb whether the real process is in this image
or behind HTTP/Lambda — the difference is the injected transport.
"""

from __future__ import annotations

from opentelemetry import trace

from petbot.domain import Input, Process, SkillContext, SkillResult
from petbot.platform.dispatch import Dispatch, Transport

# The client end of the distributed trace: this span is the root the compute side parents
# its server + agent spans under, so one Discord turn is a single trace edge->core. A no-op
# until a process installs an OTel SDK (petbot.observability.configure_observability).
_tracer = trace.get_tracer("petbot.platform.client")


class ProcessClient(Process):
    """Dispatches a neutral input to a process over a :class:`Transport`."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    async def respond(self, inp: Input, ctx: SkillContext) -> SkillResult:
        with _tracer.start_as_current_span("dispatch") as span:
            span.set_attribute("petbot.platform", ctx.platform.value)
            span.set_attribute("petbot.conversation_id", ctx.conversation_id)
            span.set_attribute("petbot.input_kind", type(inp).__name__)
            return await self._transport.send(Dispatch(input=inp, context=ctx))
