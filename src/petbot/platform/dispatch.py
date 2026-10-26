"""The dispatch envelope and the transport port.

A :class:`Dispatch` is the unit of work a frontend sends to a compute process: a
neutral :class:`~petbot.domain.input.Input` (a free-text message or a resolved
command) plus the request :class:`~petbot.domain.context.SkillContext`. The
**process** that runs is chosen by the *type* of the input, not named here — so the
envelope is just ``input`` + ``context``.

A :class:`Transport` moves a :class:`Dispatch` to the process that handles it. A
remote transport (HTTP, Lambda) serialises it; the in-process case needs no transport
at all (a process is called directly). Serialisation belongs to the transport, never
to the envelope.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from petbot.domain import Input, SkillContext, SkillResult


@dataclass(frozen=True, slots=True)
class Dispatch:
    input: Input
    context: SkillContext


class Transport(Protocol):
    async def send(self, dispatch: Dispatch) -> SkillResult: ...
