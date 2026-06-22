"""The process client: the frontend's handle to a (possibly remote) process.

A frontend doesn't run a :class:`~petbot.domain.process.Process` itself — it holds a
:class:`ProcessClient` over a :class:`~petbot.platform.dispatch.Transport` and calls
:meth:`respond`. ``ProcessClient`` *is* a ``Process`` (same ``respond`` shape), so the
frontend programs against the neutral verb whether the real process is in this image
or behind HTTP/Lambda — the difference is the injected transport.
"""

from __future__ import annotations

from petbot.domain import Input, Process, SkillContext, SkillResult
from petbot.platform.dispatch import Dispatch, Transport


class ProcessClient(Process):
    """Dispatches a neutral input to a process over a :class:`Transport`."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    async def respond(self, inp: Input, ctx: SkillContext) -> SkillResult:
        return await self._transport.send(Dispatch(input=inp, context=ctx))
