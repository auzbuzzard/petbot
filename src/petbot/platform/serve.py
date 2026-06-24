"""The remote boundary: decode a dispatch payload, run a process, encode the result.

The mirror of the remote transports on the *server* side: a transport handler (an
HTTP route, a Lambda handler) hands the raw ``{"input": …, "context": …}`` body to
:func:`serve`, which decodes it into a typed :class:`~petbot.domain.input.Input` and
:class:`~petbot.domain.context.SkillContext`, runs the given
:class:`~petbot.domain.process.Process`, and encodes the
:class:`~petbot.domain.result.SkillResult` back. The JSON lives only here and in the
remote transports.

It is also the last-resort safety net: an *unexpected* exception that escaped the
process is caught here and returned as a generic result, so a malformed payload or a
crash always becomes an answer rather than a dropped request. (Expected failures are
voiced earlier, inside the process.)
"""

from __future__ import annotations

import json
import logging
from typing import Any

from opentelemetry import trace
from opentelemetry.propagate import extract
from opentelemetry.trace import Status, StatusCode
from pydantic import TypeAdapter, ValidationError

from petbot.domain import Input, Process, SkillContext, SkillResult

logger = logging.getLogger(__name__)

# The server end of the distributed trace: extract the edge's context and run the process
# under a "serve" span, so the agent/tool spans re-parent into the one edge->core trace.
_tracer = trace.get_tracer("petbot.platform.serve")

#: Validates the wire ``input`` into the right `Input` member by its ``kind`` tag.
_INPUT: TypeAdapter[Input] = TypeAdapter(Input)

_MALFORMED = "That request was malformed."
_CRASHED = "Something went wrong handling that request."


async def serve(process: Process, body: str | bytes) -> str:
    """Decode ``body``, run it through ``process``, and encode the result as JSON."""
    try:
        raw: dict[str, Any] = json.loads(body)
        inp = _INPUT.validate_python(raw["input"])
        ctx = SkillContext.model_validate(raw["context"])
    except (ValueError, KeyError, ValidationError):
        logger.warning("Malformed dispatch payload", exc_info=True)
        return SkillResult(text=_MALFORMED).model_dump_json()
    with _tracer.start_as_current_span("serve", context=extract(raw.get("trace") or {})) as span:
        span.set_attribute("petbot.platform", ctx.platform.value)
        span.set_attribute("petbot.conversation_id", ctx.conversation_id)
        try:
            result = await process.respond(inp, ctx)
        except Exception as exc:
            logger.exception("Process raised")
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR))
            result = SkillResult(text=_CRASHED)
        return result.model_dump_json()
