"""The skill registry: a name-indexed collection that filters by capability."""

from __future__ import annotations

import logging
from collections.abc import Iterable, Iterator

from petbot.core.skills.base import Skill
from petbot.core.skills.context import Capabilities

logger = logging.getLogger(__name__)

# Maps a port requirement declared in ``Skill.requires`` to the capability flag
# a frontend must advertise to be offered that skill.
_REQUIREMENT_CAPABILITY: dict[str, str] = {
    "voice": "supports_voice",
}


class SkillNotFoundError(KeyError):
    """Raised when a skill name is not registered."""


class SkillRegistry:
    """Holds the available skills and answers two questions: get-by-name, and
    which skills a frontend with given :class:`Capabilities` may offer."""

    def __init__(self, skills: Iterable[Skill]) -> None:
        self._skills: dict[str, Skill] = {}
        for skill in skills:
            if skill.name in self._skills:
                raise ValueError(f"Duplicate skill name registered: {skill.name!r}")
            self._skills[skill.name] = skill
        logger.debug(
            "Skill registry initialised with %d skill(s): %s",
            len(self._skills),
            sorted(self._skills),
        )

    def get(self, name: str) -> Skill:
        """Return the skill registered under ``name``.

        Raises :class:`SkillNotFoundError` if it is not registered.
        """
        try:
            return self._skills[name]
        except KeyError as exc:
            raise SkillNotFoundError(name) from exc

    def available_for(self, caps: Capabilities) -> list[Skill]:
        """Return the skills a frontend with ``caps`` is allowed to expose.

        A skill is excluded when any of its ``requires`` maps to a capability
        flag the frontend has not advertised.
        """
        return [skill for skill in self if self._satisfies(skill, caps)]

    @staticmethod
    def _satisfies(skill: Skill, caps: Capabilities) -> bool:
        for requirement in skill.requires:
            flag = _REQUIREMENT_CAPABILITY.get(requirement)
            if flag is None or not getattr(caps, flag, False):
                return False
        return True

    def __iter__(self) -> Iterator[Skill]:
        """Iterate skills sorted by name (stable ordering for callers)."""
        return iter(sorted(self._skills.values(), key=lambda s: s.name))

    def __len__(self) -> int:
        return len(self._skills)
