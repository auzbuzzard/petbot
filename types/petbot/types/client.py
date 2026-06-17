"""The typed skill-client surface the edge programs against.

:class:`Skills` is a structural :class:`typing.Protocol` with one typed async
method per skill. The edge depends on *this* — never on a skill implementation —
so a call like ``await skills.derpi(BooruArgs(tags="…"), ctx)`` is fully checked
by ``mypy --strict`` across the package boundary, exactly like a TypeScript type
crossing packages. Implementations live in :mod:`petbot.platform.skills`
(``RemoteSkills`` over a transport; ``LocalSkills`` in-process). The skill-name
string and the wire envelope are encapsulated there and never surface here.
"""

from __future__ import annotations

from typing import Protocol

from petbot.domain import SkillContext, SkillResult
from petbot.types.args import BooruArgs, ChatArgs, MathArgs, MusicArgs


class Skills(Protocol):
    """Typed entrypoint to every skill, transport-agnostic."""

    async def math(self, args: MathArgs, ctx: SkillContext) -> SkillResult: ...

    async def derpi(self, args: BooruArgs, ctx: SkillContext) -> SkillResult: ...

    async def e621(self, args: BooruArgs, ctx: SkillContext) -> SkillResult: ...

    async def music(self, args: MusicArgs, ctx: SkillContext) -> SkillResult: ...

    async def chat(self, args: ChatArgs, ctx: SkillContext) -> SkillResult: ...
