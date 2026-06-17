"""A name-indexed collection of skills that filters by capability."""

from __future__ import annotations

from collections.abc import Iterable, Iterator

from petbot_domain import Capability, Skill, SkillSpec


class SkillNotFoundError(KeyError):
    """Raised when a skill name is not registered."""


class SkillRegistry:
    """Holds the available skills; answers get-by-name and capability filtering."""

    def __init__(self, skills: Iterable[Skill]) -> None:
        self._skills: dict[str, Skill] = {}
        for skill in skills:
            if skill.name in self._skills:
                raise ValueError(f"Duplicate skill name registered: {skill.name!r}")
            self._skills[skill.name] = skill

    def get(self, name: str) -> Skill:
        """Return the skill registered under ``name`` (raises :class:`SkillNotFoundError`)."""
        try:
            return self._skills[name]
        except KeyError as exc:
            raise SkillNotFoundError(name) from exc

    def available_for(self, provides: frozenset[Capability]) -> list[Skill]:
        """Skills a frontend may offer: those whose ``requires`` are all provided."""
        return [skill for skill in self if skill.requires <= provides]

    def specs(self) -> list[SkillSpec]:
        """The manifest projection — what an edge needs without importing skills."""
        return [SkillSpec.of(skill) for skill in self]

    def __iter__(self) -> Iterator[Skill]:
        """Iterate skills sorted by name (stable ordering for callers)."""
        return iter(sorted(self._skills.values(), key=lambda s: s.name))

    def __len__(self) -> int:
        return len(self._skills)
