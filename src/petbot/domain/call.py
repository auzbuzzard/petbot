"""The dispatch envelope and the transport port.

A :class:`SkillCall` is an in-memory value: the target skill's name, its
arguments as a live typed model, and the neutral
:class:`~petbot.domain.context.SkillContext`. It is deliberately *not* a wire
format — it never pre-serialises its args. Serialisation belongs to whichever
:class:`Transport` actually crosses a process boundary (HTTP, Lambda); an
in-process transport passes the typed args straight through with no JSON.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel

from petbot.domain.context import SkillContext
from petbot.domain.result import SkillResult


@dataclass(frozen=True, slots=True)
class SkillCall:
    """A unit of work handed to a worker. ``args`` is a live, typed model."""

    skill: str
    args: BaseModel
    context: SkillContext


class Transport(Protocol):
    """Moves a :class:`SkillCall` to the worker that hosts the skill and returns its result.

    The only verb. Implementations own their wire encoding (if any): a local
    transport runs the call in-process; a remote transport serialises it.
    """

    async def send(self, call: SkillCall) -> SkillResult:
        """Dispatch ``call`` and return the worker's :class:`SkillResult`."""
        ...
