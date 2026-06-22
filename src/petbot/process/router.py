"""The router: the one place that picks a process by the input type.

This is the single exhaustive ``match`` the architecture keeps — compiler-checked
dispatch on the closed :class:`~petbot.domain.input.Input` sum type (a new variant fails
type-checking until handled). Everything else is dependency injection, not branching.
A conversational :class:`~petbot.domain.input.TextInput` goes to the chat process; a
resolved :class:`~petbot.domain.input.CommandInput` to the command process. A compute
service that hosts no conversational process (the voice service) wires ``chat=None``.
"""

from __future__ import annotations

from typing import assert_never

from petbot.domain import CommandInput, Input, Process, SkillContext, SkillResult, TextInput


class RouterProcess(Process):
    """Routes a neutral input to the process that handles its kind."""

    def __init__(self, *, chat: Process | None, command: Process) -> None:
        self._chat = chat
        self._command = command

    async def respond(self, inp: Input, ctx: SkillContext) -> SkillResult:
        match inp:
            case TextInput():
                if self._chat is None:
                    raise TypeError("this service has no conversational process")
                return await self._chat.respond(inp, ctx)
            case CommandInput():
                return await self._command.respond(inp, ctx)
            case _:
                assert_never(inp)
