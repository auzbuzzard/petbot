from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel

from petbot.domain.capability import Capability
from petbot.domain.context import SkillContext
from petbot.domain.result import SkillResult


class Skill[ArgsT: BaseModel](ABC):
    """A neutral unit of behaviour, typed by its argument model.

    Subclasses declare their identity/metadata and implement :meth:`run`. The
    metadata are plain attributes (not ``ClassVar``) so a skill can be built with
    per-instance dependencies (an injected ``httpx`` client, a voice provider).
    """

    #: Stable identifier; also the wire key and the Discord slash-command name.
    name: str
    description: str
    args_model: type[ArgsT]
    requires: frozenset[Capability] = frozenset()

    @abstractmethod
    async def run(self, args: ArgsT, ctx: SkillContext) -> SkillResult: ...
