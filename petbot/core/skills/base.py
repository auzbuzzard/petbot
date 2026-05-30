"""The :class:`Skill` contract.

An ABC (not a Protocol) because skills share real behavior and metadata: a
name, a description, a JSON-Schema description of their arguments (used to wire
slash-command options today and LLM tool calls in Phase B), and an optional set
of required ports.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any, ClassVar

from petbot.core.skills.context import SkillContext, SkillResult


class Skill(ABC):
    """A neutral unit of behavior.

    Subclasses declare their identity/metadata as class variables and implement
    :meth:`run`. They must be pure with respect to the platform: read from
    ``ctx`` and ``args``, return a :class:`SkillResult`, and never import or
    touch ``discord``.
    """

    #: Stable identifier; also the slash-command name on Discord.
    name: ClassVar[str]
    #: Human/LLM-facing one-liner describing what the skill does.
    description: ClassVar[str]
    #: JSON Schema for ``args`` — the single source of truth for arguments.
    input_schema: ClassVar[Mapping[str, Any]]
    #: Ports the skill needs (e.g. ``{"voice"}``); the registry hides the skill
    #: on frontends that cannot supply them.
    requires: ClassVar[frozenset[str]] = frozenset()

    @abstractmethod
    async def run(self, args: Mapping[str, Any], ctx: SkillContext) -> SkillResult:
        """Execute the skill and return a neutral result."""
        ...
