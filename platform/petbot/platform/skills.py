"""The typed ``Skills`` client implementations.

Both satisfy the :class:`petbot.types.Skills` protocol, so the edge programs
against the typed surface and swaps the wiring by configuration:

* :class:`RemoteSkills` — the edge's client. Each method is ~one line: it builds
  a :class:`~petbot.domain.call.SkillCall` (serialising the typed args) and hands
  it to a :class:`~petbot.domain.call.Transport`. The skill-name string lives
  *here only* — irreducible at the wire, never exposed to callers.
* :class:`LocalSkills` — an in-process client over a :class:`Worker`, used by the
  chat agent to call sibling skills in the same worker with no wire hop.

The methods are written out (not decorator-generated) so ``mypy --strict`` sees
every signature and checks every call site.
"""

from __future__ import annotations

from pydantic import BaseModel

from petbot.domain import SkillCall, SkillContext, SkillResult, Transport
from petbot.platform.worker import Worker
from petbot.types import BooruArgs, ChatArgs, MathArgs, MusicArgs


class RemoteSkills:
    """Typed client that dispatches each call over a :class:`Transport`."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    async def _call(self, name: str, args: BaseModel, ctx: SkillContext) -> SkillResult:
        call = SkillCall(skill=name, args_json=args.model_dump_json(), context=ctx)
        return await self._transport.send(call)

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


class LocalSkills:
    """Typed client that runs each call in-process against a :class:`Worker`."""

    def __init__(self, worker: Worker) -> None:
        self._worker = worker

    async def math(self, args: MathArgs, ctx: SkillContext) -> SkillResult:
        return await self._worker.run_skill("math", args, ctx)

    async def derpi(self, args: BooruArgs, ctx: SkillContext) -> SkillResult:
        return await self._worker.run_skill("derpi", args, ctx)

    async def e621(self, args: BooruArgs, ctx: SkillContext) -> SkillResult:
        return await self._worker.run_skill("e621", args, ctx)

    async def music(self, args: MusicArgs, ctx: SkillContext) -> SkillResult:
        return await self._worker.run_skill("music", args, ctx)

    async def chat(self, args: ChatArgs, ctx: SkillContext) -> SkillResult:
        return await self._worker.run_skill("chat", args, ctx)
