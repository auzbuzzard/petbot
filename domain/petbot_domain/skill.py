"""The :class:`Skill` contract — the port a skill implementation satisfies."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any

from petbot_domain.capability import Capability
from petbot_domain.context import SkillContext
from petbot_domain.result import SkillResult


class Skill(ABC):
    """A neutral unit of behaviour.

    Subclasses declare their identity/metadata and implement :meth:`run`. The
    metadata are plain attributes (not ``ClassVar``): hand-written skills assign
    them at class scope, while proxy skills (a dispatching ``RemoteSkill``) set
    them per instance from a :class:`~petbot_domain.spec.SkillSpec`.
    """

    #: Stable identifier; also the slash-command name on Discord.
    name: str
    #: Human/LLM-facing one-liner describing what the skill does.
    description: str
    #: JSON Schema for ``args`` — the single source of truth for arguments.
    input_schema: Mapping[str, Any]
    #: Hard capabilities the skill needs; it is hidden on frontends lacking them.
    requires: frozenset[Capability] = frozenset()

    @abstractmethod
    async def run(self, args: Mapping[str, Any], ctx: SkillContext) -> SkillResult:
        """Execute the skill and return a neutral result."""
        ...
