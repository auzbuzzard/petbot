"""The typed ``Skills`` client.

One client over any :class:`~petbot.domain.call.Transport`, so the same code
serves both the edge (a remote transport) and the chat agent calling siblings
in-process (a local transport) — the difference is the injected transport, not
the client. It explicitly subclasses :class:`petbot.types.Skills` so mypy verifies
conformance at the definition. Each method is one line; the skill-name string and
the :class:`SkillCall` envelope live here only and never surface to callers.
"""

from __future__ import annotations

from pydantic import BaseModel

from petbot.domain import SkillCall, SkillContext, SkillResult, Transport
from petbot.types import BooruArgs, ChatArgs, MathArgs, MusicArgs, Skills


class SkillsClient(Skills):
    """Typed client that dispatches each call over a :class:`Transport`."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    async def _call(self, name: str, args: BaseModel, ctx: SkillContext) -> SkillResult:
        return await self._transport.send(SkillCall(skill=name, args=args, context=ctx))

    async def math(self, args: MathArgs, ctx: SkillContext) -> SkillResult:
        return await self._call("math", args, ctx)

    async def derpi(self, args: BooruArgs, ctx: SkillContext) -> SkillResult:
        return await self._call("derpi", args, ctx)

    async def e621(self, args: BooruArgs, ctx: SkillContext) -> SkillResult:
        return await self._call("e621", args, ctx)

    async def music(self, args: MusicArgs, ctx: SkillContext) -> SkillResult:
        return await self._call("music", args, ctx)

    async def chat(self, args: ChatArgs, ctx: SkillContext) -> SkillResult:
        return await self._call("chat", args, ctx)
