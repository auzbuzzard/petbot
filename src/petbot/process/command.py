"""The command process: run a resolved command, then voice it.

A slash command arrives as a :class:`~petbot.domain.input.CommandInput` (the tool name
and raw argument values — already chosen by the user, nothing to interpret). This
validates+runs it through the :class:`~petbot.platform.registry.ToolRegistry` and applies
the injected output :class:`~petbot.domain.ports.StylePort`. An expected
:class:`~petbot.domain.errors.SkillError` (empty search, bad input) is caught here, at the
output boundary, and voiced as the answer — so a failure sounds like PetBot, not a stack
trace. Unexpected exceptions propagate to :func:`~petbot.platform.serve.serve`.
"""

from __future__ import annotations

from petbot.domain import (
    CommandInput,
    Input,
    Process,
    SkillContext,
    SkillError,
    SkillResult,
    StylePort,
)
from petbot.platform import ToolRegistry


class CommandProcess(Process):
    """Dispatch a resolved command to its tool and voice the result."""

    def __init__(self, registry: ToolRegistry, style: StylePort) -> None:
        self._registry = registry
        self._style = style

    async def respond(self, inp: Input, ctx: SkillContext) -> SkillResult:
        if not isinstance(inp, CommandInput):
            # The router only sends resolved commands here; guard for type-safety.
            raise TypeError(f"CommandProcess received {type(inp).__name__}")
        try:
            result = await self._registry.dispatch(inp.name, inp.values, ctx)
        except SkillError as exc:
            result = SkillResult.message(exc.message)
        return await self._style.stylize(result, ctx)
