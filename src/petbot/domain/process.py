"""The pipeline verb: ``input -> output``. The one thing a frontend drives.

A :class:`Process` turns a neutral :class:`~petbot.domain.input.Input` into a
:class:`~petbot.domain.result.SkillResult`. It is the DI'd centre of the pipeline:
the conversational impl runs an LLM agent over a :class:`~petbot.domain.input.TextInput`;
the command impl runs the resolved tool of a :class:`~petbot.domain.input.CommandInput`.
A frontend holds a ``Process`` (over a transport) and calls it — it never branches on
which impl is wired; selecting the impl is dependency injection, not an ``if``.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from petbot.domain.context import SkillContext
from petbot.domain.input import Input
from petbot.domain.result import SkillResult


@runtime_checkable
class Process(Protocol):
    """Turns a neutral :class:`~petbot.domain.input.Input` into a ``SkillResult``."""

    async def respond(self, inp: Input, ctx: SkillContext) -> SkillResult:
        """Process ``inp`` against the request ``ctx`` and return a neutral result."""
        ...
