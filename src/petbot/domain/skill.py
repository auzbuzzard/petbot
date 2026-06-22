"""The :class:`Skill` contract — the port a skill implementation satisfies.

Generic over a pydantic ``args`` model: the model *is* the single source of truth
for the skill's arguments. It drives the typed client method
(:mod:`petbot.types`), the service's re-hydration + validation of a wire payload,
and — for the chat agent — the LLM tool schema (``args_model.model_json_schema``).
One declaration, three consumers, all type-checked.
"""

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
    #: Human/LLM-facing one-liner describing what the skill does.
    description: str
    #: The pydantic model for this skill's arguments — the source of truth.
    args_model: type[ArgsT]
    #: Hard capabilities the skill needs; only a providing service hosts it.
    requires: frozenset[Capability] = frozenset()

    @abstractmethod
    async def run(self, args: ArgsT, ctx: SkillContext) -> SkillResult:
        """Execute the skill against typed ``args`` and return a neutral result."""
        ...
