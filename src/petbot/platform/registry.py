from __future__ import annotations

import logging
from collections.abc import Iterable, Iterator, Mapping
from importlib.metadata import entry_points
from typing import Any

from pydantic import ValidationError

from petbot.domain import InvalidInput, Skill, SkillContext, SkillError, SkillResult

logger = logging.getLogger(__name__)

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
        return cls(_discover())

    def register(self, skill: Skill[Any]) -> None:
        self._add(skill)

    @property
    def names(self) -> frozenset[str]:
        return frozenset(self._skills)

    async def dispatch(
        self, name: str, values: Mapping[str, object], ctx: SkillContext
    ) -> SkillResult:
        skill = self._skills.get(name)
        if skill is None:
            logger.warning("Dispatch for unknown tool: %r", name)
            raise SkillError(f"I don't know how to do {name!r}.")
        try:
            args = skill.args_model.model_validate(dict(values))
        except ValidationError as exc:
            raise InvalidInput("Those arguments weren't valid.") from exc
        return await skill.run(args, ctx)
