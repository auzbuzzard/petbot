"""The tool registry: discover installed skills and run one against typed args.

A :class:`ToolRegistry` is the catalogue of tools a compute process can call —
the booru/math skills discovered from the ``petbot.skills`` entry points, plus any
built with dependencies discovery can't supply (the music skill, with its voice
provider). Both processes reach a tool the same way: :meth:`dispatch` validates raw
argument values against the named skill's ``args_model`` and runs it. A bad name or
bad arguments **raise** (a :class:`~petbot.domain.errors.SkillError`); the skill's own
expected failures raise too. The process output boundary catches and voices them.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Iterator, Mapping
from importlib.metadata import entry_points
from typing import Any

from pydantic import ValidationError

from petbot.domain import InvalidInput, Skill, SkillContext, SkillError, SkillResult

logger = logging.getLogger(__name__)

#: The entry-point group every skill package registers under.
SKILLS_GROUP = "petbot.skills"


def _discover(group: str = SKILLS_GROUP) -> Iterator[Skill[Any]]:
    for ep in entry_points(group=group):
        target = ep.load()
        # An entry point is a Skill subclass, a build factory, or a ready instance.
        # The first two are callable; an instance is used as-is.
        skill = target() if callable(target) else target
        if not isinstance(skill, Skill):
            raise TypeError(f"Entry point {ep.name!r} is not a Skill: {skill!r}")
        yield skill


class ToolRegistry:
    """The tools a compute process can call, keyed by name."""

    def __init__(self, skills: Iterable[Skill[Any]]) -> None:
        self._skills: dict[str, Skill[Any]] = {}
        for skill in skills:
            self._add(skill)

    def _add(self, skill: Skill[Any]) -> None:
        if skill.name in self._skills:
            raise ValueError(f"Duplicate skill name: {skill.name!r}")
        self._skills[skill.name] = skill

    @classmethod
    def from_installed_skills(cls) -> ToolRegistry:
        """Build a registry from the ``petbot.skills`` plugins installed here."""
        return cls(_discover())

    def register(self, skill: Skill[Any]) -> None:
        """Add a skill built with dependencies discovery can't supply (e.g. music)."""
        self._add(skill)

    @property
    def names(self) -> frozenset[str]:
        """The names of every tool this registry holds."""
        return frozenset(self._skills)

    async def dispatch(
        self, name: str, values: Mapping[str, object], ctx: SkillContext
    ) -> SkillResult:
        """Validate ``values`` against the named tool's ``args_model`` and run it.

        Raises :class:`~petbot.domain.errors.SkillError` for an unknown tool or invalid
        arguments; the tool itself may raise its own expected failures.
        """
        skill = self._skills.get(name)
        if skill is None:
            logger.warning("Dispatch for unknown tool: %r", name)
            raise SkillError(f"I don't know how to do {name!r}.")
        try:
            args = skill.args_model.model_validate(dict(values))
        except ValidationError as exc:
            raise InvalidInput("Those arguments weren't valid.") from exc
        return await skill.run(args, ctx)
